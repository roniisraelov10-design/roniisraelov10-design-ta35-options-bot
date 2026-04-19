"""
core/engine.py
==============
המנוע הראשי (Orchestrator) — לב הבוט.

האחריות של קובץ זה:
  1. לאתחל את כל המודולים בסדר הנכון (תלויות קודם)
  2. לרשום את משימות התזמון למתזמן
  3. להאזין לאירועי מערכת (Kill Switch, Shutdown)
  4. לנהל Graceful Shutdown בעת Ctrl+C או שגיאה קריטית

סדר אתחול (חשוב — שינוי הסדר שובר תלויות):
  Phase 0: EventBus        ← תשתית בסיסית, חייב להיות ראשון
  Phase 1: RiskManager     ← חייב לקום לפני כל מסחר
  Phase 2: CollarEnforcer  ← חייב לקום לפני כל מסחר
  Phase 3: Scheduler       ← מתחיל לתזמן רק אחרי שהסיכונים פעילים
  Phase 4: [Future] MarketData, Strategy, OrderManager

סדר כיבוי (הפוך מהאתחול):
  Phase 4 → Phase 0        ← קודם עוצרים מסחר, אחרון — ה-EventBus
"""

import asyncio
import logging
import signal
from datetime import time
from typing import Optional

from core.event_bus import Event, EventBus, EventType, get_event_bus
from core.scheduler import ScheduledTask, ScheduleType, Scheduler
from risk.risk_manager import RiskManager
from risk.collar_enforcer import CollarEnforcer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# קבועי תצורה — בפרויקט מלא יגיעו מ-config.py / .env
# ---------------------------------------------------------------------------
PORTFOLIO_VALUE_ILS: float = 500_000.0   # גודל תיק לדוגמה בשקלים
MAX_DAILY_LOSS_ILS:  float = 10_000.0    # גבול הפסד יומי: ₪10,000
MIN_MARGIN_RATIO:    float = 0.20        # מרג'ין מינימלי: 20%

MARGIN_CHECK_INTERVAL_SEC: float = 60.0  # בדיקת מרג'ין כל דקה
PNL_CHECK_INTERVAL_SEC:    float = 30.0  # בדיקת PnL כל 30 שניות
HEALTH_CHECK_INTERVAL_SEC: float = 15.0  # בדיקת בריאות כל 15 שניות

DAILY_RESET_TIME = time(0, 0, 5)         # איפוס יומי ב-00:00:05 (5 שניות אחרי חצות)


