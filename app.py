import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import norm

# --- 1. הגדרות תצוגה מרביות ---
st.set_page_config(page_title="Professional Option Chain", layout="wide")

st.markdown("""
<style>
    body { direction: rtl; text-align: right; }
    /* עיצוב הפאנל העליון שייראה כמו מערכת בנקאית */
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

st.title("שרשרת אופציות מקצועית (Option Chain)")

# --- 2. פאנל נתונים עליון (כמו בתמונה) ---
st.markdown("""
<div class='top-panel'>
    <div><b>נכס בסיס:</b> ת"א-35</div>
    <div><b>שוק:</b> 4,406.32</div>
    <div><b>ימים לפקיעה:</b> 5</div>
    <div><b>רווח והפסד יומי:</b> ₪0</div>
    <div><b>שווי נוכחי בש"ח:</b> ₪7,535.9</div>
</div>
""", unsafe_allow_html=True)

# --- 3. מנוע בלאק שולס וסימולציית שוק ---
S = 4406.32 # מחיר כמו בתמונה שלך
T = 5 / 365.0
r = 0.045
sigma = 0.18
strikes = np.arange(4370, 4460, 10)

data = []
for K in strikes:
    # חישוב תיאורטי
    d1 = (np.log(S/K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    c_price = (S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)) * 100
    p_price = (K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)) * 100

    # הוספת "רעש" כדי לייצר מחירי שוק (Bid/Ask)
    spread = 20
    
    data.append({
        "כמות ביקוש (C)": np.random.randint(1, 15),
        "לימט ביקוש (C)": max(10, int(c_price - spread)),
        "לימט היצע (C)": int(c_price + spread),
        "כמות היצע (C)": np.random.randint(1, 15),
        "תיאורטי (C)": int(c_price),
        "סטרייק": K,
        "תיאורטי (P)": int(p_price),
        "כמות ביקוש (P)": np.random.randint(1, 15),
        "לימט ביקוש (P)": max(10, int(p_price - spread)),
        "לימט היצע (P)": int(p_price + spread),
        "כמות היצע (P)": np.random.randint(1, 15)
    })

df = pd.DataFrame(data)

# --- 4. עיצוב צבעים לטבלה (כמו בתמונה) ---
def style_dataframe(row):
    # הפונקציה הזו צובעת את הסטרייק באפור, את הביקושים בירוק ואת ההיצע באדום
    colors = [''] * len(row)
    
    # מיפוי עמודות
    cols = df.columns
    for i, col in enumerate(cols):
        if col == "סטרייק":
            colors[i] = 'background-color: #d3d3d3; font-weight: bold; color: black;'
        elif 'ביקוש' in col:
            colors[i] = 'color: #10b981; font-weight: bold;' # ירוק
        elif 'היצע' in col:
            colors[i] = 'color: #ef4444; font-weight: bold;' # אדום
        else:
            colors[i] = 'color: #3b82f6;' # כחול לשאר
            
    return colors

# החלת העיצוב על ה-DataFrame
styled_df = df.style.apply(style_dataframe, axis=1)

# הצגת הטבלה המעוצבת על כל המסך
st.dataframe(styled_df, use_container_width=True, hide_index=True, height=400)

st.divider()
st.success("✅ שרשרת האופציות המקצועית באוויר! סטרייק באמצע, קול מימין, פוט משמאל, עם צבעי קנייה/מכירה.")
