# Levli Stock Screener v0.4

גרסה זו מושכת דרך FMP את רשימות החברות של:

- S&P 500
- NASDAQ-100
- Dow Jones

המערכת מאחדת את הרשימות, מסירה כפילויות, מסננת לפי ספר החוקים ומציגה רק מניות שעברו.

## עדכון ב-GitHub

1. חלץ את קובץ ה-ZIP.
2. ב-GitHub פתח את repository של הפרויקט.
3. לחץ `Add file` ואז `Upload files`.
4. העלה את `app.py`, `requirements.txt` ו-`README_HE.md`.
5. לחץ `Commit changes`.
6. Streamlit יתעדכן אוטומטית; אם לא, בצע Reboot app.

## FMP Key

ב-Streamlit Secrets:

```toml
FMP_API_KEY = "המפתח שלך"
```

אין לשתף את המפתח.
