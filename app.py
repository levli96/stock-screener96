from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Tuple

import pandas as pd
import streamlit as st

from config import APP_SUBTITLE, APP_TITLE, DEFAULT_SCAN_LIMIT, MAX_SCAN_LIMIT
from fmp_api import FMPClient, FMPError
from screening import build_row, passes_mandatory_screen

st.set_page_config(page_title=APP_TITLE, page_icon="⭐", layout="wide")


def saved_key() -> str:
    try:
        return str(st.secrets.get("FMP_API_KEY", "")).strip()
    except Exception:
        return ""


@st.cache_data(ttl=12 * 60 * 60, show_spinner=False)
def cached_constituents(api_key: str, endpoint: str) -> List[Dict[str, Any]]:
    return FMPClient(api_key).constituents(endpoint)


@st.cache_data(ttl=4 * 60 * 60, show_spinner=False)
def cached_quotes(api_key: str, symbols: Tuple[str, ...]) -> List[Dict[str, Any]]:
    return FMPClient(api_key).batch_quotes(symbols)


@st.cache_data(ttl=12 * 60 * 60, show_spinner=False)
def cached_company_bundle(api_key: str, symbol: str) -> Dict[str, Any]:
    client = FMPClient(api_key)
    return {
        "ratios": client.ratios_ttm(symbol),
        "metrics": client.key_metrics_ttm(symbol),
        "growth": client.financial_growth(symbol),
        "estimates": client.analyst_estimates(symbol),
    }


def load_universe(api_key: str, sp: bool, nasdaq: bool, dow: bool) -> tuple[list[str], dict[str, str]]:
    requested: list[tuple[str, str]] = []
    if sp:
        requested.append(("sp500-constituent", "S&P 500"))
    if nasdaq:
        requested.append(("nasdaq-constituent", "NASDAQ"))
    if dow:
        requested.append(("dowjones-constituent", "Dow Jones"))

    membership: dict[str, list[str]] = {}
    for endpoint, label in requested:
        rows = cached_constituents(api_key, endpoint)
        for row in rows:
            symbol = str(row.get("symbol", "")).strip().upper()
            if symbol:
                membership.setdefault(symbol, []).append(label)
    symbols = sorted(membership)
    return symbols, {s: " + ".join(membership[s]) for s in symbols}


def excel_file(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Levli Results")
    return buffer.getvalue()


st.title(APP_TITLE)
st.caption(APP_SUBTITLE)

api_key = st.sidebar.text_input(
    "FMP API Key",
    value=saved_key(),
    type="password",
    placeholder="הדבק כאן את המפתח האמיתי",
)
st.sidebar.subheader("מדדים")
use_sp = st.sidebar.checkbox("S&P 500", value=True)
use_nasdaq = st.sidebar.checkbox("NASDAQ", value=True)
use_dow = st.sidebar.checkbox("Dow Jones", value=True)
scan_limit = st.sidebar.slider(
    "מספר מניות לבדיקה בהרצה זו",
    min_value=10,
    max_value=MAX_SCAN_LIMIT,
    value=DEFAULT_SCAN_LIMIT,
    step=5,
)
st.sidebar.caption(
    "בחשבון FMP חינמי יש מכסת קריאות יומית. לכן גרסה זו בודקת קבוצה מוגבלת בכל הרצה."
)

if not api_key:
    st.info("הדבק את מפתח FMP האמיתי בצד שמאל. אל תדביק את הטקסט 'שים כאן את המפתח שלך'.")
    st.stop()

col_test, col_clear = st.columns([1, 4])
with col_test:
    if st.button("בדוק API Key"):
        try:
            FMPClient(api_key).validate_key()
            st.success("המפתח תקין והחיבור ל-FMP עובד.")
        except FMPError as exc:
            st.error(str(exc))
with col_clear:
    if st.button("נקה Cache"):
        st.cache_data.clear()
        st.success("ה-Cache נוקה.")

try:
    symbols, index_map = load_universe(api_key, use_sp, use_nasdaq, use_dow)
except FMPError as exc:
    st.error(str(exc))
    st.caption(
        "אם בדיקת המפתח מצליחה אך רשימות המדדים נכשלות, ייתכן שה-endpoint אינו כלול בחבילת FMP שלך."
    )
    st.stop()

symbols = symbols[:scan_limit]
metric1, metric2, metric3 = st.columns(3)
metric1.metric("Universe נטען", len(index_map))
metric2.metric("ייבדקו בהרצה", len(symbols))
metric3.metric("עדכון", datetime.now().strftime("%d/%m/%Y %H:%M"))

if st.button("סרוק", type="primary", use_container_width=False):
    try:
        quote_rows = cached_quotes(api_key, tuple(symbols))
        quotes = {str(row.get("symbol", "")).upper(): row for row in quote_rows}
        results: list[dict[str, Any]] = []
        progress = st.progress(0)
        status = st.empty()

        for pos, symbol in enumerate(symbols, start=1):
            status.write(f"בודק {symbol} ({pos}/{len(symbols)})")
            bundle = cached_company_bundle(api_key, symbol)
            row = build_row(
                symbol=symbol,
                index_name=index_map.get(symbol, ""),
                quote=quotes.get(symbol, {}),
                ratios=bundle["ratios"],
                metrics=bundle["metrics"],
                growth=bundle["growth"],
                estimates=bundle["estimates"],
            )
            if passes_mandatory_screen(row):
                results.append(row)
            progress.progress(pos / max(len(symbols), 1))

        status.empty()
        frame = pd.DataFrame(results)
        st.success(f"עברו את הסינון: {len(frame)} מתוך {len(symbols)} שנבדקו בהרצה זו.")

        if frame.empty:
            st.warning("לא נמצאו מניות שעברו את כל תנאי החובה בקבוצה שנבדקה.")
        else:
            frame["Star Count"] = frame["Levli Score"].str.len()
            frame = frame.sort_values(
                ["Star Count", "ROE %", "Profit Margin %"],
                ascending=[False, False, False],
            ).drop(columns=["Star Count"])

            display_columns = [
                "Ticker",
                "Company",
                "Index",
                "Levli Score",
                "P/E",
                "Forward P/E",
                "P/S",
                "P/S Status",
                "ROE %",
                "ROIC/ROI %",
                "Gross Margin %",
                "Profit Margin %",
                "Quick Ratio",
                "EPS Growth %",
                "Forward EPS Growth %",
                "Growth Status",
            ]
            st.dataframe(frame[display_columns], use_container_width=True, hide_index=True)
            st.download_button(
                "הורד Excel",
                data=excel_file(frame[display_columns]),
                file_name="levli_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    except FMPError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"שגיאה לא צפויה: {exc}")

st.caption("Levli אינו מהווה המלצת השקעה. המערכת מסננת חברות למחקר פונדמנטלי וטכני נוסף.")
