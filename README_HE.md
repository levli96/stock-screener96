# Levli Beta 1

גרסה ממוקדת שנועדה להוכיח שהמערכת עובדת מקצה לקצה על 30 מניות אמיתיות.

## מה היא עושה
- בדיקת API Key באמצעות endpoint של Income Statement שכבר אומת בחשבון.
- סריקה של 5–30 מניות מקובץ `tickers_30.csv`.
- שימוש ב-endpoints הרשמיים של FMP Stable:
  - `quote`
  - `ratios-ttm`
  - `key-metrics-ttm`
  - `income-statement-growth`
  - `analyst-estimates`
- סינון לפי כללי Levli.
- Levli Score בכוכבים.
- ייצוא ל-Excel.

## העלאה ל-GitHub
העלה את הקבצים עצמם לשורש ה-repository, לא את התיקייה כולה.

## Streamlit
Main file path: `app.py`

אחרי Commit בצע Reboot app.

## הערה על מכסת FMP
סריקה של 30 מניות צורכת עד כ-150 קריאות לפני Cache. מומלץ להתחיל ב-5 מניות ולעלות ל-30 לאחר שהבדיקה מצליחה.
