"""
risk/risk_manager.py
====================
מנהל הסיכונים — ה-Last Line of Defense של הבוט.

כל פקודת מסחר חייבת לעבור אישור מקובץ זה לפני שמועברת לברוקר.
המודול מפעיל שלוש שכבות הגנה עצמאיות:
  1. בדיקת ביטחונות (Margin Check)
  2. בדיקת הגבלת הפסד יומי (Daily Loss Limit)
  3. מתג חירום (Kill Switch) — נועל את הבוט לחלוטין

חוק בל-יעבור: מודול זה אינו יוזם מסחר — הוא רק מאשר או חוסם.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum, auto
from typing import Optional

from core.event_bus import Event, EventBus, EventType, get_event_bus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# קבועים ופרמטרים — בפרויקט אמיתי יגיעו מ-config.py
# ---------------------------------------------------------------------------
# אחוז מרג'ין מינימלי נדרש לאישור פקודה חדשה (0.20 = 20%)
MIN_MARGIN_RATIO: float = 0.20

# אחוז מרג'ין שמתחתיו נשלחת אזהרה (0.30 = 30%)
MARGIN_WARNING_RATIO: float = 0.30

# הפסד יומי מקסימלי כאחוז מהתיק (0.02 = 2%)
MAX_DAILY_LOSS_RATIO: float = 0.02

# ערך ברירת מחדל לגודל תיק לדוגמה בשקלים
DEFAULT_PORTFOLIO_VALUE: float = 500_000.0


# ---------------------------------------------------------------------------
# מבני נתונים
# ---------------------------------------------------------------------------
class RejectionReason(Enum):
    """סיבות האפשריות לדחיית פקודה."""
    KILL_SWITCH_ACTIVE    = auto()  # מתג החירום מופעל
    INSUFFICIENT_MARGIN   = auto()  # אין מספיק ביטחונות
    DAILY_LOSS_EXCEEDED   = auto()  # חריגת הפסד יומי
    NAKED_POSITION        = auto()  # כתיבה חשופה (נחסמת על ידי CollarEnforcer)
    INVALID_ORDER         = auto()  # פקודה לא תקינה (חסרים שדות)


@dataclass
class OrderRequest:
    """
    מייצג בקשה לביצוע פקודה שמגיעה מהאסטרטגיה.

    Attributes:
        order_id:           מזהה ייחודי לפקודה
        symbol:             סמל המכשיר (למשל "TA35C20000")
        option_type:        סוג האופציה: "CALL" או "PUT"
        action:             "BUY" לקנייה, "SELL" לכתיבה
        quantity:           כמות חוזים
        estimated_margin:   הביטחון הנדרש לפקודה בשקלים
        strategy_tag:       שם האסטרטגיה שיצרה את הפקודה
        hedge_order_id:     מזהה פקודת הגידור (חובה בכתיבה — מונע Naked)
        is_closing:         האם הפקודה סוגרת פוזיציה קיימת
        timestamp:          זמן יצירת הבקשה
    """
    order_id:         str
    symbol:           str
    option_type:      str           # "CALL" | "PUT"
    action:           str           # "BUY"  | "SELL"
    quantity:         int
    estimated_margin: float
    strategy_tag:     str           = "unknown"
    hedge_order_id:   Optional[str] = None
    is_closing:       bool          = False
    timestamp:        datetime      = field(default_factory=datetime.utcnow)


@dataclass
class MarginState:
    """
    מצב הביטחונות הנוכחי של החשבון.

    Attributes:
        total_equity:      שווי תיק כולל
        used_margin:       ביטחונות בשימוש כרגע
        available_margin:  ביטחונות פנויים לפקודות חדשות
        last_updated:      זמן עדכון אחרון
    """
    total_equity:     float
    used_margin:      float
    available_margin: float
    last_updated:     datetime = field(default_factory=datetime.utcnow)

    @property
    def margin_ratio(self) -> float:
        """יחס הביטחונות הפנויים מתוך סך הנכסים (0.0 – 1.0)."""
        if self.total_equity == 0:
            return 0.0
        return self.available_margin / self.total_equity


@dataclass
class DailyPnL:
    """מעקב רווח/הפסד יומי."""
    trade_date:       date  = field(default_factory=date.today)
    realized_pnl:     float = 0.0   # רווח/הפסד ממומש
    unrealized_pnl:   float = 0.0   # רווח/הפסד לא ממומש

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl

    def reset_if_new_day(self) -> None:
        """אם עבר חצות — מאפס את הנתונים לתחילת יום מסחר חדש."""
        today = date.today()
        if self.trade_date != today:
            logger.info("יום מסחר חדש — מאפס נתוני PnL יומי")
            self.trade_date   = today
            self.realized_pnl = 0.0
            self.unrealized_pnl = 0.0


# ---------------------------------------------------------------------------
# מחלקת RiskManager
# ---------------------------------------------------------------------------
class RiskManager:
    """
    מנהל הסיכונים הראשי — אחראי לאישור או דחיית כל פקודת מסחר.

    הלוגיקה:
        1. בודק שמתג החירום אינו מופעל
        2. בודק שהפסד יומי לא חרג מהגבול
        3. בודק שיש מספיק ביטחונות לפקודה החדשה
        4. מפרסם אירוע של אישור / דחייה לכל המערכת

    Usage:
        bus = get_event_bus()
        rm = RiskManager(bus, portfolio_value=500_000)
        await rm.start()
    """

    def __init__(
        self,
        event_bus:       EventBus,
        portfolio_value: float = DEFAULT_PORTFOLIO_VALUE,
        max_daily_loss:  Optional[float] = None,
        min_margin_ratio: float = MIN_MARGIN_RATIO,
    ) -> None:
        """
        Args:
            event_bus:        מופע ה-EventBus המשותף
            portfolio_value:  ערך התיק הכולל בשקלים
            max_daily_loss:   הפסד יומי מקסימלי בשקלים (None = חישוב לפי %)
            min_margin_ratio: יחס מרג'ין מינימלי לאישור פקודה
        """
        self._bus = event_bus

        # --- מצב מתג החירום ---
        # כשמופעל — אף פקודה חדשה לא תאושר
        self._kill_switch_active: bool = False
        self._kill_switch_reason: str  = ""

        # --- ביטחונות ---
        # ערכים ראשוניים — יתעדכנו מהברוקר בזמן אמת
        self._margin_state = MarginState(
            total_equity=portfolio_value,
            used_margin=0.0,
            available_margin=portfolio_value,
        )
        self._min_margin_ratio = min_margin_ratio

        # --- הפסד יומי ---
        self._daily_pnl = DailyPnL()
        self._max_daily_loss = max_daily_loss or (portfolio_value * MAX_DAILY_LOSS_RATIO)
        self._portfolio_value = portfolio_value

        # --- נעילה אסינכרונית ---
        # מונעת race condition כאשר מספר פקודות מגיעות בו-זמנית
        self._lock = asyncio.Lock()

        logger.info(
            "RiskManager אותחל | portfolio=₪%,.0f | max_daily_loss=₪%,.0f | "
            "min_margin_ratio=%.0f%%",
            portfolio_value, self._max_daily_loss, min_margin_ratio * 100
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """רושם את ה-handlers ל-EventBus ומתחיל להאזין לפקודות."""
        # האזן לבקשות פקודות נכנסות
        self._bus.subscribe_handler(EventType.ORDER_REQUEST,    self._on_order_request)
        # האזן לעדכוני PnL שמגיעים מה-pnl_calculator
        self._bus.subscribe_handler(EventType.PNL_UPDATED,      self._on_pnl_updated)
        # האזן לעדכוני מרג'ין שמגיעים מהברוקר
        self._bus.subscribe_handler(EventType.MARGIN_WARNING,   self._on_margin_update)

        logger.info("RiskManager מאזין לאירועים")

    async def stop(self) -> None:
        """הסר רישומים וסגור בצורה מסודרת."""
        self._bus.unsubscribe(EventType.ORDER_REQUEST,  self._on_order_request)
        self._bus.unsubscribe(EventType.PNL_UPDATED,    self._on_pnl_updated)
        self._bus.unsubscribe(EventType.MARGIN_WARNING, self._on_margin_update)
        logger.info("RiskManager עצר")

    # ------------------------------------------------------------------
    # Kill Switch — מתג החירום
    # ------------------------------------------------------------------
    async def activate_kill_switch(self, reason: str) -> None:
        """
        מפעיל את מתג החירום — נועל את הבוט מכל מסחר חדש.

        צעדים:
          1. מציין את הדגל הפנימי
          2. שודר אירוע KILL_SWITCH_ACTIVATED לכל המערכת
          3. שודר אירוע CANCEL_ALL_ORDERS לביטול כל הפקודות הפתוחות

        Args:
            reason: הסיבה להפעלת מתג החירום (לצורך logging והתראות)
        """
        async with self._lock:
            if self._kill_switch_active:
                logger.warning("מתג החירום כבר מופעל — %s", self._kill_switch_reason)
                return

            self._kill_switch_active = True
            self._kill_switch_reason = reason

        logger.critical("🚨 מתג חירום הופעל! סיבה: %s", reason)

        # שדר לכל המערכת שהבוט ננעל
        await self._bus.publish(Event(
            event_type=EventType.KILL_SWITCH_ACTIVATED,
            source="RiskManager",
            payload={
                "reason":    reason,
                "timestamp": datetime.utcnow().isoformat(),
            }
        ))

        # שדר ביטול כל הפקודות הפתוחות
        await self._bus.publish(Event(
            event_type=EventType.CANCEL_ALL_ORDERS,
            source="RiskManager",
            payload={"reason": f"Kill Switch: {reason}"}
        ))

        # שדר התראה חיצונית (Telegram/Email)
        await self._bus.publish(Event(
            event_type=EventType.ALERT_SEND,
            source="RiskManager",
            payload={
                "level":   "CRITICAL",
                "message": f"⛔ מתג חירום הופעל: {reason}",
            }
        ))

    async def deactivate_kill_switch(self, authorized_by: str) -> None:
        """
        מכבה את מתג החירום — אפשרי רק ידנית על ידי מפעיל מורשה.

        Args:
            authorized_by: שם המפעיל שביטל את הנעילה (לצורך audit)
        """
        async with self._lock:
            if not self._kill_switch_active:
                logger.info("מתג החירום לא היה מופעל — אין צורך בביטול")
                return

            self._kill_switch_active = False
            old_reason = self._kill_switch_reason
            self._kill_switch_reason = ""

        logger.warning(
            "✅ מתג חירום בוטל ידנית | authorized_by=%s | previous_reason=%s",
            authorized_by, old_reason
        )

        await self._bus.publish(Event(
            event_type=EventType.KILL_SWITCH_DEACTIVATED,
            source="RiskManager",
            payload={
                "authorized_by": authorized_by,
                "previous_reason": old_reason,
                "timestamp": datetime.utcnow().isoformat(),
            }
        ))

    @property
    def is_kill_switch_active(self) -> bool:
        """האם מתג החירום מופעל כרגע."""
        return self._kill_switch_active

    # ------------------------------------------------------------------
    # Margin Check — בדיקת ביטחונות
    # ------------------------------------------------------------------
    def update_margin_state(
        self,
        total_equity:     float,
        used_margin:      float,
        available_margin: float,
    ) -> None:
        """
        מעדכן את מצב הביטחונות בנתונים שהתקבלו מהברוקר.

        Args:
            total_equity:     שווי תיק כולל
            used_margin:      ביטחונות בשימוש
            available_margin: ביטחונות פנויים
        """
        self._margin_state = MarginState(
            total_equity=total_equity,
            used_margin=used_margin,
            available_margin=available_margin,
        )
        logger.debug(
            "מרג'ין עודכן | total=₪%,.0f | used=₪%,.0f | available=₪%,.0f | ratio=%.1f%%",
            total_equity, used_margin, available_margin,
            self._margin_state.margin_ratio * 100
        )

    async def check_margin(self, order: OrderRequest) -> tuple[bool, str]:
        """
        בודק האם יש מספיק ביטחונות לביצוע פקודה חדשה.

        הלוגיקה:
          - אם הפקודה סוגרת פוזיציה קיימת — תמיד אושר (משחרר מרג'ין)
          - אם הביטחונות הפנויים אחרי הפקודה יהיו מתחת למינימום — דחה
          - אם היחס אחרי הפקודה נמוך אבל עדיין מעל המינימום — אזהרה

        Args:
            order: הפקודה לבדיקה

        Returns:
            tuple של (approved: bool, reason: str)
        """
        # פקודה סוגרת — לעולם לא דורשת ביטחון נוסף
        if order.is_closing:
            logger.debug("פקודה סוגרת — לא דורשת בדיקת מרג'ין | order_id=%s", order.order_id)
            return True, "פקודה סוגרת — פטורה מבדיקת מרג'ין"

        # קנייה — גם כן דורשת רק את עלות הפרמיום, לא ביטחון
        if order.action == "BUY":
            logger.debug("פקודת קנייה — בדיקת מרג'ין חלקית | order_id=%s", order.order_id)
            if order.estimated_margin > self._margin_state.available_margin:
                return False, (
                    f"אין מספיק מזומן לקנייה: נדרש ₪{order.estimated_margin:,.0f}, "
                    f"זמין ₪{self._margin_state.available_margin:,.0f}"
                )
            return True, "קנייה מאושרת"

        # כתיבה (SELL) — בדיקה מלאה
        margin_after = self._margin_state.available_margin - order.estimated_margin
        ratio_after  = margin_after / self._margin_state.total_equity if self._margin_state.total_equity > 0 else 0.0

        # מצב קריטי — מרג'ין יירד מתחת לסף המינימלי
        if ratio_after < self._min_margin_ratio:
            msg = (
                f"מרג'ין לא מספיק לכתיבה | נדרש: ₪{order.estimated_margin:,.0f} | "
                f"זמין: ₪{self._margin_state.available_margin:,.0f} | "
                f"יחס אחרי פקודה: {ratio_after:.1%} (מינימום: {self._min_margin_ratio:.1%})"
            )
            logger.warning(msg)
            return False, msg

        # מצב אזהרה — מרג'ין נמוך אבל מעל המינימום
        if ratio_after < MARGIN_WARNING_RATIO:
            warning_msg = (
                f"⚠️ אזהרת מרג'ין נמוך אחרי פקודה | יחס: {ratio_after:.1%} | "
                f"order_id={order.order_id}"
            )
            logger.warning(warning_msg)
            # שלח אזהרה לניטור אבל אשר את הפקודה
            await self._bus.publish(Event(
                event_type=EventType.MARGIN_WARNING,
                source="RiskManager",
                payload={
                    "margin_ratio": ratio_after,
                    "order_id":     order.order_id,
                    "message":      warning_msg,
                }
            ))

        return True, f"מרג'ין תקין | יחס אחרי פקודה: {ratio_after:.1%}"

    # ------------------------------------------------------------------
    # Daily Loss Check — בדיקת הפסד יומי
    # ------------------------------------------------------------------
    async def check_daily_loss(self) -> tuple[bool, str]:
        """
        בודק האם ההפסד היומי הנוכחי חרג מהגבול המותר.

        Returns:
            tuple של (within_limit: bool, reason: str)
        """
        # איפוס ביום חדש אם צריך
        self._daily_pnl.reset_if_new_day()

        current_loss = self._daily_pnl.total_pnl  # שלילי = הפסד

        # הגענו לגבול ההפסד היומי
        if current_loss <= -abs(self._max_daily_loss):
            msg = (
                f"🚨 חריגת הפסד יומי! הפסד נוכחי: ₪{current_loss:,.0f} | "
                f"גבול: ₪{-self._max_daily_loss:,.0f}"
            )
            logger.critical(msg)

            # הפעל מתג חירום אוטומטי
            await self.activate_kill_switch(f"חריגת הפסד יומי: ₪{current_loss:,.0f}")

            return False, msg

        return True, f"הפסד יומי תקין: ₪{current_loss:,.0f} מתוך גבול ₪{-self._max_daily_loss:,.0f}"

    # ------------------------------------------------------------------
    # נקודת הכניסה המרכזית — אישור פקודה
    # ------------------------------------------------------------------
    async def approve_order(self, order: OrderRequest) -> tuple[bool, RejectionReason | None, str]:
        """
        הפונקציה המרכזית — מחליטה אם לאשר או לדחות פקודה.

        רצף הבדיקות (סדר חשוב — מהקל לכבד):
          1. תקינות הפקודה עצמה
          2. האם מתג החירום מופעל
          3. בדיקת הפסד יומי
          4. בדיקת ביטחונות

        Args:
            order: הפקודה לאישור

        Returns:
            (approved, rejection_reason_or_None, description_message)
        """
        async with self._lock:
            # --- שלב 0: וולידציה בסיסית ---
            if not order.order_id or not order.symbol:
                return False, RejectionReason.INVALID_ORDER, "פקודה לא תקינה — חסרים שדות חובה"

            # --- שלב 1: בדיקת Kill Switch ---
            if self._kill_switch_active:
                msg = f"פקודה נדחתה — מתג חירום מופעל. סיבה: {self._kill_switch_reason}"
                logger.warning(msg)
                return False, RejectionReason.KILL_SWITCH_ACTIVE, msg

            # --- שלב 2: בדיקת הפסד יומי ---
            loss_ok, loss_msg = await self.check_daily_loss()
            if not loss_ok:
                return False, RejectionReason.DAILY_LOSS_EXCEEDED, loss_msg

            # --- שלב 3: בדיקת ביטחונות ---
            margin_ok, margin_msg = await self.check_margin(order)
            if not margin_ok:
                # שדר אירוע חריגת מרג'ין
                await self._bus.publish(Event(
                    event_type=EventType.MARGIN_BREACH,
                    source="RiskManager",
                    payload={
                        "order_id":  order.order_id,
                        "message":   margin_msg,
                        "available": self._margin_state.available_margin,
                        "required":  order.estimated_margin,
                    }
                ))
                return False, RejectionReason.INSUFFICIENT_MARGIN, margin_msg

            # --- כל הבדיקות עברו — הפקודה מאושרת ---
            logger.info(
                "✅ פקודה אושרה | order_id=%s | symbol=%s | action=%s | qty=%d",
                order.order_id, order.symbol, order.action, order.quantity
            )
            return True, None, "פקודה אושרה"

    # ------------------------------------------------------------------
    # Event Handlers — תגובה לאירועים מה-EventBus
    # ------------------------------------------------------------------
    async def _on_order_request(self, event: Event) -> None:
        """
        Handler לאירוע ORDER_REQUEST.
        מקבל בקשת פקודה, מפעיל את approve_order, ומשדר את התוצאה.
        """
        try:
            # בנה מחדש את ה-OrderRequest מה-payload
            order = OrderRequest(**event.payload)
        except (TypeError, KeyError) as e:
            logger.error("payload לא תקין ב-ORDER_REQUEST: %s", e)
            return

        approved, reason, message = await self.approve_order(order)

        if approved:
            # שדר אישור — order_manager יקלוט ויבצע
            await self._bus.publish(Event(
                event_type=EventType.ORDER_APPROVED,
                source="RiskManager",
                payload={
                    "order_id": order.order_id,
                    "order":    event.payload,
                    "message":  message,
                }
            ))
        else:
            # שדר דחייה — האסטרטגיה תוכל לקלוט ולנסות חלופה
            await self._bus.publish(Event(
                event_type=EventType.ORDER_REJECTED,
                source="RiskManager",
                payload={
                    "order_id": order.order_id,
                    "reason":   reason.name if reason else "UNKNOWN",
                    "message":  message,
                }
            ))

            # שדר גם אירוע RISK_VIOLATION לניטור
            await self._bus.publish(Event(
                event_type=EventType.RISK_VIOLATION,
                source="RiskManager",
                payload={
                    "order_id": order.order_id,
                    "reason":   reason.name if reason else "UNKNOWN",
                    "message":  message,
                }
            ))

    async def _on_pnl_updated(self, event: Event) -> None:
        """
        Handler לאירוע PNL_UPDATED.
        מעדכן את הנתונים הפנימיים ובודק אם חרגנו מגבול ההפסד.
        """
        payload = event.payload
        self._daily_pnl.realized_pnl   = payload.get("realized_pnl",   self._daily_pnl.realized_pnl)
        self._daily_pnl.unrealized_pnl = payload.get("unrealized_pnl", self._daily_pnl.unrealized_pnl)

        logger.debug(
            "PnL עודכן | realized=₪%,.0f | unrealized=₪%,.0f | total=₪%,.0f",
            self._daily_pnl.realized_pnl,
            self._daily_pnl.unrealized_pnl,
            self._daily_pnl.total_pnl
        )

        # בדיקה פרואקטיבית — גם ללא פקודה חדשה
        await self.check_daily_loss()

    async def _on_margin_update(self, event: Event) -> None:
        """
        Handler לעדכון מרג'ין שמגיע מהברוקר.
        """
        payload = event.payload
        self.update_margin_state(
            total_equity=payload.get("total_equity",     self._margin_state.total_equity),
            used_margin=payload.get("used_margin",       self._margin_state.used_margin),
            available_margin=payload.get("available_margin", self._margin_state.available_margin),
        )
