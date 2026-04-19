import streamlit as st
import yfinance as yf
import numpy as np
from scipy.stats import norm
import plotly.graph_objects as go

# --- 1. הגדרות עמוד (Safe Data Infrastructure) ---
st.set_page_config(page_title="Pro Terminal - Step 2", layout="wide")
st.markdown("""<style> body { direction: rtl; text-align: right; } </style>""", unsafe_allow_html=True)

st.title("🖥️ טרמינל מסחר - שלב 2: מנוע אופציות")

# --- 2. פונקציית משיכת נתונים בטוחה ---
@st.cache_data(ttl=60) # שומר נתונים לדקה כדי למנוע קריסות (Rate Limiting)
def get_safe_price(ticker_symbol):
    try:
        data = yf.Ticker(ticker_symbol).history(period="1d")
        if not data.empty:
            return data['Close'].iloc[-1]
        return 0.0
    except Exception:
        return 0.0

# --- 3. מנוע יווניות (Black-Scholes Analytics) ---
def calculate_greeks(S, K, T, r, sigma, opt_type='call'):
    """מחשב מחיר ויווניות לפי מודל בלאק-שולס"""
    if T <= 0 or sigma <= 0 or S <= 0 or K <=0: 
        return 0.0, 0.0, 0.0, 0.0, 0.0
    
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

# --- 4. ממשק משתמש (UI) - טאבים ---
tab_market, tab_options = st.tabs(["📊 מבט לשוק (חי)", "🧮 סימולטור אופציות"])

# --- טאב 1: שוק חי ---
with tab_market:
    st.subheader("מדדים מרכזיים")
    c1, c2 = st.columns(2)
    with c1: st.metric("S&P 500 (ארה\"ב)", f"{get_safe_price('^GSPC'):,.2f}")
    with c2: st.metric("ת\"א 35 (ישראל)", f"{get_safe_price('TA35.TA'):,.2f}")

# --- טאב 2: סימולטור אופציות ---
with tab_options:
    st.subheader("מחשבון אופציות מתקדם (בלאק-שולס)")
    
    # אזור קלט נתונים
    col_input, col_results = st.columns([1, 2])
    
    with col_input:
        st.write("**הזן נתוני אופציה:**")
        # אנו משתמשים במחיר ת"א 35 כברירת מחדל אם הוא קיים, אחרת 2000
        default_spot = get_safe_price('TA35.TA')
        if default_spot == 0.0: default_spot = 2000.0
            
        S = st.number_input("מחיר נכס בסיס (Spot)", value=default_spot, step=10.0)
        K = st.number_input("סטרייק (Strike)", value=float(round(default_spot/10)*10), step=10.0)
        days = st.slider("ימים לפקיעה (DTE)", min_value=1, max_value=90, value=30)
        iv = st.slider("תנודתיות גלומה (IV %)", min_value=10, max_value=80, value=20) / 100.0
        r = 0.045 # ריבית חסרת סיכון (לדוגמה 4.5%)
        
        opt_type = st.radio("סוג אופציה:", ["Call", "Put"])

    with col_results:
        # הפעלת מנוע היווניות
        opt_str = 'call' if opt_type == "Call" else 'put'
        price, delta, gamma, theta, vega = calculate_greeks(S, K, days/365, r, iv, opt_str)
        
        st.write(f"**תוצאות ניתוח לאופציית {opt_type}:**")
        
        # תצוגת מטריקות (מכפיל 100 למחיר בארץ)
        r1, r2, r3 = st.columns(3)
        r1.metric("מחיר תיאורטי (₪)", f"₪{(price*100):,.0f}")
        r2.metric("דלתא (Δ)", f"{delta:.3f}")
        r3.metric("תטא (Θ) יומי", f"{theta:.2f}")
        
        r4, r5, r6 = st.columns(3)
        r4.metric("גמא (Γ)", f"{gamma:.5f}")
        r5.metric("וגא (ν) - 1%", f"{vega:.3f}")
        r6.metric("IV מזין", f"{(iv*100):.1f}%")

st.divider()
st.success("✅ שלב 2 מוכן. עכשיו יש לנו סימולטור יווניות עובד שמחובר לנתונים חיים.")
