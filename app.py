import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm
from datetime import datetime

# --- הגדרות עמוד ---
st.set_page_config(page_title="TA35 Options Analytics", page_icon="📊", layout="wide")
st.markdown("""<style> body { direction: rtl; text-align: right; } </style>""", unsafe_allow_html=True)

# --- מנוע מתמטי: בלאק שולס ויווניות ---
def bs_price_and_greeks(S, K, T, r, sigma, option_type='call'):
    """חישוב מחיר ויווניות לפי מודל בלאק-שולס"""
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

# --- נתוני שוק (סימולציה כהכנה לנתוני אמת) ---
# במקום הקוד הזה נכניס בעתיד חיבור ל-API
current_spot = 2085.0
current_iv = 0.18
risk_free_rate = 0.045
dte = 20 # ימים לפקיעה
time_to_expiry = dte / 365.0

st.session_state.market_data = {"underlying": current_spot, "iv": current_iv}

# --- כותרות ועיצוב (העיצוב המקצועי שלך) ---
st.title("📊 TA35 Options Analytics Dashboard")

col1, col2, col3, col4 = st.columns(4)
with col1: st.metric("💹 מדד תא 35", f"{current_spot:,.1f}")
with col2: st.metric("🎯 IV (ATM)", f"{current_iv*100:.1f}%")
with col3: st.metric("📈 IV Rank", "72/100")
with col4: st.metric("🕐 עדכון אחרון", datetime.now().strftime("%H:%M"))
st.divider()

# --- יצירת שרשרת אופציות (Option Chain) דינמית ---
st.subheader("⛓️ שרשרת אופציות פעילה (מוכנה לחיבור נתונים)")
strikes = [1950, 2000, 2050, 2100, 2150]
chain_data = []

for strike in strikes:
    # הוספת "חיוך" לתנודתיות
    iv_smile = current_iv + 0.03 * ((strike/current_spot - 1)**2)
    
    # חישוב Puts
    p_price, p_delta, _, p_theta, _ = bs_price_and_greeks(current_spot, strike, time_to_expiry, risk_free_rate, iv_smile, 'put')
    # חישוב Calls
    c_price, c_delta, _, c_theta, _ = bs_price_and_greeks(current_spot, strike, time_to_expiry, risk_free_rate, iv_smile, 'call')
    
    chain_data.append({
        "Put Delta": f"{p_delta:.2f}",
        "Put Price": f"₪{p_price * 100:,.0f}", # מכפיל 100
        "Strike": strike,
        "Call Price": f"₪{c_price * 100:,.0f}",
        "Call Delta": f"{c_delta:.2f}",
        "IV": f"{iv_smile*100:.1f}%"
    })

st.dataframe(pd.DataFrame(chain_data), use_container_width=True)
st.divider()

# --- מנוע איתותים (Bull Put / Bear Call) ---
st.subheader("🎯 הזדמנויות מסחר מחושבות")

# סימולציה של חוקי האיתות שלך:
signals = []
for data in chain_data:
    strike = data["Strike"]
    # חיפוש Bull Put (כתיבת פוט רחוק מהכסף)
    if float(data["Put Delta"]) > -0.30 and strike < current_spot:
         signals.append({
             "אסטרטגיה": "Bull Put Spread",
             "סטרייקים (Short/Long)": f"{strike}/{strike-50}",
             "פרמיה נטו": f"₪{(float(data['Put Price'].replace('₪', '').replace(',', '')) - 300):,.0f}", # סימולציה למחיר גידור
             "עוצמה": "🟢 STRONG" if float(data["Put Delta"]) > -0.15 else "🟡 MEDIUM"
         })

st.dataframe(pd.DataFrame(signals), use_container_width=True)

st.success("✅ מנוע בלאק-שולס ויווניות הוטמע בהצלחה. המערכת מוכנה לחיבור נתונים חיים!")
