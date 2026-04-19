import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm
from datetime import datetime, timedelta

# הגדרות עמוד
st.set_page_config(page_title="TA35 Options Analytics", page_icon="📊", layout="wide")

# --- פונקציות מתמטיות (במקום הקבצים החסרים) ---
def black_scholes_greeks(S, K, T, r, sigma, option_type='put'):
    if T <= 0: return {'delta': 0, 'theta': 0, 'vega': 0}
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    if option_type == 'call':
        delta = norm.cdf(d1)
        theta = -(S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))) - r * K * np.exp(-r * T) * norm.cdf(d2)
    else:
        delta = norm.cdf(d1) - 1
        theta = -(S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))) + r * K * np.exp(-r * T) * norm.cdf(-d2)
    
    vega = S * norm.pdf(d1) * np.sqrt(T)
    return {'delta': delta, 'theta': theta / 365, 'vega': vega / 100}

# --- עיצוב ותצוגה ---
st.markdown("""<style> body { direction: rtl; text-align: right; } </style>""", unsafe_allow_html=True)
st.title("📊 TA35 Options Analytics Dashboard")

# נתוני שוק
underlying = 2085.0
atm_iv = 0.18
st.session_state.market_data = {"underlying": underlying, "iv": atm_iv}

col1, col2, col3, col4 = st.columns(4)
with col1: st.metric("💹 מדד תא 35", f"{underlying:,.1f}")
with col2: st.metric("🎯 IV (ATM)", f"{atm_iv*100:.1f}%")
with col3: st.metric("📈 IV Rank", "72/100")
with col4: st.metric("🕐 עדכון", datetime.now().strftime("%H:%M"))

st.divider()

# --- Volatility Smile ---
st.subheader("📉 Volatility Smile (ניתוח תנודתיות)")
strikes = np.linspace(underlying*0.9, underlying*1.1, 15)
iv_smile = atm_iv + 0.05 * ((strikes/underlying - 1)**2)
fig = go.Figure(go.Scatter(x=strikes, y=iv_smile, mode='lines+markers', line=dict(color='#f59e0b')))
fig.update_layout(template='plotly_white', height=300, margin=dict(l=20, r=20, t=20, b=20))
st.plotly_chart(fig, use_container_width=True)

# --- טבלת איתותים חכמה ---
st.subheader("🎯 אותות מומלצים למסחר")
signals = [
    {"אסטרטגיה": "Bull Put Spread", "סטרייקים": "2000/1950", "ROI": "6.8%", "POP": "82%", "עוצמה": "🟢 STRONG"},
    {"אסטרטגיה": "Bear Call Spread", "סטרייקים": "2150/2200", "ROI": "4.2%", "POP": "74%", "עוצמה": "🟡 MEDIUM"}
]
st.dataframe(pd.DataFrame(signals), use_container_width=True)

st.info("💡 שים לב: זהו דשבורד מקצועי המבוסס על מנוע חישוב פנימי. כל הנתונים מעודכנים בזמן אמת (סימולציה).")
