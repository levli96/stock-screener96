import io
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd
import requests
import streamlit as st

try:
    import yfinance as yf
except Exception:
    yf = None

BASE_URL = "https://financialmodelingprep.com/stable"

st.set_page_config(page_title="ALS Stock Finder", layout="wide")

DEFAULT_TICKERS = [
    "AAPL", "MSFT", "NVDA", "META", "GOOGL", "AMZN", "AVGO", "COST", "AMD", "NFLX",
    "ADBE", "CRM", "NOW", "PANW", "CRWD", "INTU", "LRCX", "KLAC", "AMAT", "QCOM",
    "TSLA", "ORCL", "CSCO", "TXN", "MU", "IBM", "UBER", "SHOP", "SNOW", "PLTR"
]


def fmp_get(endpoint: str, params: Dict[str, Any]) -> Any:
    url = f"{BASE_URL}/{endpoint}"
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    return r.json()


def first_item(data: Any) -> Dict[str, Any]:
    if isinstance(data, list) and data:
        return data[0] or {}
    if isinstance(data, dict):
        return data
    return {}


def val(d: Dict[str, Any], keys: List[str]) -> Optional[float]:
    for k in keys:
        if k in d and d[k] not in (None, "", "None"):
            try:
                return float(d[k])
            except Exception:
                pass
    return None


def pct(x):
    if x is None or pd.isna(x):
        return None
    return x * 100 if abs(x) <= 2 else x


@st.cache_data(ttl=3600, show_spinner=False)
def get_symbol_data(symbol: str, api_key: str) -> Dict[str, Any]:
    params = {"symbol": symbol, "apikey": api_key}
    quote = first_item(fmp_get("quote", params))
    profile = first_item(fmp_get("profile", params))
    ratios_ttm = first_item(fmp_get("ratios-ttm", params))
    metrics_ttm = first_item(fmp_get("key-metrics-ttm", params))
    estimates = first_item(fmp_get("analyst-estimates", {"symbol": symbol, "period": "annual", "apikey": api_key}))

    price = val(quote, ["price"])
    ma50 = val(quote, ["priceAvg50", "priceAvg50d"])
    ma200 = val(quote, ["priceAvg200", "priceAvg200d"])
    pe = val(quote, ["pe", "peRatio"]) or val(metrics_ttm, ["peRatioTTM", "peRatio"])
    eps = val(quote, ["eps"]) or val(metrics_ttm, ["netIncomePerShareTTM", "netIncomePerShare"])
    forward_eps = val(estimates, ["estimatedEpsAvg", "epsAvg", "estimatedEpsHigh"])
    forward_pe = (price / forward_eps) if price and forward_eps and forward_eps > 0 else None

    return {
        "Ticker": symbol,
        "Company": profile.get("companyName") or quote.get("name") or "",
        "Sector": profile.get("sector", ""),
        "Industry": profile.get("industry", ""),
        "Price": price,
        "MA50": ma50,
        "MA200": ma200,
        "Above MA50": bool(price and ma50 and price > ma50),
        "Above MA200": bool(price and ma200 and price > ma200),
        "P/E": pe,
        "Forward P/E": forward_pe,
        "P/S": val(metrics_ttm, ["priceToSalesRatioTTM", "priceToSalesRatio"]),
        "Quick Ratio": val(ratios_ttm, ["quickRatioTTM", "quickRatio"]),
        "ROE": val(ratios_ttm, ["returnOnEquityTTM", "returnOnEquity"]),
        "ROIC/ROI": val(metrics_ttm, ["roicTTM", "roic"]) or val(ratios_ttm, ["returnOnCapitalEmployedTTM", "returnOnCapitalEmployed"]),
        "EPS": eps,
        "Forward EPS": forward_eps,
        "Gross Margin": val(ratios_ttm, ["grossProfitMarginTTM", "grossProfitMargin"]),
        "Operating Margin": val(ratios_ttm, ["operatingProfitMarginTTM", "operatingProfitMargin"]),
        "Profit Margin": val(ratios_ttm, ["netProfitMarginTTM", "netProfitMargin"]),
        "Debt/Equity": val(ratios_ttm, ["debtEquityRatioTTM", "debtEquityRatio"]),
        "Market Cap": val(profile, ["mktCap", "marketCap"]) or val(quote, ["marketCap"]),
    }


