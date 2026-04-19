"""
analytics/calendar_il.py
========================
לוח שנה מסחרי ישראלי — מחשב ימי מסחר אמיתיים עד לפקיעה.

הבעיה עם DTE "גולמי":
  אם תספור ימים קלנדריים פשוטים, תקבל DTE של 30 לאופציה שבאמת
  נותרו לה רק 19 ימי מסחר. זה יגרום לחישוב Theta שגוי לחלוטין —
  האופציה "תיראה" זולה יותר ממה שהיא באמת, כי ה-time decay האמיתי
  מחושב רק על ימי מסחר.

הפתרון:
  1. מסנן שישי + שבת (שוק סגור)
  2. מחסיר את כל חגי ישראל הרלוונטיים
  3. מחשב DTE כשבר עשרוני (חשוב לאופציות תוך-יומיות)

מקור חגים: לוח חגי בורסת ת"א הרשמי.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import FrozenSet


# ---------------------------------------------------------------------------
# חגי ישראל — ימי סגירה של הבורסה
# ---------------------------------------------------------------------------
# חגים שחלים ב-2024–2026 (יש לעדכן שנתי!)
# מקור: https://www.tase.co.il/he/market/tradinghours
_TASE_HOLIDAYS: FrozenSet[date] = frozenset({
    # --- 2024 ---
    date(2024, 4,  22),   # ערב פסח
    date(2024, 4,  23),   # פסח א'
    date(2024, 4,  28),   # שביעי של פסח
    date(2024, 4,  29),   # ערב שביעי של פסח
    date(2024, 5,  13),   # יום העצמאות
    date(2024, 6,  11),   # שבועות
    date(2024, 6,  12),   # שבועות ב'
    date(2024, 10,  2),   # ערב ראש השנה
    date(2024, 10,  3),   # ראש השנה א'
    date(2024, 10,  4),   # ראש השנה ב'
    date(2024, 10, 11),   # ערב יום כיפור
    date(2024, 10, 12),   # יום כיפור
    date(2024, 10, 16),   # ערב סוכות
    date(2024, 10, 17),   # סוכות
    date(2024, 10, 23),   # הושענא רבה
    date(2024, 10, 24),   # שמיני עצרת / שמחת תורה

    # --- 2025 ---
    date(2025, 1,  13),   # י"ג שבט (לא חג בורסה, דוגמה)
    date(2025, 4,  12),   # ערב פסח
    date(2025, 4,  13),   # פסח א'
    date(2025, 4,  18),   # שביעי של פסח
    date(2025, 5,   1),   # יום העצמאות
    date(2025, 6,   1),   # שבועות
    date(2025, 6,   2),   # שבועות ב'
    date(2025, 9,  22),   # ערב ראש השנה
    date(2025, 9,  23),   # ראש השנה א'
    date(2025, 9,  24),   # ראש השנה ב'
    date(2025, 10,  1),   # ערב יום כיפור
    date(2025, 10,  2),   # יום כיפור
    date(2025, 10,  6),   # ערב סוכות
    date(2025, 10,  7),   # סוכות
    date(2025, 10, 13),   # הושענא רבה
    date(2025, 10, 14),   # שמיני עצרת

    # --- 2026 ---
    date(2026, 4,   1),   # ערב פסח
    date(2026, 4,   2),   # פסח א'
    date(2026, 4,   7),   # שביעי של פסח
    date(2026, 4,   8),   # שביעי של פסח ב'
    date(2026, 4,  22),   # יום העצמאות
    date(2026, 5,  21),   # שבועות
    date(2026, 9,  10),   # ערב ראש השנה
    date(2026, 9,  11),   # ראש השנה א'
    date(2026, 9,  12),   # ראש השנה ב'
    date(2026, 9,  19),   # ערב יום כיפור
    date(2026, 9,  20),   # יום כיפור
    date(2026, 9,  24),   # ערב סוכות
    date(2026, 9,  25),   # סוכות
    date(2026, 10,  1),   # הושענא רבה
    date(2026, 10,  2),   # שמיני עצרת
})

# שעות מסחר רשמיות של בורסת ת"א (UTC+3 בקיץ / UTC+2 בחורף)
TASE_OPEN_HOUR:  int = 9
TASE_OPEN_MIN:   int = 59   # פקיעת אופציות ב-09:59 ביום הפקיעה
TASE_CLOSE_HOUR: int = 17
TASE_CLOSE_MIN:  int = 30


# ---------------------------------------------------------------------------
# בדיקת יום מסחר
# ---------------------------------------------------------------------------
def is_trading_day(d: date) -> bool:
    """
    מחזיר True אם d הוא יום מסחר בבורסת ת"א.

    יום מסחר = לא שישי, לא שבת, לא חג בורסה.

    Args:
        d: התאריך לבדיקה

    Returns:
        True אם ניתן לסחור ביום זה
    """
    # שישי = 4, שבת = 5 (Python weekday: Mon=0, ..., Sat=6)
    if d.weekday() in (4, 5):    # שישי ושבת
        return False
    if d in _TASE_HOLIDAYS:
        return False
    return True


@lru_cache(maxsize=512)
def count_trading_days(start: date, end: date) -> int:
    """
    סופר ימי מסחר בין שני תאריכים (start כלול, end לא כלול).
    תוצאה מוכמנת (cached) — חישוב יקר שנעשה הרבה פעמים.

    Args:
        start: תאריך התחלה
        end:   תאריך סיום (לא כלול)

    Returns:
        מספר ימי מסחר
    """
    count = 0
    current = start
    while current < end:
        if is_trading_day(current):
            count += 1
        current += timedelta(days=1)
    return count


def next_trading_day(d: date) -> date:
    """
    מחזיר את יום המסחר הבא אחרי d.

    Args:
        d: תאריך התחלה

    Returns:
        יום המסחר הראשון לאחר d
    """
    candidate = d + timedelta(days=1)
    while not is_trading_day(candidate):
        candidate += timedelta(days=1)
    return candidate


# ---------------------------------------------------------------------------
# חישוב DTE מדויק (שבר עשרוני)
# ---------------------------------------------------------------------------
def compute_dte(
    now:    datetime,
    expiry: date,
) -> float:
    """
    מחשב ימים לפקיעה (DTE) כמספר עשרוני של ימי מסחר.

    מדוע עשרוני?
      אופציה שפוקעת היום ב-09:59 ועכשיו 09:00 — DTE ≈ 0.06.
      אם נחשב 0 — נקבל חישוב Theta שגוי לחלוטין (חלוקה באפס).

    הלוגיקה:
      1. ספור ימי מסחר שלמים מהיום ועד לפקיעה
      2. הוסף שבר עשרוני לפי השעה הנוכחית ביחס ליום המסחר הנוכחי

    Args:
        now:    חתך זמן נוכחי (datetime עם שעה)
        expiry: תאריך פקיעת האופציה

    Returns:
        DTE כ-float. לדוגמה: 14.37 = 14 ימי מסחר ו-37% מיום נוסף.
        מוחזר כ-0.0 לכל היותר (לא יכול להיות שלילי).
    """
    today = now.date()

    # מקרה גבול: האופציה כבר פקעה
    if expiry < today:
        return 0.0

    # ספור ימי מסחר שלמים מהיום+1 ועד הפקיעה
    full_trading_days = count_trading_days(
        start=today + timedelta(days=1),
        end=expiry + timedelta(days=1)   # כולל את יום הפקיעה עצמו
    )

    # חשב את השבר העשרוני של היום הנוכחי
    intraday_fraction = 0.0
    if is_trading_day(today):
        # כמה מזמן יום המסחר הנוכחי עבר (0.0 = פתיחה, 1.0 = סגירה)
        open_minutes  = TASE_OPEN_HOUR  * 60 + TASE_OPEN_MIN
        close_minutes = TASE_CLOSE_HOUR * 60 + TASE_CLOSE_MIN
        now_minutes   = now.hour * 60 + now.minute

        total_session   = close_minutes - open_minutes  # 451 דקות ביום מסחר רגיל
        elapsed         = max(0, min(now_minutes - open_minutes, total_session))
        pct_elapsed     = elapsed / total_session if total_session > 0 else 0.0

        # השבר הנותר מהיום הנוכחי
        intraday_fraction = max(0.0, 1.0 - pct_elapsed)

    return max(0.0, full_trading_days + intraday_fraction)


def dte_to_years(dte_days: float) -> float:
    """
    ממיר DTE בימי מסחר לשנים — הפורמט שנדרש למשוואת Black-Scholes.

    252 = מספר ימי המסחר הממוצע בשנה (בורסת ת"א).

    Args:
        dte_days: DTE בימי מסחר

    Returns:
        T = DTE / 252 (שנים)
    """
    TRADING_DAYS_PER_YEAR = 252.0
    return max(1e-9, dte_days / TRADING_DAYS_PER_YEAR)   # מניעת חלוקה באפס