# ---------------------------------------------------------------------------
# מחלקת Engine
# ---------------------------------------------------------------------------
class Engine:
    """
    ה-Orchestrator הראשי — מנהל את מחזור החיים של כל הבוט.

    Usage:
        engine = Engine()
        await engine.run()           # חוסם עד לסגירה
        # -- או --
        await engine.startup()
        await engine.shutdown()
    """

    def __init__(self) -> None:
        # --- מצב המנוע ---
        self._running: bool  = False
        self._healthy: bool  = False

        # --- מודולים ליבה ---
        # יאותחלו בסדר ב-startup()
        self._event_bus:       Optional[EventBus]      = None
        self._risk_manager:    Optional[RiskManager]   = None
        self._collar_enforcer: Optional[CollarEnforcer] = None
        self._scheduler:       Optional[Scheduler]     = None

        # --- אירוע asyncio לסנכרון סגירה ---
        # כאשר מתבצע Ctrl+C או שגיאה קריטית — מוגדר ל-True
        # ו-run() מסיים את ההמתנה שלה
        self._shutdown_event = asyncio.Event()

        logger.info("Engine נוצר")

    # ------------------------------------------------------------------
    # נקודת הכניסה הציבורית הראשית
    # ------------------------------------------------------------------
    async def run(self) -> None:
        """
        מפעיל את הבוט מההתחלה ועד לסגירה.

        רצף:
          1. startup()  — מאתחל את כל המודולים
          2. המתנה עד לאות סגירה (Ctrl+C / Kill Switch / שגיאה)
          3. shutdown() — מכבה הכל בסדר מסודר
        """
        try:
            await self.startup()

            # המתן עד שמישהו יפעיל את _shutdown_event
            logger.info("🚀 הבוט פעיל — ממתין לאות סגירה (Ctrl+C להפסקה)")
            await self._shutdown_event.wait()

        except Exception as exc:
            logger.critical("שגיאה קריטית ב-Engine.run(): %s", exc, exc_info=True)
        finally:
            await self.shutdown()

    # ------------------------------------------------------------------
    # Phase אתחול
    # ------------------------------------------------------------------
    async def startup(self) -> None:
        """
        מאתחל את כל המודולים בסדר הנכון.

        כל Phase מאופיין בתגיות LOG ברורות כדי שבמקרה של כשל
        נדע בדיוק איפה הדבר נתקע.
        """
        logger.info("=" * 60)
        logger.info("  מתחיל אתחול Bota TA35 Options")
        logger.info("=" * 60)

        await self._phase0_event_bus()
        await self._phase1_risk_manager()
        await self._phase2_collar_enforcer()
        await self._phase3_scheduler()
        await self._phase4_signal_handlers()

        self._running = True
        self._healthy = True

        # שדר SYSTEM_STARTUP לכל המנויים
        await self._event_bus.publish(Event(
            event_type=EventType.SYSTEM_STARTUP,
            source="Engine",
            payload={
                "portfolio_value": PORTFOLIO_VALUE_ILS,
                "max_daily_loss":  MAX_DAILY_LOSS_ILS,
            }
        ))

        logger.info("=" * 60)
        logger.info("  ✅ כל המודולים פעילים — הבוט מוכן למסחר")
        logger.info("=" * 60)

    # --- Phase 0: Event Bus ---
    async def _phase0_event_bus(self) -> None:
        """
        Phase 0: אתחול ה-EventBus.
        חייב להיות ראשון — כל שאר המודולים תלויים בו.
        """
        logger.info("[Phase 0] מאתחל EventBus...")
        self._event_bus = get_event_bus()
        await self._event_bus.start()

        # רשום handler פנימי לאירועי כיבוי
        self._event_bus.subscribe_handler(
            EventType.KILL_SWITCH_ACTIVATED, self._on_kill_switch
        )
        self._event_bus.subscribe_handler(
            EventType.SYSTEM_SHUTDOWN, self._on_system_shutdown
        )

        logger.info("[Phase 0] ✅ EventBus פעיל")

    # --- Phase 1: Risk Manager ---
    async def _phase1_risk_manager(self) -> None:
        """
        Phase 1: אתחול מנהל הסיכונים.
        חייב לקום לפני כל מסחר — הוא ה-gatekeeper.
        """
        logger.info("[Phase 1] מאתחל RiskManager...")
        self._risk_manager = RiskManager(
            event_bus=self._event_bus,
            portfolio_value=PORTFOLIO_VALUE_ILS,
            max_daily_loss=MAX_DAILY_LOSS_ILS,
            min_margin_ratio=MIN_MARGIN_RATIO,
        )
        await self._risk_manager.start()
        logger.info("[Phase 1] ✅ RiskManager פעיל")

    # --- Phase 2: Collar Enforcer ---
    async def _phase2_collar_enforcer(self) -> None:
        """
        Phase 2: אתחול אוכף כלל הברזל (אין כתיבה חשופה).
        חייב לקום לפני שאסטרטגיות מתחילות לשלוח פקודות.
        """
        logger.info("[Phase 2] מאתחל CollarEnforcer...")
        self._collar_enforcer = CollarEnforcer(event_bus=self._event_bus)
        await self._collar_enforcer.start()
        logger.info("[Phase 2] ✅ CollarEnforcer פעיל — כתיבה חשופה אסורה")

    # --- Phase 3: Scheduler ---
    async def _phase3_scheduler(self) -> None:
        """
        Phase 3: אתחול המתזמן ורישום המשימות התקופתיות.
        נרשמות כאן כי כולן תלויות במודולים משלבים 1-2.
        """
        logger.info("[Phase 3] מאתחל Scheduler...")
        self._scheduler = Scheduler()

        # --- משימה 1: בדיקת ביטחונות מול הברוקר ---
        # בפרויקט מלא: תקרא לברוקר ותעדכן את RiskManager
        self._scheduler.register(ScheduledTask(
            name="margin_sync",
            coro_func=self._task_sync_margin,
            schedule_type=ScheduleType.INTERVAL,
            interval_sec=MARGIN_CHECK_INTERVAL_SEC,
            run_immediately=True,           # רוץ פעם אחת מיד בעת האתחול
        ))

        # --- משימה 2: בדיקת חריגת הפסד יומי ---
        self._scheduler.register(ScheduledTask(
            name="daily_loss_check",
            coro_func=self._task_check_daily_loss,
            schedule_type=ScheduleType.INTERVAL,
            interval_sec=PNL_CHECK_INTERVAL_SEC,
            run_immediately=False,
        ))

        # --- משימה 3: איפוס מונה יומי בחצות ---
        # מאפס את הנתונים בדיוק ב-00:00:05 (5 שניות אחרי חצות)
        self._scheduler.register(ScheduledTask(
            name="midnight_reset",
            coro_func=self._task_midnight_reset,
            schedule_type=ScheduleType.DAILY_AT,
            daily_at=DAILY_RESET_TIME,
        ))

        # --- משימה 4: בדיקת בריאות המערכת ---
        self._scheduler.register(ScheduledTask(
            name="health_check",
            coro_func=self._task_health_check,
            schedule_type=ScheduleType.INTERVAL,
            interval_sec=HEALTH_CHECK_INTERVAL_SEC,
            run_immediately=False,
        ))

        await self._scheduler.start()
        logger.info("[Phase 3] ✅ Scheduler פעיל | %d משימות רשומות",
                    len(self._scheduler.status()))

    # --- Phase 4: Signal Handlers ---
    async def _phase4_signal_handlers(self) -> None:
        """
        Phase 4: רישום handlers ל-OS signals.
        SIGINT  = Ctrl+C
        SIGTERM = kill מהמערכת (Docker, systemd)
        """
        logger.info("[Phase 4] רושם OS signal handlers...")
        loop = asyncio.get_running_loop()

        # SIGINT (Ctrl+C) ו-SIGTERM — שניהם מפעילים Graceful Shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(
                    self._handle_os_signal(s)
                )
            )

        logger.info("[Phase 4] ✅ Signal handlers רשומים (SIGINT, SIGTERM)")

    # ------------------------------------------------------------------
    # Graceful Shutdown
    # ------------------------------------------------------------------
    async def shutdown(self) -> None:
        """
        מכבה את כל המודולים בסדר הפוך מהאתחול.
        מבטיח שלא תישלחנה פקודות חדשות בזמן הכיבוי.

        סדר הכיבוי:
          4: Scheduler      ← עצור משימות תקופתיות קודם
          3: CollarEnforcer ← עצור אכיפת כללים
          2: RiskManager    ← עצור ניהול סיכונים
          1: EventBus       ← עצור תקשורת בין מודולים אחרון
        """
        if not self._running:
            logger.debug("shutdown() נקרא אבל הבוט לא היה פעיל")
            return

        logger.info("=" * 60)
        logger.info("  🛑 מתחיל Graceful Shutdown...")
        logger.info("=" * 60)

        self._running = False

        # שדר לכל המנויים שהמערכת יורדת (אחרון — לפני כיבוי ה-bus)
        if self._event_bus:
            try:
                await self._event_bus.publish(Event(
                    event_type=EventType.SYSTEM_SHUTDOWN,
                    source="Engine",
                    payload={}
                ))
                # תן זמן לאירוע להתעבד לפני כיבוי ה-bus
                await asyncio.sleep(0.5)
            except Exception:
                pass  # ה-bus כבר אולי לא פעיל

        # Phase 4→3: Scheduler
        if self._scheduler:
            logger.info("[Shutdown 4→3] עוצר Scheduler...")
            await self._scheduler.stop()
            logger.info("[Shutdown 4→3] ✅ Scheduler עצר")

        # Phase 3→2: CollarEnforcer
        if self._collar_enforcer:
            logger.info("[Shutdown 3→2] עוצר CollarEnforcer...")
            await self._collar_enforcer.stop()
            logger.info("[Shutdown 3→2] ✅ CollarEnforcer עצר")

        # Phase 2→1: RiskManager
        if self._risk_manager:
            logger.info("[Shutdown 2→1] עוצר RiskManager...")
            await self._risk_manager.stop()
            logger.info("[Shutdown 2→1] ✅ RiskManager עצר")

        # Phase 1→0: EventBus — אחרון!
        if self._event_bus:
            logger.info("[Shutdown 1→0] עוצר EventBus...")
            await self._event_bus.stop()
            logger.info("[Shutdown 1→0] ✅ EventBus עצר")

        logger.info("=" * 60)
        logger.info("  ✅ Graceful Shutdown הושלם — להתראות")
        logger.info("=" * 60)

    # ------------------------------------------------------------------
    # משימות Scheduler (stub implementations)
    # ------------------------------------------------------------------
    async def _task_sync_margin(self) -> None:
        """
        משימה תקופתית: סנכרון ביטחונות מהברוקר.

        בפרויקט מלא: קורא ל-broker_api.get_account_state() ומעדכן
        את RiskManager עם הנתונים העדכניים.
        כרגע: stub שמדמה נתונים.
        """
        logger.debug("[Scheduler] מסנכרן ביטחונות מהברוקר...")

        # TODO: החלף בקריאה אמיתית ל-broker_api
        # account = await self._broker_api.get_account_state()
        # self._risk_manager.update_margin_state(
        #     total_equity=account.total_equity,
        #     used_margin=account.used_margin,
        #     available_margin=account.available_margin,
        # )

        # --- Stub: שדר אירוע HEALTH_CHECK כהוכחת חיים ---
        await self._event_bus.publish(Event(
            event_type=EventType.HEALTH_CHECK,
            source="Engine/margin_sync",
            payload={"status": "margin_sync_stub_ok"}
        ))

    async def _task_check_daily_loss(self) -> None:
        """
        משימה תקופתית: בדיקה פרואקטיבית של הפסד יומי.

        מפעילה את check_daily_loss() ישירות — גם בין עסקאות.
        מאפשרת תגובה מהירה לשינויי שוק גדולים.
        """
        logger.debug("[Scheduler] בודק חריגת הפסד יומי...")
        if self._risk_manager:
            within_limit, msg = await self._risk_manager.check_daily_loss()
            if not within_limit:
                logger.critical("[Scheduler] חריגת הפסד יומי זוהתה: %s", msg)

    async def _task_midnight_reset(self) -> None:
        """
        משימה יומית: איפוס מונים בתחילת יום מסחר חדש.

        נקראת ב-00:00:05 — 5 שניות אחרי חצות.
        """
        logger.info("[Scheduler] 🌙 איפוס יומי בחצות — יום מסחר חדש")

        # ה-RiskManager מאפס את ה-PnL הפנימי בקריאה ל-check_daily_loss()
        # (מכיל reset_if_new_day() פנימי)
        if self._risk_manager:
            self._risk_manager._daily_pnl.reset_if_new_day()

        # שדר לכל המנויים (ה-pnl_calculator, portfolio_tracker וכו')
        await self._event_bus.publish(Event(
            event_type=EventType.HEALTH_CHECK,
            source="Engine/midnight_reset",
            payload={"type": "daily_reset", "message": "יום מסחר חדש החל"}
        ))

        logger.info("[Scheduler] ✅ איפוס יומי הושלם")

    async def _task_health_check(self) -> None:
        """
        משימה תקופתית: בדיקת תקינות המערכת.

        בודקת:
          - שה-EventBus מגיב
          - שה-RiskManager לא ננעל בלי סיבה
          - שהמתזמן עצמו פעיל
        """
        logger.debug("[Scheduler] בדיקת בריאות מערכת...")

        issues = []

        # בדיקה 1: האם Kill Switch פעיל שלא בטובת הבוט?
        if self._risk_manager and self._risk_manager.is_kill_switch_active:
            issues.append(f"Kill Switch פעיל: {self._risk_manager._kill_switch_reason}")

        # בדיקה 2: האם CollarEnforcer צבר יותר מדי ניסיונות חשופים?
        if self._collar_enforcer and self._collar_enforcer.naked_attempt_count > 0:
            issues.append(
                f"ניסיונות כתיבה חשופה: {self._collar_enforcer.naked_attempt_count}"
            )

        status = "⚠️ יש התראות" if issues else "✅ תקין"
        await self._event_bus.publish(Event(
            event_type=EventType.HEALTH_CHECK,
            source="Engine/health_check",
            payload={
                "status": status,
                "issues": issues,
                "scheduler_tasks": self._scheduler.status() if self._scheduler else [],
            }
        ))

        if issues:
            logger.warning("[Health] %s | בעיות: %s", status, issues)
        else:
            logger.debug("[Health] %s", status)

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------
    async def _on_kill_switch(self, event: Event) -> None:
        """
        Handler לאירוע KILL_SWITCH_ACTIVATED.
        כאשר Kill Switch מופעל — מתזמן ה-Scheduler מושבת כדי
        למנוע ניסיונות מסחר עתידיים.
        """
        reason = event.payload.get("reason", "לא ידוע")
        logger.critical("Engine: Kill Switch הופעל | סיבה: %s", reason)

        # השבת משימות מסחר (לא את בדיקות הבריאות)
        if self._scheduler:
            self._scheduler.disable("margin_sync")
            self._scheduler.disable("daily_loss_check")
            logger.warning("Engine: משימות מסחר הושבתו בגלל Kill Switch")

    async def _on_system_shutdown(self, event: Event) -> None:
        """
        Handler לאירוע SYSTEM_SHUTDOWN — מאותת לרשום לסגור.
        """
        logger.info("Engine: קיבל אירוע SYSTEM_SHUTDOWN")
        self._shutdown_event.set()

    async def _handle_os_signal(self, sig: signal.Signals) -> None:
        """
        Handler ל-OS signal (SIGINT/SIGTERM).
        מפעיל Graceful Shutdown בצורה אסינכרונית.

        Args:
            sig: ה-signal שהתקבל
        """
        logger.warning("Engine: קיבל signal %s — מתחיל Graceful Shutdown", sig.name)
        self._shutdown_event.set()

    # ------------------------------------------------------------------
    # Properties ציבוריים (לבדיקות ולניטור)
    # ------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    @property
    def event_bus(self) -> Optional[EventBus]:
        return self._event_bus

    @property
    def risk_manager(self) -> Optional[RiskManager]:
        return self._risk_manager

    @property
    def collar_enforcer(self) -> Optional[CollarEnforcer]:
        return self._collar_enforcer

    @property
    def scheduler(self) -> Optional[Scheduler]:
        return self._scheduler
