"""
dashboard/app.py
================
דשבורד Streamlit מקצועי — ממשק ייעוץ אופציות בזמן אמת.

ארכיטקטורה:
  - עמוד ראשי (Home): Market Overview + Signals Table
  - עמוד Payoff Diagram: גרף Risk/Reward אינטראקטיבי
  - עמוד Analysis: Volatility Smile + Greeks Panel

הפעלה:
    streamlit run dashboard/app.py

תלויות:
    pip install streamlit plotly pandas numpy scipy
"""

import asyncio
import logging
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Literal
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from dataclasses import asdict

# הוסף את תיקיית הרוט ל-path כדי ליבוא מודולים
sys.path.insert(0, str(Path(__file__).parent.parent))

# ייבוא מודלים ומנוע האותות
from signals.models import (
    SpreadSignal, IronCondorSignal, SignalStrength, StrategyType,
    OptionQuote,
)
from signals.signal_generator import SignalGenerator, BankOfIsraelRateProvider, IVRankCalculator
from analytics.calendar_il import compute_dte
from analytics.black_scholes import bs_price

# הגדרת logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# פונקציות עזר — טעינת נתונים עם Caching
# ---------------------------------------------------------------------------

@st.cache_resource
def get_signal_generator() -> SignalGenerator:
    """
    יוצר מופע SignalGenerator יחיד וקשוח בזיכרון.
    זה מהיר משמעותית מאשר יצירה חדשה בכל refresh.
    """
    provider = BankOfIsraelRateProvider(_rate=0.045)
    iv_rank_calc = IVRankCalculator(iv_52w_high=0.35, iv_52w_low=0.12)
    return SignalGenerator(
        rate_provider=provider,
        iv_rank_calc=iv_rank_calc,
        commission=8.0,
        multiplier=100.0,
    )


@st.cache_data(ttl=300)  # Cache 5 דקות
def generate_example_chain() -> tuple[list[OptionQuote], float, date]:
    """
    יוצר שרשרת אופציות דוגמה עם נתונים סבירים.
    זה מחזיר חוקי אם לא משתנים נתוני שוק (עד 5 דקות).
    """
    underlying = 20_500.0
    expiry = date.today() + timedelta(days=20)

    chain = []

    # PUT options
    put_strikes = [19_500, 19_750, 20_000, 20_250, 20_500, 20_750, 21_000]
    put_ivs = [0.24, 0.23, 0.22, 0.21, 0.20, 0.21, 0.22]

    for strike, base_iv in zip(put_strikes, put_ivs):
        mid_price = max(0.1, (strike - underlying) * 0.02 + base_iv * underlying * 0.05)
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
            volume=max(50, int(300 - abs(strike - underlying) * 0.05)),
            open_interest=max(200, int(1000 - abs(strike - underlying) * 0.3)),
            iv=base_iv,
            timestamp=datetime.now(),
        ))

    # CALL options
    call_strikes = [20_500, 20_750, 21_000, 21_250, 21_500, 21_750, 22_000]
    call_ivs = [0.22, 0.21, 0.20, 0.19, 0.20, 0.21, 0.22]

    for strike, base_iv in zip(call_strikes, call_ivs):
        mid_price = max(0.1, (strike - underlying) * 0.02 + base_iv * underlying * 0.05)
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
            volume=max(50, int(300 - abs(strike - underlying) * 0.05)),
            open_interest=max(200, int(1000 - abs(strike - underlying) * 0.3)),
            iv=base_iv,
            timestamp=datetime.now(),
        ))

    return chain, underlying, expiry


async def load_signals_async() -> list[SpreadSignal]:
    """
    טוען אותות מ-generator בצורה אסינכרונית.
    משתמש בנתוני הדוגמה שנוצרים ב-generate_example_chain().
    """
    generator = get_signal_generator()
    chain, underlying, expiry = generate_example_chain()

    # Generate Bull Put Signals
    bull_puts = await generator.generate_bull_put_signals(
        chain=chain,
        underlying_price=underlying,
        expiry=expiry,
        quantity=1,
        now=datetime.now(),
    )

    # Generate Bear Call Signals
    bear_calls = await generator.generate_bear_call_signals(
        chain=chain,
        underlying_price=underlying,
        expiry=expiry,
        quantity=1,
        now=datetime.now(),
    )

    # Merge and sort
    all_signals = bull_puts + bear_calls
    all_signals.sort(key=lambda s: (s.signal_strength.name, -s.roi_on_margin))

    return all_signals


