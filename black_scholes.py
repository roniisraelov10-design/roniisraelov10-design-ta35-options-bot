"""
analytics/black_scholes.py
==========================
מנוע Black-Scholes מלא — תמחור אופציות + יווניות + פתרון IV.

מה כלול:
  - תמחור Call/Put לפי Black-Scholes
  - חישוב כל היווניות: Delta, Gamma, Theta, Vega, Rho
  - פתרון Implied Volatility (IV) בשיטת Newton-Raphson
    עם fallback לשיטת Brent (bisection) ליציבות גבוהה
  - תמיכה בריבית בנק ישראל (קלט חיצוני)
  - Theta מחושב ב-₪ ליום (לא לשנה) — פורמט שקריא לאנשי מסחר

הנחות המודל:
  - מניות/מדד ללא דיבידנד (ניתן להוסיף q בהמשך)
  - תנודתיות קבועה (ה-Volatility Smile מטופל ב-iv_calculator.py)
  - ריבית חסרת סיכון ממשית (לא 0!)
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# קבועים
# ---------------------------------------------------------------------------
SQRT_2PI: float = math.sqrt(2 * math.pi)
TRADING_DAYS_PER_YEAR: int = 252

# גבולות חיפוש IV
IV_MIN: float = 1e-6    # 0.0001% — מינימום טכני
IV_MAX: float = 20.0    # 2000% — מקסימום שגוני (למניעת divergence)

# דיוק Newton-Raphson
NR_TOLERANCE:    float = 1e-7
NR_MAX_ITER:     int   = 100

# דיוק Brent (fallback)
BRENT_TOLERANCE: float = 1e-6
BRENT_MAX_ITER:  int   = 200


# ---------------------------------------------------------------------------
# פונקציות התפלגות נורמלית
# ---------------------------------------------------------------------------
def _norm_cdf(x: float) -> float:
    """CDF של התפלגות נורמלית סטנדרטית N(0,1)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    """PDF של התפלגות נורמלית סטנדרטית N(0,1)."""
    return math.exp(-0.5 * x * x) / SQRT_2PI


