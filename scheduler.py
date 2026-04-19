"""
core/scheduler.py
=================
מתזמן משימות אסינכרוני — מריץ פונקציות ברקע במרווחי זמן קבועים.

תפקידו העיקרי הוא לנהל את כל ה"שעונים" של הבוט:
  - בדיקת ביטחונות מול הברוקר כל X שניות
  - בדיקת חריגת הפסד יומי כל X שניות
  - איפוס מונים בחצות
  - שמירת snapshot לדיסק כל X דקות
  - וכל משימת תחזוקה תקופתית אחרת

עיצוב:
  - כל משימה מוגדרת כ-ScheduledTask (dataclass)
  - הרצה מבוססת asyncio.create_task — לא חוסמת את ה-event loop
  - שגיאה במשימה אחת לא מפילה את השאר
  - ניתן להוסיף/להסיר משימות בזמן ריצה (dynamic registration)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Callable, Coroutine, Any, Optional
from enum import Enum, auto

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# טיפוסי תזמון
# ---------------------------------------------------------------------------
class ScheduleType(Enum):
    """
    שני מצבי תזמון נתמכים:
      INTERVAL — הפעל כל N שניות (לדוגמה: בדיקת מרג'ין כל 60 שניות)
      DAILY_AT  — הפעל פעם ביום בשעה מדויקת (לדוגמה: איפוס PnL בחצות)
    """
    INTERVAL  = auto()
    DAILY_AT  = auto()


# ---------------------------------------------------------------------------
# מבנה נתונים למשימה
# ---------------------------------------------------------------------------
@dataclass
class ScheduledTask:
    """
    מגדיר משימה תקופתית יחידה.

    Attributes:
        name:           שם מזהה לצרכי logging
        coro_func:      ה-coroutine function להפעלה (ללא ארגומנטים)
        schedule_type:  INTERVAL או DAILY_AT
        interval_sec:   מרווח בשניות (רלוונטי רק ל-INTERVAL)
        daily_at:       שעת הפעלה יומית (רלוונטי רק ל-DAILY_AT)
        run_immediately: האם לרוץ פעם אחת מיד בעת רישום (לפני ההמתנה הראשונה)
        enabled:        ניתן לכבות משימה ללא הסרתה
        last_run:       זמן ריצה אחרון (מתעדכן אוטומטית)
        run_count:      מספר הפעמים שהמשימה רצה
        error_count:    מספר שגיאות שנצברו
    """
    name:            str
    coro_func:       Callable[[], Coroutine[Any, Any, None]]
    schedule_type:   ScheduleType   = ScheduleType.INTERVAL
    interval_sec:    float          = 60.0
    daily_at:        Optional[time] = None          # למשל: time(0, 0) לחצות
    run_immediately: bool           = False
    enabled:         bool           = True
    last_run:        Optional[datetime] = field(default=None, compare=False)
    run_count:       int            = field(default=0,    compare=False)
    error_count:     int            = field(default=0,    compare=False)

    # asyncio.Task שמנהל את הלולאה של המשימה הזו
    _task: Optional[asyncio.Task]   = field(default=None, compare=False, repr=False)


# ---------------------------------------------------------------------------
# מחלקת Scheduler
# ---------------------------------------------------------------------------
class Scheduler:
    """
    מתזמן משימות אסינכרוני — מנהל קבוצת ScheduledTasks.

    Usage:
        scheduler = Scheduler()

        scheduler.register(ScheduledTask(
            name="margin_check",
            coro_func=risk_manager.check_margin_periodically,
            schedule_type=ScheduleType.INTERVAL,
            interval_sec=60,
            run_immediately=True,
        ))

        await scheduler.start()
        # ... later ...
        await scheduler.stop()
    """

    def __init__(self) -> None:
        # מילון שם → משימה
        self._tasks: dict[str, ScheduledTask] = {}
        self._running: bool = False

    # ------------------------------------------------------------------
    # רישום משימות
    # ------------------------------------------------------------------
    def register(self, task: ScheduledTask) -> None:
        """
        רושם משימה חדשה למתזמן.
        ניתן לקרוא לפני start() ואחריו — המשימה תופעל מיד אם המתזמן פעיל.

        Args:
            task: המשימה לרישום
        """
        if task.name in self._tasks:
            logger.warning("משימה עם שם '%s' כבר רשומה — מוחלפת", task.name)

        self._tasks[task.name] = task
        logger.info(
            "משימה נרשמה | name=%s | type=%s | %s",
            task.name,
            task.schedule_type.name,
            f"interval={task.interval_sec}s" if task.schedule_type == ScheduleType.INTERVAL
            else f"daily_at={task.daily_at}",
        )

        # אם המתזמן כבר פעיל — הפעל את המשימה מיד
        if self._running:
            task._task = asyncio.create_task(
                self._run_task_loop(task), name=f"sched_{task.name}"
            )

    def unregister(self, name: str) -> None:
        """
        מסיר משימה מהמתזמן ומבטל אותה אם פעילה.

        Args:
            name: שם המשימה להסרה
        """
        task = self._tasks.pop(name, None)
        if task and task._task:
            task._task.cancel()
            logger.info("משימה הוסרה | name=%s", name)
        elif not task:
            logger.warning("ניסיון להסיר משימה לא קיימת | name=%s", name)

    def enable(self, name: str) -> None:
        """מפעיל מחדש משימה שהייתה מושבתת."""
        if task := self._tasks.get(name):
            task.enabled = True
            logger.info("משימה הופעלה | name=%s", name)

    def disable(self, name: str) -> None:
        """משבית משימה מבלי להסיר אותה (תמשיך לרוץ אבל תדלג)."""
        if task := self._tasks.get(name):
            task.enabled = False
            logger.info("משימה הושבתה | name=%s", name)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """מפעיל לולאת ריצה לכל המשימות הרשומות."""
        self._running = True
        for task in self._tasks.values():
            task._task = asyncio.create_task(
                self._run_task_loop(task), name=f"sched_{task.name}"
            )
        logger.info("Scheduler הופעל | %d משימות פעילות", len(self._tasks))

    async def stop(self) -> None:
        """מבטל את כל המשימות ומחכה לסיומן."""
        self._running = False
        cancel_tasks = [
            t._task for t in self._tasks.values() if t._task and not t._task.done()
        ]
        for ct in cancel_tasks:
            ct.cancel()

        # המתן שכולן ייסגרו בצורה מסודרת
        if cancel_tasks:
            await asyncio.gather(*cancel_tasks, return_exceptions=True)

        logger.info("Scheduler עצר | %d משימות בוטלו", len(cancel_tasks))

    # ------------------------------------------------------------------
    # לולאות ריצה פנימיות
    # ------------------------------------------------------------------
    async def _run_task_loop(self, task: ScheduledTask) -> None:
        """
        לולאת ריצה של משימה בודדת — רצה ברקע עד לביטול.
        בוחר את סוג הלולאה לפי schedule_type.
        """
        if task.schedule_type == ScheduleType.INTERVAL:
            await self._interval_loop(task)
        elif task.schedule_type == ScheduleType.DAILY_AT:
            await self._daily_loop(task)

    async def _interval_loop(self, task: ScheduledTask) -> None:
        """
        לולאה שמריצה משימה כל N שניות.

        אם run_immediately=True — הפעל פעם אחת לפני ההמתנה הראשונה.
        """
        # הפעלה מיידית אם נדרשת
        if task.run_immediately:
            await self._execute_task(task)

        while self._running:
            try:
                # המתן את המרווח המוגדר
                await asyncio.sleep(task.interval_sec)

                # בדוק שהמשימה עדיין מופעלת (יכול להשתנות בזמן ריצה)
                if not task.enabled:
                    logger.debug("משימה מושבתת — מדלג | name=%s", task.name)
                    continue

                await self._execute_task(task)

            except asyncio.CancelledError:
                # ביטול מסודר — צא מהלולאה
                logger.debug("לולאת INTERVAL בוטלה | name=%s", task.name)
                break
            except Exception as exc:
                # שגיאה לא צפויה — תרשום ותמשיך
                task.error_count += 1
                logger.exception(
                    "שגיאה בלתי צפויה בלולאת INTERVAL | name=%s | error=%s",
                    task.name, exc
                )
                # המתן מעט לפני הניסיון הבא (back-off פשוט)
                await asyncio.sleep(min(task.interval_sec, 10.0))

    async def _daily_loop(self, task: ScheduledTask) -> None:
        """
        לולאה שמריצה משימה פעם ביום בשעה מדויקת.

        הלוגיקה: חשב כמה שניות עד לשעה הבאה → המתן → הפעל → חזור.
        """
        if task.daily_at is None:
            logger.error("DAILY_AT ללא שעה מוגדרת | name=%s", task.name)
            return

        while self._running:
            try:
                seconds_until = self._seconds_until(task.daily_at)
                logger.debug(
                    "משימה יומית | name=%s | תרוץ בעוד %.0f שניות (%.1f שעות)",
                    task.name, seconds_until, seconds_until / 3600
                )

                await asyncio.sleep(seconds_until)

                if not task.enabled:
                    continue

                await self._execute_task(task)

            except asyncio.CancelledError:
                logger.debug("לולאת DAILY_AT בוטלה | name=%s", task.name)
                break
            except Exception as exc:
                task.error_count += 1
                logger.exception(
                    "שגיאה בלולאת DAILY_AT | name=%s | error=%s", task.name, exc
                )
                # אם נכשלנו — נסה שוב בעוד דקה
                await asyncio.sleep(60)

    async def _execute_task(self, task: ScheduledTask) -> None:
        """
        מבצע את המשימה בפועל ומעדכן את הסטטיסטיקות שלה.

        Args:
            task: המשימה לביצוע
        """
        start = datetime.utcnow()
        try:
            logger.debug("מריץ משימה | name=%s", task.name)
            await task.coro_func()
            task.run_count += 1
            task.last_run = start
            elapsed = (datetime.utcnow() - start).total_seconds()
            logger.debug(
                "משימה הושלמה | name=%s | elapsed=%.3fs | total_runs=%d",
                task.name, elapsed, task.run_count
            )
        except Exception as exc:
            task.error_count += 1
            logger.error(
                "שגיאה בביצוע משימה | name=%s | error=%s | total_errors=%d",
                task.name, exc, task.error_count
            )

    # ------------------------------------------------------------------
    # פונקציות עזר
    # ------------------------------------------------------------------
    @staticmethod
    def _seconds_until(target_time: time) -> float:
        """
        מחשב כמה שניות נשארו עד לשעה הבאה של target_time.
        אם השעה כבר עברה היום — מחזיר את הזמן עד לאותה שעה מחר.

        Args:
            target_time: השעה המבוקשת (time object)

        Returns:
            מספר שניות עד לשעה הבאה
        """
        now = datetime.now()
        target_today = datetime(
            now.year, now.month, now.day,
            target_time.hour, target_time.minute, target_time.second
        )
        delta = (target_today - now).total_seconds()

        # אם השעה כבר עברה היום — חשב ל-24 שעות קדימה
        if delta <= 0:
            delta += 86_400  # 24 * 60 * 60

        return delta

    # ------------------------------------------------------------------
    # תצוגת סטטוס
    # ------------------------------------------------------------------
    def status(self) -> list[dict]:
        """
        מחזיר סטטוס של כל המשימות הרשומות.
        שימושי לניטור ולבריאות המערכת.

        Returns:
            רשימת dict עם פרטי כל משימה
        """
        return [
            {
                "name":        t.name,
                "enabled":     t.enabled,
                "schedule":    t.schedule_type.name,
                "interval":    t.interval_sec if t.schedule_type == ScheduleType.INTERVAL else None,
                "daily_at":    str(t.daily_at) if t.daily_at else None,
                "run_count":   t.run_count,
                "error_count": t.error_count,
                "last_run":    t.last_run.isoformat() if t.last_run else "טרם רץ",
                "task_alive":  t._task and not t._task.done() if t._task else False,
            }
            for t in self._tasks.values()
        ]
