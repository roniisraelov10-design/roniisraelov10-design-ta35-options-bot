import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# --- הגדרות עמוד ---
st.set_page_config(page_title="Pro Options Terminal", layout="wide")

# --- ניהול מצב (Session State) לשפה ועיצוב ---
if 'lang' not in st.session_state: st.session_state.lang = 'he'
if 'theme' not in st.session_state: st.session_state.theme = 'dark'

# --- מילון תרגומים (דו-לשוני) ---
t = {
    'he': {
        'title': "🖥️ עמדת מסחר מתקדמת - אופציות ת\"א",
        'indices': "📊 מדדי הבורסה",
        'ta35': "ת\"א 35", 'ta125': "ת\"א 125", 'banks': "מדד הבנקים", 'tech': "מדד הטכנולוגיה", 'vix': "VTA35 (פחד)",
        'sim_title': "🧮 סימולטור אופציות (Payoff)",
        'spot': "מחיר מדד", 'strike_short': "סטרייק כתיבה", 'strike_long': "סטרייק קנייה", 'premium': "פרמיה נטו (₪)",
        'news_title': "📰 עדכוני שוק",
        'news_1': "הבורסה בתל אביב נסגרת בעליות שערים בהובלת מניות הבנקים.",
        'news_2': "בנק ישראל צפוי להודיע על החלטת הריבית מחר בשעה 16:00.",
        'news_3': "תנודתיות בשוק האופציות לקראת פקיעת החוזים השבועית."
    },
    'en': {
        'title': "🖥️ Pro Options Trading Terminal",
        'indices': "📊 Market Indices",
        'ta35': "TA-35", 'ta125': "TA-125", 'banks': "Banks 5", 'tech': "TA-Technology", 'vix': "VTA35 (Volatility)",
        'sim_title': "🧮 Options Payoff Simulator",
        'spot': "Spot Price", 'strike_short': "Short Strike", 'strike_long': "Long Strike", 'premium': "Net Premium (₪)",
        'news_title': "📰 Market News",
        'news_1': "Tel Aviv Stock Exchange closes higher led by the banking sector.",
        'news_2': "Bank of Israel expected to announce interest rate decision tomorrow.",
        'news_3': "High volatility in the options market ahead of weekly expiration."
    }
}
lang = st.session_state.lang
texts = t[lang]

# --- כפתורי שליטה (שפה ומצב תצוגה) ---
col_t1, col_t2, col_t3 = st.columns([1, 1, 8])
with col_t1:
    if st.button("🌐 HE / EN"):
        st.session_state.lang = 'en' if st.session_state.lang == 'he' else 'he'
        st.rerun()
with col_t2:
    if st.button("🌓 Dark / Light"):
        st.session_state.theme = 'light' if st.session_state.theme == 'dark' else 'dark'
        st.rerun()

# --- הזרקת עיצוב (CSS) לפי המצב שנבחר ---
if st.session_state.theme == 'dark':
    bg_color, text_color, plot_template = "#0e1117", "#fafafa", "plotly_dark"
else:
    bg_color, text_color, plot_template = "#f8f9fa", "#1e1e1e", "plotly_white"

dir_css = "rtl" if lang == 'he' else "ltr"
align_css = "right" if lang == 'he' else "left"

st.markdown(f"""
<style>
    .stApp {{ background-color: {bg_color}; }}
    body, p, h1, h2, h3, h4, h5, h6, span, div {{ 
        direction: {dir_css}; 
        text-align: {align_css}; 
        color: {text_color} !important; 
    }}
    .stMetric {{ background-color: rgba(128,128,128,0.1); padding: 15px; border-radius: 10px; }}
    div[data-testid="stMetricValue"] {{ font-size: 1.8rem; font-weight: bold; }}
</style>
""", unsafe_allow_html=True)

st.title(texts['title'])
st.divider()

# --- פס המדדים ---
st.subheader(texts['indices'])
i1, i2, i3, i4, i5 = st.columns(5)
# נתוני סימולציה לעיצוב (מספר חיובי = חץ ירוק, שלילי = חץ אדום)
with i1: st.metric(texts['ta35'], "2,085.40", "1.2%")
with i2: st.metric(texts['ta125'], "2,110.20", "0.8%")
with i3: st.metric(texts['banks'], "4,250.00", "2.1%")
with i4: st.metric(texts['tech'], "615.30", "-0.5%")
with i5: st.metric(texts['vix'], "14.50", "-3.2%")

st.divider()

# --- סימולטור ופיד חדשות (פריסה לשני טורים) ---
if lang == 'he':
    col_main, col_side = st.columns([7, 3]) # סימולטור מימין, חדשות משמאל
else:
    col_side, col_main = st.columns([3, 7]) # הפוך לאנגלית

with col_main:
    st.subheader(texts['sim_title'])
    
    # אזור הזנת נתונים
    c1, c2, c3, c4 = st.columns(4)
    with c1: spot = st.number_input(texts['spot'], value=2085, step=10)
    with c2: short_k = st.number_input(texts['strike_short'], value=2000, step=10)
    with c3: long_k = st.number_input(texts['strike_long'], value=1950, step=10)
    with c4: prem = st.number_input(texts['premium'], value=250, step=10)

    # חישוב גרף פקיעה (Bull Put Spread)
    prices = np.linspace(spot * 0.85, spot * 1.15, 100)
    pnl = []
    for p in prices:
        pnl_short = max(short_k - p, 0)
        pnl_long = max(long_k - p, 0)
        net = prem - (pnl_short - pnl_long) * 100 # מכפיל 100 לאופציות ת"א
        pnl.append(net)

    # שרטוט הגרף
    fig = go.Figure()
    # צבע ירוק לרווח, אדום להפסד
    fig.add_trace(go.Scatter(x=prices, y=pnl, fill='tozeroy', name='PnL', line=dict(color='#10b981' if prem > 0 else '#ef4444')))
    fig.add_hline(y=0, line_dash="solid", line_color="gray") # קו האפס
    fig.add_vline(x=spot, line_dash="dot", line_color="#3b82f6", annotation_text="מחיר נוכחי")
    
    fig.update_layout(
        template=plot_template, 
        margin=dict(l=20, r=20, t=30, b=20), 
        height=400,
        xaxis_title="מדד בפקיעה",
        yaxis_title="רווח/הפסד (₪)"
    )
    st.plotly_chart(fig, use_container_width=True)

with col_side:
    st.subheader(texts['news_title'])
    st.info(texts['news_1'])
    st.warning(texts['news_2'])
    st.success(texts['news_3'])
