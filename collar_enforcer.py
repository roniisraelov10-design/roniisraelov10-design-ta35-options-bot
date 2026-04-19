"""
risk/collar_enforcer.py
========================
אוכף כלל הברזל: אין כתיבה חשופה (Naked Calls / Naked Puts).

מודול זה הוא שכבת הגנה נפרדת ועצמאית מה-RiskManager.
הוא רץ לפני שהפקודה מגיעה ל-RiskManager ומוודא שכל כתיבת
אופציה מגובה בהגנה מתאימה.

אסטרטגיות מאושרות:
  ✅ Bull Put Spread  — כתיבת פוט + קניית פוט נמוך יותר
  ✅ Bear Call Spread — כתיבת קול + קניית קול גבוה יותר
  ✅ Iron Condor      — שילוב של שניהם
  ✅ Covered Call     — כתיבת קול מגובה בהחזקת הבסיס
  ✅ סגירת פוזיציה קיימת (is_closing=True)

אסטרטגיות אסורות:
  ❌ Naked Call — כתיבת קול ללא גידור
  ❌ Naked Put  — כתיבת פוט ללא גידור
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.event_bus import Event, EventBus, EventType, get_event_bus
from risk.risk_manager import OrderRequest, RejectionReason

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# מבני נתונים
# ---------------------------------------------------------------------------
@dataclass
class OpenPosition:
    """
    מייצג פוזיציה פתוחה קיימת בתיק.
    נשמר ב-CollarEnforcer כדי לבדוק גידורים לפוזיציות חדשות.

    Attributes:
        position_id:    מזהה ייחודי לפוזיציה
        symbol:         סמל המכשיר
        option_type:    "CALL" | "PUT"
        action:         "BUY" (קנייה/גידור) | "SELL" (כתיבה)
        quantity:       כמות חוזים
        strike:         מחיר המימוש
        expiry:         תאריך פקיעה
        order_id:       מזהה הפקודה המקורית
        paired_with:    מזהה הפוזיציה שמגדרת אותה (hedge)
    """
    position_id:  str
    symbol:       str
    option_type:  str           # "CALL" | "PUT"
    action:       str           # "BUY"  | "SELL"
    quantity:     int
    strike:       float
    expiry:       str           # "YYYY-MM-DD"
    order_id:     str
    paired_with:  Optional[str] = None  # ID של ה-hedge
    opened_at:    datetime      = field(default_factory=datetime.utcnow)


@dataclass
class HedgeRequirement:
    """
    מתאר את דרישות הגידור לפקודת כתיבה ספציפית.

    Attributes:
        required:        האם גידור נדרש בכלל
        hedge_type:      סוג הגידור הנדרש ("LONG_CALL" / "LONG_PUT" / "UNDERLYING")
        min_quantity:    כמות מינימלית של הגידור
        max_strike_diff: הפרש מחיר מימוש מקסימלי מותר בין הכתיבה לגידור
        description:     תיאור קריא
    """
    required:        bool
    hedge_type:      str   = ""
    min_quantity:    int   = 0
    max_strike_diff: float = float("inf")  # ברירת מחדל: כל הפרש מותר
    description:     str   = ""


# ---------------------------------------------------------------------------
# מחלקת CollarEnforcer
# ---------------------------------------------------------------------------
class CollarEnforcer:
    """
    אוכף את כלל הביטחונות — חוסם כתיבה חשופה ומוודא גידורים.

    הלוגיקה המרכזית ב-validate_order():
      1. אם הפקודה היא קנייה — תמיד תקינה (קנייה לא יוצרת חשיפה בלתי מוגבלת)
      2. אם הפקודה סוגרת פוזיציה — תמיד תקינה
      3. אם הפקודה היא כתיבה (SELL):
         א. חפש פוזיציה מגדרת בתיק הפוזיציות הפתוחות
         ב. אם לא נמצאה — חפש לפי hedge_order_id שצורף לפקודה
         ג. אם אין גידור — חסום את הפקודה ושדר NAKED_POSITION_BLOCKED

    Usage:
        enforcer = CollarEnforcer(bus)
        await enforcer.start()
        is_valid, reason, msg = await enforcer.validate_order(order)
    """

    def __init__(self, event_bus: EventBus) -> None:
        """
        Args:
            event_bus: מופע ה-EventBus המשותף
        """
        self._bus = event_bus

        # מילון של כל הפוזיציות הפתוחות הנוכחיות
        # key: position_id, value: OpenPosition
        self._open_positions: dict[str, OpenPosition] = {}

        # מונה ניסיונות כתיבה חשופה (לצורך audit ו-alerting)
        self._naked_attempt_count: int = 0

        logger.info("CollarEnforcer אותחל — כתיבה חשופה לעולם לא תאושר")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """רושם handlers ל-EventBus."""
        # האזן לפתיחת פוזיציות חדשות כדי לעדכן את הרישום הפנימי
        self._bus.subscribe_handler(EventType.POSITION_OPENED, self._on_position_opened)
        # האזן לסגירת פוזיציות כדי להסיר מהרישום
        self._bus.subscribe_handler(EventType.POSITION_CLOSED, self._on_position_closed)
        logger.info("CollarEnforcer מאזין לאירועים")

    async def stop(self) -> None:
        """הסר רישומים."""
        self._bus.unsubscribe(EventType.POSITION_OPENED, self._on_position_opened)
        self._bus.unsubscribe(EventType.POSITION_CLOSED, self._on_position_closed)

    # ------------------------------------------------------------------
    # הפונקציה המרכזית — ולידציה של פקודה
    # ------------------------------------------------------------------
    async def validate_order(
        self, order: OrderRequest
    ) -> tuple[bool, RejectionReason | None, str]:
        """
        הפונקציה המרכזית — בודקת האם פקודה עומדת בכלל אין-כתיבה-חשופה.

        Args:
            order: הפקודה לבדיקה

        Returns:
            (is_valid: bool, rejection_reason_or_None, description_message)
        """
        # --- קנייה תמיד מותרת — לא יוצרת חשיפה בלתי מוגבלת ---
        if order.action == "BUY":
            logger.debug(
                "CollarEnforcer: קנייה מאושרת ללא בדיקה | order_id=%s", order.order_id
            )
            return True, None, "קנייה — אינה מצריכה גידור"

        # --- סגירת פוזיציה תמיד מותרת ---
        if order.is_closing:
            logger.debug(
                "CollarEnforcer: פקודה סוגרת — מאושרת | order_id=%s", order.order_id
            )
            return True, None, "סגירת פוזיציה — מאושרת"

        # --- מגיעים לכאן רק בכתיבה (SELL) על פוזיציה חדשה ---
        logger.debug(
            "CollarEnforcer: בדיקת גידור לכתיבה | order_id=%s | symbol=%s | type=%s",
            order.order_id, order.symbol, order.option_type
        )

        # חשב את דרישת הגידור לפי סוג האופציה
        hedge_req = self._get_hedge_requirement(order)

        # חפש גידור מתאים בפוזיציות הפתוחות
        hedge_found, hedge_desc = self._find_hedge_in_positions(order, hedge_req)

        if hedge_found:
            logger.info(
                "✅ CollarEnforcer: גידור נמצא | order_id=%s | %s",
                order.order_id, hedge_desc
            )
            return True, None, f"כתיבה מגובה אושרה | {hedge_desc}"

        # --- לא נמצא גידור — בדוק אם צורף hedge_order_id לפקודה ---
        # מצב זה מתרחש כאשר האסטרטגיה שולחת שתי פקודות בו-זמנית (Spread)
        # הפקודה הראשונה היא הקנייה (הגידור), השנייה היא הכתיבה עם מזהה לראשונה
        if order.hedge_order_id:
            pending_hedge = self._find_pending_hedge(order)
            if pending_hedge:
                logger.info(
                    "✅ CollarEnforcer: גידור ממתין נמצא | order_id=%s | hedge_id=%s",
                    order.order_id, order.hedge_order_id
                )
                return True, None, f"כתיבה עם גידור ממתין אושרה | hedge={order.hedge_order_id}"

        # --- לא נמצא גידור — חסום את הפקודה ---
        return await self._block_naked_order(order)

    # ------------------------------------------------------------------
    # לוגיקת גידורים
    # ------------------------------------------------------------------
    def _get_hedge_requirement(self, order: OrderRequest) -> HedgeRequirement:
        """
        מחזיר את דרישת הגידור הנדרשת לפי סוג האופציה.

        כלל:
          - כתיבת CALL → נדרשת LONG CALL (Call Spread) או החזקת הבסיס
          - כתיבת PUT  → נדרשת LONG PUT  (Put Spread)

        Args:
            order: פקודת הכתיבה

        Returns:
            HedgeRequirement עם הפרטים הנדרשים
        """
        if order.option_type == "CALL":
            return HedgeRequirement(
                required=True,
                hedge_type="LONG_CALL",
                min_quantity=order.quantity,  # כמות הגידור חייבת לכסות את הכתיבה
                description=(
                    "כתיבת CALL דורשת LONG CALL באותה כמות ובמחיר מימוש גבוה יותר "
                    "(Bear Call Spread), או החזקת מדד הבסיס (Covered Call)"
                )
            )
        elif order.option_type == "PUT":
            return HedgeRequirement(
                required=True,
                hedge_type="LONG_PUT",
                min_quantity=order.quantity,
                description=(
                    "כתיבת PUT דורשת LONG PUT באותה כמות ובמחיר מימוש נמוך יותר "
                    "(Bull Put Spread)"
                )
            )
        else:
            # סוג לא מוכר — דרוש גידור כאמצעי זהירות
            logger.error(
                "סוג אופציה לא מוכר '%s' | order_id=%s", order.option_type, order.order_id
            )
            return HedgeRequirement(
                required=True,
                hedge_type="UNKNOWN",
                description=f"סוג אופציה לא מוכר: {order.option_type}"
            )

    def _find_hedge_in_positions(
        self,
        order: OrderRequest,
        hedge_req: HedgeRequirement,
    ) -> tuple[bool, str]:
        """
        מחפש בתיק הפוזיציות הפתוחות גידור מתאים לפקודה.

        הלוגיקה:
          - לכתיבת CALL: חפש LONG CALL בעל אותו סמל ומחיר מימוש גבוה יותר
          - לכתיבת PUT:  חפש LONG PUT  בעל אותו סמל ומחיר מימוש נמוך יותר
          - הכמות של הגידור חייבת לכסות לפחות את כמות הכתיבה

        Args:
            order:     פקודת הכתיבה
            hedge_req: דרישת הגידור שחושבה

        Returns:
            (found: bool, description: str)
        """
        # מיצוי מחיר המימוש מסמל הפקודה — בפרויקט אמיתי יגיע כשדה בפקודה
        # כאן נשתמש בשדה שיתווסף ל-OrderRequest בעתיד
        order_strike: float = getattr(order, "strike", 0.0)

        for pos in self._open_positions.values():
            # סנן: רק אותו סמל בסיס (למשל כל אופציות TA35 לאותה פקיעה)
            if not self._same_underlying(order.symbol, pos.symbol):
                continue

            # סנן: הגידור חייב להיות קנייה (LONG)
            if pos.action != "BUY":
                continue

            # סנן: בדוק שהכמות מספיקה
            if pos.quantity < order.quantity:
                continue

            # בדיקת סוג אופציה ומחיר מימוש לפי כיוון הכתיבה
            if order.option_type == "CALL" and pos.option_type == "CALL":
                # Bear Call Spread: הגידור (LONG CALL) חייב להיות במחיר מימוש גבוה יותר
                pos_strike = getattr(pos, "strike", float("inf"))
                if pos_strike > order_strike:
                    return True, (
                        f"Bear Call Spread | long_call_strike={pos_strike} | "
                        f"short_call_strike={order_strike} | qty={pos.quantity}"
                    )

            elif order.option_type == "PUT" and pos.option_type == "PUT":
                # Bull Put Spread: הגידור (LONG PUT) חייב להיות במחיר מימוש נמוך יותר
                pos_strike = getattr(pos, "strike", 0.0)
                if pos_strike < order_strike:
                    return True, (
                        f"Bull Put Spread | long_put_strike={pos_strike} | "
                        f"short_put_strike={order_strike} | qty={pos.quantity}"
                    )

        # לא נמצא גידור מתאים
        return False, ""

    def _find_pending_hedge(self, order: OrderRequest) -> bool:
        """
        בודק אם קיימת פקודת גידור ממתינה שצורפה לפקודת הכתיבה.

        שימוש: כאשר האסטרטגיה שולחת Spread — הפקודות נשלחות יחד.
        פקודת הכתיבה מצרפת את ה-hedge_order_id של הקנייה.
        ה-CollarEnforcer מאמת שפקודת הקנייה אכן קיימת בתור.

        בפרויקט אמיתי — זה יתממשק עם order_manager.py
        כרגע מחזירים True אם hedge_order_id סופק (האחריות על order_manager)

        Args:
            order: פקודת הכתיבה

        Returns:
            True אם גידור ממתין נמצא ותקין
        """
        # ולידציה בסיסית: לפחות ה-ID לא ריק
        if not order.hedge_order_id:
            return False

        # בגרסה הנוכחית — אנחנו סומכים על order_manager שיוודא
        # שהפקודה הממתינה תבוצע לפני הכתיבה.
        # TODO: הוסף תקשורת ישירה עם order_manager לוולידציה מלאה
        logger.debug(
            "hedge_order_id סופק — סומך על order_manager | hedge_id=%s",
            order.hedge_order_id
        )
        return True

    @staticmethod
    def _same_underlying(symbol_a: str, symbol_b: str) -> bool:
        """
        בודק האם שתי אופציות הן על אותו נכס בסיס.

        בת"א 35, פורמט הסמל לרוב: "TA35CYYYYMMDDXXXXX"
        כרגע בדיקה פשוטה — בפרויקט אמיתי יתבסס על פרסר מלא.

        Args:
            symbol_a, symbol_b: שני סמלים לבדיקה

        Returns:
            True אם שניהם על ת"א 35
        """
        # הנחת עבודה: כל האופציות במערכת הן על ת"א 35
        # בעתיד: parse את ה-symbol ובדוק את שדה הבסיס
        return symbol_a[:4] == symbol_b[:4]  # TA35 = 4 תווים ראשונים

    # ------------------------------------------------------------------
    # חסימת כתיבה חשופה
    # ------------------------------------------------------------------
    async def _block_naked_order(
        self, order: OrderRequest
    ) -> tuple[bool, RejectionReason, str]:
        """
        חוסם פקודת כתיבה חשופה ומשדר אירועי אזהרה.

        Args:
            order: הפקודה החשופה שנחסמה

        Returns:
            (False, NAKED_POSITION, error_message) — תמיד
        """
        self._naked_attempt_count += 1

        msg = (
            f"🚫 כתיבה חשופה נחסמה! | order_id={order.order_id} | "
            f"symbol={order.symbol} | type={order.option_type} | qty={order.quantity} | "
            f"strategy={order.strategy_tag} | "
            f"סה\"כ ניסיונות חשופים: {self._naked_attempt_count}"
        )
        logger.critical(msg)

        # שדר NAKED_POSITION_BLOCKED לניטור ולהתראות
        await self._bus.publish(Event(
            event_type=EventType.NAKED_POSITION_BLOCKED,
            source="CollarEnforcer",
            payload={
                "order_id":       order.order_id,
                "symbol":         order.symbol,
                "option_type":    order.option_type,
                "quantity":       order.quantity,
                "strategy_tag":   order.strategy_tag,
                "attempt_number": self._naked_attempt_count,
                "timestamp":      datetime.utcnow().isoformat(),
            }
        ))

        # שדר גם RISK_VIOLATION כדי שה-RiskManager ידע
        await self._bus.publish(Event(
            event_type=EventType.RISK_VIOLATION,
            source="CollarEnforcer",
            payload={
                "reason":  "NAKED_POSITION",
                "message": msg,
            }
        ))

        # שדר התראה חיצונית — כתיבה חשופה היא חריגה קריטית
        await self._bus.publish(Event(
            event_type=EventType.ALERT_SEND,
            source="CollarEnforcer",
            payload={
                "level":   "CRITICAL",
                "message": f"🚫 ניסיון כתיבה חשופה נחסם: {order.symbol} | {order.option_type}",
            }
        ))

        return False, RejectionReason.NAKED_POSITION, msg

    # ------------------------------------------------------------------
    # ניהול פוזיציות פתוחות
    # ------------------------------------------------------------------
    def add_open_position(self, position: OpenPosition) -> None:
        """
        מוסיף פוזיציה חדשה לרישום הפנימי.
        נקרא על ידי portfolio_tracker כאשר פקודה בוצעה בשוק.

        Args:
            position: הפוזיציה החדשה שנפתחה
        """
        self._open_positions[position.position_id] = position
        logger.debug(
            "פוזיציה נרשמה ב-CollarEnforcer | id=%s | %s %s x%d",
            position.position_id, position.action,
            position.option_type, position.quantity
        )

    def remove_open_position(self, position_id: str) -> None:
        """
        מסיר פוזיציה מהרישום כאשר היא נסגרת.

        Args:
            position_id: מזהה הפוזיציה לסגירה
        """
        removed = self._open_positions.pop(position_id, None)
        if removed:
            logger.debug("פוזיציה הוסרה מ-CollarEnforcer | id=%s", position_id)
        else:
            logger.warning("ניסיון להסיר פוזיציה לא קיימת | id=%s", position_id)

    def get_open_positions(self) -> list[OpenPosition]:
        """מחזיר רשימה של כל הפוזיציות הפתוחות הנוכחיות."""
        return list(self._open_positions.values())

    @property
    def naked_attempt_count(self) -> int:
        """מספר ניסיונות הכתיבה החשופה שנחסמו מאז הפעלת הבוט."""
        return self._naked_attempt_count

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------
    async def _on_position_opened(self, event: Event) -> None:
        """Handler לאירוע POSITION_OPENED — מעדכן את הרישום הפנימי."""
        payload = event.payload
        try:
            position = OpenPosition(
                position_id=payload["position_id"],
                symbol=payload["symbol"],
                option_type=payload["option_type"],
                action=payload["action"],
                quantity=payload["quantity"],
                strike=payload.get("strike", 0.0),
                expiry=payload.get("expiry", ""),
                order_id=payload.get("order_id", ""),
                paired_with=payload.get("paired_with"),
            )
            self.add_open_position(position)
        except KeyError as e:
            logger.error("שדה חסר ב-POSITION_OPENED payload: %s", e)

    async def _on_position_closed(self, event: Event) -> None:
        """Handler לאירוע POSITION_CLOSED — מסיר מהרישום."""
        position_id = event.payload.get("position_id")
        if position_id:
            self.remove_open_position(position_id)
        else:
            logger.warning("POSITION_CLOSED ללא position_id ב-payload")
