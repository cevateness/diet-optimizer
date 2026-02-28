from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from dietopt.api.main import create_app
from dietopt.providers import ProviderUnavailableError


def test_logs_search_select_with_turkish_alias_falls_back_to_local(tmp_path: Path) -> None:
    app = create_app(db_url=f"sqlite:///{tmp_path / 'alias_flow.db'}", seed_defaults=True)

    class _FailingProvider:
        name = "openfoodfacts"

        def search_foods(self, query: str, limit: int = 5):
            raise ProviderUnavailableError("provider down")

    with TestClient(app) as client:
        client.app.state.providers["openfoodfacts"] = _FailingProvider()

        user_resp = client.post("/v1/users", json={"name": "alias-user"})
        assert user_resp.status_code == 200
        user_id = user_resp.json()["user_id"]

        search_resp = client.post(
            "/v1/logs/search",
            json={"query": "simit", "limit": 5, "provider": "openfoodfacts"},
        )
        assert search_resp.status_code == 200
        payload = search_resp.json()
        assert payload["candidates"]
        assert payload["recommended_food_id"] == "simit"
        assert payload["candidates"][0]["match_type"] in ("alias", "name")
        assert payload["search_id"]

        resolve_resp = client.post(
            "/v1/logs/resolve",
            json={
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "search_id": payload["search_id"],
                "candidate_index": 0,
                "grams": 90.0,
            },
        )
        assert resolve_resp.status_code == 200

        summary = client.get("/v1/summary/today", params={"user_id": user_id})
        assert summary.status_code == 200
        assert summary.json()["consumed"]["calories_kcal"] > 0
