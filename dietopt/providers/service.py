"""Provider service with DB-backed caching and food upserts."""

from __future__ import annotations

from typing import List

from sqlmodel import Session

from dietopt.core.models import FoodRecord
from dietopt.store import (
    get_cached_food_search,
    set_cached_food_search,
    upsert_food,
)

from .base import FoodProvider


def search_and_cache_foods(
    session: Session,
    provider: FoodProvider,
    query: str,
    limit: int = 5,
    cache_ttl_hours: int = 24,
) -> tuple[List[FoodRecord], bool]:
    """Search via cache first, then provider, then cache+upsert DB."""
    normalized_query = query.strip().lower()
    if not normalized_query:
        return [], False

    cached = get_cached_food_search(
        session=session,
        provider=provider.name,
        query_text=normalized_query,
        max_age_hours=cache_ttl_hours,
    )
    if cached is not None:
        return cached[:limit], True

    foods = provider.search_foods(query=normalized_query, limit=limit)
    if foods:
        for food in foods:
            upsert_food(session=session, food=food)
        set_cached_food_search(
            session=session,
            provider=provider.name,
            query_text=normalized_query,
            foods=foods,
        )
    return foods, False
