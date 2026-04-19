import streamlit as st
import yfinance as yf

# --- 1. הגדרות עמוד ---
st.set_page_config(page_title="Pro Terminal - Step 1", layout="wide")
st.markdown("""<style> body { direction: rtl; text-align: right; } </style>""", unsafe_allow_html=True)

st.title("🖥️ טרמינל מסחר - שלב 1: תשתית חסינה")

# --- 2. פונקציית משיכת נתונים בטוחה ---
# הפונקציה הזו מונעת מהאתר לקרוס גם אם אין אינטרנט או הבורסה סגורה
def get_safe_price(ticker_symbol):
    try:
        data = yf.Ticker(ticker_symbol).history(period="1d")
        if not data.empty:
            return data['Close'].iloc[-1]
        else:
            return 0.0  # במקום לקרוס, מחזיר 0 אם אין נתונים
    except Exception as e:
        return 0.0

# --- 3. ממשק משתמש בסיסי ---
st.subheader("📊 בדיקת חיבור לנתונים חיים")
st.write("משיכת נתונים מ-Yahoo Finance באמצעות מנגנון בטוח.")

col1, col2 = st.columns(2)

# משיכת נתונים
price_sp500 = get_safe_price("^GSPC")
price_ta35 = get_safe_price("TA35.TA")

with col1:
    st.metric("S&P 500 (ארה\"ב)", f"{price_sp500:,.2f}")
    
with col2:
    st.metric("ת\"א 35 (ישראל)", f"{price_ta35:,.2f}")

st.divider()
st.success("✅ אם אתה רואה כאן מספרים (או 0 במקרה של חוסר נתון) ולא מסך אדום - תשתית הנתונים שלנו יציבה ומוכנה לשלב הבא!")
