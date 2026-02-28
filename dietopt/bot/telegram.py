"""Telegram adapter entrypoint with API-backed log workflow."""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

from .api_client import DietApiClient, DietApiClientError

_MSG_PATTERN = re.compile(r"^\s*(?P<query>.+?)\s+(?P<grams>\d+(?:\.\d+)?)\s*g?\s*$", re.IGNORECASE)


class TelegramAdapter:
    """Feature-flagged Telegram adapter that proxies to API endpoints."""

    def __init__(
        self,
        enabled: bool | None = None,
        api_client: DietApiClient | None = None,
    ) -> None:
        self.enabled = enabled if enabled is not None else (os.getenv("DIETOPT_TELEGRAM_ENABLED") == "1")
        self.api_client = api_client or DietApiClient(
            base_url=os.getenv("DIETOPT_API_BASE_URL", "http://127.0.0.1:8000")
        )

    def is_enabled(self) -> bool:
        return self.enabled

    def parse_log_message(self, message_text: str) -> tuple[str, float] | None:
        """Parse `food grams` text like `simit 120g`."""
        match = _MSG_PATTERN.match(message_text)
        if match is None:
            return None
        return match.group("query").strip(), float(match.group("grams"))

    def handle_message(
        self,
        message_text: str,
        user_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("Telegram adapter is disabled. Set DIETOPT_TELEGRAM_ENABLED=1 to enable.")
        if not user_id:
            return {
                "status": "missing_user",
                "message": "User mapping required. Provide a user_id for this chat.",
            }

        parsed = self.parse_log_message(message_text)
        if parsed is None:
            return {
                "status": "help",
                "message": "Format: '<food> <grams>g' (example: 'simit 120g').",
            }
        query, grams = parsed
        try:
            search = self.api_client.logs_search(query=query, limit=5)
        except DietApiClientError as exc:
            return {"status": "error", "message": str(exc)}

        candidates = search.get("candidates", [])
        if not candidates:
            return {"status": "no_match", "message": f"No candidate found for '{query}'."}
        if search.get("selection_required", False):
            return {
                "status": "choose_candidate",
                "query": query,
                "grams": grams,
                "search_id": search.get("search_id"),
                "candidates": candidates[:5],
                "message": "Choose a candidate index and call /v1/logs/resolve with search_id + candidate_index.",
            }

        chosen_id = search.get("recommended_food_id") or candidates[0]["food_id"]
        try:
            logged = self.api_client.logs_select(user_id=user_id, food_id=chosen_id, grams=grams, timestamp=timestamp)
            summary = self.api_client.summary_today(user_id=user_id)
            plan_status, plan_payload = self.api_client.optimize_today(user_id=user_id)
        except DietApiClientError as exc:
            return {"status": "error", "message": str(exc)}

        return {
            "status": "logged_and_optimized",
            "logged": logged,
            "summary": summary,
            "plan_status": plan_status,
            "plan": plan_payload,
        }

    def handle_selection(
        self,
        user_id: str,
        search_id: str,
        candidate_index: int,
        grams: float,
        timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        """Resolve one ambiguous candidate and continue summary/optimize flow."""
        if not self.enabled:
            raise RuntimeError("Telegram adapter is disabled. Set DIETOPT_TELEGRAM_ENABLED=1 to enable.")
        try:
            logged = self.api_client.logs_resolve(
                user_id=user_id,
                search_id=search_id,
                candidate_index=candidate_index,
                grams=grams,
                timestamp=timestamp,
            )
            summary = self.api_client.summary_today(user_id=user_id)
            plan_status, plan_payload = self.api_client.optimize_today(user_id=user_id)
        except DietApiClientError as exc:
            return {"status": "error", "message": str(exc)}

        return {
            "status": "resolved_and_optimized",
            "logged": logged,
            "summary": summary,
            "plan_status": plan_status,
            "plan": plan_payload,
        }
