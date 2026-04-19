# TA35 Options Analytics Dashboard 📊

**דשבורד אנליטיקה בזמן אמת לאופציות ת"א 35 עם דיוק מתמטי ברמת מקצוע.**

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://ta35-options-bot.streamlit.app)

---

## 🎯 מה זה?

מערכת ניתוח מתקדמת שמחשבת אותות סחר מדויקים לאסטרטגיות מגודרות (Spreads, Iron Condors) בבורסת ת"א.

### מאפיינים ייחודיים:
- ✅ **דיוק מתמטי**: Black-Scholes + Volatility Smile per strike
- ✅ **לוח שנה ישראלי**: DTE מחושב תחת חגים ישראליים
- ✅ **עלויות אמיתיות**: Bid/Ask בלבד, לא Mid-Price
- ✅ **יווניות מצרפיות**: Net Delta, Theta, Vega לפוזיציה כולה
- ✅ **Payoff Diagram**: גרף סיכון/רווח אינטראקטיבי
- ✅ **4 שכבות סינון**: Liquidity, Credit %, POP, ROI
- ✅ **בזמן אמת**: עדכונים כל 5 דקות

---

## 🚀 התחלה מהירה

### אתר חי:
```
https://ta35-options-bot.streamlit.app
```

### הפעלה מקומית:
```bash
pip install -r requirements.txt
streamlit run dashboard/app.py
```

---

## 📋 מבנה הפרויקט

```
ta35_options_bot/
├── dashboard/          # 🖥️ Streamlit UI
│   ├── app.py         # דשבורד ראשי עם 3 עמודים
│   └── README.md      # הוראות דשבורד
├── signals/           # 🎯 מנוע אותות
│   ├── models.py      # Dataclasses (SpreadSignal, IronCondorSignal)
│   └── signal_generator.py  # מחשבון אותות עם 4 סינונים
├── analytics/         # 🧮 חישובים מתמטיים
│   ├── black_scholes.py    # BS + Greeks + IV Solver
│   ├── calendar_il.py      # DTE עם חגים ישראליים
│   ├── iv_calculator.py    # Volatility Smile
│   └── rate_provider.py    # ריבית בנק ישראל
├── core/              # 🔧 תשתית
│   ├── engine.py      # Orchestrator
│   ├── event_bus.py   # Pub/Sub אסינכרוני
│   └── scheduler.py   # משימות תקופתיות
├── risk/              # ⚠️ ניהול סיכונים
│   ├── risk_manager.py     # אישור אותות
│   └── collar_enforcer.py  # מניעת כתיבה חשופה
└── requirements.txt   # תלויות Python

```

---

## 🎨 עמודי הדשבורד

### 1️⃣ **Home — Market Overview + Signals Table**
- מחיר ת"א 35 + IV Rank
- גרף Volatility Smile
- טבלת אותות צבעונית:
  - 🟢 **חזק**: RR > 30% + POP > 70%
  - 🟡 **בינוני**: RR > 20% + POP > 65%
  - 🔴 **חלש**: כל השאר

### 2️⃣ **Payoff Diagram — Risk Profile**
- גרף PnL אינטראקטיבי
- אזור רווח (ירוק) ואזור הפסד (אדום)
- Greeks: Delta, Gamma, Theta, Vega
- טיפים אוטומטיים

### 3️⃣ **Analysis — Nietzsche Dive**
- Greeks לפי רגל (Short/Long)
- Sensitivity Analysis (שינוי בסיס + IV)
- Risk Metrics מפורטים

---

## 📊 כיצד זה עובד

### 4 שכבות סינון (Pipeline):

```
Options Chain
    ↓
Liquidity Filter    (OI ≥ 100, Volume ≥ 10, Bid-Ask ≤ 25%)
    ↓
Credit % Filter     (Credit ≥ 20% של רוחב Spread)
    ↓
POP Filter          (הסתברות ≥ 60%)
    ↓
ROI Filter          (ROI ≥ 3% על ביטחון)
    ↓
✅ SpreadSignal (עבור דשבורד)
```

