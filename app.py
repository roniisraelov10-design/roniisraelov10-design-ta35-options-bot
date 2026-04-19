import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# הגדרות עמוד מקצועיות מהקוד שלך
st.set_page_config(page_title="TA35 Options Dashboard", page_icon="📊", layout="wide")

# עיצוב CSS מינימליסטי (לקוח מהקוד המקצועי שלך)
st.markdown("""
<style>
    body { direction: rtl; text-align: right; }
    .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

st.title("📊 TA35 Options Analytics Dashboard")

# --- נתוני שוק (סימולציה של מה ששלחת) ---
underlying = 20500.0
atm_iv = 0.22

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("💹 מדד תא 35", f"{underlying:,.0f}")
with col2:
    st.metric("🎯 IV (ATM)", f"{atm_iv*100:.1f}%")
with col3:
    st.metric("📈 IV Rank", "65/100")
with col4:
    st.metric("🕐 עדכון אחרון", datetime.now().strftime("%H:%M:%S"))

st.divider()

# --- גרף Volatility Smile (מהקוד המקצועי שלך) ---
st.subheader("📉 Volatility Smile (IV לפי סטרייק)")
moneyness = np.linspace(0.90, 1.10, 20)
strikes = underlying * moneyness
iv_values = atm_iv + 0.02 * (moneyness - 1.0) ** 2

fig = go.Figure()
fig.add_trace(go.Scatter(x=strikes, y=iv_values, mode='lines+markers', name='IV Smile', line=dict(color='#f59e0b', width=3)))
fig.update_layout(template='plotly_white', height=350, margin=dict(t=20, b=20, l=20, r=20))
st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- טבלת אותות (הגרסה המקצועית) ---
st.subheader("🎯 אותות מומלצים — טבלת הזדמנויות")
signals_data = [
    {"אסטרטגיה": "Bull Put Spread", "סטרייק": "19500/19250", "DTE": "20", "Max Profit": "₪2,800", "ROI": "5.2%", "עוצמה": "🟢 STRONG"},
    {"אסטרטגיה": "Bear Call Spread", "סטרייק": "21500/21750", "DTE": "20", "Max Profit": "₪1,500", "ROI": "2.1%", "עוצמה": "🟡 MEDIUM"}
]
st.table(pd.DataFrame(signals_data))

st.success("האתר עודכן בהצלחה עם הקוד המקצועי!")
