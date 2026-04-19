"""
dashboard/run_with_example_data.py
==================================
סקריפט לבדיקה שטוען נתוני דוגמה ומפעיל את הדשבורד עם אותות חיים.

הפעלה:
    python dashboard/run_with_example_data.py

זה ישלח אל st.session_state את הנתונים, ואז קורא:
    streamlit run dashboard/app.py
"""

import asyncio
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# הוסף את תיקיית הרוט ל-path
sys.path.insert(0, str(Path(__file__).parent.parent))

from signals.models import OptionQuote, StrategyType
from signals.signal_generator import SignalGenerator, BankOfIsraelRateProvider, IVRankCalculator
from analytics.calendar_il import compute_dte


# ---------------------------------------------------------------------------
# יצירת שרשרת אופציות דוגמה (Mock Data)
# ---------------------------------------------------------------------------
def create_example_option_chain() -> list[OptionQuote]:
    """
    יוצר שרשרת אופציות דוגמה לתאריך פקיעה הקרוב.
    """
    expiry = date.today() + timedelta(days=20)  # 20 ימים קדימה
    underlying = 20_500.0

    chain = []

    # --- PUT options (Bull Put Spread candidates) ---
    put_strikes = [19_500, 19_750, 20_000, 20_250, 20_500, 20_750, 21_000]
    put_ivs = [0.24, 0.23, 0.22, 0.21, 0.20, 0.21, 0.22]  # Smile pattern

    for strike, base_iv in zip(put_strikes, put_ivs):
        # Bid-Ask spread סביר (בדרך כלל 1-3 נקודות עבור תיכנת כבדה)
        mid_price = (strike - underlying) * 0.02 + base_iv * underlying * 0.05
        bid = max(0.01, mid_price - 1.5)
        ask = mid_price + 1.5

        chain.append(OptionQuote(
            symbol=f"TA35P{strike}",
            option_type="PUT",
            strike=float(strike),
            expiry=expiry,
            bid=bid,
            ask=ask,
            last=(bid + ask) / 2,
            volume=max(50, 300 - abs(strike - underlying) * 0.05),
            open_interest=max(200, 1000 - abs(strike - underlying) * 0.3),
            iv=base_iv,
            timestamp=datetime.now(),
        ))

    # --- CALL options (Bear Call Spread candidates) ---
    call_strikes = [20_500, 20_750, 21_000, 21_250, 21_500, 21_750, 22_000]
    call_ivs = [0.22, 0.21, 0.20, 0.19, 0.20, 0.21, 0.22]  # Smile pattern

    for strike, base_iv in zip(call_strikes, call_ivs):
        mid_price = (strike - underlying) * 0.02 + base_iv * underlying * 0.05
        bid = max(0.01, mid_price - 1.5)
        ask = mid_price + 1.5

        chain.append(OptionQuote(
            symbol=f"TA35C{strike}",
            option_type="CALL",
            strike=float(strike),
            expiry=expiry,
            bid=bid,
            ask=ask,
            last=(bid + ask) / 2,
            volume=max(50, 300 - abs(strike - underlying) * 0.05),
            open_interest=max(200, 1000 - abs(strike - underlying) * 0.3),
            iv=base_iv,
            timestamp=datetime.now(),
        ))

    return chain


# ---------------------------------------------------------------------------
# פונקציה ראשית
# ---------------------------------------------------------------------------
async def generate_example_signals():
    """
    מייצרת אותות דוגמה באמצעות SignalGenerator.
    """
    print("🔄 טוען נתונים...")

    # יצור שרשרת דוגמה
    chain = create_example_option_chain()
    expiry = chain[0].expiry
    underlying_price = 20_500.0

    print(f"✅ יצרנו שרשרת עם {len(chain)} אופציות | פקיעה: {expiry}")

    # יצור מופע generator
    provider = BankOfIsraelRateProvider(
        _rate=0.045,  # 4.5% ריבית
        _last_updated=datetime.now(),
    )
    iv_rank_calc = IVRankCalculator(
        iv_52w_high=0.35,
        iv_52w_low=0.12,
    )

    generator = SignalGenerator(
        rate_provider=provider,
        iv_rank_calc=iv_rank_calc,
        commission=8.0,
        multiplier=100.0,
    )

    print("🧮 מחשב אותות...")

    # יצור Bull Put Signals
    bull_puts = await generator.generate_bull_put_signals(
        chain=chain,
        underlying_price=underlying_price,
        expiry=expiry,
        quantity=1,
        now=datetime.now(),
    )
    print(f"✅ Bull Put Spreads: {len(bull_puts)} אותות")

    # יצור Bear Call Signals
    bear_calls = await generator.generate_bear_call_signals(
        chain=chain,
        underlying_price=underlying_price,
        expiry=expiry,
        quantity=1,
        now=datetime.now(),
    )
    print(f"✅ Bear Call Spreads: {len(bear_calls)} אותות")

    # חבר הכל
    all_signals = bull_puts + bear_calls

    # מיין לפי עוצמה ו-ROI
    all_signals.sort(
        key=lambda s: (s.signal_strength.name, -s.roi_on_margin)
    )

    print(f"✅ סך הכל: {len(all_signals)} אותות מעבר לסינונים")

    return all_signals, underlying_price


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    """
    טוען נתונים דוגמה ומהדפיס דוח.
    """
    print("\n" + "=" * 70)
    print("  📊 דוגמה לדשבורד Streamlit — הצגת אותות סופר-מדויקים")
    print("=" * 70 + "\n")

    signals, underlying = await generate_example_signals()

    if signals:
        print("\n" + "🎯 הזדמנויות חמות:".center(70))
        print("-" * 70)

        for i, sig in enumerate(signals[:5], 1):  # הצג חמישה הראשונים
            print(f"\n#{i} {sig.strategy_type.value} | {sig.signal_strength.value}")
            print(f"   סטרייקים: {sig.short_leg.quote.strike:,.0f} / {sig.long_leg.quote.strike:,.0f}")
            print(f"   פרמיום כניסה: ₪{sig.net_credit:.2f}")
            print(f"   רווח מקסימלי: ₪{sig.max_profit:,.0f}")
            print(f"   ROI/מרג'ין: {sig.roi_on_margin:.1%}")
            print(f"   POP: {sig.pop:.1%}")

    else:
        print("❌ לא נמצאו אותות המעברים את הסינונים")

    print("\n" + "=" * 70)
    print("  הפעלת דשבורד Streamlit...")
    print("=" * 70)
    print("\nהרץ את הפקודה הבאה:")
    print("    streamlit run dashboard/app.py\n")

    # שמור נתונים ל-Session State דרך Streamlit
    # (זה דורך session state של Streamlit וחייב לקרות מקוד Streamlit)
    print("💡 כדי לראות את הדשבורד עם נתונים אלה, בדשבורד יש ללחוץ:")
    print("   📊 'עדכן אותות' בתפריט הצד")


if __name__ == "__main__":
    asyncio.run(main())
