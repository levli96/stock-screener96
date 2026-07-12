from __future__ import annotations

from typing import Any, Dict, Optional

from config import (
    CHEAP_PS,
    EXCELLENT_GROSS_MARGIN,
    EXCELLENT_PROFIT_MARGIN,
    EXCELLENT_ROE,
    REASONABLE_PS,
)


def ps_status(ps: Optional[float], eps_growth: Optional[float], forward_growth: Optional[float]) -> str:
    if ps is None:
        return "אין מידע"
    if ps < CHEAP_PS:
        return "זול וטוב"
    if ps <= REASONABLE_PS:
        return "סביר"
    strong_growth = (eps_growth is not None and eps_growth > 30) or (
        forward_growth is not None and forward_growth > 30
    )
    return "מוצדק רק בצמיחה חזקה" if strong_growth else "יקר ללא צמיחה חזקה"


def levli_stars(row: Dict[str, Any]) -> str:
    count = 0
    count += int((row.get("ROE %") or -999) > EXCELLENT_ROE)
    count += int((row.get("Gross Margin %") or -999) > EXCELLENT_GROSS_MARGIN)
    count += int((row.get("Profit Margin %") or -999) > EXCELLENT_PROFIT_MARGIN)
    count += int(row.get("P/S") is not None and row["P/S"] < CHEAP_PS)
    count += int(row.get("Growth Status") == "מצוין")
    # Every company shown has passed the mandatory screen; minimum display is one star.
    return "⭐" * max(count, 1)