def score_row(row: pd.Series) -> float:
    score = 0.0
    if row.get("Above MA50"):
        score += 12
    if row.get("Above MA200"):
        score += 8

    pe, fpe = row.get("P/E"), row.get("Forward P/E")
    if pd.notna(pe) and pd.notna(fpe) and pe > fpe:
        score += 12
    ps = row.get("P/S")
    if pd.notna(ps):
        score += max(0, min(8, 8 * (12 - min(ps, 12)) / 12))

    roe = pct(row.get("ROE")); roic = pct(row.get("ROIC/ROI")); gm = pct(row.get("Gross Margin")); pm = pct(row.get("Profit Margin")); qr = row.get("Quick Ratio")
    if roe is not None:
        score += min(15, max(0, (roe / 30) * 15))
    if roic is not None:
        score += min(12, max(0, (roic / 20) * 12))
    if gm is not None:
        score += min(13, max(0, (gm / 45) * 13))
    if pm is not None:
        score += min(13, max(0, (pm / 20) * 13))
    if pd.notna(qr):
        score += min(7, max(0, (qr / 2) * 7))
    return round(min(score, 100), 1)


def risk_flags(row: pd.Series) -> str:
    flags = []
    if pd.notna(row.get("Debt/Equity")) and row.get("Debt/Equity") > 2:
        flags.append("חוב גבוה")
    if pct(row.get("Profit Margin")) is not None and pct(row.get("Profit Margin")) < 7:
        flags.append("שולי רווח נמוכים")
    if pd.notna(row.get("P/S")) and row.get("P/S") > 12:
        flags.append("P/S גבוה")
    if not row.get("Above MA50"):
        flags.append("מתחת MA50")
    if pd.isna(row.get("Forward P/E")):
        flags.append("חסר Forward P/E")
    return ", ".join(flags) if flags else ""


def pass_filters(row: pd.Series, cfg: Dict[str, Any], mode: str) -> bool:
    checks = []
    # Strict: כל התנאים חובה
    if mode == "Strict":
        checks = [
            bool(row.get("Above MA50")),
            pd.notna(row.get("P/E")) and pd.notna(row.get("Forward P/E")) and row.get("P/E") > row.get("Forward P/E"),
            pd.notna(row.get("Quick Ratio")) and row.get("Quick Ratio") >= cfg["min_quick_ratio"],
            pct(row.get("ROE")) is not None and pct(row.get("ROE")) >= cfg["min_roe"],
            pct(row.get("ROIC/ROI")) is not None and pct(row.get("ROIC/ROI")) >= cfg["min_roic"],
            pct(row.get("Gross Margin")) is not None and pct(row.get("Gross Margin")) >= cfg["min_gross_margin"],
            pct(row.get("Profit Margin")) is not None and pct(row.get("Profit Margin")) >= cfg["min_profit_margin"],
        ]
        return all(checks)

    # Balanced: תנאי ליבה + ציון מינימלי
    if mode == "Balanced":
        core = [
            bool(row.get("Above MA50")),
            pd.notna(row.get("Quick Ratio")) and row.get("Quick Ratio") >= max(0.8, cfg["min_quick_ratio"] * 0.8),
            pct(row.get("ROE")) is not None and pct(row.get("ROE")) >= max(8, cfg["min_roe"] * 0.75),
            pct(row.get("Profit Margin")) is not None and pct(row.get("Profit Margin")) > 0,
        ]
        return all(core) and row.get("Amir Score", 0) >= 60

    # Opportunistic: לא מסנן קשיח — מכניס מועמדות עם ציון ונותן דגלי סיכון
    return row.get("Amir Score", 0) >= 50


def recommendation(score: float, flags: str, mode: str) -> str:
    risk_count = 0 if not flags else len(flags.split(","))
    if score >= 85 and risk_count <= 1:
        return "Strong Candidate"
    if score >= 70 and risk_count <= 2:
        return "Watch"
    if mode == "Opportunistic" and score >= 50:
        return "Speculative"
    return "Ignore"


def to_excel(df: pd.DataFrame) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="ALS Results")
    return out.getvalue()


@st.cache_data(ttl=3600, show_spinner=False)
def yf_prices(tickers: List[str], start: str, end: str) -> pd.DataFrame:
    if yf is None:
        raise RuntimeError("yfinance לא מותקן")
    data = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False, group_by="ticker")
    if len(tickers) == 1:
        return data[["Close"]].rename(columns={"Close": tickers[0]})
    close = pd.DataFrame({t: data[t]["Close"] for t in tickers if t in data.columns.levels[0]})
    return close.dropna(how="all")


