import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import norm
import yfinance as yf

# --- 1. הגדרות תצוגה ---
st.set_page_config(page_title="Global Multi-Market Terminal", layout="wide")

# --- ניהול מצב שפה ועיצוב ---
if 'lang' not in st.session_state: st.session_state.lang = 'HE'
if 'theme' not in st.session_state: st.session_state.theme = 'Black'

# --- מילון תרגומים רב-לשוני ---
translations = {
    'HE': {
        'dir': 'rtl', 'us_market': '🇺🇸 שוק ארה"ב', 'il_market': '🇮🇱 שוק ישראל', 'commodities': '🏗️ סחורות',
        'sim': '🧮 סימולטור אופציות', 'chain': '⛓️ שרשרת אופציות', 'course': '🎓 הרשמה לקורס',
        'spot': 'נכס בסיס', 'strike': 'סטרייק', 'dte': 'ימים לפקיעה', 'iv': 'תנודתיות גלומה',
        'gold': 'זהב', 'oil': 'נפט', 'copper': 'נחושת', 'silver': 'כסף', 'banks': 'בנקים', 'tech': 'טכנולוגיה'
    },
    'EN': {
        'dir': 'ltr', 'us_market': '🇺🇸 US Market', 'il_market': '🇮🇱 Israel Market', 'commodities': '🏗️ Commodities',
        'sim': '🧮 Options Simulator', 'chain': '⛓️ Option Chain', 'course': '🎓 Course Signup',
        'spot': 'Spot Price', 'strike': 'Strike', 'dte': 'DTE', 'iv': 'Implied Volatility',
        'gold': 'Gold', 'oil': 'Crude Oil', 'copper': 'Copper', 'silver': 'Silver', 'banks': 'Banks', 'tech': 'Tech'
    },
    'RU': {
        'dir': 'ltr', 'us_market': '🇺🇸 Рынок США', 'il_market': '🇮🇱 Рынок Израиля', 'commodities': '🏗️ Товары',
        'sim': '🧮 Симулятор опционов', 'chain': '⛓️ Цепочка опционов', 'course': '🎓 Запись על курс',
        'spot': 'Цена актива', 'strike': 'Страйк', 'dte': 'Дней до эксп.', 'iv': 'Волатильность',
        'gold': 'Золото', 'oil': 'Нефть', 'copper': 'Медь', 'silver': 'Серебро', 'banks': 'Банки', 'tech': 'Технологии'
    }
}

L = translations[st.session_state.lang]

# --- הגדרות צבעים (שחור, לבן, ירוק) ---
themes = {
    'Black': {"bg": "#0e1117", "text": "#ffffff", "card": "#1f2937", "chart": "plotly_dark"},
    'White': {"bg": "#ffffff", "text": "#000000", "card": "#f0f2f6", "chart": "plotly_white"},
    'Green': {"bg": "#001a00", "text": "#00ff00", "card": "#003300", "chart": "plotly_dark"}
}
current_theme = themes[st.session_state.theme]

st.markdown(f"""
<style>
    .stApp {{ background-color: {current_theme['bg']}; color: {current_theme['text']}; direction: {L['dir']}; }}
    .stMetric {{ background-color: {current_theme['card']}; padding: 15px; border-radius: 10px; border: 1px solid {current_theme['text'] if st.session_state.theme == 'Green' else 'transparent'}; }}
    h1, h2, h3, p, span {{ color: {current_theme['text']} !important; }}
</style>
""", unsafe_allow_html=True)

# --- סרגל צד לשליטה ---
with st.sidebar:
    st.session_state.lang = st.selectbox("Language / שפה / Язык", ['HE', 'EN', 'RU'], index=['HE', 'EN', 'RU'].index(st.session_state.lang))
    st.session_state.theme = st.radio("Theme / צבע", ['Black', 'White', 'Green'], index=['Black', 'White', 'Green'].index(st.session_state.theme))
    st.divider()
    st.subheader(L['course'])
    with st.form("course_form"):
        st.text_input("Name")
        st.text_input("Phone")
        st.form_submit_button("Send")

# --- פונקציית נתונים מרכזית ---
@st.cache_data(ttl=60)
def fetch_market_data(tickers):
    res = {}
    for name, sym in tickers.items():
        try:
            h = yf.Ticker(sym).history(period="2d")
            c, p = h['Close'].iloc[-1], h['Close'].iloc[-2]
            res[name] = {"price": c, "change": ((c-p)/p)*100}
        except:
            res[name] = {"price": 0.0, "change": 0.0}
    return res

# --- חלוקה ללשוניות ---
tab_us, tab_il, tab_comm, tab_sim, tab_chain = st.tabs([L['us_market'], L['il_market'], L['commodities'], L['sim'], L['chain']])

# --- לשונית ארה"ב ---
with tab_us:
    us_tickers = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Russell 2000": "^RUT", "VIX": "^VIX"}
    data = fetch_market_data(us_tickers)
    cols = st.columns(4)
    for i, (name, val) in enumerate(data.items()):
        cols[i].metric(name, f"{val['price']:,.2f}", f"{val['change']:.2f}%")

# --- לשונית ישראל ---
with tab_il:
    il_tickers = {"ת''א 35": "TA35.TA", "ת''א 125": "TA125.TA", L['banks']: "PIBK5.TA", L['tech']: "TA-TECH.TA", "VTA35": "VTA35.TA"}
    data = fetch_market_data(il_tickers)
    cols = st.columns(5)
    for i, (name, val) in enumerate(data.items()):
        cols[i].metric(name, f"{val['price']:,.2f}", f"{val['change']:.2f}%")

# --- לשונית סחורות ---
with tab_comm:
    comm_tickers = {L['gold']: "GC=F", L['oil']: "CL=F", L['copper']: "HG=F", L['silver']: "SI=F"}
    data = fetch_market_data(comm_tickers)
    cols = st.columns(4)
    for i, (name, val) in enumerate(data.items()):
        cols[i].metric(name, f"{val['price']:,.2f}", f"{val['change']:.2f}%")

# --- לשונית סימולטור (הקוד הקודם שלך משולב) ---
with tab_sim:
    st.subheader(L['sim'])
    col_in, col_res = st.columns([1, 2])
    with col_in:
        spot = st.number_input(L['spot'], value=2100.0)
        strike = st.number_input(L['strike'], value=2100.0)
        days = st.slider(L['dte'], 1, 90, 5)
        iv = st.slider(L['iv'], 10, 80, 20) / 100
        
    # חישוב בלאק-שולס
    T = days / 365.0
    d1 = (np.log(spot/strike) + (0.045 + 0.5 * iv**2) * T) / (iv * np.sqrt(T))
    d2 = d1 - iv * np.sqrt(T)
    call_price = (spot * norm.cdf(d1) - strike * np.exp(-0.045 * T) * norm.cdf(d2)) * 100
    
    with col_res:
        st.metric("Theoretical Call Price", f"₪{call_price:,.0f}")

# --- לשונית שרשרת אופציות (העיצוב הבנקאי שלך) ---
with tab_chain:
    st.subheader(L['chain'])
    # כאן נשאר הקוד של הטבלה הצבעונית (FMR Style)
    strikes = np.arange(round(spot/10)*10 - 50, round(spot/10)*10 + 60, 10)
    chain_data = []
    for k in strikes:
        chain_data.append({"Bid (C)": 100, "Ask (C)": 110, "Strike": k, "Bid (P)": 90, "Ask (P)": 100})
    st.table(pd.DataFrame(chain_data))