### דיוק מתמטי:

1. **DTE**: יום מסחר בפועל (לא קלנדרי) + חגים ישראליים
2. **IV**: Smile pattern - IV שונה לכל סטרייק
3. **P&L**: Bid/Ask בלבד + עמלות ריאליות
4. **Greeks**: Newton-Raphson IV Solver + Black-Scholes

---

## 🔒 כללי ברזל

### עקרונות שלא מפוסקים:
- ❌ **לעולם לא**: כתיבה חשופה (Naked Calls/Puts)
- ❌ **לעולם לא**: Mid-Price בחישובי עלות
- ✅ **תמיד**: Bid ל-SELL, Ask ל-BUY
- ✅ **תמיד**: 4 סינונים קשים לפני אות

---

## 🔧 טכנולוגיה

| Layer | Tool | מטרה |
|-------|------|-------|
| UI | **Streamlit** | דשבורד |
| Graphs | **Plotly** | גרפים אינטראקטיביים |
| Math | **NumPy, SciPy** | Black-Scholes, חישובים |
| Data | **Pandas** | טבלאות |
| Async | **asyncio** | פעולות מקביליות |

---

## 📖 מדריכים

### ל-משתמשים:
- [`dashboard/README.md`](dashboard/README.md) — איך להשתמש בדשבורד
- [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — עלייה ל-Streamlit Cloud

### ל-מפתחים:
- [`analytics/README.md`](analytics/README.md) — חישובים מתמטיים
- [`signals/README.md`](signals/README.md) — מנוע האותות
- [`core/README.md`](core/README.md) — תשתית

---

## 🚀 פריסה (Deployment)

### Streamlit Cloud (מוסה):
```bash
# 1. Push ל-GitHub
git push origin main

# 2. בדף https://share.streamlit.io
# "New app" → בחר repository

# 3. סיימת! האתר חי ב-2 דקות
```

ראה [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) לפרטים.

---

## 🔬 בדיקה מקומית

```bash
# 1. דרישות
pip install -r requirements.txt

# 2. הפעלה
streamlit run dashboard/app.py

# 3. בדפדפן: http://localhost:8501
```

---

## 📝 דוגמה: איך נוצר אות

```python
# 1. טוען שרשרת אופציות מהשוק
chain = [
    OptionQuote(symbol="TA35P19500", ..., bid=45, ask=47),
    OptionQuote(symbol="TA35P19000", ..., bid=25, ask=27),
    ...
]

# 2. יוצר SignalGenerator
generator = SignalGenerator()

# 3. מייצר Bull Put Spreads
signals = await generator.generate_bull_put_signals(
    chain=chain,
    underlying_price=20_500,
    expiry=date(2025, 1, 31),
)

# 4. מסננים אוטומטית:
# ✅ Liquidity OK → Credit % OK → POP OK → ROI OK
# 📊 הצג בדשבורד

# 5. בוחר אות, לחץ Payoff → גרף סיכון/רווח
```

---

## 🤝 תרומה

הפרויקט פתוח לשיפורים:
- 🐛 דווח על באגים
- 💡 הצע פיצ'רים
- 🔧 שלח Pull Request

---

## 📄 רישיון

MIT License — חופשי לשימוש ותיקייה.

---

## 📞 תמיכה

- 📧 Email: [your email]
- 💬 GitHub Issues
- 🔗 Streamlit Community

---

## ⭐ נקודות מפתח

```
✨ מערכת של המומחים למסחר ת"א 35
✨ דיוק מתמטי בדרגת מוסד
✨ פתוחה, שקופה, וקוד ברמה גבוהה
✨ בחינם וישתמשי הקהילה בלבד
```

**מוכן לסחור? 🚀**

```
https://ta35-options-bot.streamlit.app
```

---

**Made with ❤️ by Options Analytics Team**
