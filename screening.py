from __future__ import annotations

from typing import Any, Dict, Optional

from config import (
    MIN_GROSS_MARGIN,
    MIN_PROFIT_MARGIN,
    MIN_QUICK_RATIO,
    MIN_ROE,
    MIN_ROIC,
)
from growth import as_percent, eps_growth_from_statement, forward_eps_data, growth_status, to_float
from levli_score import levli_stars, ps_status


def pick(data: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = to_float(data.get(key))
        if value is not None:
            return value
    return None


def build_row(
    symbol: str,
    index_name: str,
    quote: Dict[str, Any],
    ratios: Dict[str, Any],
    metrics: Dict[str, Any],
    growth: Dict[str, Any],
    estimates: list[Dict[str, Any]],
) -> Dict[str, Any]:
    price = pick(quote, "price")
    ma50 = pick(quote, "priceAvg50")
    ma200 = pick(quote, "priceAvg200")
    pe = pick(quote, "pe", "peRatio") or pick(metrics, "peRatioTTM", "peRatio")
    eps = pick(quote, "eps") or pick(metrics, "netIncomePerShareTTM")
    eps_growth = eps_growth_from_statement(growth)
    forward_eps, forward_growth = forward_eps_data(eps, estimates)
    forward_pe = (
        price / forward_eps
        if price is not None and forward_eps is not None and forward_eps > 0
        else None
    )

    row: Dict[str, Any] = {
        "Ticker": symbol,
        "Company": quote.get("name") or symbol,
        "Index": index_name,
        "Price": price,
        "MA50": ma50,
        "MA200": ma200,
        # FMP quote includes current MA values, not a historical MA50 slope series.
        # v0.5 uses MA50 > MA200 as a transparent proxy for an established rising trend.
        "MA50 Rising": bool(ma50 is not None and ma200 is not None and ma50 > ma200),
        "Price > MA50": bool(price is not None and ma50 is not None and price > ma50),
        "P/E": pe,
        "Forward P/E": forward_pe,
        "P/S": pick(metrics, "priceToSalesRatioTTM", "priceToSalesRatio"),
        "Quick Ratio": pick(ratios, "quickRatioTTM", "quickRatio"),
        "ROE %": as_percent(pick(ratios, "returnOnEquityTTM", "returnOnEquity")),
        "ROIC/ROI %": as_percent(
            pick(
                ratios,
                "returnOnInvestedCapitalTTM",
                "returnOnCapitalEmployedTTM",
                "returnOnInvestedCapital",
            )
            or pick(metrics, "roicTTM", "returnOnInvestedCapitalTTM")
        ),
        "Gross Margin %": as_percent(pick(ratios, "grossProfitMarginTTM", "grossProfitMargin")),
        "Profit Margin %": as_percent(pick(ratios, "netProfitMarginTTM", "netProfitMargin")),
        "EPS Growth %": eps_growth,
        "Forward EPS Growth %": forward_growth,
    }
    row["P/S Status"] = ps_status(row["P/S"], eps_growth, forward_growth)
    row["Growth Status"] = growth_status(eps_growth, forward_growth)
    row["Levli Score"] = levli_stars(row)
    return row


def passes_mandatory_screen(row: Dict[str, Any]) -> bool:
    return all(
        [
            row.get("Price > MA50") is True,
            row.get("MA50 Rising") is True,
            row.get("P/E") is not None
            and row.get("Forward P/E") is not None
            and row["P/E"] > row["Forward P/E"],
            (row.get("Quick Ratio") or -999) > MIN_QUICK_RATIO,
            (row.get("ROE %") or -999) >= MIN_ROE,
            (row.get("ROIC/ROI %") or -999) >= MIN_ROIC,
            (row.get("Gross Margin %") or -999) >= MIN_GROSS_MARGIN,
            (row.get("Profit Margin %") or -999) >= MIN_PROFIT_MARGIN,
        ]
    )
