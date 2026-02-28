from pathlib import Path

from fastapi.testclient import TestClient

from dietopt.api.main import create_app
from dietopt.providers import ProviderUnavailableError


def test_food_search_provider_failure_returns_502(tmp_path: Path) -> None:
    app = create_app(db_url=f"sqlite:///{tmp_path / 'err.db'}", seed_defaults=False)

    class _FailingProvider:
        name = "openfoodfacts"

        def search_foods(self, query: str, limit: int = 5):
            raise ProviderUnavailableError("Open Food Facts request failed: test error")

    with TestClient(app) as client:
        client.app.state.providers["openfoodfacts"] = _FailingProvider()
        resp = client.post(
            "/v1/foods/search",
            json={"query": "provider-unreachable-only-term", "provider": "openfoodfacts", "limit": 5},
        )
        assert resp.status_code == 502
        assert "Open Food Facts request failed" in resp.json()["detail"]
