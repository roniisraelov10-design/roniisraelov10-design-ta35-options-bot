import streamlit as st

# הגדרות עמוד
st.set_page_config(page_title="TA35 Bot", layout="wide")

# נתוני בסיס
if 'market_data' not in st.session_state:
    st.session_state.market_data = {'underlying_price': 2000}

st.title("TA-35 Options Bot")

# הצגת נתון מרכזי
st.metric(
    label="TA-35 Index",
    value=f"{st.session_state.market_data['underlying_price']}",
    delta=None
)

st.success("The app is running! We can now add more features safely.")
