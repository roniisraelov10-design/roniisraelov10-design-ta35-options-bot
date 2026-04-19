import streamlit as st
import pandas as pd
import numpy as np

# הגדרות עמוד
st.set_page_config(page_title="בוט אופציות ת"א 35", layout="wide")

st.title("🤖 מערכת ניהול אופציות מעו"ף - ת"א 35")

# סימולציה של נתוני שוק (בהמשך נחבר ל-API)
index_price = 2050.50
st.sidebar.metric("מדד ת"א 35", f"{index_price}", "0.45%")

# פונקציה פשוטה לחישוב יווניות (לצורכי תצוגה)
def calculate_greeks(strike, type="Call"):
    delta = 0.5 if type == "Call" else -0.5
    theta = -0.8
    return delta, theta

# יצירת נתונים לטבלת אופציות
strikes = [2000, 2020, 2040, 2060, 2080, 2100]
data = []

for s in strikes:
    d_c, t_c = calculate_greeks(s, "Call")
    d_p, t_p = calculate_greeks(s, "Put")
    data.append({
        "Strike": s,
        "Call Delta": d_c,
        "Call Theta": t_c,
        "Put Delta": d_p,
        "Put Theta": t_p
    })

df = pd.DataFrame(data)

# תצוגה למשתמש
st.subheader("📊 לוח אופציות (Option Chain) ויווניות")
st.table(df)

st.info("💡 הערה: הנתונים כרגע הם סימולציה. בשלב הבא נחבר אותם לנתוני אמת.")
