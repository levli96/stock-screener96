from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import streamlit as st

from config import APP_SUBTITLE, APP_TITLE
from fmp_api import FMPClient, FMPError
from screening import build_row, passes_mandatory_screen

st.set_page_config(page_title=APP_TITLE, page_icon="⭐", layout="wide")


def saved_key() -> str:
    try:
        return str(st.secrets.get("FMP_API_KEY", "")).strip()
    except Exception:
        return ""


def load_tickers() -> list[str]:
    path = Path(__file__).with_name("tickers_30.csv")
    frame = pd.read_csv(path)
    return [str(value).strip().upper() for value in frame["Ticker"] if str(value).strip()]


def excel_file(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Levli Results")
    return buffer.getvalue()


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def company_bundle(api_key: str, symbol: str) -> Dict[str, Any]:
    client = FMPClient(api_key)
    return {
        "quote": client.quote(symbol),
        "ratios": client.ratios_ttm(symbol),
        "metrics": client.key_metrics_ttm(symbol),
        "growth": client.income_growth(symbol),
        "estimates": client.analyst_estimates(symbol),
    }


st.title(APP_TITLE)
st.caption(APP_SUBTITLE)
st.info("גרסת בדיקה ממוקדת: 30 מניות אמיתיות, ללא רשימות מדדים וללא פיצ'רים נוספים.")

api_key = st.sidebar.text_input("FMP API Key", value=saved_key(), type="password", placeholder="הדבק כאן את המפתח")
scan_count = st.sidebar.slider("מספר מניות לסריקה", 5, 30, 30, 5)
st.sidebar.caption("30 מניות × עד 5 קריאות = עד 150 קריאות, לפני שימוש ב-Cache.")

if not api_key:
    st.warning("הזן את מפתח FMP בצד שמאל.")
    st.stop()

col1, col2 = st.columns([1, 4])
with col1:
    if st.button("בדוק API Key"):
        try:
            FMPClient(api_key).validate_key()
            st.success("החיבור ל-FMP תקין.")
        except FMPError as exc:
            st.error(str(exc))
with col2:
    if st.button("נקה Cache"):
        st.cache_data.clear()
        st.success("ה-Cache נוקה.")

symbols = load_tickers()[:scan_count]
m1, m2 = st.columns(2)
m1.metric("מניות לבדיקה", len(symbols))
m2.metric("זמן", datetime.now().strftime("%d/%m/%Y %H:%M"))

if st.button("סרוק", type="primary"):
    results: list[dict[str, Any]] = []
    diagnostics: list[dict[str, str]] = []
    progress = st.progress(0)
    status = st.empty()

    for i, symbol in enumerate(symbols, start=1):
        status.write(f"בודק {symbol} ({i}/{len(symbols)})")
        try:
            bundle = company_bundle(api_key, symbol)
            row = build_row(symbol, **bundle)
            if passes_mandatory_screen(row):
                results.append(row)
            diagnostics.append({"Ticker": symbol, "Status": "OK"})
        except FMPError as exc:
            diagnostics.append({"Ticker": symbol, "Status": str(exc)})
        except Exception as exc:
            diagnostics.append({"Ticker": symbol, "Status": f"שגיאה: {exc}"})
        progress.progress(i / len(symbols))

    status.empty()
    frame = pd.DataFrame(results)
    errors = pd.DataFrame([row for row in diagnostics if row["Status"] != "OK"])

    st.success(f"הסריקה הסתיימה. עברו: {len(frame)} מתוך {len(symbols)}.")
    if not errors.empty:
        st.warning(f"ב-{len(errors)} מניות הייתה בעיית נתונים או הרשאה. פירוט בתחתית המסך.")

    if frame.empty:
        st.info("לא נמצאו מניות שעברו את כל תנאי החובה. זה יכול להיות תקין בסינון קשיח.")
    else:
        frame["Star Count"] = frame["Levli Score"].str.len()
        frame = frame.sort_values(["Star Count", "ROE %", "Profit Margin %"], ascending=[False, False, False]).drop(columns="Star Count")
        columns = [
            "Ticker", "Company", "Levli Score", "P/E", "Forward P/E", "P/S", "P/S Status",
            "ROE %", "ROIC/ROI %", "Gross Margin %", "Profit Margin %", "Quick Ratio",
            "EPS Growth %", "Forward EPS Growth %", "Growth Status",
        ]
        st.dataframe(frame[columns], use_container_width=True, hide_index=True)
        st.download_button("הורד Excel", excel_file(frame[columns]), "levli_beta1_results.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    if not errors.empty:
        with st.expander("פירוט שגיאות נתונים"):
            st.dataframe(errors, use_container_width=True, hide_index=True)

st.caption("Levli אינו המלצת השקעה. זהו מסנן פונדמנטלי למחקר נוסף.")
