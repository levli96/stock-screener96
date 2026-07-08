# ALS Stock Finder v0.3

גרסה זו מוסיפה:

- בחירת יקום מניות: רשימת דוגמה / S&P 500 דרך FMP / העלאת CSV / הדבקה ידנית
- שלושה מצבי סינון: Strict / Balanced / Opportunistic
- Amir Score מפורק ל-Quality / Growth / Valuation / Trend
- Risk Flags ו-Recommendation
- כרטיס מניה בסיסי
- ייצוא לאקסל
- Backtest Lab בסיסי

## איך לעדכן את Streamlit

1. חלץ את קובץ ה-ZIP.
2. היכנס ל-GitHub repository שלך.
3. לחץ Add file → Upload files.
4. גרור את הקבצים:
   - app.py
   - requirements.txt
   - README_HE.md
   - tickers_sample.csv
5. לחץ Commit changes.
6. ב-Streamlit לחץ Reboot app אם לא התעדכן לבד.

## API Key

עדיף לשמור את המפתח ב-Streamlit Secrets:

```toml
FMP_API_KEY = "your_key_here"
```

אפשר גם להזין אותו בשדה בצד שמאל, אבל אל תשתף אותו עם אף אחד.

## הערה חשובה על Backtest

ה-Backtest בגרסה זו הוא בסיסי בלבד. הוא בודק ביצועים היסטוריים של טיקרים שנבחרו היום. זה עדיין לא Point-in-Time מלא ולכן קיימת הטיית הישרדות/מידע. בגרסה מתקדמת נבנה מנגנון היסטורי אמיתי.

## הערה על Forward EPS / Forward P/E

אם FMP לא מספק תחזית אנליסטים זמינה בתוכנית שלך, האפליקציה מחשבת קירוב לפי EPS Growth. העמודות מסומנות בכוכבית.

המידע לצורכי מחקר בלבד ואינו המלצת השקעה.
