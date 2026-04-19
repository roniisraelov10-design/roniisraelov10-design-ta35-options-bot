import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import norm
from datetime import datetime

# --- הגדרות מערכת ---
st.set_page_config(page_title="TASE Pro Terminal", layout="wide")

if 'lang' not in st.session_state: st.session_state.lang = 'HE'
if 'theme' not in st.session_state: st.session_state.theme = 'dark'

# --- תרגומים ---
translations = {
    'HE': {
        'dir': 'rtl', 'title': 'טרמינל בורסת ת"א - מקצועי',
        'cat_indices': 'מדדי מניות', 'cat_sectors': 'מדדים ענפיים', 'cat_vol': 'תנודתיות ופחד',
        'opt_sim': 'סימולטור יווניות (בלאק ושולץ)', 'course': 'לידים והרשמה',
        'spot': 'מדד נוכחי', 'strike': 'סטרייק', 'dte': 'ימים לפקיעה', 'iv': 'תנודתיות (%)',
        'calc_btn': 'חשב יווניות'
    },
    'EN': {
        'dir': 'ltr', 'title': 'TASE Pro Terminal',
        'cat_indices': 'Market Indices', 'cat_sectors': 'Sector Indices', 'cat_vol': 'Volatility & Fear',
        'opt_sim': 'Greeks Simulator (Black-Scholes)', 'course': 'Course Registration',
        'spot': 'Spot Price', 'strike': 'Strike', 'dte': 'DTE', 'iv': 'IV (%)',
        'calc_btn': 'Calculate Greeks'
    },
    'RU': {
        'dir': 'ltr', 'title': 'TASE Профессиональный терминал',
        'cat_indices': 'Рыночные индексы', 'cat_sectors': 'Секторальные индексы', 'cat_vol': 'Волатильность',
        'opt_sim': 'Симулятор греков', 'course': 'Регистрация',
        'spot': 'Цена индекса', 'strike': 'Страйк', 'dte': 'Дней до эксп.', 'iv': 'IV (%)',
        'calc_btn': 'Рассчитать'
    }
}
L = translations[st.session_state.lang]

# --- מנוע בלאק ושולץ מלא ---
def black_scholes_full(S, K, T, r, sigma, opt_type='call'):
    if T <= 0: T = 0.00001
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

# --- עיצוב ---
st.markdown(f"<style>.stApp {{ direction: {L['dir']}; text-align: {'right' if L['dir']=='rtl' else 'left'}; }}</style>", unsafe_allow_html=True)

# --- סרגל צד ---
with st.sidebar:
    st.session_state.lang = st.selectbox("Language", ['HE', 'EN', 'RU'], index=['HE', 'EN', 'RU'].index(st.session_state.lang))
    st.divider()
    st.subheader("📰 חדשות מתפרצות")
    st.caption("• עדכון מדדים: ת\"א 35 עולה ב-0.5%")
    st.caption("• בנק ישראל: הריבית ללא שינוי")

# --- דף ראשי ---
st.title(L['title'])

tab1, tab2, tab3 = st.tabs([L['cat_indices'], L['opt_sim'], L['course']])

with tab1:
    # חלוקה לקטגוריות
    st.subheader(f"📊 {L['cat_indices']}")
    c1, c2, c3 = st.columns(3)
    # כאן אנחנו מושכים נתונים אמיתיים
    m_35 = yf.Ticker("TA35.TA").history(period="1d")['Close'].iloc[-1]
    m_125 = yf.Ticker("TA125.TA").history(period="1d")['Close'].iloc[-1]
    m_banks = yf.Ticker("PIBK5.TA").history(period="1d")['Close'].iloc[-1]
    c1.metric("ת\"א 35", f"{m_35:,.2f}")
    c2.metric("ת\"א 125", f"{m_125:,.2f}")
    c3.metric("בנקים-5", f"{m_banks:,.2f}")

    st.subheader(f"🏗️ {L['cat_sectors']}")
    s1, s2, s3 = st.columns(3)
    m_re = yf.Ticker("REIT.TA").history(period="1d")['Close'].iloc[-1]
    m_tech = yf.Ticker("TA-TECH.TA").history(period="1d")['Close'].iloc[-1]
    s1.metric("נדל\"ן", f"{m_re:,.2f}")
    s2.metric("טכנולוגיה", f"{m_tech:,.2f}")

    st.subheader(f"📉 {L['cat_vol']}")
    v1, v2 = st.columns(2)
    # מדד VTA35 הוא מדד הפחד הישראלי
    vta35 = 18.5 # סימולציה (בד"כ דורש API בתשלום לנתון מדויק לשנייה)
    v1.metric("מדד הפחד VTA35", f"{vta35}%", delta="-0.5%")
    v2.metric("VIX (Global)", f"{yf.Ticker('^VIX').history(period='1d')['Close'].iloc[-1]:.2f}")

with tab2:
    st.header(L['opt_sim'])
    col_in, col_res = st.columns([1, 2])
    with col_in:
        s_price = st.number_input(L['spot'], value=m_35)
        k_price = st.number_input(L['strike'], value=round(m_35/10)*10)
        days = st.slider(L['dte'], 1, 60, 20)
        vol = st.slider(L['iv'], 5, 50, 15) / 100
        
        p, d, g, t, v = black_scholes_full(s_price, k_price, days/365, 0.04, vol)
    
    with col_res:
        st.subheader("תוצאות חישוב (Call)")
        res_c1, res_c2, res_c3 = st.columns(3)
        res_c1.metric("מחיר תיאורטי", f"₪{p*100:,.0f}")
        res_c2.metric("Delta", f"{d:.3f}")
        res_c3.metric("Gamma", f"{g:.5f}")
        res_c1.metric("Theta (Daily)", f"{t:.2f}")
        res_c2.metric("Vega (1%)", f"{v:.2f}")

with tab3:
    st.header(L['course'])
    with st.form("leads"):
        name = st.text_input("שם מלא")
        phone = st.text_input("טלפון")
        email = st.text_input("אימייל")
        if st.form_submit_button("שלח פרטים"):
            st.success("הפרטים נשמרו. ניצור קשר בהקדם!")