# ---------------------------------------------------------------------------
# חישוב d1 ו-d2 — לב המשוואה
# ---------------------------------------------------------------------------
def _d1_d2(
    S: float,   # מחיר הבסיס
    K: float,   # מחיר המימוש (Strike)
    T: float,   # זמן לפקיעה בשנים
    r: float,   # ריבית חסרת סיכון (שנתית, עשרוני)
    sigma: float,  # תנודתיות (שנתית, עשרוני)
) -> tuple[float, float]:
    """
    מחשב את d1 ו-d2 של Black-Scholes.

    d1 = [ln(S/K) + (r + 0.5σ²)T] / (σ√T)
    d2 = d1 - σ√T
    """
    if T <= 0 or sigma <= 0:
        raise ValueError(f"T ו-sigma חייבים להיות חיוביים | T={T:.6f} sigma={sigma:.4f}")

    sqrt_T   = math.sqrt(T)
    ln_S_K   = math.log(S / K)
    d1 = (ln_S_K + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    return d1, d2


# ---------------------------------------------------------------------------
# תמחור Call ו-Put
# ---------------------------------------------------------------------------
def bs_price(
    S:      float,
    K:      float,
    T:      float,
    r:      float,
    sigma:  float,
    option_type: Literal["CALL", "PUT"],
) -> float:
    """
    מחיר תיאורטי של אופציה לפי Black-Scholes.

    Args:
        S:           מחיר נכס הבסיס
        K:           מחיר מימוש
        T:           זמן לפקיעה בשנים (DTE / 252)
        r:           ריבית חסרת סיכון (שנתית, עשרוני — למשל 0.045 = 4.5%)
        sigma:       תנודתיות (IV שנתית, עשרוני — למשל 0.18 = 18%)
        option_type: "CALL" או "PUT"

    Returns:
        מחיר תיאורטי של האופציה (נקודות מדד)
    """
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    discount = math.exp(-r * T)   # גורם היוון

    if option_type == "CALL":
        return S * _norm_cdf(d1) - K * discount * _norm_cdf(d2)
    else:   # PUT
        return K * discount * _norm_cdf(-d2) - S * _norm_cdf(-d1)


# ---------------------------------------------------------------------------
# מחלקת Greeks מלאה
# ---------------------------------------------------------------------------
@dataclass
class OptionGreeks:
    """
    כל היווניות של אופציה בודדת.

    כל הערכים הם לחוזה אחד (ניתן להכפיל ב-quantity לפוזיציה).

    Attributes:
        delta:  שינוי מחיר האופציה לכל שינוי נקודה בבסיס (0 עד ±1)
        gamma:  שינוי ב-Delta לכל שינוי נקודה בבסיס (תמיד חיובי)
        theta:  ₪ שאופציה מאבדת ביום מסחר אחד (תמיד שלילי לקונה)
        vega:   שינוי מחיר לכל 1% שינוי ב-IV
        rho:    שינוי מחיר לכל 1% שינוי בריבית
        iv:     ה-Implied Volatility שממנה חושבו היווניות
        price:  מחיר תיאורטי BS
    """
    delta: float
    gamma: float
    theta: float   # ₪ ליום מסחר
    vega:  float   # ₪ ל-1% שינוי ב-IV
    rho:   float
    iv:    float
    price: float

    def __repr__(self) -> str:
        return (
            f"Greeks(Δ={self.delta:+.4f} Γ={self.gamma:.5f} "
            f"Θ={self.theta:+.4f}/day Vega={self.vega:.4f} "
            f"IV={self.iv:.1%} P={self.price:.2f})"
        )


def compute_greeks(
    S:           float,
    K:           float,
    T:           float,
    r:           float,
    sigma:       float,
    option_type: Literal["CALL", "PUT"],
) -> OptionGreeks:
    """
    מחשב את כל היווניות של אופציה.

    שים לב על Theta:
      BS נותן Theta בשנים — אנחנו ממירים ל-ₓ ליום מסחר (÷252).
      הסימן הוא שלילי לקונה: כל יום שעובר, הקונה מפסיד Theta.

    Args:
        S, K, T, r, sigma: פרמטרי Black-Scholes
        option_type: "CALL" או "PUT"

    Returns:
        OptionGreeks עם כל הערכים
    """
    d1, d2   = _d1_d2(S, K, T, r, sigma)
    sqrt_T   = math.sqrt(T)
    discount = math.exp(-r * T)
    pdf_d1   = _norm_pdf(d1)

    # --- Delta ---
    if option_type == "CALL":
        delta = _norm_cdf(d1)
    else:
        delta = _norm_cdf(d1) - 1.0   # שקול ל: -N(-d1)

    # --- Gamma (זהה ל-Call ו-Put) ---
    gamma = pdf_d1 / (S * sigma * sqrt_T)

    # --- Theta (ליום מסחר, לא לשנה) ---
    theta_annual_part1 = -(S * pdf_d1 * sigma) / (2 * sqrt_T)

    if option_type == "CALL":
        theta_annual = theta_annual_part1 - r * K * discount * _norm_cdf(d2)
    else:
        theta_annual = theta_annual_part1 + r * K * discount * _norm_cdf(-d2)

    # המרה מ"לשנה" ל"ליום מסחר"
    theta = theta_annual / TRADING_DAYS_PER_YEAR

    # --- Vega (ל-1% שינוי ב-IV) ---
    vega_per_unit = S * sqrt_T * pdf_d1   # ל-100% (שינוי של 1.0 ב-sigma)
    vega = vega_per_unit / 100.0           # ל-1% שינוי ב-IV

    # --- Rho (ל-1% שינוי בריבית) ---
    if option_type == "CALL":
        rho = K * T * discount * _norm_cdf(d2) / 100.0
    else:
        rho = -K * T * discount * _norm_cdf(-d2) / 100.0

    # --- מחיר תיאורטי ---
    price = bs_price(S, K, T, r, sigma, option_type)

    return OptionGreeks(
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        rho=rho,
        iv=sigma,
        price=price,
    )


# ---------------------------------------------------------------------------
# פתרון Implied Volatility — Newton-Raphson
# ---------------------------------------------------------------------------
def _iv_newton_raphson(
    market_price: float,
    S: float, K: float, T: float, r: float,
    option_type: Literal["CALL", "PUT"],
    initial_guess: float = 0.20,
) -> float | None:
    """
    פתרון IV בשיטת Newton-Raphson — מהיר אבל יכול לא להתכנס.

    הרעיון: מתחיל מ-sigma ראשוני ומשפר בכל איטרציה:
      sigma_new = sigma - (BS_price(sigma) - market_price) / Vega(sigma)

    Returns:
        IV כ-float, או None אם לא התכנס
    """
    sigma = initial_guess

    for i in range(NR_MAX_ITER):
        try:
            price = bs_price(S, K, T, r, sigma, option_type)
            # Vega = נגזרת מחיר לפי sigma (ב-100% לא ב-1%)
            d1, _ = _d1_d2(S, K, T, r, sigma)
            vega   = S * math.sqrt(T) * _norm_pdf(d1)   # ל-100% שינוי ב-sigma

            if abs(vega) < 1e-10:
                # Vega כמעט אפס — Newton-Raphson יתפוצץ
                return None

            diff   = price - market_price
            sigma_new = sigma - diff / vega

            # וולידציה — sigma חייב להישאר בגבולות סבירים
            sigma_new = max(IV_MIN, min(IV_MAX, sigma_new))

            if abs(sigma_new - sigma) < NR_TOLERANCE:
                return sigma_new   # התכנסות!

            sigma = sigma_new

        except (ValueError, ZeroDivisionError, OverflowError):
            return None   # בעיה מתמטית — fallback ל-Brent

    return None   # לא התכנס תוך NR_MAX_ITER


def _iv_brent(
    market_price: float,
    S: float, K: float, T: float, r: float,
    option_type: Literal["CALL", "PUT"],
) -> float | None:
    """
    פתרון IV בשיטת Brent (bisection משופרת) — איטי אבל תמיד מתכנס.
    משמש כ-fallback כאשר Newton-Raphson נכשל.

    הרעיון: חפש את sigma שבו BS_price(sigma) = market_price
    בתוך קטע [IV_MIN, IV_MAX] על ידי חלוקה חוזרת לשניים.
    """
    def price_diff(sigma: float) -> float:
        try:
            return bs_price(S, K, T, r, sigma, option_type) - market_price
        except (ValueError, OverflowError):
            return float("nan")

    lo, hi = IV_MIN, IV_MAX
    f_lo = price_diff(lo)
    f_hi = price_diff(hi)

    # בדוק שהפתרון נמצא בקטע
    if math.isnan(f_lo) or math.isnan(f_hi):
        return None
    if f_lo * f_hi > 0:
        # אין שינוי סימן — הפתרון לא בקטע (מחיר חריג מאוד)
        return None

    for _ in range(BRENT_MAX_ITER):
        mid    = 0.5 * (lo + hi)
        f_mid  = price_diff(mid)

        if math.isnan(f_mid):
            return None

        if abs(f_mid) < BRENT_TOLERANCE or (hi - lo) < BRENT_TOLERANCE:
            return mid

        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid

    return 0.5 * (lo + hi)


def solve_iv(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type:  Literal["CALL", "PUT"],
) -> float | None:
    """
    מחשב Implied Volatility ממחיר שוק של אופציה.

    אסטרטגיה:
      1. נסה Newton-Raphson — מהיר ומדויק
      2. אם נכשל — Brent fallback — איטי אבל תמיד מתכנס
      3. אם גם Brent נכשל — החזר None

    Args:
        market_price: מחיר השוק של האופציה (Mid/Ask/Bid לפי הצורך)
        S:            מחיר נכס הבסיס
        K:            מחיר מימוש
        T:            זמן לפקיעה בשנים
        r:            ריבית חסרת סיכון
        option_type:  "CALL" או "PUT"

    Returns:
        IV כ-float עשרוני (0.18 = 18%), או None אם לא ניתן לחשב
    """
    # ולידציות בסיסיות
    if market_price <= 0 or T <= 0 or S <= 0 or K <= 0:
        logger.debug("solve_iv: קלט לא תקין | price=%.4f T=%.6f S=%.2f K=%.2f",
                     market_price, T, S, K)
        return None

    # ניסיון 1: Newton-Raphson עם ניחוש ראשוני חכם
    moneyness  = S / K
    init_sigma = 0.20 + abs(1.0 - moneyness) * 0.3   # ניחוש ראשוני לפי Moneyness
    iv = _iv_newton_raphson(market_price, S, K, T, r, option_type, init_sigma)

    if iv is not None and IV_MIN < iv < IV_MAX:
        return iv

    # ניסיון 2: Brent (fallback)
    iv = _iv_brent(market_price, S, K, T, r, option_type)

    if iv is not None and IV_MIN < iv < IV_MAX:
        return iv

    logger.warning(
        "solve_iv: לא הצליח לפתור IV | price=%.4f S=%.2f K=%.2f T=%.4f",
        market_price, S, K, T
    )
    return None
