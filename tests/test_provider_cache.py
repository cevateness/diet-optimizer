from pathlib import Path

from dietopt.providers import OpenFoodFactsProvider, search_and_cache_foods
from dietopt.store import create_db_and_tables, get_engine, get_foods, get_session


def test_openfoodfacts_provider_cache_and_upsert(tmp_path: Path) -> None:
    call_counter = {"count": 0}

    def fake_fetch(_: str) -> dict:
        call_counter["count"] += 1
        return {
            "products": [
                {
                    "code": "111",
                    "product_name": "Test Yogurt",
                    "nutriments": {
                        "energy-kcal_100g": 97,
                        "proteins_100g": 10,
                        "carbohydrates_100g": 3.6,
                        "fat_100g": 4.0,
                        "fiber_100g": 0.0,
                        "saturated-fat_100g": 2.5,
                        "sodium_100g": 0.36,
                    },
                },
                {
                    "code": "222",
                    "product_name": "Missing Fiber Product",
                    "nutriments": {
                        "energy-kcal_100g": 200,
                        "proteins_100g": 8,
                        "carbohydrates_100g": 20,
                        "fat_100g": 5,
                        "saturated-fat_100g": 1.0,
                        "sodium_100g": 0.1,
                    },
                },
            ]
        }

    db_url = f"sqlite:///{tmp_path / 'provider_cache.db'}"
    engine = get_engine(db_url)
    create_db_and_tables(engine)

    provider = OpenFoodFactsProvider(fetch_json=fake_fetch)
    with get_session(engine) as session:
        foods, cached = search_and_cache_foods(
            session=session,
            provider=provider,
            query="yogurt",
            limit=5,
            cache_ttl_hours=24,
        )
        assert cached is False
        assert call_counter["count"] == 1
        assert len(foods) == 1
        assert foods[0].id == "off:111"
        assert abs(foods[0].calories_kcal_g - 0.97) < 1e-9

        persisted = get_foods(session)
        assert len(persisted) == 1
        assert persisted[0].source == "openfoodfacts"

        foods_2, cached_2 = search_and_cache_foods(
            session=session,
            provider=provider,
            query="yogurt",
            limit=5,
            cache_ttl_hours=24,
        )
        assert cached_2 is True
        assert call_counter["count"] == 1
        assert len(foods_2) == 1

