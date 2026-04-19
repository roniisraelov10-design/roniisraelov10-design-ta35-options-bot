"""
DEPLOYMENT_GUIDE.md
==================
מדריך פריסה (Deployment) — העלאת TA35 Dashboard ל-Streamlit Cloud
עם הוראות כמו ללא-מתכנתים.

זמן משוער: 15 דקות
"""

# 🚀 מדריך פריסה — Streamlit Cloud

## שלב 0: דרישות מקדימות
אתה צריך:
- ✅ GitHub account (חינם)
- ✅ Streamlit Community Cloud account (חינם)
- ✅ ה-folder כל הקובץ שלנו מוכן

---

## שלב 1️⃣: יצירת GitHub Repository

### 1.1 — פתח GitHub
1. עבור ל-https://github.com
2. לחץ **Sign up** או התחבר עם החשבון שלך
3. אם זו הפעם הראשונה, אשר את ה-email שלך

### 1.2 — צור Repository חדש
1. בפינה שמאלה עליונה, לחץ על **[+]** → **New repository**
2. לחץ **New repository**
3. הגדרות:
   - **Repository name**: `ta35-options-bot` (שם חופשי, אבל זה יופיע ב-URL)
   - **Description**: `TA35 Options Analytics Dashboard - Real-time signals`
   - **Public** ✅ (משום שtracklit Cloud זקוקה ל-public repository)
   - **Add .gitignore**: בחר Python
   - **Add a README.md**: בחר (קל)

4. לחץ **Create repository**

### 1.3 — Clone ל-המחשב שלך
```bash
# פתח Terminal / Command Prompt
cd ~/Desktop  # (או כל מיקום שאתה רוצה)

# Clone את ה-repo
git clone https://github.com/YOUR_USERNAME/ta35-options-bot.git

# נכנס לתיקייה
cd ta35-options-bot
```

### 1.4 — העתק את קבצי הפרויקט שלנו
```bash
# אם אתה בעד תיקיית הפרויקט המקורית (ta35_options_bot/):
# העתק את כל התיקיות הללו ל-ta35-options-bot/:

# Windows:
copy ..\ta35_options_bot\* .
copy ..\ta35_options_bot\.streamlit .streamlit
copy ..\ta35_options_bot\.gitignore .gitignore

# Mac/Linux:
cp -r ../ta35_options_bot/* .
cp -r ../ta35_options_bot/.streamlit .streamlit
cp -r ../ta35_options_bot/.gitignore .gitignore
```

המבנה צריך להיות:
```
ta35-options-bot/
├── requirements.txt
├── dashboard/
│   ├── app.py
│   └── README.md
├── signals/
│   ├── models.py
│   ├── signal_generator.py
│   └── ...
├── analytics/
│   ├── calendar_il.py
│   ├── black_scholes.py
│   └── ...
├── core/
│   ├── event_bus.py
│   ├── engine.py
│   └── ...
├── risk/
│   ├── risk_manager.py
│   └── collar_enforcer.py
├── .streamlit/
│   └── config.toml
└── .gitignore
```

---

## שלב 2️⃣: Push ל-GitHub

```bash
# בתיקיית ta35-options-bot/, הרץ:

# הוסף את כל הקבצים
git add .

# צור commit
git commit -m "Initial commit: TA35 Options Analytics Dashboard"

# Push ל-GitHub
git push origin main
```

אם יש שגיאה, בדוק:
1. שאתה בתיקייה נכונה: `pwd` (חייב להראות ta35-options-bot/)
2. שקונפיגורציית Git נעשתה: 
   ```bash
   git config --global user.name "Your Name"
   git config --global user.email "your.email@example.com"
   ```

---

## שלב 3️⃣: חיבור GitHub ל-Streamlit Cloud

### 3.1 — פתח Streamlit Community Cloud
1. עבור ל-https://streamlit.io/cloud
2. לחץ **Sign up** או התחבר עם GitHub account שלך

### 3.2 — ממשק GitHub
Streamlit יבקש הרשאה:
- **Authorize streamlitcloud**: אשר
- בחר את Repository: **ta35-options-bot**

### 3.3 — Deploy האפליקציה
1. בדף https://share.streamlit.io, לחץ **New app**
2. הגדרות:
   - **GitHub account**: בחר שלך
   - **Repository**: `YOUR_USERNAME/ta35-options-bot`
   - **Branch**: `main`
   - **Main file path**: `dashboard/app.py`

