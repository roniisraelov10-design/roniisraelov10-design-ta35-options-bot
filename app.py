import streamlit as st
import pandas as pd

# הגדרות עמוד - שים לב לשימוש בגרש בודד למניעת שגיאות
st.set_page_config(page_title='בוט אופציות תא 35', layout='wide')

st.title('🤖 בוט אופציות מדד תא 35')

# נתוני שוק בסיסיים
underlying = 2000
st.metric(label='מדד תא 35', value=underlying)

st.subheader('📊 טבלת אופציות (סימולציה)')

# יצירת טבלה בסיסית כדי שהאתר יראה מקצועי
data = {
    'Strike': [1950, 1980, 2000, 2020, 2050],
    'Call Price': [6500, 4200, 2800, 1500, 600],
    'Put Price': [400, 900, 2800, 4500, 7200],
    'Delta': [0.85, 0.65, 0.50, 0.35, 0.15]
}
df = pd.DataFrame(data)
st.table(df)

st.success('האתר מחובר ופועל! כעת נשאר רק לחבר נתונים חיים.')
