from dietopt.bot import TelegramAdapter


class _FakeApiClient:
    def __init__(self) -> None:
        self.selected = []

    def logs_search(self, query: str, limit: int = 5):
        if query == "ambiguous":
            return {
                "candidates": [
                    {"food_id": "a", "name": "A"},
                    {"food_id": "b", "name": "B"},
                ],
                "selection_required": True,
                "recommended_food_id": "a",
            }
        return {
            "candidates": [{"food_id": "simit", "name": "Simit"}],
            "selection_required": False,
            "recommended_food_id": "simit",
        }

    def logs_select(self, user_id: str, food_id: str, grams: float, timestamp=None):
        self.selected.append((user_id, food_id, grams))
        return {"status": "ok", "logged": {"food_id": food_id, "grams": grams}}

    def logs_resolve(self, user_id: str, search_id: str, candidate_index: int, grams: float, timestamp=None):
        self.selected.append((user_id, f"{search_id}:{candidate_index}", grams))
        return {
            "status": "ok",
            "resolved_from_search_id": search_id,
            "candidate_index": candidate_index,
            "logged": {"food_id": "resolved-food", "grams": grams},
        }

    def summary_today(self, user_id: str):
        return {"consumed": {"calories_kcal": 100.0}}

    def optimize_today(self, user_id: str):
        return 200, {"plan": [], "today_plan_summary": "ok"}


def test_telegram_adapter_help_and_choose_candidate() -> None:
    adapter = TelegramAdapter(enabled=True, api_client=_FakeApiClient())
    help_resp = adapter.handle_message("invalid format", user_id="u1")
    assert help_resp["status"] == "help"

    choose_resp = adapter.handle_message("ambiguous 100g", user_id="u1")
    assert choose_resp["status"] == "choose_candidate"
    assert len(choose_resp["candidates"]) == 2


def test_telegram_adapter_logs_and_optimizes_on_single_candidate() -> None:
    fake = _FakeApiClient()
    adapter = TelegramAdapter(enabled=True, api_client=fake)
    resp = adapter.handle_message("simit 120g", user_id="u1")
    assert resp["status"] == "logged_and_optimized"
    assert fake.selected
    assert fake.selected[0][1] == "simit"
    assert fake.selected[0][2] == 120.0


def test_telegram_adapter_handle_selection_uses_logs_resolve() -> None:
    fake = _FakeApiClient()
    adapter = TelegramAdapter(enabled=True, api_client=fake)
    resp = adapter.handle_selection(user_id="u1", search_id="sid-1", candidate_index=1, grams=80.0)
    assert resp["status"] == "resolved_and_optimized"
    assert fake.selected
    assert fake.selected[0][1] == "sid-1:1"