def backtest_momentum(tickers: List[str], start: str, end: str, ma_window: int, rebalance: str, top_n: int):
    all_tickers = list(dict.fromkeys(tickers + ["SPY"]))
    prices = yf_prices(all_tickers, start, end)
    if prices.empty or "SPY" not in prices.columns:
        return pd.DataFrame(), pd.DataFrame()
    stocks = [t for t in tickers if t in prices.columns]
    prices = prices[stocks + ["SPY"]].dropna(how="all")
    ma = prices[stocks].rolling(ma_window).mean()
    ma_slope = ma.diff(20) > 0
    signals = (prices[stocks] > ma) & ma_slope
    returns = prices[stocks].pct_change().fillna(0)
    spy_ret = prices["SPY"].pct_change().fillna(0)

    if rebalance == "חודשי":
        rebalance_dates = prices.resample("ME").last().index
    else:
        rebalance_dates = prices.resample("QE").last().index

    weights = pd.DataFrame(0.0, index=prices.index, columns=stocks)
    for d in rebalance_dates:
        if d not in prices.index:
            idx = prices.index.searchsorted(d)
            if idx >= len(prices.index):
                continue
            d = prices.index[idx]
        eligible = signals.loc[d]
        chosen = eligible[eligible].index.tolist()[:top_n]
        if chosen:
            weights.loc[d:, :] = 0
            weights.loc[d:, chosen] = 1 / len(chosen)

    port_ret = (weights.shift(1).fillna(0) * returns).sum(axis=1)
    out = pd.DataFrame({"ALS Momentum": (1 + port_ret).cumprod(), "SPY": (1 + spy_ret).cumprod()})
    stats = performance_stats(out)
    return out, stats


