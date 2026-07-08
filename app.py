import io
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="ALS Stock Finder", page_icon="🔎", layout="wide")

FMP_BASE = "https://financialmodelingprep.com/api/v3"

st.markdown("""
<style>
.metric-card {background:#111827; border:1px solid #293244; border-radius:14px; padding:18px;}
.good {color:#22c55e; font-weight:700}
.warn {color:#f59e0b; font-weight:700}
.bad {color:#ef4444; font-weight:700}
.small {font-size:0.9rem; color:#9ca3af}
</style>
""", unsafe_allow_html=True)


def get_secret_key() -> str:
    try:
        return st.secrets.get("FMP_API_KEY", "")
    except Exception:
        return ""


def fmp_get(path: str, api_key: str, params: Optional[Dict[str, Any]] = None) -> Any:
    if not api_key:
        raise ValueError("חסר FMP API Key")
    params = params or {}
    params["apikey"] = api_key
    url = f"{FMP_BASE}/{path.lstrip('/')}"
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and data.get("Error Message"):
        raise RuntimeError(data.get("Error Message"))
    return data


@st.cache_data(ttl=60*60*12, show_spinner=False)
def load_sp500(api_key: str) -> List[str]:
    data = fmp_get("sp500_constituent", api_key)
    return sorted([x.get("symbol") for x in data if x.get("symbol")])


@st.cache_data(ttl=60*60*4, show_spinner=False)
def fetch_quote_batch(symbols: tuple, api_key: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    chunk_size = 80
    symbols = tuple([s.strip().upper() for s in symbols if s.strip()])
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i+chunk_size]
        data = fmp_get("quote/" + ",".join(chunk), api_key)
        if isinstance(data, list):
            for row in data:
                if row.get("symbol"):
                    out[row["symbol"].upper()] = row
        time.sleep(0.15)
    return out


@st.cache_data(ttl=60*60*12, show_spinner=False)
def fetch_company_data(symbol: str, api_key: str) -> Dict[str, Any]:
    symbol = symbol.upper()
    result: Dict[str, Any] = {"ticker": symbol}
    endpoints = {
        "profile": f"profile/{symbol}",
        "ratios": f"ratios-ttm/{symbol}",
        "metrics": f"key-metrics-ttm/{symbol}",
        "growth": f"financial-growth/{symbol}",
    }
    for key, path in endpoints.items():
        try:
            data = fmp_get(path, api_key)
            result[key] = data[0] if isinstance(data, list) and data else {}
        except Exception as e:
            result[key] = {"_error": str(e)}
        time.sleep(0.08)
    return result


def pct(x: Any) -> Optional[float]:
    if x is None or x == "":
        return None
    try:
        x = float(x)
        if abs(x) <= 1.5:
            return x * 100
        return x
    except Exception:
        return None