@st.cache_data(ttl=300)
def get_signals_sync() -> list[SpreadSignal]:
    """
    Wrapper סינכרוני ל-load_signals_async().
    Streamlit ממשק סינכרוני, אבל generator שלנו אסינכרוני.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        signals = loop.run_until_complete(load_signals_async())
        return signals
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# פונקציות עזר — פורמט ותמחור
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="TA35 Options Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# עיצוב CSS מינימליסטי ופרופסיונלי
st.markdown("""
<style>
    :root {
        --primary-color: #0066cc;
        --success-color: #10b981;
        --warning-color: #f59e0b;
        --danger-color: #ef4444;
        --neutral-bg: #f9fafb;
        --card-bg: #ffffff;
    }

    /* כיתוב בעברית */
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        direction: rtl;
        text-align: right;
    }

    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
    }

    .signal-strong {
        background-color: #d1fae5;
        color: #065f46;
        font-weight: bold;
    }

    .signal-medium {
        background-color: #fef3c7;
        color: #92400e;
        font-weight: bold;
    }

    .signal-weak {
        background-color: #fee2e2;
        color: #991b1b;
        font-weight: bold;
    }

    .profit-positive {
        color: #10b981;
        font-weight: bold;
    }

    .profit-negative {
        color: #ef4444;
        font-weight: bold;
    }

    .roi-high {
        color: #059669;
        font-weight: bold;
    }

    .roi-medium {
        color: #d97706;
    }

    .roi-low {
        color: #dc2626;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1f2937 0%, #111827 100%);
    }

    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# מצב Session — אחסון בזמן סשן Streamlit
# ---------------------------------------------------------------------------
if "signals" not in st.session_state:
    st.session_state.signals = []
if "selected_signal" not in st.session_state:
    st.session_state.selected_signal = None
if "market_data" not in st.session_state:
    st.session_state.market_data = {
        "underlying_price": 20_000.0,
        "atm_iv": 0.25,
        "iv_rank": 65.0,
        "timestamp": datetime.now(),
    }


# ---------------------------------------------------------------------------
# פונקציות עזר — פורמט ותמחור
# ---------------------------------------------------------------------------
def format_currency(value: float) -> str:
    """פורמט מחיר בשקלים עם עיצוב."""
    return f"₪{value:,.0f}" if abs(value) >= 1 else f"₪{value:.2f}"


def format_percent(value: float, decimals: int = 1) -> str:
    """פורמט אחוז."""
    return f"{value * 100:.{decimals}f}%"


def color_signal_strength(strength: SignalStrength) -> str:
    """מחזיר CSS color class לפי עוצמת אות."""
    mapping = {
        SignalStrength.STRONG: "signal-strong",
        SignalStrength.MEDIUM: "signal-medium",
        SignalStrength.WEAK:   "signal-weak",
    }
    return mapping.get(strength, "signal-weak")


def color_profit(value: float) -> str:
    """מחזיר CSS class לפי רווח/הפסד."""
    return "profit-positive" if value > 0 else "profit-negative"


def color_roi(roi: float) -> str:
    """מחזיר CSS class לפי ROI."""
    if roi > 0.05:
        return "roi-high"
    elif roi > 0.02:
        return "roi-medium"
    else:
        return "roi-low"


