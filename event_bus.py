"""
core/event_bus.py
=================
אוטובוס אירועים אסינכרוני המבוסס על דפוס Publish/Subscribe.
כל מודול במערכת מתקשר עם שאר המודולים אך ורק דרך קובץ זה —
כך שאין תלות ישירה בין מודולים ומבנה הקוד נשאר נקי ומודולרי.
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# הגדרת סוגי האירועים האפשריים במערכת
# ---------------------------------------------------------------------------
class EventType(Enum):
    """כל האירועים האפשריים שמודולים יכולים לשדר או להירשם אליהם."""

    # אירועי נתוני שוק
    MARKET_DATA_TICK        = auto()  # עדכון מחיר חדש
    OPTIONS_CHAIN_UPDATED   = auto()  # שרשרת אופציות התעדכנה
    GREEKS_UPDATED          = auto()  # ערכי הגריקים התעדכנו

    # אירועי פקודות ומסחר
    ORDER_REQUEST           = auto()  # בקשה לביצוע פקודה חדשה
    ORDER_APPROVED          = auto()  # פקודה אושרה על ידי מנהל הסיכונים
    ORDER_REJECTED          = auto()  # פקודה נדחתה
    ORDER_FILLED            = auto()  # פקודה בוצעה בפועל בשוק
    ORDER_CANCELLED         = auto()  # פקודה בוטלה
    CANCEL_ALL_ORDERS       = auto()  # בקשה לביטול כל הפקודות (Kill Switch)

    # אירועי סיכון
    RISK_VIOLATION          = auto()  # חריגה מכללי הסיכון
    NAKED_POSITION_BLOCKED  = auto()  # ניסיון כתיבה חשופה נחסם
    MARGIN_WARNING          = auto()  # אזהרה על מרג'ין נמוך
    MARGIN_BREACH           = auto()  # חריגת מרג'ין קריטית
    DAILY_LOSS_BREACH       = auto()  # הגיע לגבול ההפסד היומי
    KILL_SWITCH_ACTIVATED   = auto()  # מתג חירום הופעל
    KILL_SWITCH_DEACTIVATED = auto()  # מתג חירום בוטל (ידנית)

    # אירועי תיק
    POSITION_OPENED         = auto()  # פוזיציה חדשה נפתחה
    POSITION_CLOSED         = auto()  # פוזיציה נסגרה
    PNL_UPDATED             = auto()  # עדכון רווח/הפסד

    # אירועי מערכת
    SYSTEM_STARTUP          = auto()  # המערכת עלתה
    SYSTEM_SHUTDOWN         = auto()  # המערכת יורדת
    HEALTH_CHECK            = auto()  # בדיקת תקינות
    ALERT_SEND              = auto()  # שליחת התראה חיצונית (Telegram וכו')


# ---------------------------------------------------------------------------
# מבנה נתונים לאירוע
# ---------------------------------------------------------------------------
@dataclass
class Event:
    """
    מייצג אירוע בודד שמועבר בין מודולים.

    Attributes:
        event_type: סוג האירוע מתוך ה-Enum
        payload:    המידע הנלווה לאירוע (dict עם פרטים)
        source:     שם המודול ששלח את האירוע
        timestamp:  זמן יצירת האירוע
        event_id:   מזהה ייחודי לאירוע (לצורך audit)
    """
    event_type: EventType
    payload:    dict[str, Any]       = field(default_factory=dict)
    source:     str                  = "unknown"
    timestamp:  datetime             = field(default_factory=datetime.utcnow)
    event_id:   int                  = field(default_factory=lambda: id(object()))


# סוג עזר: כל handler הוא coroutine שמקבל Event ומחזיר None
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


# ---------------------------------------------------------------------------
# מחלקת ה-EventBus עצמה
# ---------------------------------------------------------------------------
class EventBus:
    """
    אוטובוס אירועים אסינכרוני — ה"עורק" של המערכת כולה.

    שימוש בסיסי:
        bus = EventBus()

        # הרשמה לאירוע:
        @bus.subscribe(EventType.ORDER_REQUEST)
        async def on_order(event: Event):
            print(event.payload)

        # שידור אירוע:
        await bus.publish(Event(EventType.ORDER_REQUEST, payload={...}))
    """

    def __init__(self) -> None:
        # מילון שמפה כל EventType לרשימת ה-handlers הרשומים אליו
        self._subscribers: dict[EventType, list[EventHandler]] = defaultdict(list)

        # תור אסינכרוני שדרכו עוברים כל האירועים לפני שמועברים ל-handlers
        self._queue: asyncio.Queue[Event] = asyncio.Queue()

        # דגל שמציין האם ה-bus פעיל ומאזין
        self._running: bool = False

        # משימת ה-asyncio שמריצה את לולאת העיבוד
        self._dispatch_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Subscription API
    # ------------------------------------------------------------------
    def subscribe(self, event_type: EventType) -> Callable:
        """
        דקורטור להרשמה לסוג אירוע ספציפי.

        Args:
            event_type: סוג האירוע להאזנה

        Returns:
            דקורטור שעוטף את ה-handler ורושם אותו

        Example:
            @bus.subscribe(EventType.KILL_SWITCH_ACTIVATED)
            async def handle_kill(event: Event): ...
        """
        def decorator(handler: EventHandler) -> EventHandler:
            self._subscribers[event_type].append(handler)
            logger.debug(
                "מנוי חדש נרשם | event=%s | handler=%s",
                event_type.name, handler.__qualname__
            )
            return handler
        return decorator

    def subscribe_handler(self, event_type: EventType, handler: EventHandler) -> None:
        """
        גרסה פרוגרמטית של subscribe — לשימוש מחוץ לדקורטור.

        Args:
            event_type: סוג האירוע
            handler:    ה-coroutine function לרישום
        """
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """
        מסיר handler מרשימת המנויים.

        Args:
            event_type: סוג האירוע
            handler:    ה-handler להסרה
        """
        try:
            self._subscribers[event_type].remove(handler)
        except ValueError:
            logger.warning("ניסיון להסיר handler שאינו רשום: %s", handler.__qualname__)

    # ------------------------------------------------------------------
    # Publish API
    # ------------------------------------------------------------------
    async def publish(self, event: Event) -> None:
        """
        מפרסם אירוע לתור — כל ה-handlers הרשומים יקבלו אותו בתורם.

        Args:
            event: האירוע לפרסום
        """
        logger.debug(
            "אירוע נכנס לתור | type=%s | source=%s | id=%s",
            event.event_type.name, event.source, event.event_id
        )
        await self._queue.put(event)

    def publish_sync(self, event: Event) -> None:
        """
        גרסה סינכרונית של publish — לשימוש ממקומות שאינם async.
        שימושי בעיקר עבור signal handlers ו-callbacks חיצוניים.
        """
        asyncio.get_event_loop().call_soon_threadsafe(
            self._queue.put_nowait, event
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """מפעיל את לולאת עיבוד האירועים ברקע."""
        self._running = True
        self._dispatch_task = asyncio.create_task(
            self._dispatch_loop(), name="event_bus_dispatch"
        )
        logger.info("EventBus הופעל בהצלחה")

    async def stop(self) -> None:
        """עוצר את לולאת העיבוד בצורה מסודרת."""
        self._running = False
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
        logger.info("EventBus נעצר")

    # ------------------------------------------------------------------
    # לולאת העיבוד הפנימית
    # ------------------------------------------------------------------
    async def _dispatch_loop(self) -> None:
        """
        לולאה אסינכרונית שרצה ברקע ומוציאה אירועים מהתור.
        לכל אירוע — מפעילה את כל ה-handlers הרשומים במקביל.
        """
        while self._running:
            try:
                # המתן לאירוע הבא בתור (blocking async)
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch_event(event)
                self._queue.task_done()

            except asyncio.TimeoutError:
                # תור ריק — המשך ולנסות שוב
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("שגיאה בלולאת ה-dispatch: %s", exc)

    async def _dispatch_event(self, event: Event) -> None:
        """
        מעביר אירוע אחד לכל ה-handlers הרשומים.
        שגיאה ב-handler אחד לא עוצרת את השאר.
        """
        handlers = self._subscribers.get(event.event_type, [])

        if not handlers:
            logger.debug("אין מנויים לאירוע %s", event.event_type.name)
            return

        # הפעל את כל ה-handlers במקביל
        results = await asyncio.gather(
            *[handler(event) for handler in handlers],
            return_exceptions=True  # שגיאות לא מפילות את ה-gather
        )

        # דווח על שגיאות בלי לשבור את הזרימה
        for handler, result in zip(handlers, results):
            if isinstance(result, Exception):
                logger.error(
                    "שגיאה ב-handler %s לאירוע %s: %s",
                    handler.__qualname__, event.event_type.name, result
                )


# ---------------------------------------------------------------------------
# Singleton — מופע יחיד של ה-bus לכל המערכת
# ---------------------------------------------------------------------------
_bus_instance: EventBus | None = None


def get_event_bus() -> EventBus:
    """
    מחזיר את המופע היחיד של ה-EventBus (Singleton).
    כל מודול במערכת קורא לפונקציה זו כדי לקבל את אותו ה-bus.
    """
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = EventBus()
    return _bus_instance