def val(d: Dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            try:
                return float(d[k])
            except Exception:
                continue
    return None


def safe_score(value: Optional[float], min_v: float, great_v: float, cap: float = 100) -> float:
    if value is None or np.isnan(value):
        return 35.0
    if value <= min_v:
        return max(0, (value / min_v) * 50) if min_v != 0 else 0
    if value >= great_v:
        return cap
    return 50 + 50 * ((value - min_v) / (great_v - min_v))


def inverse_score(value: Optional[float], good: float, bad: float) -> float:
    if value is None or np.isnan(value):
        return 45.0
    if value <= good:
        return 100.0
    if value >= bad:
        return 0.0
    return 100 * (bad - value) / (bad - good)


def build_row(symbol: str, q: Dict[str, Any], cd: Dict[str, Any]) -> Dict[str, Any]:
    profile = cd.get("profile", {})
    ratios = cd.get("ratios", {})
    metrics = cd.get("metrics", {})
    growth = cd.get("growth", {})

    price = val(q, "price")
    ma50 = val(q, "priceAvg50")
    ma200 = val(q, "priceAvg200")
    pe = val(q, "pe") or val(metrics, "peRatioTTM")
    eps = val(q, "eps") or val(metrics, "netIncomePerShareTTM")
    ps = val(metrics, "priceToSalesRatioTTM")
    quick = val(ratios, "quickRatioTTM")
    roe = pct(val(ratios, "returnOnEquityTTM"))
    roic = pct(val(ratios, "returnOnInvestedCapitalTTM")) or pct(val(ratios, "returnOnCapitalEmployedTTM"))
    gross = pct(val(ratios, "grossProfitMarginTTM"))
    operating = pct(val(ratios, "operatingProfitMarginTTM"))
    profit = pct(val(ratios, "netProfitMarginTTM"))
    revenue_growth = pct(val(growth, "revenueGrowth"))
    eps_growth = pct(val(growth, "epsgrowth", "epsGrowth"))
    debt_equity = val(ratios, "debtEquityRatioTTM")
    current_ratio = val(ratios, "currentRatioTTM")
    fcf = val(metrics, "freeCashFlowPerShareTTM")
    market_cap = val(profile, "mktCap") or val(q, "marketCap")

    # FMP free tiers often don't provide forward PE/EPS consistently in v3. Approximate if EPS growth is available.
    forward_eps = None
    if eps is not None and eps_growth is not None:
        forward_eps = eps * (1 + eps_growth / 100)
    forward_pe = None
    if price is not None and forward_eps not in (None, 0):
        forward_pe = price / forward_eps if forward_eps and forward_eps > 0 else None

    above50 = bool(price is not None and ma50 is not None and price > ma50)
    above200 = bool(price is not None and ma200 is not None and price > ma200)
    pe_improves = bool(pe is not None and forward_pe is not None and pe > forward_pe)

    quality = np.mean([
        safe_score(roe, 12, 30), safe_score(roic, 9, 20),
        safe_score(gross, 38, 55), safe_score(profit, 7, 20)
    ])
    growth_score = np.mean([safe_score(revenue_growth, 5, 20), safe_score(eps_growth, 8, 25), safe_score(forward_eps, eps or 0.01, (eps or 0.01)*1.25) if eps and forward_eps else 45])
    valuation = np.mean([inverse_score(pe, 18, 60), inverse_score(ps, 3, 18), 90 if pe_improves else 35])
    trend = np.mean([100 if above50 else 25, 100 if above200 else 35])
    final = 0.35*quality + 0.25*growth_score + 0.20*valuation + 0.20*trend

    risk_flags = []
    if debt_equity is not None and debt_equity > 1.5: risk_flags.append("Debt/Equity גבוה")
    if profit is not None and profit < 7: risk_flags.append("Profit Margin נמוך")
    if gross is not None and gross < 38: risk_flags.append("Gross Margin נמוך")
    if not above50: risk_flags.append("מתחת ל-MA50")
    if ps is not None and ps > 12: risk_flags.append("P/S גבוה")
    if eps is not None and eps <= 0: risk_flags.append("EPS שלילי")
    if revenue_growth is not None and revenue_growth < 0: risk_flags.append("ירידה בהכנסות")

    if final >= 85 and len(risk_flags) <= 1:
        rec = "Strong Candidate"
    elif final >= 70:
        rec = "Watch"
    else:
        rec = "Speculative / Ignore"

    return {
        "Ticker": symbol, "Company": profile.get("companyName") or q.get("name"), "Sector": profile.get("sector"),
        "Industry": profile.get("industry"), "Price": price, "Market Cap": market_cap,
        "MA50": ma50, "MA200": ma200, "Above MA50": above50, "Above MA200": above200,
        "P/E": pe, "Forward P/E*": forward_pe, "P/S": ps, "Quick Ratio": quick, "Current Ratio": current_ratio,
        "ROE %": roe, "ROIC/ROI %": roic, "EPS": eps, "Forward EPS*": forward_eps,
        "Revenue Growth %": revenue_growth, "EPS Growth %": eps_growth,
        "Gross Margin %": gross, "Operating Margin %": operating, "Profit Margin %": profit,
        "Debt/Equity": debt_equity, "FCF/Share": fcf,
        "Quality": round(float(quality), 1), "Growth": round(float(growth_score), 1), "Valuation": round(float(valuation), 1), "Trend": round(float(trend), 1),
        "Amir Score": round(float(final), 1), "Risk Flags": "; ".join(risk_flags), "Recommendation": rec,
    }


def passes_mode(row: pd.Series, mode: str, thresholds: Dict[str, float]) -> bool:
    strict = (
        bool(row.get("Above MA50")) and
        row.get("P/E", np.nan) > row.get("Forward P/E*", np.inf) and
        row.get("Quick Ratio", 0) >= thresholds["quick"] and
        row.get("ROE %", 0) >= thresholds["roe"] and
        row.get("ROIC/ROI %", 0) >= thresholds["roic"] and
        row.get("Gross Margin %", 0) >= thresholds["gross"] and
        row.get("Profit Margin %", 0) >= thresholds["profit"]
    )
    if mode == "Strict":
        return strict
    if mode == "Balanced":
        core = bool(row.get("Above MA50")) and row.get("Quick Ratio", 0) >= 0.8 and row.get("Profit Margin %", -999) > 0 and row.get("ROE %", 0) >= 8
        return core and row.get("Amir Score", 0) >= 60
    return row.get("Amir Score", 0) >= 50


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="ALS Results")
    return bio.getvalue()