# ---------------------------------------------------------------------------
# עמוד 1: Market Overview + Signals Table
# ---------------------------------------------------------------------------
def page_home():
    """עמוד הבית — סקירה כללית וטבלת אותות."""
    st.title("📊 TA35 Options Analytics Dashboard")

    # טען אותות מ-cache (או מחשב אם expired)
    signals = get_signals_sync()
    chain, underlying, expiry = generate_example_chain()

    # עדכן את session state
    st.session_state.signals = signals
    st.session_state.market_data = {
        "underlying_price": underlying,
        "atm_iv": 0.22,  # ATM IV מחוקי
        "iv_rank": 65.0,  # IV Rank גבוה = טוב לכתיבה
        "timestamp": datetime.now(),
    }

    # --- Market Overview Header ---
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "💹 ת"א 35 נוכחי",
            f"{st.session_state.market_data['underlying_price']:,.0f}",
            delta=None,
        )

    with col2:
        st.metric(
            "🎯 IV (ATM)",
            format_percent(st.session_state.market_data['atm_iv']),
            delta=None,
        )

    with col3:
        iv_rank = st.session_state.market_data['iv_rank']
        delta_color = "normal" if iv_rank > 50 else "inverse"
        st.metric(
            "📈 IV Rank",
            f"{iv_rank:.0f}/100",
            delta=None,
        )

    with col4:
        now = datetime.now()
        st.metric(
            "🕐 עדכון אחרון",
            now.strftime("%H:%M:%S"),
            delta=None,
        )

    st.divider()

    # --- Volatility Smile Chart ---
    st.subheader("📉 Volatility Smile (IV לפי Moneyness)")
    col_chart, col_info = st.columns([3, 1], gap="medium")

    with col_chart:
        # יצירת גרף Smile תיאורטי (בפרויקט אמיתי: נתונים מהשוק)
        moneyness = np.linspace(0.90, 1.10, 20)
        strikes = st.session_state.market_data['underlying_price'] * moneyness

        # Smile pattern פשוט (ממציא לדוגמה)
        atm_iv = st.session_state.market_data['atm_iv']
        iv_values = atm_iv + 0.02 * (moneyness - 1.0) ** 2

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=strikes,
            y=iv_values,
            mode='lines+markers',
            name='Put Smile',
            line=dict(color='#f59e0b', width=3),
            marker=dict(size=8),
            fill='tozeroy',
            fillcolor='rgba(245, 158, 11, 0.2)',
        ))

        fig.update_layout(
            title="חיוך התנודתיות — IV לפי סטרייק",
            xaxis_title="מחיר מימוש (Strike)",
            yaxis_title="Implied Volatility (IV)",
            hovermode='x unified',
            height=350,
            margin=dict(t=40, b=40, l=50, r=20),
            template='plotly_white',
        )

        st.plotly_chart(fig, use_container_width=True)

    with col_info:
        st.write("**שימוש בגרף:**")
        st.write("""
        🔵 עקומה תלולה = Smile חזק = יותר סיכון לקצוות
        
        🟡 עקומה שטוחה = Smile חלש = שוק סדיר
        
        ✅ גדול מ-70% = זמן מעולה לכתיבה
        """)

    st.divider()

    # --- Signals Table ---
    st.subheader("🎯 אותות מומלצים — טבלת הזדמנויות")

    if not st.session_state.signals:
        st.info(
            "📭 אין אותות זמינים כרגע. בדוק את נתוני השוק או נסה לעדכן את ה-DTE.",
            icon="ℹ️"
        )
        return

    # יצירת DataFrame מהאותות
    signals_data = []
    for sig in st.session_state.signals:
        signals_data.append({
            "🎯 אסטרטגיה":       sig.strategy_type.value,
            "סטרייק כתיבה":      f"{sig.short_leg.quote.strike:,.0f}",
            "סטרייק גידור":      f"{sig.long_leg.quote.strike:,.0f}",
            "DTE":               f"{sig.dte:.0f}",
            "פרמיום כניסה":      format_currency(sig.net_credit),
            "רווח מקסימלי":     format_currency(sig.max_profit),
            "הפסד מקסימלי":     format_currency(sig.max_loss),
            "Risk/Reward":       f"1:{1/sig.risk_reward_ratio:.2f}",
            "ROI/מרג'ין":        format_percent(sig.roi_on_margin),
            "POP":               format_percent(sig.pop),
            "Net Θ (₪/יום)":    f"{sig.position_greeks.net_theta:+.2f}",
            "עוצמה":            sig.signal_strength.value,
            "🔗 פרטים":         f"View #{sig.signal_id}",
        })

    df = pd.DataFrame(signals_data)

    # תצוגה צבעונית של הטבלה
    def highlight_signal_strength(val):
        """צבע את עמודת "עוצמה" לפי חוזק האות."""
        if "🟢" in val:
            return 'background-color: #d1fae5; font-weight: bold'
        elif "🟡" in val:
            return 'background-color: #fef3c7; font-weight: bold'
        elif "🔴" in val:
            return 'background-color: #fee2e2; font-weight: bold'
        return ''

    def highlight_roi(val):
        """צבע את ROI."""
        if "₪" in val or "%" in val:
            try:
                roi_str = val.replace('%', '')
                roi = float(roi_str) / 100
                if roi > 0.05:
                    return 'color: #059669; font-weight: bold'
                elif roi > 0.02:
                    return 'color: #d97706'
                else:
                    return 'color: #dc2626'
            except:
                pass
        return ''

    # הצג את הטבלה עם styling
    st.dataframe(
        df.style.applymap(lambda x: highlight_signal_strength(x) if isinstance(x, str) else ''),
        use_container_width=True,
    )

    # פתרון לבחירה של אות לצפייה בפרטים
    st.write("**בחר אות להצגת גרף Payoff:**")
    signal_options = [f"Signal #{s.signal_id} | {s.strategy_type.value}" for s in st.session_state.signals]
    selected_idx = st.selectbox("", range(len(signal_options)), format_func=lambda i: signal_options[i])
    st.session_state.selected_signal = st.session_state.signals[selected_idx]

    # כפתור ללחוץ לעמוד Payoff
    if st.button("📈 הצג גרף Payoff", use_container_width=True):
        st.switch_page("pages/payoff_diagram.py")


