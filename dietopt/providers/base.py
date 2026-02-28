"""Provider protocol for deterministic nutrient acquisition."""

from __future__ import annotations

from typing import List, Protocol

from dietopt.core.models import FoodRecord


class FoodProvider(Protocol):
    """External provider interface; outputs canonical nutrient records."""

    name: str

    def search_foods(self, query: str, limit: int = 5) -> List[FoodRecord]:
        """Search foods and return canonical per-gram nutrient records."""

