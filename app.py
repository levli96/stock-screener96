from __future__ import annotations

import csv
import html
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from config import APP_SUBTITLE, APP_TITLE
from fmp_api import FMPClient, FMPError
from screening import build_row, diagnostic_row, passes_mandatory_screen

st.set_page_config(page_title=APP_TITLE, page_icon="⭐", layout="wide")


def saved_key() -> str:
    try:
        return str(st.secrets.get("FMP_API_KEY", "")).strip()
    except Exception:
        return ""


def load_tickers() -> list[str]:
    path = Path(__file__).with_name("tickers_30.csv")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [str(row.get("Ticker", "")).strip().upper() for row in reader if str(row.get("Ticker", "")).strip()]


def scan_symbol(api_key: str, symbol: str) -> dict[str, Any]:
    client = FMPClient(api_key)
    bundle = {
        "quote": client.quote(symbol),
        "ratios": client.ratios_ttm(symbol),
        "metrics": client.key_metrics_ttm(symbol),
        "growth": client.income_growth(symbol),
        "estimates": client.analyst_estimates(symbol),
    }
    return build_row(symbol, **bundle)


def fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "כן" if value else "לא"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value)


def render_html_table(rows: list[dict[str, Any]], columns: list[str]) -> None:
    head = "".join(f"<th>{html.escape(col)}</th>" for col in columns)
    body_parts: list[str] = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(fmt(row.get(col)))}</td>" for col in columns)
        body_parts.append(f"<tr>{cells}</tr>")
    table = f"""
    <div style="overflow-x:auto; width:100%;">
      <table style="border-collapse:collapse; width:100%; font-size:14px;">
        <thead><tr>{head}</tr></thead>
        <tbody>{''.join(body_parts)}</tbody>
      </table>
    </div>
    <style>
      table th, table td {{ border:1px solid #ddd; padding:7px; text-align:left; white-space:nowrap; }}
      table th {{ background:#f3f4f6; position:sticky; top:0; }}
      table tr:nth-child(even) {{ background:#fafafa; }}
    </style>
    """
    st.markdown(table, unsafe_allow_html=True)


def csv_bytes(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    import io
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column) for column in columns})
    return buffer.getvalue().encode("utf-8-sig")


st.title(APP_TITLE)
st.caption(APP_SUBTITLE)
st.info("גרסת בדיקה ממוקדת: סריקה יציבה + הסבר ברור אילו תנאי חובה עברו או נכשלו.")

api_key = st.sidebar.text_input("FMP API Key", value=saved_key(), type="password", placeholder="הדבק כאן את המפתח")
scan_count = st.sidebar.select_slider("מספר מניות לסריקה", options=[1, 3, 5, 10, 20, 30], value=10)
st.sidebar.caption("ברירת המחדל היא 10 מניות. אפשר להרחיב בהדרגה עד 30.")

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
    st.caption("אין Cache בגרסה זו, כדי למנוע קריסות.")

symbols = load_tickers()[:scan_count]
m1, m2 = st.columns(2)
m1.metric("מניות לבדיקה", len(symbols))
m2.metric("זמן", datetime.now().strftime("%d/%m/%Y %H:%M"))

if st.button("סרוק", type="primary"):
    results: list[dict[str, Any]] = []
    diagnostics: list[dict[str, str]] = []
    screen_details: list[dict[str, Any]] = []
    progress = st.progress(0)
    status = st.empty()

    for i, symbol in enumerate(symbols, start=1):
        status.info(f"בודק {symbol} ({i}/{len(symbols)})")
        try:
            row = scan_symbol(api_key, symbol)
            screen_details.append(diagnostic_row(row))
            if passes_mandatory_screen(row):
                results.append(row)
            diagnostics.append({"Ticker": symbol, "Status": "OK"})
        except FMPError as exc:
            diagnostics.append({"Ticker": symbol, "Status": str(exc)})
        except Exception as exc:
            diagnostics.append({"Ticker": symbol, "Status": f"שגיאה: {type(exc).__name__}: {exc}"})
        progress.progress(i / len(symbols))

    status.empty()
    st.success(f"הסריקה הסתיימה. עברו: {len(results)} מתוך {len(symbols)}.")

    columns = [
        "Ticker", "Company", "Levli Score", "P/E", "Forward P/E", "P/S", "P/S Status",
        "ROE %", "ROIC/ROI %", "Gross Margin %", "Profit Margin %", "Quick Ratio",
        "EPS Growth %", "Forward EPS Growth %", "Growth Status",
    ]

    if results:
        results.sort(key=lambda row: (len(str(row.get("Levli Score", ""))), row.get("ROE %") or -999, row.get("Profit Margin %") or -999), reverse=True)
        render_html_table(results, columns)
        st.download_button(
            "הורד CSV",
            data=csv_bytes(results, columns),
            file_name="levli_beta1_2_results.csv",
            mime="text/csv",
        )
    else:
        st.info("לא נמצאו מניות שעברו את כל תנאי החובה. הסריקה עצמה הסתיימה בהצלחה.")


    st.subheader("בדיקת תנאי החובה")
    if screen_details:
        diagnostic_columns = [
            "Ticker", "Company", "Passed", "Price > MA50", "MA50 Rising",
            "P/E > Fwd P/E", "Quick > 1", "ROE ≥ 12%", "ROIC ≥ 9%",
            "GM ≥ 38%", "PM ≥ 7%", "Failed Criteria",
        ]
        render_html_table(screen_details, diagnostic_columns)

    errors = [row for row in diagnostics if row["Status"] != "OK"]
    if errors:
        with st.expander("פירוט שגיאות נתונים"):
            render_html_table(errors, ["Ticker", "Status"])

st.caption("Levli אינו המלצת השקעה. זהו מסנן פונדמנטלי למחקר נוסף.")