# ---------------------------------------------------------------------------
# פונקציית עזר: Payoff Diagram
# ---------------------------------------------------------------------------
def build_payoff_diagram(signal: SpreadSignal, underlying_price: float) -> go.Figure:
    """
    בונה גרף Payoff דינמי (Risk Profile) לאסטרטגיה.

    הגרף מציג:
      - ציר X: מחיר בסיס בפקיעה
      - ציר Y: P&L בשקלים
      - הנקודה הנוכחית של הבסיס מסומנת
      - אזורי רווח/הפסד צבעוניים
    """
    short_strike = signal.short_leg.quote.strike
    long_strike  = signal.long_leg.quote.strike
    short_iv     = signal.iv_short
    long_iv      = signal.iv_long
    net_credit   = signal.net_credit
    spread_width = signal.spread_width
    quantity     = signal.short_leg.quantity

    # טווח מחירים לטבלה
    price_range = np.linspace(
        min(short_strike, long_strike) * 0.85,
        max(short_strike, long_strike) * 1.15,
        200
    )

    # חשב P&L לכל מחיר בטווח (בפקיעה, כאשר Theta = 0)
    pnl_values = []
    for S_expiry in price_range:
        # עבור Bull Put Spread: כל מחיר בטווח נותן P&L ספציפי
        if signal.strategy_type == StrategyType.BULL_PUT_SPREAD:
            # SHORT put בתוך הכסף (ITM)
            short_payoff = max(short_strike - S_expiry, 0)
            # LONG put כגידור
            long_payoff  = max(long_strike - S_expiry, 0)
            # נטו: כל יחידה של הפסד שלנו מכוסה על ידי הקנייה
            intrinsic = (short_payoff - long_payoff) * signal.short_leg.quantity
            pnl = (net_credit - intrinsic) * 100  # ×100 לשקלים (מכפיל)
        else:  # BEAR_CALL_SPREAD
            # SHORT call
            short_payoff = max(S_expiry - short_strike, 0)
            # LONG call כגידור
            long_payoff  = max(S_expiry - long_strike, 0)
            intrinsic = (short_payoff - long_payoff) * signal.short_leg.quantity
            pnl = (net_credit - intrinsic) * 100

        pnl_values.append(pnl)

    pnl_values = np.array(pnl_values)

    # צוד הנקודות לפי רווח/הפסד
    profit_mask  = pnl_values >= 0
    loss_mask    = pnl_values < 0

    fig = go.Figure()

    # אזור רווח (ירוק)
    fig.add_trace(go.Scatter(
        x=price_range[profit_mask],
        y=pnl_values[profit_mask],
        fill='tozeroy',
        fillcolor='rgba(16, 185, 129, 0.3)',
        line=dict(color='#10b981', width=2),
        name='אזור רווח',
        mode='lines',
    ))

    # אזור הפסד (אדום)
    fig.add_trace(go.Scatter(
        x=price_range[loss_mask],
        y=pnl_values[loss_mask],
        fill='tozeroy',
        fillcolor='rgba(239, 68, 68, 0.3)',
        line=dict(color='#ef4444', width=2),
        name='אזור הפסד',
        mode='lines',
    ))

    # קו ב-Zero
    fig.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="Break Even")

    # מחיר בסיס נוכחי
    fig.add_vline(
        x=underlying_price,
        line_dash="dot",
        line_color="blue",
        annotation_text=f"ערך כרגע: {underlying_price:,.0f}",
    )

    # ערכי הקיצוניים (Max Profit / Max Loss)
    fig.add_hline(y=signal.max_profit, line_dash="dot", line_color="green", opacity=0.5)
    fig.add_hline(y=-signal.max_loss, line_dash="dot", line_color="red", opacity=0.5)

    fig.update_layout(
        title=f"Risk Profile | {signal.strategy_type.value} | {signal.expiry.isoformat()}",
        xaxis_title="מחיר בסיס בפקיעה",
        yaxis_title="P&L (₪)",
        hovermode='x unified',
        height=500,
        showlegend=True,
        template='plotly_white',
        margin=dict(t=60, b=50, l=70, r=20),
    )

    return fig


