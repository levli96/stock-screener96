from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import requests

from config import FMP_BASE_URL


class FMPError(RuntimeError):
    """Readable error returned by the FMP service."""


@dataclass
class FMPClient:
    api_key: str
    timeout: int = 30

    def __post_init__(self) -> None:
        self.api_key = self.api_key.strip()
        if not self.api_key:
            raise FMPError("חסר FMP API Key")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Levli/0.5"})

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        query = dict(params or {})
        query["apikey"] = self.api_key
        url = f"{FMP_BASE_URL}/{endpoint.lstrip('/')}"
        try:
            response = self.session.get(url, params=query, timeout=self.timeout)
        except requests.RequestException as exc:
            raise FMPError(f"שגיאת תקשורת מול FMP: {exc}") from exc

        if response.status_code == 401:
            raise FMPError(
                "FMP דחה את המפתח (401). ודא שהדבקת את ה-API Key האמיתי ולא את טקסט הדוגמה."
            )
        if response.status_code == 403:
            raise FMPError("ה-endpoint אינו כלול כנראה בחבילת FMP שלך (403).")
        if response.status_code == 429:
            raise FMPError("חרגת ממכסת הקריאות היומית של FMP (429).")
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise FMPError(f"שגיאת FMP {response.status_code}: {response.text[:180]}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise FMPError("FMP החזיר תשובה שאינה JSON.") from exc

        if isinstance(data, dict):
            message = data.get("Error Message") or data.get("error") or data.get("message")
            if message:
                raise FMPError(str(message))
        return data

    def validate_key(self) -> bool:
        data = self.get("quote-short", {"symbol": "AAPL"})
        return isinstance(data, list) and len(data) > 0

    def constituents(self, endpoint: str) -> List[Dict[str, Any]]:
        data = self.get(endpoint)
        return data if isinstance(data, list) else []

    def batch_quotes(self, symbols: Iterable[str]) -> List[Dict[str, Any]]:
        joined = ",".join(symbols)
        if not joined:
            return []
        data = self.get("batch-quote", {"symbols": joined})
        return data if isinstance(data, list) else []

    def ratios_ttm(self, symbol: str) -> Dict[str, Any]:
        data = self.get("ratios-ttm", {"symbol": symbol})
        return data[0] if isinstance(data, list) and data else {}

    def key_metrics_ttm(self, symbol: str) -> Dict[str, Any]:
        data = self.get("key-metrics-ttm", {"symbol": symbol})
        return data[0] if isinstance(data, list) and data else {}

    def financial_growth(self, symbol: str) -> Dict[str, Any]:
        data = self.get("financial-growth", {"symbol": symbol, "limit": 1})
        return data[0] if isinstance(data, list) and data else {}

    def analyst_estimates(self, symbol: str) -> List[Dict[str, Any]]:
        data = self.get(
            "analyst-estimates",
            {"symbol": symbol, "period": "annual", "page": 0, "limit": 3},
        )
        return data if isinstance(data, list) else []
