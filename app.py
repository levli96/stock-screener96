import io
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

import pandas as pd
import requests
import streamlit as st

BASE_URL = "https://financialmodelingprep.com/stable"

st.set_page_config(page_title="ALS Stock Finder", layout="wide")

DEFAULT_TICKERS = [
    "AAPL", "MSFT", "NVDA", "META", "GOOGL", "AMZN", "AVGO", "COST", "AMD", "NFLX",
    "ADBE", "CRM", "NOW", "PANW", "CRWD", "INTU", "LRCX", "KLAC", "AMAT", "QCOM"
]


def fmp_get(endpoint: str, params: Dict[str, Any]) -> Any:
    url = f"{BASE_URL}/{endpoint}"
    r = requests.get(url, params=params, timeout=20)
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

    # FMP field names can vary by endpoint/version. These fallback lists are intentionally broad.
    forward_eps = val(estimates, ["estimatedEpsAvg", "epsAvg", "estimatedEpsHigh"])
    forward_pe = (price / forward_eps) if price and forward_eps and forward_eps > 0 else None

    ps = val(metrics_ttm, ["priceToSalesRatioTTM", "priceToSalesRatio"])
    quick_ratio = val(ratios_ttm, ["quickRatioTTM", "quickRatio"])
    roe = val(ratios_ttm, ["returnOnEquityTTM", "returnOnEquity"])
    roic = val(metrics_ttm, ["roicTTM", "roic"]) or val(ratios_ttm, ["returnOnCapitalEmployedTTM", "returnOnCapitalEmployed"])
    gross_margin = val(ratios_ttm, ["grossProfitMarginTTM", "grossProfitMargin"])
    profit_margin = val(ratios_ttm, ["netProfitMarginTTM", "netProfitMargin"])
    operating_margin = val(ratios_ttm, ["operatingProfitMarginTTM", "operatingProfitMargin"])
    debt_equity = val(ratios_ttm, ["debtEquityRatioTTM", "debtEquityRatio"])

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
        "P/S": ps,
        "Quick Ratio": quick_ratio,
        "ROE": roe,
        "ROIC/ROI": roic,
        "EPS": eps,
        "Forward EPS": forward_eps,
        "Gross Margin": gross_margin,
        "Operating Margin": operating_margin,
        "Profit Margin": profit_margin,
        "Debt/Equity": debt_equity,
        "Market Cap": val(profile, ["mktCap", "marketCap"]) or val(quote, ["marketCap"]),
    }


def pct(x):
    if x is None or pd.isna(x): return None
    return x * 100 if abs(x) <= 2 else x


def score_row(row: pd.Series, cfg: Dict[str, float]) -> float:
    score = 0
    # Trend 20
    if row.get("Above MA50"): score += 12
    if row.get("Above MA200"): score += 8
    # Valuation/expectations 20
    pe, fpe = row.get("P/E"), row.get("Forward P/E")
    if pd.notna(pe) and pd.notna(fpe) and pe > fpe: score += 12
    if pd.notna(row.get("P/S")):
        ps = row.get("P/S")
        score += max(0, min(8, 8 * (10 - min(ps, 10)) / 10))
    # Quality 60
    roe = pct(row.get("ROE")); roic = pct(row.get("ROIC/ROI")); gm = pct(row.get("Gross Margin")); pm = pct(row.get("Profit Margin")); qr = row.get("Quick Ratio")
    if roe is not None: score += min(15, max(0, (roe / 30) * 15))
    if roic is not None: score += min(12, max(0, (roic / 20) * 12))
    if gm is not None: score += min(13, max(0, (gm / 45) * 13))
    if pm is not None: score += min(13, max(0, (pm / 20) * 13))
    if pd.notna(qr): score += min(7, max(0, (qr / 2) * 7))
    return round(min(score, 100), 1)


