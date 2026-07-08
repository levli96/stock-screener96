# ALS Stock Finder v0.2

גרסה זו כוללת:
- חיבור ל-FMP לסקרינר בסיסי
- שלושה מצבי סינון: Strict / Balanced / Opportunistic
- Amir Score
- ייצוא לאקסל
- Backtest בסיסי למומנטום/מחיר מול SPY באמצעות yfinance

## הפעלה ב-Streamlit
העלה ל-GitHub את הקבצים:
- app.py
- requirements.txt
- tickers_sample.csv
- README_HE.md

ב-Streamlit ודא:
- Repository: הריפוזיטורי שלך
- Branch: main
- Main file path: app.py

## הערה חשובה על Backtest
ה-Backtest בגרסה זו בודק את רכיב המומנטום/מחיר בלבד: מחיר מעל MA50 ו-MA50 עולה.
Backtest מלא של כל הפקטורים הפונדמנטליים דורש נתונים היסטוריים נקודתיים (Point-in-Time) כדי למנוע Look-Ahead Bias.