@st.cache_data(ttl=60*60*12, show_spinner=False)
def historical_prices(symbol: str, api_key: str, from_date: str, to_date: str) -> pd.DataFrame:
    data = fmp_get(f"historical-price-full/{symbol}", api_key, {"from": from_date, "to": to_date})
    hist = data.get("historical", []) if isinstance(data, dict) else []
    df = pd.DataFrame(hist)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    return df[["date", "close"]]


def app_sidebar():
    st.sidebar.title("הגדרות")
    key_default = get_secret_key()
    api_key = st.sidebar.text_input("FMP API Key", value=key_default, type="password")
    st.sidebar.divider()
    mode = st.sidebar.radio("סגנון סינון", ["Strict", "Balanced", "Opportunistic"], index=1)
    st.sidebar.caption("Strict = קשיח; Balanced = מומלץ; Opportunistic = יותר תוצאות עם יותר סיכון")
    st.sidebar.divider()
    source = st.sidebar.radio("יקום מניות", ["רשימת דוגמה", "S&P 500 דרך FMP", "CSV העלאה", "הדבקה ידנית"], index=0)
    max_tickers = st.sidebar.slider("מספר טיקרים לסריקה", 10, 500, 50, 10)
    st.sidebar.divider()
    st.sidebar.subheader("ספי בסיס")
    thresholds = {
        "quick": st.sidebar.number_input("Quick Ratio מינימלי", value=1.0, step=0.1),
        "roe": st.sidebar.number_input("ROE % מינימלי", value=12.0, step=1.0),
        "roic": st.sidebar.number_input("ROIC/ROI % מינימלי", value=9.0, step=1.0),
        "gross": st.sidebar.number_input("Gross Margin % מינימלי", value=38.0, step=1.0),
        "profit": st.sidebar.number_input("Profit Margin % מינימלי", value=7.0, step=1.0),
    }
    return api_key, mode, source, max_tickers, thresholds


def get_tickers(source: str, api_key: str, max_tickers: int) -> List[str]:
    if source == "רשימת דוגמה":
        try:
            df = pd.read_csv("tickers_sample.csv")
            tickers = df.iloc[:, 0].astype(str).str.upper().tolist()
        except Exception:
            tickers = ["AAPL", "MSFT", "NVDA", "META", "GOOGL", "AMZN"]
    elif source == "S&P 500 דרך FMP":
        tickers = load_sp500(api_key)
    elif source == "CSV העלאה":
        file = st.sidebar.file_uploader("העלה CSV עם עמודת ticker", type=["csv"])
        if not file:
            return []
        df = pd.read_csv(file)
        col = "ticker" if "ticker" in df.columns else df.columns[0]
        tickers = df[col].astype(str).str.upper().tolist()
    else:
        text = st.sidebar.text_area("הדבק טיקרים, מופרדים בפסיק", "AAPL,MSFT,NVDA,META")
        tickers = [x.strip().upper() for x in text.replace("\n", ",").split(",") if x.strip()]
    return tickers[:max_tickers]


