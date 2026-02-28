from pathlib import Path

from fastapi.testclient import TestClient

from dietopt.api.main import create_app
from dietopt.store import get_session, load_foods_from_csv


def test_optimize_returns_structured_infeasibility_payload(tmp_path: Path) -> None:
    app = create_app(db_url=f"sqlite:///{tmp_path / 'infeasible.db'}", seed_defaults=False)

    with TestClient(app) as client:
        fixture = Path(__file__).parent / "fixtures" / "foods_tiny.csv"
        with get_session(app.state.engine) as session:
            load_foods_from_csv(session, str(fixture))

        user_resp = client.post("/v1/users", json={"name": "infeasible-user"})
        user_id = user_resp.json()["user_id"]

        config_payload = {
            "user_id": user_id,
            "config": {
                "horizon_days": 1,
                "constraints": {
                    "protein_g": {"min": 1000.0},
                    "calories_kcal": {"max": 200.0},
                },
                "objectives_lex": [
                    {
                        "name": "min_total_deviation",
                        "type": "deviation",
                        "targets": ["protein_g", "calories_kcal"],
                        "target_values": {
                            "protein_g": 1000.0,
                            "calories_kcal": 100.0,
                        },
                    },
                    {
                        "name": "min_cost",
                        "type": "linear",
                        "metric": "cost_try",
                        "sense": "min",
                    },
                ],
                "food_bounds": {
                    "min_grams_per_food": 0.0,
                    "max_grams_per_food": 50.0,
                },
            },
        }
        put_resp = client.put("/v1/config", json=config_payload)
        assert put_resp.status_code == 200

        optimize = client.post("/v1/plan/optimize", json={"user_id": user_id, "horizon_days": 1})
        assert optimize.status_code == 422
        detail = optimize.json()["detail"]
        assert detail["code"] == "infeasible_plan"
        assert detail["stage"] >= 1
        assert detail["objective"]
        assert detail["suggested_relaxations"]
        assert any(item["constraint"] in ("protein_g", "calories_kcal") for item in detail["suggested_relaxations"])

