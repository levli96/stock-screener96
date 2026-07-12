from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def to_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def as_percent(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value * 100 if abs(value) <= 1.5 else value


def eps_growth_from_statement(growth: Dict[str, Any]) -> Optional[float]:
    for key in ("growthEPS", "epsGrowth", "epsgrowth"):
        value = as_percent(to_float(growth.get(key)))
        if value is not None:
            return value
    return None


def forward_eps_data(
    current_eps: Optional[float], estimates: List[Dict[str, Any]]
) -> Tuple[Optional[float], Optional[float]]:
    """Return next annual EPS estimate and its growth versus current EPS."""
    if current_eps in (None, 0) or not estimates:
        return None, None

    estimate_value: Optional[float] = None
    for row in estimates:
        for key in ("epsAvg", "estimatedEpsAvg", "epsEstimatedAverage"):
            estimate_value = to_float(row.get(key))
            if estimate_value is not None:
                break
        if estimate_value is not None:
            break

    if estimate_value is None:
        return None, None
    growth = ((estimate_value / current_eps) - 1) * 100
    return estimate_value, growth


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
