from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from config import FMP_BASE_URL


class FMPError(RuntimeError):
    pass


@dataclass
class FMPClient:
    api_key: str
    timeout: int = 30

    def __post_init__(self) -> None:
        self.api_key = self.api_key.strip()
        if not self.api_key:
            raise FMPError("חסר FMP API Key")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Levli-Beta1/1.0"})

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        query = dict(params or {})
        query["apikey"] = self.api_key
        url = f"{FMP_BASE_URL}/{endpoint.lstrip('/')}"
        try:
            response = self.session.get(url, params=query, timeout=self.timeout)
        except requests.RequestException as exc:
            raise FMPError(f"שגיאת תקשורת מול FMP: {exc}") from exc

        if response.status_code == 401:
            raise FMPError("FMP החזיר 401. בדוק שהמפתח הוזן במלואו.")
        if response.status_code == 403:
            raise FMPError(f"אין הרשאה ל-endpoint: {endpoint} (403)")
        if response.status_code == 429:
            raise FMPError("מכסת הקריאות היומית של FMP הסתיימה (429).")
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise FMPError(f"FMP {response.status_code}: {response.text[:180]}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise FMPError("FMP החזיר תשובה שאינה JSON.") from exc

        if isinstance(data, dict):
            message = data.get("Error Message") or data.get("error") or data.get("message")
            if message:
                raise FMPError(str(message))
        return data

    def first(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        data = self.get(endpoint, params)
        if isinstance(data, list) and data:
            return data[0] if isinstance(data[0], dict) else {}
        return data if isinstance(data, dict) else {}

    def validate_key(self) -> bool:
        data = self.get("income-statement", {"symbol": "AAPL", "limit": 1})
        return isinstance(data, list) and bool(data)

    def quote(self, symbol: str) -> Dict[str, Any]:
        return self.first("quote", {"symbol": symbol})

    def ratios_ttm(self, symbol: str) -> Dict[str, Any]:
        return self.first("ratios-ttm", {"symbol": symbol})

    def key_metrics_ttm(self, symbol: str) -> Dict[str, Any]:
        return self.first("key-metrics-ttm", {"symbol": symbol})

    def income_growth(self, symbol: str) -> Dict[str, Any]:
        return self.first("income-statement-growth", {"symbol": symbol, "limit": 1})

    def analyst_estimates(self, symbol: str) -> List[Dict[str, Any]]:
        data = self.get(
            "analyst-estimates",
            {"symbol": symbol, "period": "annual", "page": 0, "limit": 10},
        )
        return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []
