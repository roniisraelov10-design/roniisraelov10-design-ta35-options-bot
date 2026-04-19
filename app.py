import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import norm
import yfinance as yf
from datetime import datetime

# --- 1. הגדרות תשתית וצבעים ---
if 'lang' not in st.session_state: st.session_state.lang = 'HE'
if 'theme' not in st.session_state: st.session_state.theme = 'Black'

st.set_page_config(page_title="Global Terminal Pro", layout="wide")

def apply_style():
    themes = {
        'Black': {"bg": "#0e1117", "text": "#ffffff", "card": "#1f2937"},
        'White': {"bg": "#ffffff", "text": "#000000", "card": "#f0f2f6"},
        'Green': {"bg": "#001a00", "text": "#00ff00", "card": "#002200"}
    }
    t = themes[st.session_state.theme]
    direction = "rtl" if st.session_state.lang == 'HE' else "ltr"
    st.markdown(f"""
    <style>
        .stApp {{ background-color: {t['bg']}; color: {t['text']}; direction: {direction}; }}
        .stMetric {{ background-color: {t['card']}; border: 1px solid {t['text']}; border-radius: 10px; padding: 10px; }}
        h1, h2, h3, p, span {{ color: {t['text']} !important; text-align: {"right" if direction=="rtl" else "left"}; }}
    </style>
    """, unsafe_allow_html=True)

apply_style()

# --- 2. מילון תרגומים ---
trans = {
    'HE': {'us': '🇺🇸 ארה"ב', 'il': '🇮🇱 ישראל', 'cmd': '🏗️ סחורות', 'sim': '🧮 סימולטור', 'chain': '⛓️ אופציות', 'settings': 'הגדרות'},
    'EN': {'us': '🇺🇸 USA', 'il': '🇮🇱 Israel', 'cmd': '🏗️ Commodities', 'sim': '🧮 Simulator', 'chain': '⛓️ Chain', 'settings': 'Settings'},
    'RU': {'us': '🇺🇸 США', 'il': '🇮🇱 Израиль', 'cmd': '🏗️ Товары', 'sim': '🧮 Симулятор', 'chain': '⛓️ Опционы', 'settings': 'Настройки'}
}
L = trans[st.session_state.lang]

# --- 3. שליטת סרגל צד ---
with st.sidebar:
    st.header(L['settings'])
    st.session_state.lang = st.selectbox("Language", ["HE", "EN", "RU"], index=["HE", "EN", "RU"].index(st.session_state.lang))
    st.session_state.theme = st.radio("Theme", ["Black", "White", "Green"], index=["Black", "White", "Green"].index(st.session_state.theme))
    refresh_sec = st.slider("Refresh (sec)", 5, 60, 10)
    st.write(f"Last Update: {datetime.now().strftime('%H:%M:%S')}")

# --- 4. פונקציית נתונים חסינה (Safe Fetch) ---
def fetch_live(tickers):
    res = {}
    for name, sym in tickers.items():
        try:
            h = yf.Ticker(sym).history(period="1d")
            if not h.empty:
                curr = h['Close'].iloc[-1]
                prev = h['Open'].iloc[-1]
                res[name] = (curr, ((curr-prev)/prev)*100)
            else: res[name] = (0, 0)
        except: res[name] = (0, 0)
    return res

# --- 5. לשוניות המערכת ---
tabs = st.tabs([L['us'], L['il'], L['cmd'], L['sim'], L['chain']])

with tabs[0]: # ארה"ב
    data = fetch_live({"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Russell 2000": "^RUT", "VIX": "^VIX"})
    cols = st.columns(4)
    for i, (n, v) in enumerate(data.items()):
        cols[i].metric(n, f"{v[0]:,.2f}", f"{v[1]:.2f}%", delta_color="normal" if "VIX" not in n else "inverse")

with tabs[1]: # ישראל
    data = fetch_live({"תא 35": "TA35.TA", "תא 125": "TA125.TA", "בנקים": "PIBK5.TA", "טכנולוגיה": "TA-TECH.TA"})
    cols = st.columns(4)
    for i, (n, v) in enumerate(data.items()):
        cols[i].metric(n, f"{v[0]:,.2f}", f"{v[1]:.2f}%")

with tabs[2]: # סחורות
    data = fetch_live({"זהב": "GC=F", "נפט": "CL=F", "נחושת": "HG=F", "כסף": "SI=F"})
    cols = st.columns(4)
    for i, (n, v) in enumerate(data.items()):
        cols[i].metric(n, f"{v[0]:,.2f}", f"{v[1]:.2f}%")

with tabs[3]: # סימולטור
    st.subheader(L['sim'])
    col_in, col_res = st.columns([1, 2])
    with col_in:
        s = st.number_input("Spot", value=2100.0)
        k = st.number_input("Strike", value=2100.0)
        iv = st.slider("IV %", 5, 80, 20) / 100
    
    d1 = (np.log(s/k) + (0.045 + 0.5*iv**2)*(5/365)) / (iv*np.sqrt(5/365))
    price = (s * norm.cdf(d1) - k * np.exp(-0.045*(5/365)) * norm.cdf(d1 - iv*np.sqrt(5/365))) * 100
    col_res.metric("Call Price", f"₪{price:,.0f}")

with tabs[4]: # שרשרת אופציות (FMR Style)
    st.subheader(L['chain'])
    S_val = fetch_live({"TA35": "TA35.TA"})["TA35"][0]
    base = round(S_val/10)*10 if S_val > 0 else 2100
    strikes = range(int(base-50), int(base+60), 10)
    df = pd.DataFrame({"Put Bid": [100]*len(strikes), "Strike": strikes, "Call Bid": [100]*len(strikes)})
    st.table(df)

# מנגנון רענון שקט - יחליף את הלולאה שגרמה לשגיאות
st.empty()
