import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime

# --- הגדרות עמוד ---
st.set_page_config(page_title="Global Pro Terminal", layout="wide", initial_sidebar_state="expanded")

# --- עיצוב CSS (Dark Mode & RTL) ---
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    body { direction: rtl; text-align: right; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; font-weight: bold; }
    .recommendation-box { padding: 20px; border-radius: 10px; border: 1px solid #3b82f6; background-color: rgba(59, 130, 246, 0.1); }
</style>
""", unsafe_allow_html=True)

# --- סרגל צד: קטגוריות בורסות ---
st.sidebar.title("🌍 בורסות עולם")
market_category = st.sidebar.radio("בחר שוק:", ["🇮🇱 ישראל", "🇺🇸 וול סטריט", "🇪🇺 אירופה", "🪙 קריפטו"])

# --- פונקציות נתונים ---
@st.cache_data(ttl=60)
def get_live_data(tickers):
    data = {}
    for label, sym in tickers.items():
        try:
            t = yf.Ticker(sym)
            val = t.history(period="1d")['Close'].iloc[-1]
            data[label] = val
        except: data[label] = 0
    return data

# --- דף ראשי ---
st.title(f"🖥️ טרמינל מסחר: {market_category}")

if market_category == "🇮🇱 ישראל":
    indices = {"תא 35": "TA35.TA", "תא 125": "TA125.TA", "בנקים": "PIBK5.TA", "נדלן": "REIT.TA"}
elif market_category == "🇺🇸 וול סטריט":
    indices = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Dow Jones": "^DJI", "VIX": "^VIX"}
else:
    indices = {"Global": "^GSPC"}

live_prices = get_live_data(indices)
cols = st.columns(len(indices))
for i, (name, price) in enumerate(live_prices.items()):
    cols[i].metric(name, f"{price:,.2f}")

st.divider()

# --- מערכת אופציות וסימולציה ---
st.header("🧮 סימולטור אסטרטגיות חכם")

col_input, col_graph = st.columns([1, 2])

with col_input:
    st.subheader("🏦 בנק אסטרטגיות")
    strategy = st.selectbox("בחר אסטרטגיה לטעינה מהירה:", 
                            ["ידני", "Bull Put Spread", "Bear Call Spread", "Iron Condor", "Long Straddle"])
    
    spot = st.number_input("מחיר נוכחי", value=float(list(live_prices.values())[0]) if live_prices else 2000.0)
    
    # לוגיקת טעינה אוטומטית מהבנק
    if strategy == "Bull Put Spread":
        s_k, l_k, prem = round(spot*0.96, -1), round(spot*0.94, -1), 350
    elif strategy == "Iron Condor":
        s_k, l_k, prem = round(spot*0.96, -1), round(spot*1.04, -1), 600
    else:
        s_k, l_k, prem = spot-20, spot-40, 200

    short_k = st.number_input("סטרייק כתיבה", value=float(s_k))
    long_k = st.number_input("סטרייק הגנה", value=float(l_k))
    net_prem = st.number_input("פרמיה נטו (₪)", value=float(prem))

    # מנוע המלצות
    st.markdown("---")
    st.subheader("💡 המלצת המערכת")
    iv = 18 # כאן נחבר בעתיד IV אמיתי
    if iv > 22:
        st.success("תנודתיות גבוהה: מומלץ לבצע אסטרטגיות כתיבה (Credit Spreads) לניצול שחיקה.")
    else:
        st.info("תנודתיות נמוכה: מומלץ להמתין או לבצע אסטרטגיות קנייה זולות.")

with col_graph:
    # חישוב גרף PnL
    x = np.linspace(spot*0.8, spot*1.2, 100)
    y = [net_prem - (max(short_k - p, 0) - max(long_k - p, 0))*100 for p in x]
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, fill='tozeroy', line=dict(color='#10b981')))
    fig.add_hline(y=0, line_color="white")
    fig.update_layout(template="plotly_dark", title="תרשים רווח/הפסד בפקיעה")
    st.plotly_chart(fig, use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.subheader("📰 חדשות מתפרצות")
st.sidebar.write("• הפד צפוי להשאיר את הריבית ללא שינוי")
st.sidebar.write("• תנודות חדות במניות הטכנולוגיה בניו יורק")