def performance_stats(equity: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in equity.columns:
        s = equity[col].dropna()
        if len(s) < 2:
            continue
        total = s.iloc[-1] / s.iloc[0] - 1
        years = max((s.index[-1] - s.index[0]).days / 365.25, 0.01)
        cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1
        daily = s.pct_change().dropna()
        vol = daily.std() * np.sqrt(252) if len(daily) else np.nan
        sharpe = (daily.mean() * 252) / vol if vol and vol > 0 else np.nan
        dd = s / s.cummax() - 1
        rows.append({"מדד": col, "Total Return %": total * 100, "CAGR %": cagr * 100, "Volatility %": vol * 100, "Sharpe": sharpe, "Max Drawdown %": dd.min() * 100})
    return pd.DataFrame(rows)


st.title("ALS Stock Finder — Amir Logic Screener")
st.caption("v0.2 — סקרינר + מצבי סינון + Backtest בסיסי")

tab1, tab2 = st.tabs(["🔎 Screener", "🧪 Backtest Lab"])

with tab1:
    with st.sidebar:
        st.header("הגדרות")
        api_key = st.text_input("FMP API Key", type="password")
        st.subheader("סגנון סינון")
        mode = st.radio("Mode", ["Strict", "Balanced", "Opportunistic"], index=1)
        st.caption("Strict = קשיח; Balanced = מומלץ; Opportunistic = יותר תוצאות עם יותר סיכון")

        st.subheader("יקום מניות")
        input_mode = st.radio("מקור טיקרים", ["רשימת דוגמה", "הדבקה ידנית", "העלאת CSV"])
        tickers = DEFAULT_TICKERS.copy()
        if input_mode == "הדבקה ידנית":
            raw = st.text_area("הדבק טיקרים, מופרדים בפסיק או שורה", "AAPL,MSFT,NVDA,META,GOOGL")
            tickers = [x.strip().upper() for x in raw.replace("\n", ",").split(",") if x.strip()]
        elif input_mode == "העלאת CSV":
            f = st.file_uploader("CSV עם עמודה symbol או ticker", type=["csv"])
            if f:
                tmp = pd.read_csv(f)
                col = "symbol" if "symbol" in tmp.columns else "ticker" if "ticker" in tmp.columns else tmp.columns[0]
                tickers = tmp[col].dropna().astype(str).str.upper().tolist()

        max_tickers = st.slider("מספר טיקרים לסריקה", 1, min(300, len(tickers)), min(30, len(tickers)))
        tickers = tickers[:max_tickers]

        st.subheader("רפי איכות")
        min_quick_ratio = st.number_input("Quick Ratio מינימלי", value=1.0, step=0.1)
        min_roe = st.number_input("ROE מינימלי %", value=12.0, step=1.0)
        min_roic = st.number_input("ROIC/ROI מינימלי %", value=9.0, step=1.0)
        min_gross_margin = st.number_input("Gross Margin מינימלי %", value=38.0, step=1.0)
        min_profit_margin = st.number_input("Profit Margin מינימלי %", value=7.0, step=1.0)

    cfg = dict(min_quick_ratio=min_quick_ratio, min_roe=min_roe, min_roic=min_roic, min_gross_margin=min_gross_margin, min_profit_margin=min_profit_margin)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("טיקרים לסריקה", len(tickers))
    c2.metric("Mode", mode)
    c3.metric("מקור נתונים", "FMP")
    c4.metric("עדכון", datetime.now().strftime("%d/%m/%Y %H:%M"))

    if st.button("סרוק מניות", type="primary"):
        if not api_key:
            st.error("צריך להכניס FMP API Key בצד שמאל.")
        else:
            rows = []
            progress = st.progress(0)
            status = st.empty()
            for i, sym in enumerate(tickers, start=1):
                status.write(f"סורק {sym} ({i}/{len(tickers)})...")
                try:
                    rows.append(get_symbol_data(sym, api_key))
                    time.sleep(0.12)
                except Exception as e:
                    rows.append({"Ticker": sym, "Error": str(e)})
                progress.progress(i / len(tickers))

            df = pd.DataFrame(rows)
            for c in ["ROE", "ROIC/ROI", "Gross Margin", "Operating Margin", "Profit Margin"]:
                if c in df.columns:
                    df[c + " %"] = df[c].apply(pct)
            df["Amir Score"] = df.apply(score_row, axis=1)
            df["Risk Flags"] = df.apply(risk_flags, axis=1)
            df["Pass"] = df.apply(lambda r: pass_filters(r, cfg, mode), axis=1)
            df["Recommendation"] = df.apply(lambda r: recommendation(r["Amir Score"], r["Risk Flags"], mode), axis=1)
            df = df.sort_values(["Pass", "Amir Score"], ascending=[False, False])
            passed = df[df["Pass"] == True].copy()

            st.success(f"הסריקה הסתיימה. נכנסו לפי {mode}: {len(passed)} מתוך {len(df)}")
            show_cols = [c for c in ["Ticker", "Company", "Sector", "Price", "Amir Score", "Recommendation", "Risk Flags", "P/E", "Forward P/E", "P/S", "Quick Ratio", "ROE %", "ROIC/ROI %", "Gross Margin %", "Profit Margin %", "EPS", "Forward EPS", "Above MA50", "Above MA200"] if c in df.columns]
            st.subheader("תוצאות")
            st.dataframe(passed[show_cols], use_container_width=True)
            st.download_button("הורד Excel", data=to_excel(df), file_name="als_results_v02.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            with st.expander("כל המניות שנסרקו"):
                st.dataframe(df[show_cols + (["Error"] if "Error" in df.columns else [])], use_container_width=True)
    else:
        st.info("הכנס FMP API Key ולחץ 'סרוק מניות'. מומלץ להתחיל ב-Balanced כדי לא לקבל טבלה ריקה.")

with tab2:
    st.subheader("Backtest Lab — גרסה ראשונה")
    st.warning("הבדיקה כאן היא Backtest בסיסי של רכיב המומנטום בלבד: מחיר מעל MA50 ו-MA50 עולה. Backtest מלא של כל הפקטורים הפונדמנטליים דורש נתוני עבר נקודתיים כדי למנוע הצצה לעתיד.")
    colA, colB = st.columns(2)
    with colA:
        raw_bt = st.text_area("טיקרים לבדיקה", "AAPL,MSFT,NVDA,META,GOOGL,AMZN,AVGO,COST,AMD,NFLX")
        bt_tickers = [x.strip().upper() for x in raw_bt.replace("\n", ",").split(",") if x.strip()]
        start = st.date_input("תאריך התחלה", pd.to_datetime("2020-01-01"))
    with colB:
        end = st.date_input("תאריך סיום", pd.to_datetime(datetime.today().date()))
        ma_window = st.number_input("ממוצע נע", value=50, min_value=20, max_value=200, step=10)
        rebalance = st.radio("איזון מחדש", ["חודשי", "רבעוני"], index=0)
        top_n = st.number_input("מספר מניות מקסימלי בתיק", value=10, min_value=1, max_value=50)

    if st.button("הרץ Backtest", type="primary"):
        if yf is None:
            st.error("חסר yfinance. ודא שהקובץ requirements.txt כולל yfinance.")
        else:
            try:
                equity, stats = backtest_momentum(bt_tickers, str(start), str(end), int(ma_window), rebalance, int(top_n))
                if equity.empty:
                    st.error("לא התקבלו נתונים לבדיקה.")
                else:
                    st.line_chart(equity)
                    st.subheader("מדדי ביצוע")
                    st.dataframe(stats.round(2), use_container_width=True)
            except Exception as e:
                st.error(f"שגיאה בהרצת Backtest: {e}")

st.caption("המידע לצורכי מחקר בלבד ואינו המלצת השקעה.")