# ---------------------------------------------------------------------------
# עמוד 2: Payoff Diagram (אם נבחרה אות)
# ---------------------------------------------------------------------------
def page_payoff():
    """עמוד עם גרף Payoff אינטראקטיבי."""
    if st.session_state.selected_signal is None:
        st.warning("אנא בחר אות מהטבלה בעמוד הבית")
        st.stop()

    sig = st.session_state.selected_signal
    st.title(f"📈 Risk Profile | {sig.strategy_type.value}")

    # מידע עיליון
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("סטרייק כתיבה", f"{sig.short_leg.quote.strike:,.0f}")
    with col2:
        st.metric("סטרייק גידור", f"{sig.long_leg.quote.strike:,.0f}")
    with col3:
        st.metric("פרמיום כניסה", format_currency(sig.net_credit))
    with col4:
        st.metric("רווח מקסימלי", format_currency(sig.max_profit))
    with col5:
        st.metric("הפסד מקסימלי", format_currency(sig.max_loss))

    st.divider()

    # גרף
    fig = build_payoff_diagram(sig, st.session_state.market_data['underlying_price'])
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # טבלה של Greeks
    st.subheader("📊 יווניות מצרפיות בפקיעה")
    greeks_col1, greeks_col2, greeks_col3, greeks_col4 = st.columns(4)

    with greeks_col1:
        st.metric("Δ (Delta)", f"{sig.position_greeks.net_delta:+.4f}")

    with greeks_col2:
        st.metric("Γ (Gamma)", f"{sig.position_greeks.net_gamma:.5f}")

    with greeks_col3:
        st.metric("Θ (Theta)", f"₪{sig.position_greeks.net_theta:+.2f}/יום")

    with greeks_col4:
        st.metric("ν (Vega)", f"{sig.position_greeks.net_vega:+.4f}")

    # הערות
    st.subheader("💡 הערות וטיפים")
    for note in sig.notes:
        st.write(f"• {note}")