def pass_filters(row: pd.Series, cfg: Dict[str, Any]) -> bool:
    checks = []
    if cfg["require_above_ma50"]: checks.append(bool(row.get("Above MA50")))
    if cfg["require_pe_gt_fpe"]:
        pe, fpe = row.get("P/E"), row.get("Forward P/E")
        checks.append(pd.notna(pe) and pd.notna(fpe) and pe > fpe)
    checks.append(pd.notna(row.get("Quick Ratio")) and row.get("Quick Ratio") >= cfg["min_quick_ratio"])
    checks.append(pct(row.get("ROE")) is not None and pct(row.get("ROE")) >= cfg["min_roe"])
    checks.append(pct(row.get("ROIC/ROI")) is not None and pct(row.get("ROIC/ROI")) >= cfg["min_roic"])
    checks.append(pct(row.get("Gross Margin")) is not None and pct(row.get("Gross Margin")) >= cfg["min_gross_margin"])
    checks.append(pct(row.get("Profit Margin")) is not None and pct(row.get("Profit Margin")) >= cfg["min_profit_margin"])
    return all(checks)


def to_excel(df: pd.DataFrame) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="ALS Results")
    return out.getvalue()


st.title("ALS Stock Finder — Amir Logic Screener")
st.caption("גרסת FMP v0.1 — סקרינר מניות לפי הפקטורים שלך")

with st.sidebar:
    st.header("הגדרות")
    api_key = st.text_input("FMP API Key", type="password")
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

    max_tickers = st.slider("מספר טיקרים לסריקה", 1, min(200, len(tickers)), min(20, len(tickers)))
    tickers = tickers[:max_tickers]

    st.subheader("תנאי חובה")
    require_above_ma50 = st.checkbox("מחיר מעל MA50", value=True)
    require_pe_gt_fpe = st.checkbox("P/E גדול מ-Forward P/E", value=True)
    min_quick_ratio = st.number_input("Quick Ratio מינימלי", value=1.0, step=0.1)
    min_roe = st.number_input("ROE מינימלי %", value=12.0, step=1.0)
    min_roic = st.number_input("ROIC/ROI מינימלי %", value=9.0, step=1.0)
    min_gross_margin = st.number_input("Gross Margin מינימלי %", value=38.0, step=1.0)
    min_profit_margin = st.number_input("Profit Margin מינימלי %", value=7.0, step=1.0)

cfg = dict(
    require_above_ma50=require_above_ma50,
    require_pe_gt_fpe=require_pe_gt_fpe,
    min_quick_ratio=min_quick_ratio,
    min_roe=min_roe,
    min_roic=min_roic,
    min_gross_margin=min_gross_margin,
    min_profit_margin=min_profit_margin,
)

col1, col2, col3 = st.columns(3)
col1.metric("טיקרים לסריקה", len(tickers))
col2.metric("מקור נתונים", "FMP")
col3.metric("עדכון", datetime.now().strftime("%d/%m/%Y %H:%M"))

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
                time.sleep(0.15)
            except Exception as e:
                rows.append({"Ticker": sym, "Error": str(e)})
            progress.progress(i / len(tickers))

        df = pd.DataFrame(rows)
        if df.empty:
            st.warning("לא התקבלו נתונים.")
        else:
            for c in ["ROE", "ROIC/ROI", "Gross Margin", "Operating Margin", "Profit Margin"]:
                if c in df.columns:
                    df[c + " %"] = df[c].apply(pct)
            df["Pass"] = df.apply(lambda r: pass_filters(r, cfg) if "Error" not in r or pd.isna(r.get("Error")) else False, axis=1)
            df["Amir Score"] = df.apply(score_row, axis=1, cfg=cfg)
            df = df.sort_values(["Pass", "Amir Score"], ascending=[False, False])
            passed = df[df["Pass"] == True].copy()

            st.success(f"הסריקה הסתיימה. עברו את תנאי החובה: {len(passed)} מתוך {len(df)}")
            st.subheader("תוצאות שעברו")
            st.dataframe(passed, use_container_width=True)
            st.download_button("הורד Excel", data=to_excel(df), file_name="als_results.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            with st.expander("כל המניות שנסרקו"):
                st.dataframe(df, use_container_width=True)
else:
    st.info("הכנס FMP API Key ולחץ 'סרוק מניות'. להתחלה מומלץ לסרוק 10–20 טיקרים בלבד בגלל מגבלות תוכנית חינמית.")

st.caption("המידע לצורכי מחקר בלבד ואינו המלצת השקעה.")
