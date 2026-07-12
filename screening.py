from __future__ import annotations

from typing import Any, Dict, Optional

from config import MIN_GROSS_MARGIN, MIN_PROFIT_MARGIN, MIN_QUICK_RATIO, MIN_ROE, MIN_ROIC
from growth import as_percent, eps_growth_from_statement, forward_eps_data, growth_status, pick
from levli_score import levli_stars, ps_status


def _first_value(primary: Dict[str, Any], secondary: Dict[str, Any], *keys: str) -> Optional[float]:
    value = pick(primary, *keys)
    return value if value is not None else pick(secondary, *keys)


def build_row(symbol: str, quote: Dict[str, Any], ratios: Dict[str, Any], metrics: Dict[str, Any], growth: Dict[str, Any], estimates: list[Dict[str, Any]]) -> Dict[str, Any]:
    price = pick(quote, "price")
    ma50 = pick(quote, "priceAvg50", "priceAverage50")
    ma200 = pick(quote, "priceAvg200", "priceAverage200")
    pe = _first_value(quote, metrics, "pe", "peRatio", "peRatioTTM")
    eps = _first_value(quote, metrics, "eps", "netIncomePerShareTTM")
    eps_growth = eps_growth_from_statement(growth)
    forward_eps, forward_growth = forward_eps_data(eps, estimates)
    forward_pe = price / forward_eps if price is not None and forward_eps is not None and forward_eps > 0 else None

    row: Dict[str, Any] = {
        "Ticker": symbol,
        "Company": quote.get("name") or quote.get("companyName") or symbol,
        "Price": price,
        "MA50": ma50,
        "MA200": ma200,
        "Price > MA50": bool(price is not None and ma50 is not None and price > ma50),
        "MA50 Rising": bool(ma50 is not None and ma200 is not None and ma50 > ma200),
        "P/E": pe,
        "Forward P/E": forward_pe,
        "P/S": _first_value(metrics, ratios, "priceToSalesRatioTTM", "priceToSalesRatio"),
        "Quick Ratio": _first_value(ratios, metrics, "quickRatioTTM", "quickRatio"),
        "ROE %": as_percent(_first_value(ratios, metrics, "returnOnEquityTTM", "returnOnEquity")),
        "ROIC/ROI %": as_percent(_first_value(metrics, ratios, "roicTTM", "returnOnInvestedCapitalTTM", "returnOnCapitalEmployedTTM", "returnOnInvestedCapital")),
        "Gross Margin %": as_percent(_first_value(ratios, metrics, "grossProfitMarginTTM", "grossProfitMargin")),
        "Profit Margin %": as_percent(_first_value(ratios, metrics, "netProfitMarginTTM", "netProfitMargin")),
        "EPS Growth %": eps_growth,
        "Forward EPS Growth %": forward_growth,
    }
    row["P/S Status"] = ps_status(row["P/S"], eps_growth, forward_growth)
    row["Growth Status"] = growth_status(eps_growth, forward_growth)
    row["Levli Score"] = levli_stars(row)
    return row


def passes_mandatory_screen(row: Dict[str, Any]) -> bool:
    return all([
        row.get("Price > MA50") is True,
        row.get("MA50 Rising") is True,
        row.get("P/E") is not None and row.get("Forward P/E") is not None and row["P/E"] > row["Forward P/E"],
        (row.get("Quick Ratio") or -999) > MIN_QUICK_RATIO,
        (row.get("ROE %") or -999) >= MIN_ROE,
        (row.get("ROIC/ROI %") or -999) >= MIN_ROIC,
        (row.get("Gross Margin %") or -999) >= MIN_GROSS_MARGIN,
        (row.get("Profit Margin %") or -999) >= MIN_PROFIT_MARGIN,
    ])