3. לחץ **Deploy!**

**Streamlit יתחיל לבנות ולהפעיל את הדשבורד...**

---

## שלב 4️⃣: המתן לעדכון

Streamlit יעדכן את requirements.txt ויתקין את כל הספריות.
זה יכול לקחת 1–3 דקות.

### ביטויי הצלחה:
```
✅ Collecting packages
✅ Installing dependencies
✅ Your app is running
```

### ביטויי שגיאה שכיחים:

**❌ "ModuleNotFoundError: No module named 'signals'"**
- **סיבה**: Streamlit לא מוצא את המודולים שלנו
- **פתרון**: וודא שכל תיקיות ה-Python (signals/, analytics/, core/) בעלות קובץ `__init__.py`

**❌ "ImportError: cannot import name 'SpreadSignal'"**
- **סיבה**: קובץ לא בתיקייה הנכונה
- **פתרון**: בדוק את מבנה התיקיות (ראה לעיל)

**❌ "Timeout or Memory Error"**
- **סיבה**: יום הראשון יכול להיות איט
- **פתרון**: המתן 5 דקות והרענן את הדף

---

## שלב 5️⃣: גישה לאתר החי

כשהכל מוכן, Streamlit יתן לך **URL ציבורי**:
```
https://share.streamlit.io/YOUR_USERNAME/ta35-options-bot/main/dashboard/app.py
```

או פשוט:
```
https://ta35-options-bot.streamlit.app
```

**שתף את ה-URL הזה עם מישהו — הם יראו את הדשבורד חי!**

---

## שלב 6️⃣: בדיקה של הפונקציונליות

בדפדפן:
1. **טוען את הדשבורד?** ✅ אם כן, הצעדים עבדו!
2. **טבלת האותות מופיעה?** ✅ יש קריאה מ-generate_example_chain()
3. **הגרפים עובדים?** ✅ בחר אות, לחץ View Payoff

### אם כל זה עובד:
🎉 **מברוק! הדשבורד שלך חי באינטרנט!**

---

## שלב 7️⃣: עדכונים עתידיים

כאשר תרצה לשנות את הקוד:
```bash
# 1. בנה את השינויים מקומית
# (ערוך את app.py, models.py וכו')

# 2. בדוק מקומית
streamlit run dashboard/app.py

# 3. Push ל-GitHub
git add .
git commit -m "Updated signal parameters"
git push origin main

# 4. Streamlit יעדכן אוטומטית!
# (במשך ~2 דקות הדשבורד החי יתחדש)
```

---

## 🔐 אבטחה — משתנים סביבה (כאשר צריך API keys)

בעתיד, אם נצטרך API keys (broker, בנק ישראל וכו'):

### בדשבורד Streamlit:
1. לחץ ⚙️ **Settings** → **Secrets**
2. הוסף:
   ```
   broker_api_key = "your_key_here"
   bank_of_israel_api = "url_here"
   ```
3. בקוד: `st.secrets["broker_api_key"]`

(זה מוסתר מהציבור!)

---

## 🐛 Troubleshooting

| בעיה | פתרון |
|------|-------|
| "Could not find main file" | וודא שמסלול: `dashboard/app.py` נכון |
| "Module not found errors" | הוסף `__init__.py` לכל תיקיית Python |
| "Streamlit won't start" | בדוק requirements.txt לסינטקס |
| "Payoff diagram blank" | בחר אות מהטבלה קודם לחיפוש Payoff |
| "Signals table empty" | בדוק שהדוגמה nטוענת (טעינה 5 דקות בשלב 1) |

---

## ✨ תוצאה סופית

**URL לשתף:**
```
https://ta35-options-bot.streamlit.app
```

**המערכת מבטיחה:**
- ✅ **דיוק**: לוח שנה ישראלי, DTE עם חגים
- ✅ **מתן Bid/Ask בלבד**: לא Mid (עלות אמיתית)
- ✅ **4 סינונים**: POP, ROI, Credit, Liquidity
- ✅ **Payoff Diagram**: גרף אינטראקטיבי
- ✅ **Greeks מצרפיים**: Delta, Theta, Vega לפוזיציה

---

**שאלות? בדוק את:**
- dashboard/README.md — הוראות מפורטות
- requirements.txt — כל התלויות
- .gitignore — קבצים שלא להעלות

**וזהו! 🚀**