def screener_tab(api_key: str, mode: str, source: str, max_tickers: int, thresholds: Dict[str, float]):
    col1, col2, col3 = st.columns(3)
    col1.metric("Mode", mode)
    col2.metric("מקור נתונים", "FMP")
    col3.metric("עדכון", datetime.now().strftime("%d/%m/%Y %H:%M"))

    if not api_key:
        st.info("הכנס FMP API Key בצד שמאל או ב-Streamlit Secrets בשם FMP_API_KEY.")
        return

    tickers = get_tickers(source, api_key, max_tickers)
    st.metric("טיקרים לסריקה", len(tickers))
    run = st.button("סרוק מניות", type="primary")
    if not run:
        st.caption("המידע לצורכי מחקר בלבד ואינו המלצת השקעה.")
        return
    if not tickers:
        st.warning("לא נמצאו טיקרים לסריקה.")
        return

    progress = st.progress(0)
    status = st.empty()
    rows = []
    try:
        quotes = fetch_quote_batch(tuple(tickers), api_key)
        for i, sym in enumerate(tickers, start=1):
            status.write(f"סורק {sym} ({i}/{len(tickers)})...")
            cd = fetch_company_data(sym, api_key)
            row = build_row(sym, quotes.get(sym, {}), cd)
            rows.append(row)
            progress.progress(i / len(tickers))
    except Exception as e:
        st.error(f"שגיאה במשיכת נתונים: {e}")
        return

    df = pd.DataFrame(rows)
    df["Pass"] = df.apply(lambda r: passes_mode(r, mode, thresholds), axis=1)
    passed = df[df["Pass"]].sort_values("Amir Score", ascending=False)
    st.success(f"הסריקה הסתיימה. עברו את מצב {mode}: {len(passed)} מתוך {len(df)}")

    show_all = st.checkbox("הצג גם מניות שלא עברו", value=(len(passed) == 0))
    result = df.sort_values("Amir Score", ascending=False) if show_all else passed
    st.session_state["last_results"] = result

    cols = ["Ticker", "Company", "Amir Score", "Recommendation", "Risk Flags", "Price", "P/E", "Forward P/E*", "P/S", "Quick Ratio", "ROE %", "ROIC/ROI %", "Gross Margin %", "Profit Margin %", "Revenue Growth %", "EPS", "Forward EPS*", "Above MA50", "Above MA200"]
    st.dataframe(result[cols], use_container_width=True, height=520)
    st.caption("* Forward EPS / Forward P/E מחושבים בקירוב לפי EPS Growth כאשר אין תחזית אנליסטים זמינה ב-FMP.")

    xlsx = dataframe_to_excel_bytes(result)
    st.download_button("הורד Excel", data=xlsx, file_name="als_results.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    if not result.empty:
        pick = st.selectbox("כרטיס מניה", result["Ticker"].tolist())
        r = result[result["Ticker"] == pick].iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Amir Score", r["Amir Score"])
        c2.metric("Quality", r["Quality"])
        c3.metric("Growth", r["Growth"])
        c4.metric("Trend", r["Trend"])
        st.write("**חוזקות / חולשות:**")
        strengths = []
        if r.get("ROE %", 0) >= 30: strengths.append("ROE גבוה מאוד")
        if r.get("Gross Margin %", 0) >= 45: strengths.append("Gross Margin חזק")
        if r.get("Profit Margin %", 0) >= 20: strengths.append("Profit Margin גבוה")
        if r.get("Above MA50"): strengths.append("מחיר מעל MA50")
        if r.get("P/E", 0) > r.get("Forward P/E*", 999): strengths.append("Forward P/E נמוך מ-P/E")
        st.write("✅ " + ", ".join(strengths) if strengths else "אין חוזקות חריגות לפי הכללים")
        st.write("⚠️ " + (r.get("Risk Flags") or "אין דגלי סיכון מרכזיים"))


def backtest_tab(api_key: str):
    st.subheader("Backtest Lab בסיסי")
    st.warning("גרסה זו בודקת ביצועים היסטוריים של רשימת מניות שנבחרה היום. זה עדיין לא Point-in-Time מלא, ולכן יש הטיית הישרדות/מידע. ב-v1 נבנה Backtest אמיתי יותר.")
    if not api_key:
        st.info("הכנס FMP API Key כדי להריץ בדיקה.")
        return
    default_symbols = []
    if "last_results" in st.session_state and not st.session_state["last_results"].empty:
        default_symbols = st.session_state["last_results"].head(10)["Ticker"].tolist()
    text = st.text_area("טיקרים לבדיקה", ",".join(default_symbols or ["AAPL", "MSFT", "NVDA"]))
    symbols = [s.strip().upper() for s in text.replace("\n", ",").split(",") if s.strip()]
    start = st.date_input("תאריך התחלה", value=datetime.now().date() - timedelta(days=365))
    end = st.date_input("תאריך סיום", value=datetime.now().date())
    benchmark = st.text_input("Benchmark", value="SPY")
    if st.button("הרץ Backtest בסיסי"):
        if not symbols:
            st.warning("אין טיקרים")
            return
        rows = []
        series = []
        for sym in symbols + [benchmark.upper()]:
            df = historical_prices(sym, api_key, str(start), str(end))
            if df.empty:
                continue
            first, last = df["close"].iloc[0], df["close"].iloc[-1]
            ret = (last / first - 1) * 100
            rows.append({"Ticker": sym, "Return %": round(ret, 2), "Start": first, "End": last})
            df["norm"] = df["close"] / first * 100
            df["Ticker"] = sym
            series.append(df)
        if rows:
            res = pd.DataFrame(rows)
            st.dataframe(res, use_container_width=True)
            if series:
                chart = pd.concat(series)
                fig = px.line(chart, x="date", y="norm", color="Ticker", title="Normalized return: 100 = start")
                st.plotly_chart(fig, use_container_width=True)


def main():
    st.title("ALS Stock Finder — Amir Logic Screener")
    st.caption("v0.3 — S&P 500 + Amir Score + מצבי סינון + Backtest בסיסי")
    api_key, mode, source, max_tickers, thresholds = app_sidebar()
    tab1, tab2 = st.tabs(["🔎 Screener", "🧪 Backtest Lab"])
    with tab1:
        screener_tab(api_key, mode, source, max_tickers, thresholds)
    with tab2:
        backtest_tab(api_key)


if __name__ == "__main__":
    main()
