import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm
from datetime import datetime
import yfinance as yf

# --- הגדרות עמוד ---
st.set_page_config(page_title="TA35 & Global Dashboard", page_icon="🌍", layout="wide")
st.markdown("""<style> body { direction: rtl; text-align: right; } </style>""", unsafe_allow_html=True)

# --- פונקציות מתמטיות (בלאק שולס) ---
def bs_price_and_greeks(S, K, T, r, sigma, option_type='call'):
    if T <= 0: return 0, 0, 0, 0, 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if option_type == 'call':
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        delta = norm.cdf(d1)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vega = S * norm.pdf(d1) * np.sqrt(T) / 100
    theta = -(S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)))
    if option_type == 'call':
        theta = theta - r * K * np.exp(-r * T) * norm.cdf(d2)
    else:
        theta = theta + r * K * np.exp(-r * T) * norm.cdf(-d2)
    theta = theta / 365
    return price, delta, gamma, theta, vega

# --- משיכת נתוני שוק גלובליים מ-Yahoo Finance ---
@st.cache_data(ttl=60) # שומר בזיכרון לדקה כדי שהאתר יטוס ולא ייתקע
def get_global_markets():
    tickers = ["^GSPC", "^IXIC", "ILS=X", "TA35.TA"] # S&P500, Nasdaq, USD/ILS, TA35
    data = {}
    for t in tickers:
        try:
            ticker = yf.Ticker(t)
            hist = ticker.history(period="2d")
            if len(hist) >= 2:
                current = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                change = ((current - prev) / prev) * 100
                data[t] = {"price": current, "change": change}
            else:
                data[t] = {"price": 0, "change": 0}
        except:
            data[t] = {"price": 0, "change": 0}
    return data

global_data = get_global_markets()

# --- כותרות ועיצוב ---
st.title("🌍 דשבורד מסחר עולמי ואופציות ת\"א 35")

# --- פס מדדים עולמי - חי! ---
st.subheader("🌐 שווקים בעולם (מעודכן בזמן אמת)")
g1, g2, g3, g4 = st.columns(4)
with g1:
    st.metric("🇺🇸 S&P 500", f"{global_data['^GSPC']['price']:,.2f}", f"{global_data['^GSPC']['change']:.2f}%")
with g2:
    st.metric("🇺🇸 Nasdaq", f"{global_data['^IXIC']['price']:,.2f}", f"{global_data['^IXIC']['change']:.2f}%")
with g3:
    st.metric("💵 דולר / שקל", f"{global_data['ILS=X']['price']:.4f}", f"{global_data['ILS=X']['change']:.2f}%")
with g4:
    # משיכת ת"א 35 או שימוש בערך ברירת מחדל אם הבורסה סגורה
    ta35_price = global_data['TA35.TA']['price'] if global_data['TA35.TA']['price'] > 0 else 2085.0
    st.metric("🇮🇱 ת\"א 35", f"{ta35_price:,.2f}", f"{global_data['TA35.TA']['change']:.2f}%")

st.divider()

# --- נתוני שוק לבוט האופציות ---
current_spot = ta35_price
current_iv = 0.18
risk_free_rate = 0.045
dte = 20
time_to_expiry = dte / 365.0

# --- יצירת שרשרת אופציות (Option Chain) דינמית ---
st.subheader("⛓️ מנוע אופציות ת\"א 35 (מבוסס על המדד החי)")
# מחשב סטרייקים באופן דינמי סביב המחיר הנוכחי
base_strike = round(current_spot / 10) * 10
strikes = [base_strike - 100, base_strike - 50, base_strike, base_strike + 50, base_strike + 100]

chain_data = []
for strike in strikes:
    iv_smile = current_iv + 0.03 * ((strike/current_spot - 1)**2)
    p_price, p_delta, _, _, _ = bs_price_and_greeks(current_spot, strike, time_to_expiry, risk_free_rate, iv_smile, 'put')
    c_price, c_delta, _, _, _ = bs_price_and_greeks(current_spot, strike, time_to_expiry, risk_free_rate, iv_smile, 'call')
    
    chain_data.append({
        "Put Delta": f"{p_delta:.2f}",
        "Put Price": f"₪{p_price * 100:,.0f}",
        "Strike": strike,
        "Call Price": f"₪{c_price * 100:,.0f}",
        "Call Delta": f"{c_delta:.2f}"
    })

st.dataframe(pd.DataFrame(chain_data), use_container_width=True)
st.divider()

# --- מנוע איתותים ---
st.subheader("🎯 הזדמנויות מסחר מחושבות")
signals = []
for data in chain_data:
    strike = data["Strike"]
    put_delta = float(data["Put Delta"])
    if put_delta > -0.30 and strike < current_spot:
         signals.append({
             "אסטרטגיה": "Bull Put Spread",
             "סטרייקים (Short/Long)": f"{strike}/{strike-50}",
             "פרמיה נטו מחושבת": f"₪{(float(data['Put Price'].replace('₪', '').replace(',', '')) - 300):,.0f}",
             "עוצמה": "🟢 STRONG" if put_delta > -0.15 else "🟡 MEDIUM"
         })

st.dataframe(pd.DataFrame(signals), use_container_width=True)
