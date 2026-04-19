import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import norm
import yfinance as yf

# --- 1. הגדרות תצוגה ---
st.set_page_config(page_title="Professional Trading Terminal", layout="wide")

st.markdown("""
<style>
    body { direction: rtl; text-align: right; }
    .top-panel {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 5px;
        border-top: 4px solid #1f77b4;
        display: flex;
        justify-content: space-between;
        font-size: 16px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. יצירת הלשוניות (Tabs) ---
tab_market, tab_chain = st.tabs(["📈 ישראל - שוק ההון וסימולטור", "⛓️ שרשרת אופציות (FMR)"])

# ==========================================
# לשונית 1: התוספת החדשה (Investing + סימולטור)
# ==========================================
with tab_market:
    st.subheader("ישראל - שוק ההון (נתונים חיים)")
    
    @st.cache_data(ttl=60)
    def fetch_investing_data():
        tickers = {"ת''א 35": "TA35.TA", "ת''א-125": "TA125.TA", "USD/ILS": "ILS=X", "EUR/ILS": "EURILS=X", "זהב": "GC=F"}
        res = []
        for name, sym in tickers.items():
            try:
                h = yf.Ticker(sym).history(period="2d")
                c, p = h['Close'].iloc[-1], h['Close'].iloc[-2]
                res.append({"שם": name, "שער אחרון": c, "שינוי %": ((c-p)/p)*100})
            except:
                res.append({"שם": name, "שער אחרון": 0.0, "שינוי %": 0.0})
        return res

    inv_data = fetch_investing_data()
    
    # שורת המדדים העליונה (כמו בתמונה)
    m_cols = st.columns(5)
    for i, item in enumerate(inv_data):
        m_cols[i].metric(item["שם"], f"{item['שער אחרון']:,.2f}", f"{item['שינוי %']:.2f}%")
        
    st.divider()
    
    # סימולטור אופציות מתחת לנתונים
    st.subheader("🧮 סימולטור אופציות מדויק")
    col_input, col_results = st.columns([1, 2])
    
    # הזרקת מחיר ת"א 35 הנוכחי ישירות לסימולטור
    spot_ta35 = next((item["שער אחרון"] for item in inv_data if item["שם"] == "ת''א 35"), 2085.0)
    if spot_ta35 == 0: spot_ta35 = 2085.0

    with col_input:
        S_sim = st.number_input("נכס בסיס (Spot)", value=float(spot_ta35), step=10.0)
        K_sim = st.number_input("סטרייק (Strike)", value=float(round(spot_ta35/10)*10), step=10.0)
        days_sim = st.slider("ימים לפקיעה", 1, 90, 5)
        iv_sim = st.slider("תנודתיות גלומה (IV %)", 10, 80, 18) / 100.0
        opt_type_sim = st.radio("סוג אופציה:", ["Call", "Put"])

    with col_results:
        # פונקציה פנימית לחישוב בלאק-שולס
        T_sim = days_sim / 365.0
        r_sim = 0.045
        d1_sim = (np.log(S_sim/K_sim) + (r_sim + 0.5 * iv_sim**2) * T_sim) / (iv_sim * np.sqrt(T_sim))
        d2_sim = d1_sim - iv_sim * np.sqrt(T_sim)
        
        if opt_type_sim == "Call":
            price_sim = S_sim * norm.cdf(d1_sim) - K_sim * np.exp(-r_sim * T_sim) * norm.cdf(d2_sim)
            delta_sim = norm.cdf(d1_sim)
        else:
            price_sim = K_sim * np.exp(-r_sim * T_sim) * norm.cdf(-d2_sim) - S_sim * norm.cdf(-d1_sim)
            delta_sim = norm.cdf(d1_sim) - 1
            
        st.write(f"**תוצאות מדוייקות ({opt_type_sim}):**")
        r1, r2 = st.columns(2)
        r1.metric("מחיר תיאורטי (₪)", f"₪{(price_sim*100):,.0f}")
        r2.metric("דלתא (Δ)", f"{delta_sim:.3f}")


# ==========================================
# לשונית 2: שרשרת האופציות הקיימת שלך (בדיוק כפי שהייתה)
# ==========================================
with tab_chain:
    st.title("שרשרת אופציות מקצועית (Option Chain)")

    # פונקציה חדשה שמושכת את הנתון האמיתי במקום המספר הקבוע
    @st.cache_data(ttl=60)
    def get_ta35_spot():
        try:
            val = yf.Ticker("TA35.TA").history(period="1d")['Close'].iloc[-1]
            return val if val > 0 else 4406.32
        except:
            return 4406.32

    S = get_ta35_spot()
    T = 5 / 365.0
    r = 0.045
    sigma = 0.18
    
    # בניית סטרייקים לפי המדד החי
    base_strike = round(S / 10) * 10
    strikes = np.arange(base_strike - 50, base_strike + 60, 10)

    st.markdown(f"""
    <div class='top-panel'>
        <div><b>נכס בסיס:</b> ת"א-35</div>
        <div><b>שוק:</b> {S:,.2f}</div>
        <div><b>ימים לפקיעה:</b> 5</div>
        <div><b>רווח והפסד יומי:</b> ₪0</div>
        <div><b>שווי נוכחי בש"ח:</b> ₪7,535.9</div>
    </div>
    """, unsafe_allow_html=True)

    data = []
    for K in strikes:
        d1 = (np.log(S/K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        c_price = (S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)) * 100
        p_price = (K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)) * 100

        spread = 20
        data.append({
            "כמות (C)": np.random.randint(1, 15),
            "ביקוש (C)": max(10, int(c_price - spread)),
            "היצע (C)": int(c_price + spread),
            "תיאורטי (C)": int(c_price),
            "סטרייק": K,
            "תיאורטי (P)": int(p_price),
            "ביקוש (P)": max(10, int(p_price - spread)),
            "היצע (P)": int(p_price + spread),
            "כמות (P)": np.random.randint(1, 15)
        })

    df = pd.DataFrame(data)

    def style_dataframe(row):
        colors = [''] * len(row)
        cols = df.columns
        for i, col in enumerate(cols):
            if col == "סטרייק": colors[i] = 'background-color: #d3d3d3; font-weight: bold; color: black;'
            elif 'ביקוש' in col: colors[i] = 'color: #10b981; font-weight: bold;'
            elif 'היצע' in col: colors[i] = 'color: #ef4444; font-weight: bold;'
            else: colors[i] = 'color: #3b82f6;'
        return colors

    styled_df = df.style.apply(style_dataframe, axis=1)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)
