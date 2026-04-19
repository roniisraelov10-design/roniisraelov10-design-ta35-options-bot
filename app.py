import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
import plotly.graph_objects as go

# --- 1. הגדרות עמוד ---
st.set_page_config(page_title="TASE Pro Terminal", layout="wide")
st.markdown("""<style> body { direction: rtl; text-align: right; } </style>""", unsafe_allow_html=True)

st.title("🖥️ טרמינל מסחר מורחב - בורסת ת\"א")

# --- 2. משיכת נתונים בטוחה מהבורסה הישראלית ---
@st.cache_data(ttl=60)
def get_safe_price(ticker_symbol):
    try:
        data = yf.Ticker(ticker_symbol).history(period="1d")
        if not data.empty:
            return data['Close'].iloc[-1]
        return 0.0
    except Exception:
        return 0.0

@st.cache_data(ttl=60)
def get_tase_heavyweights():
    """מושך את הנתונים החיים של המניות הכבדות בתל אביב"""
    tickers = {
        "לאומי": "LEUMI.TA",
        "פועלים": "POLI.TA",
        "טבע": "TEVA.TA",
        "אלביט מערכות": "ESLT.TA",
        "נייס": "NICE.TA",
        "דיסקונט": "DSCT.TA",
        "מזרחי טפחות": "MZTF.TA",
        "איי.סי.אל": "ICL.TA"
    }
    
    data = []
    for name, symbol in tickers.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="2d")
            if len(hist) >= 2:
                current = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                change_pct = ((current - prev) / prev) * 100
                
                # מניות בתל אביב מוצגות לרוב באגורות ב-Yahoo, לכן מחלקים ב-100 לשקלים
                data.append({
                    "שם המניה": name,
                    "סימול": symbol,
                    "מחיר אחרון (₪)": current / 100,
                    "שינוי (%)": change_pct
                })
        except Exception:
            pass
            
    if data:
        df = pd.DataFrame(data)
        return df
    return pd.DataFrame()

# --- 3. מנוע יווניות ---
def calculate_greeks(S, K, T, r, sigma, opt_type='call'):
    if T <= 0 or sigma <= 0 or S <= 0 or K <=0: return 0.0, 0.0, 0.0, 0.0, 0.0
    d1 = (np.log(S/K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if opt_type == 'call':
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        delta = norm.cdf(d1)
        theta = (- (S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T)) - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1
        theta = (- (S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T)) + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vega = (S * norm.pdf(d1) * np.sqrt(T)) / 100
    return price, delta, gamma, theta, vega

# --- 4. טאבים לתצוגה ---
tab_market, tab_stocks, tab_options = st.tabs(["📊 מבט לשוק", "🇮🇱 מניות ת\"א 35", "🧮 סימולטור אופציות"])

# --- טאב 1: מבט לשוק ---
with tab_market:
    st.subheader("מדדים מרכזיים (חי)")
    c1, c2, c3 = st.columns(3)
    with c1: st.metric("S&P 500 (ארה\"ב)", f"{get_safe_price('^GSPC'):,.2f}")
    with c2: st.metric("ת\"א 35 (ישראל)", f"{get_safe_price('TA35.TA'):,.2f}")
    with c3: st.metric("ת\"א 125 (ישראל)", f"{get_safe_price('TA125.TA'):,.2f}")

# --- טאב 2: מניות ת"א 35 החיות ---
with tab_stocks:
    st.subheader("סורק מניות מובילות בבורסת תל אביב")
    st.write("נתונים נמשכים בזמן אמת (או בעיכוב של עד 15 דק') מ-Yahoo Finance.")
    
    with st.spinner("שואב נתונים מבורסת תל אביב..."):
        df_tase = get_tase_heavyweights()
        
    if not df_tase.empty:
        # עיצוב הטבלה: ירוק לעליות, אדום לירידות
        def color_change(val):
            color = 'green' if val > 0 else 'red' if val < 0 else 'gray'
            return f'color: {color}; font-weight: bold'
            
        st.dataframe(
            df_tase.style.format({
                "מחיר אחרון (₪)": "₪{:.2f}",
                "שינוי (%)": "{:.2f}%"
            }).map(color_change, subset=["שינוי (%)"]),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("לא הצלחנו למשוך נתונים כרגע. ייתכן שהבורסה סגורה או שיש עומס על השרת.")

# --- טאב 3: סימולטור אופציות ---
with tab_options:
    st.subheader("מחשבון אופציות מתקדם")
    col_input, col_results = st.columns([1, 2])
    
    with col_input:
        default_spot = get_safe_price('TA35.TA')
        if default_spot == 0.0: default_spot = 2000.0
            
        S = st.number_input("מחיר מדד (Spot)", value=default_spot, step=10.0)
        K = st.number_input("סטרייק (Strike)", value=float(round(default_spot/10)*10), step=10.0)
        days = st.slider("ימים לפקיעה", 1, 90, 30)
        iv = st.slider("תנודתיות גלומה (IV %)", 10, 80, 20) / 100.0
        opt_type = st.radio("סוג:", ["Call", "Put"])

    with col_results:
        opt_str = 'call' if opt_type == "Call" else 'put'
        price, delta, gamma, theta, vega = calculate_greeks(S, K, days/365, 0.045, iv, opt_str)
        
        st.write(f"**תוצאות ניתוח לאופציית {opt_type}:**")
        r1, r2, r3 = st.columns(3)
        r1.metric("מחיר תיאורטי (₪)", f"₪{(price*100):,.0f}")
        r2.metric("דלתא (Δ)", f"{delta:.3f}")
        r3.metric("תטא (Θ) יומי", f"{theta:.2f}")
