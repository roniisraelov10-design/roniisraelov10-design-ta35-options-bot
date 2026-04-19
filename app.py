import streamlit as st

# הגדרות עמוד
st.set_page_config(page_title="בוט אופציות תא 35", layout="wide")

# נתוני דמה כדי שהאתר יעלה
if 'market_data' not in st.session_state:
    st.session_state.market_data = {'underlying_price': 2000}

st.title("🤖 בוט אופציות ת"א 35")

# --- הצגת נתונים ---
col1, col2 = st.columns(2)

with col1:
    st.metric(
        label="מדד תא 35",
        value=f"{st.session_state.market_data['underlying_price']}",
        delta=None
    )

st.success("המערכת מחוברת! כעת ניתן להמשיך להוסיף לוגיקה.")
