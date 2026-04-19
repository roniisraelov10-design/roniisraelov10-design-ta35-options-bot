"""
signals/models.py
=================
מודלי הנתונים (Dataclasses) של מנוע האותות.

כל אובייקט כאן הוא immutable ומיועד להעברה בין מודולים דרך ה-EventBus
ולהצגה בדשבורד Streamlit.

היררכיה:
  OptionLeg          ← רגל בודדת של אסטרטגיה (CALL/PUT אחד)
  SpreadSignal        ← המלצת מרווח מלאה (2 רגליים)
  IronCondorSignal   ← המלצת Iron Condor (4 רגליים)
  MarketSnapshot     ← תמונת שוק כללית (IV Rank, VIX תל-אביבי)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum, auto
from typing import Literal, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class StrategyType(Enum):
    BULL_PUT_SPREAD    = "Bull Put Spread"
    BEAR_CALL_SPREAD   = "Bear Call Spread"
    IRON_CONDOR        = "Iron Condor"


class SignalStrength(Enum):
    """עוצמת האות — לצביעה בדשבורד."""
    STRONG = "🟢 חזק"     # RR > 1:3 + POP > 70%
    MEDIUM = "🟡 בינוני"  # RR > 1:2 + POP > 60%
    WEAK   = "🔴 חלש"     # מתחת לסף


class IVEnvironment(Enum):
    """סביבת ה-IV הנוכחית ביחס להיסטוריה."""
    HIGH     = "גבוה"    # IV Rank > 50 — זמן טוב לכתיבה
    MODERATE = "בינוני"  # IV Rank 25–50
    LOW      = "נמוך"    # IV Rank < 25 — לא אידיאלי לכתיבה


# ---------------------------------------------------------------------------
# אובייקטי נתוני שוק
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OptionQuote:
    """
    ציטוט של אופציה בודדת מהשוק.

    frozen=True: לא ניתן לשנות אחרי יצירה — בטוח לשימוש ב-cache.

    Attributes:
        symbol:      סמל האופציה
        option_type: "CALL" או "PUT"
        strike:      מחיר המימוש
        expiry:      תאריך הפקיעה
        bid:         מחיר הקונה (כתיבה תבוצע לפי זה)
        ask:         מחיר המוכר (קנייה תבוצע לפי זה)
        last:        מחיר עסקה אחרונה
        volume:      נפח מסחר יומי (חוזים)
        open_interest: ריבית פתוחה (חוזים)
        iv:          Implied Volatility שחושבה מה-Mid (לדיספליי בלבד)
        timestamp:   זמן הציטוט
    """
    symbol:        str
    option_type:   Literal["CALL", "PUT"]
    strike:        float
    expiry:        date
    bid:           float
    ask:           float
    last:          float
    volume:        int
    open_interest: int
    iv:            Optional[float] = None   # IV שחושבה ממחיר Mid
    timestamp:     datetime        = field(default_factory=datetime.utcnow)

    @property
    def mid(self) -> float:
        """Mid-Price — לדיספליי בלבד! לעולם לא לחישוב עלות פוזיציה."""
        return (self.bid + self.ask) / 2.0

    @property
    def spread_pct(self) -> float:
        """
        רוחב ה-Bid-Ask Spread כאחוז מה-Mid.
        ערך גבוה = נזילות נמוכה = יש להיזהר.
        """
        if self.mid == 0:
            return float("inf")
        return (self.ask - self.bid) / self.mid


@dataclass(frozen=True)
class OptionGreeksSnapshot:
    """
    יווניות של אופציה בודדת בנקודת זמן.
    """
    delta: float
    gamma: float
    theta: float   # ₪ ליום מסחר
    vega:  float   # ₪ ל-1% שינוי IV
    rho:   float
    iv:    float   # IV ספציפי לסטרייק הזה (Volatility Smile!)


# ---------------------------------------------------------------------------
# רגל בודדת באסטרטגיה
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OptionLeg:
    """
    רגל אחת באסטרטגיה — קנייה או כתיבה של אופציה אחת.

    Attributes:
        quote:       ציטוט השוק של האופציה
        greeks:      היווניות של האופציה
        action:      "BUY" (קנייה) או "SELL" (כתיבה)
        quantity:    כמות חוזים
        fill_price:  מחיר הביצוע המשוער:
                       - קנייה → Ask (שמרני!)
                       - כתיבה → Bid (שמרני!)
    """
    quote:      OptionQuote
    greeks:     OptionGreeksSnapshot
    action:     Literal["BUY", "SELL"]
    quantity:   int

    @property
    def fill_price(self) -> float:
        """
        מחיר הביצוע המשוער לפי כיוון הפקודה.

        כלל ברזל: לעולם לא Mid-Price!
          קנייה  → Ask (אנחנו "נוגעים" ב-Ask)
          כתיבה → Bid (הקונה שמולנו "נוגע" ב-Ask שלו = ה-Bid שלנו)
        """
        return self.quote.ask if self.action == "BUY" else self.quote.bid

    @property
    def cost(self) -> float:
        """
        עלות/הכנסה של הרגל הזו (נקודות מדד × כמות).
        חיובי = קנייה (הוצאה), שלילי = כתיבה (הכנסה).
        """
        sign = 1.0 if self.action == "BUY" else -1.0
        return sign * self.fill_price * self.quantity

    @property
    def net_delta(self) -> float:
        sign = 1.0 if self.action == "BUY" else -1.0
        return sign * self.greeks.delta * self.quantity

    @property
    def net_gamma(self) -> float:
        sign = 1.0 if self.action == "BUY" else -1.0
        return sign * self.greeks.gamma * self.quantity

    @property
    def net_theta(self) -> float:
        """Theta חיובי ל-Seller (מרוויח מזמן), שלילי ל-Buyer."""
        sign = 1.0 if self.action == "BUY" else -1.0
        return sign * self.greeks.theta * self.quantity

    @property
    def net_vega(self) -> float:
        sign = 1.0 if self.action == "BUY" else -1.0
        return sign * self.greeks.vega * self.quantity


# ---------------------------------------------------------------------------
# יווניות ברמת הפוזיציה המשולבת
# ---------------------------------------------------------------------------
@dataclass
class PositionGreeks:
    """
    יווניות מצרפיות של כל הרגליים יחד.

    כאן נמדדת החשיפה האמיתית של הפוזיציה כולה.
    לדוגמה ב-Bull Put Spread:
      net_theta חיובי = אנחנו מרוויחים מזמן (כי הכתיבה גדולה מהקנייה)
      net_delta נמוך  = הפוזיציה יחסית ניטרלית לכיוון השוק
    """
    net_delta: float   # חשיפה לכיוון השוק
    net_gamma: float   # שינוי ב-Delta לתנועה של נקודה
    net_theta: float   # ₪ שמרוויחים/מפסידים ביום מסחר
    net_vega:  float   # רגישות לשינויי IV

    @classmethod
    def from_legs(cls, legs: list[OptionLeg]) -> "PositionGreeks":
        """מחשב יווניות מצרפיות מרשימת רגליים."""
        return cls(
            net_delta=sum(leg.net_delta for leg in legs),
            net_gamma=sum(leg.net_gamma for leg in legs),
            net_theta=sum(leg.net_theta for leg in legs),
            net_vega =sum(leg.net_vega  for leg in legs),
        )


# ---------------------------------------------------------------------------
# המלצת מרווח (2 רגליים)
# ---------------------------------------------------------------------------
@dataclass
class SpreadSignal:
    """
    המלצת מסחר מלאה לאסטרטגיית מרווח (Bull Put / Bear Call).

    זה האובייקט המרכזי שה-signal_generator מייצר ומעביר לדשבורד.

    Attributes:
        signal_id:          מזהה ייחודי
        strategy_type:      Bull Put / Bear Call
        generated_at:       זמן יצירת האות
        expiry:             פקיעת האופציות
        dte:                ימי מסחר לפקיעה
        short_leg:          הרגל הכתובה (מניבת הפרמיום)
        long_leg:           רגל הגידור (מגינה מהפסד בלתי מוגבל)
        position_greeks:    יווניות מצרפיות
        net_credit:         פרמיום נטו שנגבה (לאחר קניית הגידור)
        max_profit:         רווח מקסימלי (= net_credit − עמלות)
        max_loss:           הפסד מקסימלי (רוחב Spread − net_credit)
        required_margin:    ביטחון נדרש (= max_loss)
        breakeven:          מחיר נקודת האיזון
        risk_reward_ratio:  max_profit / max_loss
        roi_on_margin:      max_profit / required_margin
        pop:                Probability of Profit (0–1)
        iv_short:           IV של הרגל הכתובה
        iv_long:            IV של הרגל הגנובה
        iv_rank:            דירוג ה-IV הנוכחי ביחס לשנה (0–100)
        iv_environment:     HIGH / MODERATE / LOW
        signal_strength:    STRONG / MEDIUM / WEAK
        commission_total:   סך עמלות (2 רגליים × 2 סטרייקים)
        notes:              הערות טקסטואליות לדשבורד
    """
    # --- זהות ---
    signal_id:     str
    strategy_type: StrategyType
    generated_at:  datetime
    expiry:        date
    dte:           float            # ימי מסחר, עשרוני

    # --- רגליים ---
    short_leg: OptionLeg            # הרגל הכתובה
    long_leg:  OptionLeg            # רגל הגידור

    # --- יווניות ---
    position_greeks: PositionGreeks

    # --- פרופיל רווח/הפסד ---
    net_credit:         float       # פרמיום נטו שנגבה (נקודות)
    max_profit:         float       # ₪ (לאחר עמלות)
    max_loss:           float       # ₪ (תמיד חיובי)
    required_margin:    float       # ₪
    breakeven:          float       # נקודות מדד
    commission_total:   float       # ₪

    # --- מדדי איכות ---
    risk_reward_ratio:  float       # max_profit / max_loss
    roi_on_margin:      float       # max_profit / required_margin (%)
    pop:                float       # הסתברות לרווח (0.0 – 1.0)

    # --- IV ---
    iv_short:           float       # IV רגל כתובה
    iv_long:            float       # IV רגל גידור
    iv_rank:            float       # IV Rank שנתי (0–100)
    iv_environment:     IVEnvironment

    # --- ציון כולל ---
    signal_strength:    SignalStrength
    notes:              list[str] = field(default_factory=list)

    @property
    def spread_width(self) -> float:
        """רוחב המרווח = הפרש בין שני הסטרייקים."""
        return abs(self.short_leg.quote.strike - self.long_leg.quote.strike)

    @property
    def credit_pct_of_width(self) -> float:
        """
        אחוז הפרמיום מרוחב המרווח — מדד חשוב לאיכות ה-Spread.
        ערך גבוה = גביית פרמיום טובה יחסית לסיכון.
        מתחת ל-20% — בדרך כלל לא שווה כניסה.
        """
        if self.spread_width == 0:
            return 0.0
        return self.net_credit / self.spread_width

    def to_display_dict(self) -> dict:
        """
        ממיר לדיקשנרי נוח להצגה בדשבורד Streamlit.
        כל ערך מעוצב לקריאה אנושית.
        """
        return {
            "אסטרטגיה":          self.strategy_type.value,
            "DTE":               f"{self.dte:.1f}",
            "פקיעה":             self.expiry.isoformat(),
            "סטרייק כתיבה":      f"{self.short_leg.quote.strike:,.0f}",
            "סטרייק גידור":      f"{self.long_leg.quote.strike:,.0f}",
            "רוחב Spread":       f"{self.spread_width:,.0f}",
            "פרמיום נטו":        f"₪{self.net_credit:.2f}",
            "רווח מקסימלי":     f"₪{self.max_profit:,.0f}",
            "הפסד מקסימלי":     f"₪{self.max_loss:,.0f}",
            "Risk/Reward":       f"1:{1/self.risk_reward_ratio:.1f}" if self.risk_reward_ratio > 0 else "N/A",
            "ROI מרג'ין":        f"{self.roi_on_margin:.1%}",
            "POP":               f"{self.pop:.1%}",
            "Net Delta":         f"{self.position_greeks.net_delta:+.4f}",
            "Net Theta (₪/יום)": f"₪{self.position_greeks.net_theta:+.2f}",
            "Net Vega":          f"{self.position_greeks.net_vega:+.4f}",
            "IV כתיבה":         f"{self.iv_short:.1%}",
            "IV Rank":           f"{self.iv_rank:.0f}/100",
            "סביבת IV":         self.iv_environment.value,
            "עוצמת אות":        self.signal_strength.value,
            "נקודת איזון":       f"{self.breakeven:,.0f}",
            "עמלות":             f"₪{self.commission_total:.2f}",
        }


# ---------------------------------------------------------------------------
# המלצת Iron Condor (4 רגליים)
# ---------------------------------------------------------------------------
@dataclass
class IronCondorSignal:
    """
    המלצת Iron Condor = Bull Put Spread + Bear Call Spread.

    Iron Condor מרוויח כאשר השוק נשאר בטווח מוגדר.
    זו האסטרטגיה האידיאלית בסביבת IV גבוה + שוק צדדי.

    Attributes:
        signal_id:       מזהה ייחודי
        generated_at:    זמן יצירה
        put_spread:      ה-Bull Put Spread הפנימי
        call_spread:     ה-Bear Call Spread הפנימי
        position_greeks: יווניות מצרפיות של כל 4 הרגליים
        total_credit:    פרמיום כולל (Put + Call)
        max_profit:      ₪ (total_credit × מכפיל חוזה − עמלות)
        max_loss:        ₪ (רוחב Spread המקסימלי − total_credit)
        required_margin: ₪ (מרג'ין הנדרש ל-Iron Condor)
        lower_breakeven: נקודת איזון תחתונה
        upper_breakeven: נקודת איזון עליונה
        profit_zone_width: רוחב אזור הרווח בנקודות מדד
        risk_reward_ratio: יחס סיכוי/סיכון
        roi_on_margin:     ROI על הביטחון
        pop:               הסתברות לרווח
        iv_rank:           דירוג IV שנתי
        signal_strength:   עוצמת האות
    """
    signal_id:          str
    generated_at:       datetime
    put_spread:         SpreadSignal
    call_spread:        SpreadSignal
    position_greeks:    PositionGreeks
    total_credit:       float
    max_profit:         float
    max_loss:           float
    required_margin:    float
    lower_breakeven:    float
    upper_breakeven:    float
    profit_zone_width:  float
    risk_reward_ratio:  float
    roi_on_margin:      float
    pop:                float
    iv_rank:            float
    signal_strength:    SignalStrength
    notes:              list[str] = field(default_factory=list)

    @property
    def expiry(self) -> date:
        """תאריך פקיעה (זהה לשני ה-Spreads)."""
        return self.put_spread.expiry

    @property
    def dte(self) -> float:
        """DTE משותף."""
        return self.put_spread.dte