# ---------------------------------------------------------------------------
# עמוד 3: Analysis (IV Smile + Greeks)
# ---------------------------------------------------------------------------
def page_analysis():
    """עמוד Analysis — Volatility Smile + Greeks Panel בפירוט."""
    st.title("🔬 ניתוח מעמיק")

    if st.session_state.selected_signal is None:
        st.info("אנא בחר אות מהטבלה בעמוד הבית לצפייה בניתוח מעמיק")
        return

    sig = st.session_state.selected_signal

    # --- Tab 1: Greeks Table ---
    st.subheader("📋 יווניות מפורטות — לפי רגל")
    col1, col2 = st.columns(2)

    with col1:
        st.write("**רגל כתיבה (Short)**")
        short_greeks_data = {
            "Delta": f"{sig.short_leg.net_delta:+.4f}",
            "Gamma": f"{sig.short_leg.net_gamma:.5f}",
            "Theta": f"₪{sig.short_leg.net_theta:+.2f}/יום",
            "Vega": f"{sig.short_leg.net_vega:+.4f}",
            "IV": format_percent(sig.iv_short),
        }
        st.table(short_greeks_data)

    with col2:
        st.write("**רגל גידור (Long)**")
        long_greeks_data = {
            "Delta": f"{sig.long_leg.net_delta:+.4f}",
            "Gamma": f"{sig.long_leg.net_gamma:.5f}",
            "Theta": f"₪{sig.long_leg.net_theta:+.2f}/יום",
            "Vega": f"{sig.long_leg.net_vega:+.4f}",
            "IV": format_percent(sig.iv_long),
        }
        st.table(long_greeks_data)

    st.divider()

    # --- Tab 2: Sensitivity Analysis ---
    st.subheader("📊 ניתוח רגישות — PnL לפי שינויי בסיס ו-IV")

    col_slider1, col_slider2 = st.columns(2)
    with col_slider1:
        spot_change = st.slider(
            "שינוי במחיר בסיס (%)",
            min_value=-10.0,
            max_value=10.0,
            value=0.0,
            step=0.1
        )

    with col_slider2:
        iv_change = st.slider(
            "שינוי ב-IV (%)",
            min_value=-50.0,
            max_value=50.0,
            value=0.0,
            step=1.0
        )

    # חשב P&L עם שינויים
    new_spot = st.session_state.market_data['underlying_price'] * (1 + spot_change / 100)
    new_iv_short = sig.iv_short * (1 + iv_change / 100)
    new_iv_long = sig.iv_long * (1 + iv_change / 100)

    # מדדים של שינוי
    sensitivity_data = {
        "מחיר בסיס חדש": f"{new_spot:,.0f}",
        "IV כתיבה חדש": format_percent(new_iv_short),
        "IV גידור חדש": format_percent(new_iv_long),
    }
    st.table(sensitivity_data)

    st.divider()

    # --- Tab 3: Risk Metrics ---
    st.subheader("⚠️ מדדי סיכון")
    risk_col1, risk_col2, risk_col3 = st.columns(3)

    with risk_col1:
        st.metric("Risk/Reward Ratio", f"1:{1/sig.risk_reward_ratio:.2f}")

    with risk_col2:
        st.metric("ROI על מרג'ין", format_percent(sig.roi_on_margin))

    with risk_col3:
        st.metric("Probability of Profit", format_percent(sig.pop))


# ---------------------------------------------------------------------------
# Main App Logic
# ---------------------------------------------------------------------------
def main():
    """הפונקציה הראשית — בחר עמוד לתצוגה."""

    # Sidebar Navigation
    st.sidebar.title("🧭 תפריט")
    page = st.sidebar.radio(
        "בחר עמוד:",
        ["🏠 עמוד בית", "📈 Payoff Diagram", "🔬 ניתוח מעמיק"],
        label_visibility="collapsed",
    )

    # Sidebar Controls
    st.sidebar.divider()
    st.sidebar.subheader("⚙️ בקרות")

    if st.sidebar.button("🔄 עדכן אותות", use_container_width=True):
        st.write("**טוען אותות...**")
        # TODO: קרא מ-signal_generator
        st.session_state.signals = []
        st.info("✅ מוכן לעדכון (דרוש חיבור מלא ל-signal_generator)")

    if st.sidebar.button("📊 עדכן נתוני שוק", use_container_width=True):
        st.write("**טוען נתוני שוק...**")
        # TODO: קרא מ-feed_handler
        st.info("✅ מוכן לעדכון (דרוש חיבור מלא ל-feed_handler)")

    # בחר עמוד
    if page == "🏠 עמוד בית":
        page_home()
    elif page == "📈 Payoff Diagram":
        page_payoff()
    elif page == "🔬 ניתוח מעמיק":
        page_analysis()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # טען אותות לדוגמה (בפרויקט אמיתי: מ-signal_generator)
    # דוגמה בקוד אמיתי:
    # generator = SignalGenerator()
    # signals = asyncio.run(generator.generate_bull_put_signals(...))
    # st.session_state.signals = signals

    main()
