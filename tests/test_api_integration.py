from pathlib import Path
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from dietopt.api.main import create_app
from dietopt.core.models import FoodRecord
from dietopt.store import get_session, load_foods_from_csv


def test_full_flow_integration(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'integration.db'}"
    app = create_app(db_url=db_url, seed_defaults=False)

    with TestClient(app) as client:
        class _FakeOffProvider:
            name = "openfoodfacts"

            def __init__(self) -> None:
                self.calls = 0

            def search_foods(self, query: str, limit: int = 5) -> list[FoodRecord]:
                self.calls += 1
                return [
                    FoodRecord(
                        id="off:999",
                        name="Provider Yogurt",
                        calories_kcal_g=0.97,
                        protein_g_g=0.10,
                        carbs_g_g=0.036,
                        fat_g_g=0.04,
                        fiber_g_g=0.0,
                        sat_fat_g_g=0.025,
                        sodium_mg_g=3.6,
                        source="openfoodfacts",
                        source_id="999",
                    )
                ][:limit]

        fake_provider = _FakeOffProvider()
        client.app.state.providers["openfoodfacts"] = fake_provider

        fixture = Path(__file__).parent / "fixtures" / "foods_tiny.csv"
        with get_session(app.state.engine) as session:
            load_foods_from_csv(session, str(fixture))

        user_resp = client.post("/v1/users", json={"name": "integration-user"})
        assert user_resp.status_code == 200
        user_id = user_resp.json()["user_id"]

        profile_payload = {
            "user_id": user_id,
            "age": 30,
            "sex": "male",
            "height_cm": 180,
            "weight_kg": 85,
            "activity_level": "moderate",
            "goal": "maintain",
        }
        resp = client.post("/v1/profile", json=profile_payload)
        assert resp.status_code == 200

        derive_resp = client.post(
            "/v1/profile/derive-targets",
            json={"user_id": user_id, "strictness": "normal"},
        )
        assert derive_resp.status_code == 200
        targets = derive_resp.json()["targets"]

        config_payload = {
            "user_id": user_id,
            "config": {
                "horizon_days": 1,
                "constraints": {
                    "calories_kcal": {"min": 700, "max": 1100},
                    "protein_g": {"min": 60, "max": 130},
                    "carbs_g": {"min": 50, "max": 200},
                    "fat_g": {"min": 15, "max": 70},
                    "fiber_g": {"min": 8},
                    "sat_fat_g": {"max": 20},
                    "sodium_mg": {"max": 3000},
                    "budget_try": {"max": 250},
                },
                "objectives_lex": [
                    {
                        "name": "min_total_deviation",
                        "type": "deviation",
                        "targets": ["calories_kcal", "protein_g", "carbs_g", "fat_g"],
                        "target_values": {
                            "calories_kcal": targets["calories_kcal"],
                            "protein_g": targets["protein_g"],
                            "carbs_g": targets["carbs_g"],
                            "fat_g": targets["fat_g"],
                        },
                        "tolerance": 0.01,
                    },
                    {
                        "name": "min_cost",
                        "type": "linear",
                        "metric": "cost_try",
                        "sense": "min",
                    },
                ],
                "food_bounds": {
                    "min_grams_per_food": 0,
                    "max_grams_per_food": 400,
                },
            },
        }
        cfg_resp = client.put("/v1/config", json=config_payload)
        assert cfg_resp.status_code == 200

        log_resp = client.post(
            "/v1/logs",
            json={
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "items": [{"food_id": "lean_chicken", "grams": 120.0}],
            },
        )
        assert log_resp.status_code == 200

        log_search_resp = client.post(
            "/v1/logs/search",
            json={"query": "yogurt", "limit": 5, "provider": "openfoodfacts"},
        )
        assert log_search_resp.status_code == 200
        log_search_json = log_search_resp.json()
        assert log_search_json["candidates"]
        chosen_id = log_search_json["recommended_food_id"]
        assert chosen_id is not None
        assert log_search_json["search_id"]

        log_resolve_resp = client.post(
            "/v1/logs/resolve",
            json={
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "search_id": log_search_json["search_id"],
                "candidate_index": 0,
                "grams": 125.0,
            },
        )
        assert log_resolve_resp.status_code == 200

        log_select_resp = client.post(
            "/v1/logs/select",
            json={
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "food_id": chosen_id,
                "grams": 150.0,
            },
        )
        assert log_select_resp.status_code == 200

        search_1 = client.post(
            "/v1/foods/search",
            json={"query": "provider-only-term", "provider": "openfoodfacts", "limit": 5},
        )
        assert search_1.status_code == 200
        assert search_1.json()["items"]
        assert search_1.json()["cached"] is False

        search_2 = client.post(
            "/v1/foods/search",
            json={"query": "provider-only-term", "provider": "openfoodfacts", "limit": 5},
        )
        assert search_2.status_code == 200
        assert search_2.json()["cached"] is True
        assert fake_provider.calls == 1

        summary_resp = client.get("/v1/summary/today", params={"user_id": user_id})
        assert summary_resp.status_code == 200
        summary_json = summary_resp.json()
        assert "consumed" in summary_json
        assert "remaining_bounds" in summary_json

        opt_resp = client.post(
            "/v1/plan/optimize",
            json={"user_id": user_id, "horizon_days": 1},
        )
        assert opt_resp.status_code == 200
        plan_json = opt_resp.json()
        assert "objective_report" in plan_json
        assert "constraint_report" in plan_json
        assert "provenance" in plan_json
        assert plan_json["provenance"]["solver"] == "scipy.optimize.linprog(method=highs)"

        latest_resp = client.get("/v1/plan/today", params={"user_id": user_id})
        assert latest_resp.status_code == 200
        latest_json = latest_resp.json()
        assert latest_json["objective_report"]
        assert latest_json["constraint_report"]
        assert latest_json["provenance"]
