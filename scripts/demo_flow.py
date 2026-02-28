"""End-to-end API demo flow for local MVP verification.

Assumes API is running at http://127.0.0.1:8000 by default.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def api_call(base_url: str, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(url=url, data=body, headers=headers, method=method.upper())
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"raw": raw}
        return exc.code, data
    except URLError as exc:
        raise RuntimeError(f"Could not reach API at {url}: {exc}") from exc


def _print(title: str, data: Any) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def run_demo(base_url: str) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()

    status, user = api_call(base_url, "POST", "/v1/users", {"name": "demo-user"})
    if status != 200:
        raise RuntimeError(f"Failed to create user: {status} {user}")
    user_id = user["user_id"]
    _print("Create user", user)

    status, profile = api_call(
        base_url,
        "POST",
        "/v1/profile",
        {
            "user_id": user_id,
            "age": 30,
            "sex": "male",
            "height_cm": 180,
            "weight_kg": 85,
            "activity_level": "moderate",
            "goal": "maintain",
        },
    )
    if status != 200:
        raise RuntimeError(f"Failed to set profile: {status} {profile}")
    _print("Set profile", profile)

    status, derived = api_call(
        base_url,
        "POST",
        "/v1/profile/derive-targets",
        {"user_id": user_id, "strictness": "normal"},
    )
    if status != 200:
        raise RuntimeError(f"Failed to derive targets: {status} {derived}")
    _print("Derived targets", derived)

    targets = derived["targets"]
    status, config_resp = api_call(
        base_url,
        "PUT",
        "/v1/config",
        {
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
                    {"name": "min_cost", "type": "linear", "metric": "cost_try", "sense": "min"},
                ],
                "food_bounds": {"min_grams_per_food": 0, "max_grams_per_food": 400},
            },
        },
    )
    if status != 200:
        raise RuntimeError(f"Failed to set config: {status} {config_resp}")
    _print("Set config", config_resp)

    status, log_search = api_call(
        base_url,
        "POST",
        "/v1/logs/search",
        {"query": "simit", "limit": 5, "provider": "openfoodfacts"},
    )
    if status != 200:
        raise RuntimeError(f"Failed to search log candidates: {status} {log_search}")
    _print("Search for 'simit'", log_search)
    if not log_search["candidates"]:
        raise RuntimeError("No candidates returned for simit.")

    selected_food_id = log_search["recommended_food_id"] or log_search["candidates"][0]["food_id"]
    status, selected = api_call(
        base_url,
        "POST",
        "/v1/logs/select",
        {
            "user_id": user_id,
            "timestamp": now_iso,
            "food_id": selected_food_id,
            "grams": 120.0,
        },
    )
    if status != 200:
        raise RuntimeError(f"Failed to log selected food: {status} {selected}")
    _print("Log selected food", selected)

    status, summary = api_call(base_url, "GET", f"/v1/summary/today?user_id={user_id}")
    if status != 200:
        raise RuntimeError(f"Failed to fetch summary: {status} {summary}")
    _print("Today summary", summary)

    status, plan = api_call(
        base_url,
        "POST",
        "/v1/plan/optimize",
        {"user_id": user_id, "horizon_days": 1, "meal_slots": ["lunch", "dinner", "snack"]},
    )
    if status != 200:
        raise RuntimeError(f"Failed to optimize plan: {status} {plan}")
    _print("Optimize plan", plan)

    # Demonstrate infeasible case with intentionally conflicting bounds.
    status, inf_cfg = api_call(
        base_url,
        "PUT",
        "/v1/config",
        {
            "user_id": user_id,
            "config": {
                "horizon_days": 1,
                "constraints": {
                    "protein_g": {"min": 1000.0},
                    "calories_kcal": {"max": 150.0},
                },
                "objectives_lex": [
                    {
                        "name": "min_total_deviation",
                        "type": "deviation",
                        "targets": ["protein_g", "calories_kcal"],
                        "target_values": {"protein_g": 1000.0, "calories_kcal": 100.0},
                    }
                ],
                "food_bounds": {"min_grams_per_food": 0, "max_grams_per_food": 50},
            },
        },
    )
    if status != 200:
        raise RuntimeError(f"Failed to set infeasible config: {status} {inf_cfg}")

    status, infeasible = api_call(base_url, "POST", "/v1/plan/optimize", {"user_id": user_id, "horizon_days": 1})
    if status != 422:
        raise RuntimeError(f"Expected 422 infeasible response, got {status}: {infeasible}")
    _print("Infeasible response (expected 422)", infeasible)

    print("\nDemo flow completed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an API demo flow against dietopt service.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    run_demo(args.base_url)


if __name__ == "__main__":
    main()

