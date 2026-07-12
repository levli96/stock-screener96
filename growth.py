from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple


def to_float(value: Any) -> Optional[float]:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def as_percent(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value * 100 if abs(value) <= 1.5 else value


def pick(data: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = to_float(data.get(key))
        if value is not None:
            return value
    return None


def eps_growth_from_statement(growth: Dict[str, Any]) -> Optional[float]:
    return as_percent(pick(growth, "growthEPS", "epsGrowth", "growthEps", "epsgrowth"))


def _estimate_eps(row: Dict[str, Any]) -> Optional[float]:
    return pick(row, "epsAvg", "estimatedEpsAvg", "epsEstimatedAverage", "epsAverage")


def forward_eps_data(current_eps: Optional[float], estimates: List[Dict[str, Any]]) -> Tuple[Optional[float], Optional[float]]:
    if current_eps in (None, 0) or not estimates:
        return None, None

    today = date.today().isoformat()
    ordered = sorted(estimates, key=lambda r: str(r.get("date", "9999-12-31")))
    future_rows = [r for r in ordered if str(r.get("date", "")) >= today]
    candidates = future_rows or ordered

    for row in candidates:
        estimate = _estimate_eps(row)
        if estimate is not None:
            return estimate, ((estimate / current_eps) - 1) * 100
    return None, None


def growth_status(eps_growth: Optional[float], forward_growth: Optional[float]) -> str:
    if eps_growth is None or forward_growth is None:
        return "אין מספיק מידע"
    if eps_growth <= 10:
        return "תקין" if forward_growth <= 16 else "תחזית אופטימית"
    if eps_growth <= 30:
        return "טוב" if forward_growth <= 30 else "תחזית אופטימית"
    if forward_growth < 25:
        return "האטה משמעותית צפויה"
    if forward_growth <= 46:
        return "מצוין"
    return "תחזית אופטימית"
