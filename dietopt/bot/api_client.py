"""Lightweight API client for bot adapters."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class DietApiClientError(RuntimeError):
    """Raised when API requests fail in the bot client."""


class DietApiClient:
    """HTTP client wrapper for bot-facing API workflows."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(url=url, headers=headers, data=body, method=method.upper())
        try:
            with urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, (json.loads(raw) if raw else {})
        except HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"raw": raw}
            return exc.code, payload
        except URLError as exc:
            raise DietApiClientError(f"Failed to reach API at {url}: {exc}") from exc

    def logs_search(self, query: str, limit: int = 5) -> dict[str, Any]:
        status, payload = self._request(
            "POST",
            "/v1/logs/search",
            {"query": query, "limit": limit, "provider": "openfoodfacts"},
        )
        if status != 200:
            raise DietApiClientError(f"/v1/logs/search failed with status {status}: {payload}")
        return payload

    def logs_select(self, user_id: str, food_id: str, grams: float, timestamp: datetime | None = None) -> dict[str, Any]:
        ts = timestamp or datetime.now(timezone.utc)
        status, payload = self._request(
            "POST",
            "/v1/logs/select",
            {
                "user_id": user_id,
                "timestamp": ts.isoformat(),
                "food_id": food_id,
                "grams": grams,
            },
        )
        if status != 200:
            raise DietApiClientError(f"/v1/logs/select failed with status {status}: {payload}")
        return payload

    def logs_resolve(
        self,
        user_id: str,
        search_id: str,
        candidate_index: int,
        grams: float,
        timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        ts = timestamp or datetime.now(timezone.utc)
        status, payload = self._request(
            "POST",
            "/v1/logs/resolve",
            {
                "user_id": user_id,
                "timestamp": ts.isoformat(),
                "search_id": search_id,
                "candidate_index": candidate_index,
                "grams": grams,
            },
        )
        if status != 200:
            raise DietApiClientError(f"/v1/logs/resolve failed with status {status}: {payload}")
        return payload

    def summary_today(self, user_id: str) -> dict[str, Any]:
        status, payload = self._request("GET", f"/v1/summary/today?user_id={user_id}")
        if status != 200:
            raise DietApiClientError(f"/v1/summary/today failed with status {status}: {payload}")
        return payload

    def optimize_today(self, user_id: str) -> tuple[int, dict[str, Any]]:
        status, payload = self._request(
            "POST",
            "/v1/plan/optimize",
            {"user_id": user_id, "horizon_days": 1},
        )
        return status, payload
