"""
signals/signal_generator.py
============================
מנוע יצירת האותות — המוח האנליטי של המערכת.

תפקידו:
  1. מקבל שרשרת אופציות (Options Chain) + נתוני שוק
  2. מחשב IV לכל סטרייק (Volatility Smile) בנפרד
  3. מחפש צירופי Spread / Iron Condor שעומדים בכל הסננים
  4. מחשב לכל מועמד: RR, ROI, POP, Greeks מצרפיים
  5. מדרג לפי SignalStrength ומחזיר רשימת המלצות

עקרון מחיר ברזל:
  כל חישוב עלות / הכנסה = Bid/Ask בלבד, לעולם לא Mid.
  עמלות נוכות לפני חישוב Max Profit.

ריבית חסרת סיכון:
  שואבת מבנק ישראל (באמצעות קריאה חיצונית ב-BankOfIsraelRateProvider).
  ברירת מחדל: 4.5% (ריבית נכון לאמצע 2024).
"""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Optional

from analytics.black_scholes import (
    OptionGreeks,
    compute_greeks,
    solve_iv,
)
from analytics.calendar_il import compute_dte, dte_to_years
from signals.models import (
    IVEnvironment,
    IronCondorSignal,
    OptionGreeksSnapshot,
    OptionLeg,
    OptionQuote,
    PositionGreeks,
    SignalStrength,
    SpreadSignal,
    StrategyType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# קבועי תצורה — בפרויקט מלא יגיעו מ-config.py
# ---------------------------------------------------------------------------
# ריבית חסרת סיכון ברירת מחדל (בנק ישראל, שנתית עשרונית)
DEFAULT_RISK_FREE_RATE: float = 0.045      # 4.5%

# עמלת קנייה/מכירה לחוזה — ₪ (יש לעדכן לפי הברוקר)
COMMISSION_PER_LEG: float = 8.0            # ₪8 לחוזה לכל רגל

# מכפיל חוזה (כמה ₪ שווה נקודת מדד אחת בחוזה ת"א 35)
CONTRACT_MULTIPLIER: float = 100.0         # ₪100 לנקודה

# --- סף DTE ---
MIN_DTE: float = 7.0    # לא נכנס לאופציות עם פחות מ-7 ימי מסחר
MAX_DTE: float = 45.0   # לא נכנס לאופציות עם יותר מ-45 ימי מסחר

# --- סף איכות אות ---
MIN_CREDIT_PCT_OF_WIDTH: float = 0.20      # פרמיום ≥ 20% מרוחב ה-Spread
MIN_POP:                 float = 0.60      # הסתברות ≥ 60% לרווח
MIN_ROI_ON_MARGIN:       float = 0.03      # ROI ≥ 3% על הביטחון

# --- סף IV ---
IV_RANK_HIGH_THRESHOLD:  float = 50.0      # IV Rank > 50 = סביבת IV גבוהה
IV_RANK_MOD_THRESHOLD:   float = 25.0      # IV Rank > 25 = סביבת IV בינונית

# --- סף Liquidity ---
MIN_OPEN_INTEREST: int   = 100             # לפחות 100 חוזים פתוחים
MIN_VOLUME:        int   = 10              # לפחות 10 עסקאות ביום
MAX_BID_ASK_PCT:   float = 0.25           # Bid-Ask Spread ≤ 25% מה-Mid


# ---------------------------------------------------------------------------
# ספק ריבית בנק ישראל (Stub — בפרויקט אמיתי: HTTP ל-BOI API)
# ---------------------------------------------------------------------------
@dataclass
class BankOfIsraelRateProvider:
    """
    מספק ריבית חסרת סיכון עדכנית מבנק ישראל.

    בפרויקט אמיתי: קורא ל-API של בנק ישראל:
    https://www.boi.org.il/roles/monetarypolicy/interestrate/

    כרגע: מחזיר ערך קשוע עם אפשרות לעדכון ידני.
    """
    _rate: float = DEFAULT_RISK_FREE_RATE
    _last_updated: Optional[datetime] = None

    @property
    def rate(self) -> float:
        """ריבית שנתית עשרונית (0.045 = 4.5%)."""
        return self._rate

    def update(self, new_rate: float) -> None:
        """מעדכן את הריבית ידנית (נקרא לאחר fetch מהאינטרנט)."""
        logger.info("ריבית בנק ישראל עודכנה: %.2f%% → %.2f%%",
                    self._rate * 100, new_rate * 100)
        self._rate = new_rate
        self._last_updated = datetime.utcnow()

    async def fetch_from_boi(self) -> float:
        """
        Stub: בעתיד יבצע HTTP GET ל-API של בנק ישראל.
        כרגע מחזיר את הריבית הקשועה.
        """
        # TODO: החלף ב-aiohttp.get("https://api.boi.org.il/...")
        return self._rate


# ---------------------------------------------------------------------------
# מנגנון IV Rank / Percentile (Volatility Regime)
# ---------------------------------------------------------------------------
@dataclass
class IVRankCalculator:
    """
    מחשב IV Rank ו-IV Percentile לאופציות ת"א 35.

    IV Rank = (IV_current - IV_52w_low) / (IV_52w_high - IV_52w_low) × 100

    ערך גבוה (>50) = IV גבוה ביחס לשנה האחרונה = זמן טוב לכתיבה.
    ערך נמוך (<25) = IV נמוך = פרמיום זול = לא אידיאלי לכתיבה.

    בפרויקט אמיתי: הערכים יגיעו מ-DB היסטורי.
    """
    iv_52w_high: float = 0.35    # IV מקסימלי בשנה האחרונה (35%)
    iv_52w_low:  float = 0.12    # IV מינימלי בשנה האחרונה (12%)

    def rank(self, current_iv: float) -> float:
        """
        מחזיר IV Rank בין 0 ל-100.

        Args:
            current_iv: ה-ATM IV הנוכחי (עשרוני)

        Returns:
            ציון 0–100
        """
        denom = self.iv_52w_high - self.iv_52w_low
        if denom == 0:
            return 50.0
        rank = (current_iv - self.iv_52w_low) / denom * 100
        return max(0.0, min(100.0, rank))

    def environment(self, rank: float) -> IVEnvironment:
        """ממיר IV Rank לקטגוריה."""
        if rank >= IV_RANK_HIGH_THRESHOLD:
            return IVEnvironment.HIGH
        elif rank >= IV_RANK_MOD_THRESHOLD:
            return IVEnvironment.MODERATE
        else:
            return IVEnvironment.LOW


# ---------------------------------------------------------------------------
# חישוב POP — Probability of Profit
# ---------------------------------------------------------------------------
def compute_pop(
    S:           float,
    breakeven:   float,
    T:           float,
    r:           float,
    sigma:       float,
    direction:   Literal["ABOVE", "BELOW"],
) -> float:
    """
    מחשב הסתברות סטטיסטית לרווח (POP) לאסטרטגיית מרווח.

    השיטה: מנוע BS נותן N(d2) = הסתברות ש-S_T > K בפקיעה.
    אנחנו מנצלים את זה ישירות:

    Bull Put Spread מרוויח אם S_expiry > breakeven:
      POP = N(d2) עם K = breakeven

    Bear Call Spread מרוויח אם S_expiry < breakeven:
      POP = N(-d2) עם K = breakeven

    Args:
        S:          מחיר בסיס נוכחי
        breakeven:  נקודת האיזון של האסטרטגיה
        T:          זמן לפקיעה בשנים
        r:          ריבית
        sigma:      תנודתיות (ATM IV)
        direction:  ABOVE = מרוויחים אם S_expiry > breakeven
                    BELOW = מרוויחים אם S_expiry < breakeven

    Returns:
        הסתברות לרווח (0.0 – 1.0)
    """
    if T <= 0 or sigma <= 0:
        return 0.0

    sqrt_T = math.sqrt(T)
    # d2 מחושב עם K = breakeven
    try:
        ln_ratio = math.log(S / breakeven)
        d2 = (ln_ratio + (r - 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    except (ValueError, ZeroDivisionError):
        return 0.5

    # N(d2) = הסתברות ש-S_T > breakeven
    prob_above = 0.5 * (1.0 + math.erf(d2 / math.sqrt(2)))

    return prob_above if direction == "ABOVE" else 1.0 - prob_above


# ---------------------------------------------------------------------------
# מנוע האותות הראשי
# ---------------------------------------------------------------------------
class SignalGenerator:
    """
    המנוע האנליטי — בוחן שרשרת אופציות ומייצר המלצות מדויקות.

    שימוש:
        generator = SignalGenerator()
        signals = await generator.generate_bull_put_signals(
            chain=options_chain,
            underlying_price=2050.0,
            expiry=date(2025, 1, 31),
        )
    """

    def __init__(
        self,
        rate_provider:   Optional[BankOfIsraelRateProvider] = None,
        iv_rank_calc:    Optional[IVRankCalculator]         = None,
        commission:      float = COMMISSION_PER_LEG,
        multiplier:      float = CONTRACT_MULTIPLIER,
    ) -> None:
        """
        Args:
            rate_provider: ספק ריבית בנק ישראל (None = ברירת מחדל)
            iv_rank_calc:  מחשב IV Rank (None = ברירת מחדל)
            commission:    עמלה לרגל לחוזה בשקלים
            multiplier:    מכפיל חוזה (₪ לנקודה)
        """
        self._rates     = rate_provider or BankOfIsraelRateProvider()
        self._iv_rank   = iv_rank_calc  or IVRankCalculator()
        self._commission = commission
        self._multiplier = multiplier

    # ------------------------------------------------------------------
    # API ציבורי
    # ------------------------------------------------------------------
    async def generate_bull_put_signals(
        self,
        chain:             list[OptionQuote],
        underlying_price:  float,
        expiry:            date,
        quantity:          int    = 1,
        now:               Optional[datetime] = None,
    ) -> list[SpreadSignal]:
        """
        מייצר המלצות Bull Put Spread מהשרשרת.

        Bull Put Spread = כתיבת PUT בסטרייק גבוה + קניית PUT בסטרייק נמוך.
        מרוויח אם השוק עולה, צדדי, או יורד מעט.

        Args:
            chain:            רשימת OptionQuote — כל האופציות לפקיעה זו
            underlying_price: מחיר ת"א 35 הנוכחי
            expiry:           תאריך הפקיעה
            quantity:         כמות חוזים לכל רגל
            now:              זמן נוכחי (None = datetime.now())

        Returns:
            רשימת SpreadSignal ממוינת לפי SignalStrength + ROI
        """
        now = now or datetime.now()
        r   = self._rates.rate

        # חשב DTE
        dte = compute_dte(now, expiry)
        if not (MIN_DTE <= dte <= MAX_DTE):
            logger.info("DTE=%.1f מחוץ לטווח [%d,%d] — מדלג | expiry=%s",
                        dte, MIN_DTE, MAX_DTE, expiry)
            return []

        T = dte_to_years(dte)

        # סנן רק PUT-ים
        puts = [q for q in chain if q.option_type == "PUT" and q.expiry == expiry]

        # חשב IV לכל סטרייק (Volatility Smile)
        quote_with_iv = await self._enrich_with_iv(puts, underlying_price, T, r)

        # חשב ATM IV לצורכי POP ו-IV Rank
        atm_iv   = self._get_atm_iv(quote_with_iv, underlying_price)
        iv_rank  = self._iv_rank.rank(atm_iv)
        iv_env   = self._iv_rank.environment(iv_rank)

        # בנה את כל צירופי ה-Spread האפשריים
        signals: list[SpreadSignal] = []
        for short_quote, short_iv in quote_with_iv:
            for long_quote, long_iv in quote_with_iv:
                # Bull Put Spread: short בסטרייק גבוה, long בסטרייק נמוך
                if long_quote.strike >= short_quote.strike:
                    continue

                signal = self._build_spread_signal(
                    strategy_type=StrategyType.BULL_PUT_SPREAD,
                    short_quote=short_quote,
                    long_quote=long_quote,
                    short_iv=short_iv,
                    long_iv=long_iv,
                    underlying_price=underlying_price,
                    T=T,
                    r=r,
                    dte=dte,
                    expiry=expiry,
                    quantity=quantity,
                    iv_rank=iv_rank,
                    iv_env=iv_env,
                )
                if signal is not None:
                    signals.append(signal)

        # מיין: STRONG קודם, אחר כך לפי ROI יורד
        signals.sort(
            key=lambda s: (s.signal_strength.name, -s.roi_on_margin)
        )
        logger.info("Bull Put Signals: נמצאו %d המלצות | expiry=%s | DTE=%.1f",
                    len(signals), expiry, dte)
        return signals

    async def generate_iron_condor_signals(
        self,
        chain:            list[OptionQuote],
        underlying_price: float,
        expiry:           date,
        quantity:         int   = 1,
        now:              Optional[datetime] = None,
    ) -> list[IronCondorSignal]:
        """
        מייצר המלצות Iron Condor מהשרשרת.

        Iron Condor = Bull Put Spread + Bear Call Spread (4 רגליים).
        מרוויח כאשר השוק נשאר בטווח מוגדר עד לפקיעה.

        Args:
            chain:            שרשרת מלאה (CALL + PUT)
            underlying_price: מחיר בסיס נוכחי
            expiry:           תאריך פקיעה
            quantity:         כמות חוזים
            now:              זמן נוכחי

        Returns:
            רשימת IronCondorSignal ממוינת
        """
        now = now or datetime.now()

        # יצור Bull Put Signals
        put_signals = await self.generate_bull_put_signals(
            chain=chain,
            underlying_price=underlying_price,
            expiry=expiry,
            quantity=quantity,
            now=now,
        )

        # יצור Bear Call Signals
        call_signals = await self.generate_bear_call_signals(
            chain=chain,
            underlying_price=underlying_price,
            expiry=expiry,
            quantity=quantity,
            now=now,
        )

        # חבר צמדים של Put + Call לאיירון קונדור
        condors: list[IronCondorSignal] = []
        for put_sig in put_signals:
            for call_sig in call_signals:
                condor = self._build_iron_condor(put_sig, call_sig, underlying_price)
                if condor is not None:
                    condors.append(condor)

        condors.sort(key=lambda c: (c.signal_strength.name, -c.roi_on_margin))
        logger.info("Iron Condor Signals: נמצאו %d המלצות | expiry=%s",
                    len(condors), expiry)
        return condors

    async def generate_bear_call_signals(
        self,
        chain:            list[OptionQuote],
        underlying_price: float,
        expiry:           date,
        quantity:         int   = 1,
        now:              Optional[datetime] = None,
    ) -> list[SpreadSignal]:
        """
        מייצר המלצות Bear Call Spread.

        Bear Call Spread = כתיבת CALL בסטרייק נמוך + קניית CALL בסטרייק גבוה.
        מרוויח אם השוק יורד, צדדי, או עולה מעט.
        """
        now = now or datetime.now()
        r   = self._rates.rate
        dte = compute_dte(now, expiry)

        if not (MIN_DTE <= dte <= MAX_DTE):
            return []

        T     = dte_to_years(dte)
        calls = [q for q in chain if q.option_type == "CALL" and q.expiry == expiry]
        quote_with_iv = await self._enrich_with_iv(calls, underlying_price, T, r)

        atm_iv  = self._get_atm_iv(quote_with_iv, underlying_price)
        iv_rank = self._iv_rank.rank(atm_iv)
        iv_env  = self._iv_rank.environment(iv_rank)

        signals: list[SpreadSignal] = []
        for short_quote, short_iv in quote_with_iv:
            for long_quote, long_iv in quote_with_iv:
                # Bear Call Spread: short בסטרייק נמוך, long בסטרייק גבוה
                if long_quote.strike <= short_quote.strike:
                    continue

                signal = self._build_spread_signal(
                    strategy_type=StrategyType.BEAR_CALL_SPREAD,
                    short_quote=short_quote,
                    long_quote=long_quote,
                    short_iv=short_iv,
                    long_iv=long_iv,
                    underlying_price=underlying_price,
                    T=T,
                    r=r,
                    dte=dte,
                    expiry=expiry,
                    quantity=quantity,
                    iv_rank=iv_rank,
                    iv_env=iv_env,
                )
                if signal is not None:
                    signals.append(signal)

        signals.sort(key=lambda s: (s.signal_strength.name, -s.roi_on_margin))
        return signals

    # ------------------------------------------------------------------
    # לוגיקת בניית אות — הלב המתמטי
    # ------------------------------------------------------------------
    def _build_spread_signal(
        self,
        strategy_type:    StrategyType,
        short_quote:      OptionQuote,
        long_quote:       OptionQuote,
        short_iv:         float,
        long_iv:          float,
        underlying_price: float,
        T:                float,
        r:                float,
        dte:              float,
        expiry:           date,
        quantity:         int,
        iv_rank:          float,
        iv_env:           IVEnvironment,
    ) -> Optional[SpreadSignal]:
        """
        בונה SpreadSignal אחד לצמד short/long.
        מחזיר None אם הצמד לא עומד בכל הסננים.
        """
        # --- סנן 1: נזילות ---
        if not self._passes_liquidity_filter(short_quote):
            return None
        if not self._passes_liquidity_filter(long_quote):
            return None

        # --- חשב יווניות עם ה-IV הספציפי לכל סטרייק (Smile!) ---
        try:
            short_greeks_raw = compute_greeks(
                underlying_price, short_quote.strike, T, r, short_iv, short_quote.option_type
            )
            long_greeks_raw  = compute_greeks(
                underlying_price, long_quote.strike,  T, r, long_iv,  long_quote.option_type
            )
        except (ValueError, ZeroDivisionError) as e:
            logger.debug("שגיאה בחישוב Greeks: %s", e)
            return None

        # --- בנה רגליים עם מחירי Bid/Ask (לעולם לא Mid!) ---
        short_leg = OptionLeg(
            quote=short_quote,
            greeks=_to_snapshot(short_greeks_raw, short_iv),
            action="SELL",
            quantity=quantity,
        )
        long_leg = OptionLeg(
            quote=long_quote,
            greeks=_to_snapshot(long_greeks_raw, long_iv),
            action="BUY",
            quantity=quantity,
        )

        # --- חשב פרמיום נטו ---
        # כתיבה (SELL): מקבלים Bid
        # קנייה (BUY): משלמים Ask
        # net_credit חיובי = קיבלנו יותר ממה ששילמנו
        net_credit = (short_quote.bid - long_quote.ask) * quantity
        if net_credit <= 0:
            # אין תועלת — ה-Spread עולה לנו כסף
            return None

        # --- חשב רוחב ה-Spread ---
        spread_width = abs(short_quote.strike - long_quote.strike)

        # --- סנן 2: פרמיום מינימלי ---
        if (net_credit / spread_width) < MIN_CREDIT_PCT_OF_WIDTH:
            return None

        # --- חישוב P&L בשקלים עם עמלות ---
        # כל רגל: 2 עסקאות (כניסה + יציאה אפשרית) × quantity חוזים
        commission_total = self._commission * 2 * quantity * 2  # 2 רגליים

        max_profit_pts  = net_credit                            # נקודות מדד
        max_profit_ils  = max_profit_pts * self._multiplier - commission_total
        max_loss_pts    = spread_width - net_credit
        max_loss_ils    = max_loss_pts * self._multiplier + commission_total
        required_margin = max_loss_ils                          # ₪

        if max_profit_ils <= 0 or max_loss_ils <= 0:
            return None

        # --- חישוב נקודת איזון (Breakeven) ---
        if strategy_type == StrategyType.BULL_PUT_SPREAD:
            # Breakeven = short strike − net credit
            breakeven = short_quote.strike - net_credit
            pop_direction: Literal["ABOVE", "BELOW"] = "ABOVE"
        else:  # BEAR_CALL_SPREAD
            # Breakeven = short strike + net credit
            breakeven = short_quote.strike + net_credit
            pop_direction = "BELOW"

        # --- חישוב POP ---
        pop = compute_pop(
            S=underlying_price,
            breakeven=breakeven,
            T=T,
            r=r,
            sigma=short_iv,   # IV של הרגל הקרובה לכסף
            direction=pop_direction,
        )

        # --- סנן 3: POP מינימלי ---
        if pop < MIN_POP:
            return None

        # --- יחס Risk/Reward ו-ROI ---
        rr_ratio      = max_profit_ils / max_loss_ils
        roi_on_margin = max_profit_ils / required_margin

        # --- סנן 4: ROI מינימלי ---
        if roi_on_margin < MIN_ROI_ON_MARGIN:
            return None

        # --- יווניות מצרפיות ---
        position_greeks = PositionGreeks.from_legs([short_leg, long_leg])

        # --- קביעת עוצמת אות ---
        strength = self._classify_strength(rr_ratio, pop, iv_rank)

        # --- הערות אוטומטיות ---
        notes = self._generate_notes(
            short_quote, long_quote, net_credit, spread_width,
            pop, iv_rank, iv_env, position_greeks, dte
        )

        return SpreadSignal(
            signal_id=str(uuid.uuid4())[:8],
            strategy_type=strategy_type,
            generated_at=datetime.utcnow(),
            expiry=expiry,
            dte=dte,
            short_leg=short_leg,
            long_leg=long_leg,
            position_greeks=position_greeks,
            net_credit=net_credit,
            max_profit=max_profit_ils,
            max_loss=max_loss_ils,
            required_margin=required_margin,
            breakeven=breakeven,
            commission_total=commission_total,
            risk_reward_ratio=rr_ratio,
            roi_on_margin=roi_on_margin,
            pop=pop,
            iv_short=short_iv,
            iv_long=long_iv,
            iv_rank=iv_rank,
            iv_environment=iv_env,
            signal_strength=strength,
            notes=notes,
        )

    def _build_iron_condor(
        self,
        put_spread:       SpreadSignal,
        call_spread:      SpreadSignal,
        underlying_price: float,
    ) -> Optional[IronCondorSignal]:
        """
        משלב Bull Put Spread + Bear Call Spread ל-Iron Condor.

        תנאי: Call spread חייב להיות מעל מחיר הבסיס,
              Put spread חייב להיות מתחת.
        """
        # וולידציה: הסטרייקים לא חופפים
        put_short_strike  = put_spread.short_leg.quote.strike
        call_short_strike = call_spread.short_leg.quote.strike

        if call_short_strike <= put_short_strike:
            return None   # הסטרייקים חופפים — Iron Condor לא תקין

        # חשב ביטחון נדרש: נלקח ה-Spread הגדול יותר (לא שניהם!)
        # כי רק אחד יכול להפסיד בפקיעה
        required_margin = max(put_spread.required_margin, call_spread.required_margin)

        # פרמיום כולל
        total_credit = put_spread.net_credit + call_spread.net_credit
        commission_total = put_spread.commission_total + call_spread.commission_total

        # P&L
        max_profit = total_credit * self._multiplier - commission_total
        max_loss   = max(
            put_spread.max_loss_pts if hasattr(put_spread, 'max_loss_pts')
            else put_spread.spread_width - put_spread.net_credit,
            call_spread.spread_width - call_spread.net_credit
        ) * self._multiplier + commission_total

        if max_profit <= 0:
            return None

        # נקודות איזון
        lower_be = put_spread.breakeven
        upper_be = call_spread.breakeven
        profit_zone_width = upper_be - lower_be

        if profit_zone_width <= 0:
            return None

        # יחסי איכות
        rr_ratio      = max_profit / max_loss if max_loss > 0 else 0
        roi_on_margin = max_profit / required_margin if required_margin > 0 else 0

        # POP של Iron Condor ≈ POP_put × POP_call (עצמאות קירובית)
        pop = put_spread.pop * call_spread.pop

        if pop < MIN_POP:
            return None

        # יווניות מצרפיות (4 רגליים)
        all_legs = [
            put_spread.short_leg,  put_spread.long_leg,
            call_spread.short_leg, call_spread.long_leg,
        ]
        position_greeks = PositionGreeks.from_legs(all_legs)

        # עוצמת אות
        iv_rank  = (put_spread.iv_rank + call_spread.iv_rank) / 2
        strength = self._classify_strength(rr_ratio, pop, iv_rank)

        notes = [
            f"אזור רווח: {lower_be:,.0f} – {upper_be:,.0f} נקודות ({profit_zone_width:,.0f} רוחב)",
            f"Net Theta: ₪{position_greeks.net_theta:+.2f}/יום",
            f"IV Rank: {iv_rank:.0f}/100 — {put_spread.iv_environment.value}",
        ]

        return IronCondorSignal(
            signal_id=str(uuid.uuid4())[:8],
            generated_at=datetime.utcnow(),
            put_spread=put_spread,
            call_spread=call_spread,
            position_greeks=position_greeks,
            total_credit=total_credit,
            max_profit=max_profit,
            max_loss=max_loss,
            required_margin=required_margin,
            lower_breakeven=lower_be,
            upper_breakeven=upper_be,
            profit_zone_width=profit_zone_width,
            risk_reward_ratio=rr_ratio,
            roi_on_margin=roi_on_margin,
            pop=pop,
            iv_rank=iv_rank,
            signal_strength=strength,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # פונקציות עזר
    # ------------------------------------------------------------------
    async def _enrich_with_iv(
        self,
        quotes:           list[OptionQuote],
        underlying_price: float,
        T:                float,
        r:                float,
    ) -> list[tuple[OptionQuote, float]]:
        """
        מחשב IV לכל ציטוט בנפרד — יוצר את ה-Volatility Smile.

        משתמש ב-Mid לחישוב IV בלבד (לא לתמחור!) כי IV הוא מדד תיאורטי.
        תמחור בפועל → תמיד Bid/Ask.

        Returns:
            רשימת (OptionQuote, IV) לכל ציטוט שהצליח
        """
        result: list[tuple[OptionQuote, float]] = []

        for q in quotes:
            # השתמש ב-Mid לחישוב IV (תיאורטי בלבד!)
            iv = solve_iv(
                market_price=q.mid,
                S=underlying_price,
                K=q.strike,
                T=T,
                r=r,
                option_type=q.option_type,
            )

            if iv is not None and 0.01 < iv < 5.0:
                # עדכן את האובייקט עם ה-IV שחושב
                enriched = OptionQuote(
                    symbol=q.symbol,
                    option_type=q.option_type,
                    strike=q.strike,
                    expiry=q.expiry,
                    bid=q.bid,
                    ask=q.ask,
                    last=q.last,
                    volume=q.volume,
                    open_interest=q.open_interest,
                    iv=iv,
                    timestamp=q.timestamp,
                )
                result.append((enriched, iv))
            else:
                logger.debug(
                    "IV לא הצליח | symbol=%s strike=%.0f mid=%.4f",
                    q.symbol, q.strike, q.mid
                )

        return result

    @staticmethod
    def _get_atm_iv(quote_with_iv: list[tuple[OptionQuote, float]], spot: float) -> float:
        """
        מוצא את ה-ATM IV (אופציה הקרובה ביותר ל-ATM).
        משמש לחישוב POP ו-IV Rank.
        """
        if not quote_with_iv:
            return DEFAULT_RISK_FREE_RATE  # ברירת מחדל חירום

        # מצא את הסטרייק הקרוב ביותר ל-Spot
        closest = min(quote_with_iv, key=lambda x: abs(x[0].strike - spot))
        return closest[1]

    @staticmethod
    def _passes_liquidity_filter(quote: OptionQuote) -> bool:
        """
        בודק שהאופציה נזילה מספיק לכניסה בתנאים סבירים.

        קריטריונים:
          1. Open Interest ≥ MIN_OPEN_INTEREST
          2. Volume ≥ MIN_VOLUME
          3. Bid-Ask Spread ≤ MAX_BID_ASK_PCT
          4. Bid > 0 (חייב להיות מחיר קונה)
        """
        if quote.open_interest < MIN_OPEN_INTEREST:
            return False
        if quote.volume < MIN_VOLUME:
            return False
        if quote.bid <= 0:
            return False
        if quote.spread_pct > MAX_BID_ASK_PCT:
            return False
        return True

    @staticmethod
    def _classify_strength(
        rr_ratio: float,
        pop:      float,
        iv_rank:  float,
    ) -> SignalStrength:
        """
        מסווג את עוצמת האות לפי שלושה מדדים.

        STRONG: RR > 30% + POP > 70% + IV Rank > 40
        MEDIUM: RR > 20% + POP > 65%
        WEAK:   כל השאר

        Args:
            rr_ratio: max_profit / max_loss
            pop:      הסתברות רווח (0–1)
            iv_rank:  דירוג IV (0–100)
        """
        if rr_ratio >= 0.30 and pop >= 0.70 and iv_rank >= 40:
            return SignalStrength.STRONG
        elif rr_ratio >= 0.20 and pop >= 0.65:
            return SignalStrength.MEDIUM
        else:
            return SignalStrength.WEAK

    @staticmethod
    def _generate_notes(
        short_quote:      OptionQuote,
        long_quote:       OptionQuote,
        net_credit:       float,
        spread_width:     float,
        pop:              float,
        iv_rank:          float,
        iv_env:           IVEnvironment,
        greeks:           PositionGreeks,
        dte:              float,
    ) -> list[str]:
        """
        מייצר הערות טקסטואליות אוטומטיות לדשבורד.
        כל הערה מדגישה נקודה חשובה שהמשתמש צריך לדעת.
        """
        notes = []

        # הערת פרמיום
        credit_pct = net_credit / spread_width * 100
        notes.append(f"גביית {credit_pct:.1f}% מרוחב ה-Spread")

        # הערת Theta
        if greeks.net_theta > 0:
            notes.append(f"Theta חיובי: ₪{greeks.net_theta:+.2f}/יום מסחר")
        else:
            notes.append(f"⚠️ Theta שלילי: ₪{greeks.net_theta:+.2f}/יום")

        # הערת DTE
        if dte < 14:
            notes.append(f"⚠️ DTE נמוך ({dte:.0f} ימים) — Gamma Risk גבוה")
        elif dte > 35:
            notes.append(f"DTE ארוך ({dte:.0f} ימים) — שקול צמצום DTE")

        # הערת IV
        if iv_env == IVEnvironment.HIGH:
            notes.append(f"✅ IV Rank {iv_rank:.0f}/100 — סביבה טובה לכתיבה")
        elif iv_env == IVEnvironment.LOW:
            notes.append(f"⚠️ IV Rank {iv_rank:.0f}/100 — פרמיום נמוך יחסית")

        # הערת נזילות
        if short_quote.spread_pct > 0.15:
            notes.append(
                f"⚠️ Bid-Ask רחב בכתיבה ({short_quote.spread_pct:.0%}) — "
                f"שקול Limit Order"
            )

        return notes


# ---------------------------------------------------------------------------
# פונקציית עזר — המרת OptionGreeks ל-OptionGreeksSnapshot
# ---------------------------------------------------------------------------
def _to_snapshot(g: OptionGreeks, iv: float) -> OptionGreeksSnapshot:
    """ממיר OptionGreeks (מהמחשבן) ל-OptionGreeksSnapshot (ל-models)."""
    return OptionGreeksSnapshot(
        delta=g.delta,
        gamma=g.gamma,
        theta=g.theta,
        vega=g.vega,
        rho=g.rho,
        iv=iv,
    )
