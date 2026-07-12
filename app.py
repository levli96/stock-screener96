import io
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Levli Stock Screener", page_icon="⭐", layout="wide")
FMP_BASE = "https://financialmodelingprep.com/api/v3"


def secret_key() -> str:
    try:
        return st.secrets.get("FMP_API_KEY", "")
    except Exception:
        return ""


def fmp_get(path: str, api_key: str, params: Optional[Dict[str, Any]] = None) -> Any:
    if not api_key:
        raise ValueError("חסר FMP API Key")
    params = dict(params or {})
    params["apikey"] = api_key
    response = requests.get(f"{FMP_BASE}/{path.lstrip('/')}", params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and (data.get("Error Message") or data.get("error")):
        raise RuntimeError(data.get("Error Message") or data.get("error"))
    return data


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def load_constituents(endpoint: str, api_key: str) -> List[Dict[str, Any]]:
    data = fmp_get(endpoint, api_key)
    return data if isinstance(data, list) else []


def load_universe(api_key: str, use_sp: bool, use_nasdaq: bool, use_dow: bool) -> Tuple[List[str], Dict[str, str]]:
    definitions = []
    if use_sp:
        definitions.append(("sp500_constituent", "S&P 500"))
    if use_nasdaq:
        definitions.append(("nasdaq_constituent", "NASDAQ-100"))
    if use_dow:
        definitions.append(("dowjones_constituent", "Dow Jones"))

    index_map: Dict[str, List[str]] = {}
    for endpoint, label in definitions:
        rows = load_constituents(endpoint, api_key)
        for row in rows:
            symbol = str(row.get("symbol", "")).strip().upper()
            if symbol:
                index_map.setdefault(symbol, []).append(label)

    symbols = sorted(index_map)
    joined = {symbol: " + ".join(index_map[symbol]) for symbol in symbols}
    return symbols, joined


@st.cache_data(ttl=60 * 60 * 4, show_spinner=False)
def fetch_quotes(symbols: tuple, api_key: str) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(symbols), 80):
        chunk = symbols[i:i + 80]
        data = fmp_get("quote/" + ",".join(chunk), api_key)
        if isinstance(data, list):
            for row in data:
                symbol = str(row.get("symbol", "")).upper()
                if symbol:
                    output[symbol] = row
        time.sleep(0.12)
    return output


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def fetch_company_data(symbol: str, api_key: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    endpoints = {
        "profile": f"profile/{symbol}",
        "ratios": f"ratios-ttm/{symbol}",
        "metrics": f"key-metrics-ttm/{symbol}",
        "growth": f"financial-growth/{symbol}?limit=1",
    }
    for name, endpoint in endpoints.items():
        try:
            data = fmp_get(endpoint, api_key)
            result[name] = data[0] if isinstance(data, list) and data else {}
        except Exception:
            result[name] = {}
        time.sleep(0.06)
    return result


def number(data: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return None


def percent(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value * 100 if abs(value) <= 1.5 else value


def ps_status(ps: Optional[float], eps_growth: Optional[float], forward_eps_growth: Optional[float]) -> str:
    if ps is None:
        return "אין מידע"
    if ps < 2:
        return "זול וטוב"
    if ps <= 8:
        return "סביר"
    strong_growth = (eps_growth is not None and eps_growth > 30) or (forward_eps_growth is not None and forward_eps_growth > 30)
    return "מוצדק רק בצמיחה חזקה" if strong_growth else "יקר ללא צמיחה חזקה"


def growth_status(eps_growth: Optional[float], forward_eps_growth: Optional[float]) -> str:
    if eps_growth is None or forward_eps_growth is None:
        return "אין מספיק מידע"
    if eps_growth <= 10:
        return "תקין" if forward_eps_growth <= 16 else "תחזית אופטימית"
    if eps_growth <= 30:
        return "טוב" if forward_eps_growth <= 30 else "תחזית אופטימית"
    if forward_eps_growth < 25:
        return "האטה משמעותית צפויה"
    if forward_eps_growth <= 46:
        return "מצוין"
    return "תחזית אופטימית"


def stars(row: Dict[str, Any]) -> str:
    count = 0
    count += int((row.get("ROE %") or -999) > 30)
    count += int((row.get("Gross Margin %") or -999) > 45)
    count += int((row.get("Profit Margin %") or -999) > 20)
    count += int(row.get("P/S") is not None and row["P/S"] < 2)
    count += int(row.get("Growth Status") == "מצוין")
    return "⭐" * max(count, 1)


def build_row(symbol: str, index_name: str, quote: Dict[str, Any], company: Dict[str, Any]) -> Dict[str, Any]:
    profile = company.get("profile", {})
    ratios = company.get("ratios", {})
    metrics = company.get("metrics", {})
    growth = company.get("growth", {})

    price = number(quote, "price")
    ma50 = number(quote, "priceAvg50")
    pe = number(quote, "pe") or number(metrics, "peRatioTTM")
    eps = number(quote, "eps") or number(metrics, "netIncomePerShareTTM")
    eps_growth = percent(number(growth, "epsgrowth", "epsGrowth"))

    # Forward values are estimated from current EPS growth when analyst estimates
    # are unavailable under the user's FMP plan.
    forward_eps = eps * (1 + eps_growth / 100) if eps is not None and eps_growth is not None else None
    forward_pe = price / forward_eps if price is not None and forward_eps not in (None, 0) and forward_eps > 0 else None
    forward_eps_growth = ((forward_eps / eps) - 1) * 100 if eps not in (None, 0) and forward_eps is not None else None

    row = {
        "Ticker": symbol,
        "Company": profile.get("companyName") or quote.get("name"),
        "Index": index_name,
        "Price": price,
        "MA50": ma50,
        "MA50 Rising": bool(ma50 is not None and number(quote, "priceAvg200") is not None and ma50 > number(quote, "priceAvg200")),
        "Price > MA50": bool(price is not None and ma50 is not None and price > ma50),
        "P/E": pe,
        "Forward P/E": forward_pe,
        "P/S": number(metrics, "priceToSalesRatioTTM"),
        "Quick Ratio": number(ratios, "quickRatioTTM"),
        "ROE %": percent(number(ratios, "returnOnEquityTTM")),
        "ROIC/ROI %": percent(number(ratios, "returnOnInvestedCapitalTTM", "returnOnCapitalEmployedTTM")),
        "Gross Margin %": percent(number(ratios, "grossProfitMarginTTM")),
        "Profit Margin %": percent(number(ratios, "netProfitMarginTTM")),
        "EPS Growth %": eps_growth,
        "Forward EPS Growth %": forward_eps_growth,
    }
    row["P/S Status"] = ps_status(row["P/S"], row["EPS Growth %"], row["Forward EPS Growth %"])
    row["Growth Status"] = growth_status(row["EPS Growth %"], row["Forward EPS Growth %"])
    row["Levli Score"] = stars(row)
    return row


def passes(row: Dict[str, Any]) -> bool:
    required = [
        row.get("Price > MA50") is True,
        row.get("MA50 Rising") is True,
        row.get("P/E") is not None and row.get("Forward P/E") is not None and row["P/E"] > row["Forward P/E"],
        (row.get("Quick Ratio") or -999) > 1,
        (row.get("ROE %") or -999) >= 12,
        (row.get("ROIC/ROI %") or -999) >= 9,
        (row.get("Gross Margin %") or -999) >= 38,
        (row.get("Profit Margin %") or -999) >= 7,
    ]
    return all(required)


def excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Levli Results")
    return buffer.getvalue()


st.title("Levli Stock Screener")
st.caption("A Fundamental Quality Filter for Serious Investors")

api_key = st.sidebar.text_input("FMP API Key", value=secret_key(), type="password")
st.sidebar.subheader("מדדים לסריקה")
use_sp = st.sidebar.checkbox("S&P 500", value=True)
use_nasdaq = st.sidebar.checkbox("NASDAQ-100", value=True)
use_dow = st.sidebar.checkbox("Dow Jones", value=True)
max_tickers = st.sidebar.slider("מקסימום מניות לסריקה", 30, 700, 650, 10)

if not api_key:
    st.info("הכנס FMP API Key בצד שמאל או שמור אותו ב-Streamlit Secrets בשם FMP_API_KEY.")
    st.stop()

try:
    symbols, index_map = load_universe(api_key, use_sp, use_nasdaq, use_dow)
except Exception as exc:
    st.error(f"לא ניתן לטעון את רשימות המדדים מ-FMP: {exc}")
    st.stop()

symbols = symbols[:max_tickers]
col1, col2, col3 = st.columns(3)
col1.metric("Universe", len(symbols))
col2.metric("מקור", "FMP")
col3.metric("עדכון", datetime.now().strftime("%d/%m/%Y %H:%M"))

if st.button("סרוק", type="primary"):
    rows: List[Dict[str, Any]] = []
    progress = st.progress(0)
    status = st.empty()
    try:
        quotes = fetch_quotes(tuple(symbols), api_key)
        for i, symbol in enumerate(symbols, 1):
            status.write(f"סורק {symbol} ({i}/{len(symbols)})")
            row = build_row(symbol, index_map.get(symbol, ""), quotes.get(symbol, {}), fetch_company_data(symbol, api_key))
            if passes(row):
                rows.append(row)
            progress.progress(i / max(len(symbols), 1))
    except Exception as exc:
        st.error(f"שגיאה בסריקה: {exc}")
        st.stop()

    result = pd.DataFrame(rows)
    st.success(f"עברו את הסינון הפונדמנטלי: {len(result)} מתוך {len(symbols)}")
    if result.empty:
        st.warning("לא נמצאו מניות שעברו את כל תנאי החובה.")
    else:
        result["Star Count"] = result["Levli Score"].str.len()
        result = result.sort_values(["Star Count", "ROE %", "Profit Margin %"], ascending=[False, False, False])
        result.insert(0, "Rank", range(1, len(result) + 1))
        display_cols = [
            "Rank", "Ticker", "Company", "Index", "Levli Score", "P/E", "Forward P/E", "P/S", "P/S Status",
            "ROE %", "ROIC/ROI %", "Gross Margin %", "Profit Margin %", "Quick Ratio",
            "EPS Growth %", "Forward EPS Growth %", "Growth Status"
        ]
        st.dataframe(result[display_cols], use_container_width=True, height=600)
        st.download_button(
            "הורד Excel",
            data=excel_bytes(result[display_cols]),
            file_name="levli_results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.caption("Forward EPS Growth ו-Forward P/E עשויים להיות מחושבים בקירוב כאשר חבילת FMP אינה מחזירה תחזיות אנליסטים.")

st.caption("המערכת מסננת חברות למחקר נוסף ואינה המלצת קנייה או מכירה.")
