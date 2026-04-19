import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import norm
import yfinance as yf
import time
from datetime import datetime

# --- 1. הגדרות דף וסטייל ---
st.set_page_config(page_title="Live Trading Terminal", layout="wide")

# פונקציה להזרקת עיצוב לפי בחירת צבע (שחור/לבן/ירוק)
def apply_theme(theme_name):
    themes = {
        'Black': {"bg": "#0e1117", "text": "#ffffff", "card": "#1f2937"},
        'White': {"bg": "#ffffff", "text": "#000000", "card": "#f0f2f6"},
        'Green': {"bg": "#001a00", "text": "#00ff00", "card": "#003300"}
    }
    t = themes[theme_name]
    st.markdown(f"""
    <style>
        .stApp {{ background-color: {t['bg']}; color: {t['text']}; }}
        .metric-card {{ background-color: {t['card']}; padding: 15px; border-radius: 10px; border: 1px solid {t['text']}; margin: 5px; }}
        h1, h2, h3, span, p {{ color: {t['text']} !important; }}
    </style>
    """, unsafe_allow_html=True)

# --- 2. סרגל צד (Sidebar) לבקרות ---
with st.sidebar:
    st.title("⚙️ הגדרות טרמינל")
    lang = st.selectbox("שפה / Language", ["עברית", "English", "Русский"])
    theme_choice = st.radio("ערכת נושא", ["Black", "White", "Green"])
    refresh_rate = st.slider("קצב רענון (שניות)", 5, 60, 10)
    st.divider()
    st.info(f"עדכון אחרון: {datetime.now().strftime('%H:%M:%S')}")

apply_theme(theme_choice)

# --- 3. פונקציית משיכת נתונים חיים ---
def get_live_data():
    # רשימת הטיקרים המורחבת שביקשת
    tickers = {
        "S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Russell 2000": "^RUT", "VIX": "^VIX",
        "ת''א 35": "TA35.TA", "ת''א 125": "TA125.TA", "בנקים": "PIBK5.TA",
        "נפט": "CL=F", "זהב": "GC=F", "נחושת": "HG=F", "כסף": "SI=F"
    }
    results = {}
    for name, sym in tickers.items():
        try:
            ticker = yf.Ticker(sym)
            data = ticker.history(period="1d")
            if not data.empty:
                current = data['Close'].iloc[-1]
                prev = data['Open'].iloc[-1]
                change = ((current - prev) / prev) * 100
                results[name] = (current, change)
        except:
            results[name] = (0.0, 0.0)
    return results

# --- 4. מבנה הלשוניות ---
tab_markets, tab_simulator, tab_chain = st.tabs(["🌍 שווקים גלובליים", "🧮 סימולטור אופציות", "⛓️ שרשרת אופציות"])

# --- לשונית שווקים (מתרעננת אוטומטית) ---
with tab_markets:
    market_placeholder = st.empty()
    
    # לולאת הרענון החי
    while True:
        with market_placeholder.container():
            live_data = get_live_data()
            
            st.subheader("🇺🇸 מדדי ארה\"ב")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("S&P 500", f"{live_data.get('S&P 500')[0]:,.2f}", f"{live_data.get('S&P 500')[1]:.2f}%")
            c2.metric("Nasdaq", f"{live_data.get('Nasdaq')[0]:,.2f}", f"{live_data.get('Nasdaq')[1]:.2f}%")
            c3.metric("Russell 2000", f"{live_data.get('Russell 2000')[0]:,.2f}", f"{live_data.get('Russell 2000')[1]:.2f}%")
            c4.metric("VIX", f"{live_data.get('VIX')[0]:,.2f}", f"{live_data.get('VIX')[1]:.2f}%", delta_color="inverse")

            st.divider()
            st.subheader("🇮🇱 בורסת תל אביב")
            i1, i2, i3 = st.columns(3)
            i1.metric("ת''א 35", f"{live_data.get('ת''א 35')[0]:,.2f}", f"{live_data.get('ת''א 35')[1]:.2f}%")
            i2.metric("ת''א 125", f"{live_data.get('ת''א 125')[0]:,.2f}", f"{live_data.get('ת''א 125')[1]:.2f}%")
            i3.metric("מדד הבנקים", f"{live_data.get('בנקים')[0]:,.2f}", f"{live_data.get('בנקים')[1]:.2f}%")

            st.divider()
            st.subheader("🏗️ סחורות")
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("זהב", f"{live_data.get('זהב')[0]:,.2f}", f"{live_data.get('זהב')[1]:.2f}%")
            s2.metric("נפט", f"{live_data.get('נפט')[0]:,.2f}", f"{live_data.get('נפט')[1]:.2f}%")
            s3.metric("נחושת", f"{live_data.get('נחושת')[0]:,.2f}", f"{live_data.get('נחושת')[1]:.2f}%")
            s4.metric("כסף", f"{live_data.get('כסף')[0]:,.2f}", f"{live_data.get('כסף')[1]:.2f}%")

        time.sleep(refresh_rate)
        st.rerun() # פקודה שמרעננת רק את הנתונים

# --- לשונית סימולטור (בנפרד) ---
with tab_simulator:
    st.header("🧮 סימולטור מחיר ואסטרטגיה")
    col_in, col_out = st.columns([1, 2])
    
    with col_in:
        S = st.number_input("מחיר נכס בסיס", value=2100.0)
        K = st.number_input("מחיר מימוש (Strike)", value=2100.0)
        T = st.slider("ימים לפקיעה", 1, 120, 30) / 365
        sigma = st.slider("תנודתיות (IV %)", 5, 100, 20) / 100
        r = 0.045
        
    d1 = (np.log(S/K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    call_p = (S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    put_p = (K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))
    
    with col_out:
        res1, res2 = st.columns(2)
        res1.metric("מחיר CALL תיאורטי", f"₪{call_p*100:,.0f}")
        res2.metric("מחיר PUT תיאורטי", f"₪{put_p*100:,.0f}")
        
        # גרף Payoff פשוט
        x = np.linspace(S*0.8, S*1.2, 100)
        y = np.maximum(x - K, 0) - call_p
        st.line_chart(pd.DataFrame({'Price': x, 'Profit': y}).set_index('Price'))

# --- לשונית שרשרת אופציות ---
with tab_chain:
    st.subheader("⛓️ שרשרת אופציות חיה (FMR Style)")
    # כאן נכנס הקוד של הטבלה הצבעונית מהשלבים הקודמים...
    st.write("הטבלה מתעדכנת לפי המדד החי בלשונית הראשונה.")
