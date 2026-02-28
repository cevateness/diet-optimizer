"""Open Food Facts provider implementation with strict numeric normalization."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from dietopt.core.models import FoodRecord

FetchFn = Callable[[str], Dict[str, Any]]


class ProviderUnavailableError(RuntimeError):
    """Raised when an upstream provider request fails or returns invalid payload."""


def _default_fetch_json(url: str) -> Dict[str, Any]:
    try:
        with urlopen(url, timeout=10) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ProviderUnavailableError("Provider payload is not a JSON object.")
            return payload
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
        raise ProviderUnavailableError(f"Open Food Facts request failed: {exc}") from exc


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nutrient_100g(nutriments: Dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in nutriments:
            value = _to_float(nutriments.get(key))
            if value is not None:
                return value
    return None


class OpenFoodFactsProvider:
    """Open Food Facts adapter.

    The provider only returns foods with required numeric nutrients present.
    This avoids filling missing values with LLM or synthetic estimates.
    """

    name = "openfoodfacts"

    def __init__(self, fetch_json: FetchFn | None = None) -> None:
        self._fetch_json = fetch_json or _default_fetch_json

    def search_foods(self, query: str, limit: int = 5) -> List[FoodRecord]:
        if not query.strip():
            return []

        params = urlencode(
            {
                "search_terms": query,
                "search_simple": 1,
                "action": "process",
                "json": 1,
                "page_size": max(1, min(limit, 20)),
            }
        )
        url = f"https://world.openfoodfacts.org/cgi/search.pl?{params}"
        try:
            payload = self._fetch_json(url)
        except ProviderUnavailableError:
            raise
        except Exception as exc:  # defensive wrapper for custom fetch implementations
            raise ProviderUnavailableError(f"Open Food Facts request failed: {exc}") from exc
        products = payload.get("products", [])

        rows: List[FoodRecord] = []
        for product in products:
            row = self._normalize_product(product)
            if row is not None:
                rows.append(row)
            if len(rows) >= limit:
                break
        return rows

    def _normalize_product(self, product: Dict[str, Any]) -> FoodRecord | None:
        nutriments = product.get("nutriments", {})
        code = str(product.get("code", "")).strip()
        name = (product.get("product_name") or product.get("generic_name") or "").strip()
        if not code or not name:
            return None

        calories_100g = _nutrient_100g(nutriments, "energy-kcal_100g", "energy-kcal")
        protein_100g = _nutrient_100g(nutriments, "proteins_100g", "proteins")
        carbs_100g = _nutrient_100g(nutriments, "carbohydrates_100g", "carbohydrates")
        fat_100g = _nutrient_100g(nutriments, "fat_100g", "fat")
        fiber_100g = _nutrient_100g(nutriments, "fiber_100g", "fibre_100g", "fiber", "fibre")
        satfat_100g = _nutrient_100g(
            nutriments,
            "saturated-fat_100g",
            "saturated_fat_100g",
            "saturated-fat",
        )
        sodium_100g = _nutrient_100g(nutriments, "sodium_100g", "sodium")
        if sodium_100g is None:
            salt_100g = _nutrient_100g(nutriments, "salt_100g", "salt")
            if salt_100g is not None:
                sodium_100g = salt_100g * 0.393

        required = (
            calories_100g,
            protein_100g,
            carbs_100g,
            fat_100g,
            fiber_100g,
            satfat_100g,
            sodium_100g,
        )
        if any(v is None for v in required):
            return None

        # Convert provider per-100g values to canonical per-gram fields.
        return FoodRecord(
            id=f"off:{code}",
            name=name,
            calories_kcal_g=calories_100g / 100.0,
            protein_g_g=protein_100g / 100.0,
            carbs_g_g=carbs_100g / 100.0,
            fat_g_g=fat_100g / 100.0,
            fiber_g_g=fiber_100g / 100.0,
            sat_fat_g_g=satfat_100g / 100.0,
            sodium_mg_g=sodium_100g * 10.0,
            cost_try_g=0.0,
            preference_score_g=0.0,
            source=self.name,
            source_id=code,
            retrieved_at=datetime.now(timezone.utc),
        )
