"""Run deterministic quality scenarios and print markdown/JSON output."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from dietopt.core.models import FoodRecord, UserProfile
from dietopt.core.nutrition import compute_consumed_totals, compute_remaining_bounds
from dietopt.presets import derive_config_from_profile
from dietopt.quality import build_quality_report
from dietopt.solver import LPInfeasibleError, solve_lexicographic


def _load_foods(csv_path: Path) -> List[FoodRecord]:
    foods: List[FoodRecord] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            foods.append(
                FoodRecord(
                    id=row["id"],
                    name=row["name"],
                    calories_kcal_g=float(row["calories_kcal_g"]),
                    protein_g_g=float(row["protein_g_g"]),
                    carbs_g_g=float(row["carbs_g_g"]),
                    fat_g_g=float(row["fat_g_g"]),
                    fiber_g_g=float(row["fiber_g_g"]),
                    sat_fat_g_g=float(row["sat_fat_g_g"]),
                    sodium_mg_g=float(row["sodium_mg_g"]),
                    cost_try_g=float(row["cost_try_g"]),
                    preference_score_g=float(row["preference_score_g"]),
                    source=row.get("source", "local"),
                )
            )
    return foods


@dataclass(frozen=True)
class Scenario:
    name: str
    profile: UserProfile
    consumed_logs: List[Tuple[str, float]]


def _status_triplet(report: object) -> str:
    return ", ".join(
        [
            f"cal:{getattr(report, 'calorie_realism_check').status}",
            f"macro:{getattr(report, 'macro_plausibility_check').status}",
            f"mono:{getattr(report, 'monotony_check').status}",
        ]
    )


def run_quality_suite(foods_csv: Path) -> Dict[str, object]:
    foods = _load_foods(foods_csv)
    foods_by_id = {food.id: food for food in foods}

    scenarios = [
        Scenario(
            name="male_moderate_cut",
            profile=UserProfile(
                age=35,
                sex="male",
                height_cm=195,
                weight_kg=109,
                activity_level="moderate",
                goal="cut",
            ),
            consumed_logs=[("simit", 120.0), ("ayran", 250.0)],
        ),
        Scenario(
            name="female_maintain",
            profile=UserProfile(
                age=29,
                sex="female",
                height_cm=168,
                weight_kg=64,
                activity_level="light",
                goal="maintain",
            ),
            consumed_logs=[("yogurt_greek", 180.0), ("oats_dry", 60.0)],
        ),
    ]

    runs: List[Dict[str, object]] = []
    for scenario in scenarios:
        targets, _constraints, config = derive_config_from_profile(scenario.profile, strictness="normal")
        consumed = compute_consumed_totals(scenario.consumed_logs, foods_by_id=foods_by_id)
        remaining = compute_remaining_bounds(config.constraints, consumed)
        try:
            solved = solve_lexicographic(foods=foods, config=config, remaining_bounds=remaining)
            quality = build_quality_report(
                consumed_totals=consumed,
                planned_totals=solved.totals_planned,
                config=config,
                food_grams=solved.food_grams,
                foods_by_id=foods_by_id,
                profile=scenario.profile,
                preset_targets=targets,
            )
            runs.append(
                {
                    "scenario": scenario.name,
                    "status": "ok",
                    "planned_calories_kcal": round(solved.totals_planned.get("calories_kcal", 0.0), 2),
                    "quality": quality.model_dump(mode="json"),
                    "quality_status_summary": _status_triplet(quality),
                }
            )
        except LPInfeasibleError as exc:
            runs.append(
                {
                    "scenario": scenario.name,
                    "status": "infeasible",
                    "stage": exc.stage,
                    "objective": exc.objective_name,
                    "solver_message": exc.solver_message,
                }
            )

    return {"foods_csv": str(foods_csv), "runs": runs}


def _print_markdown(data: Dict[str, object]) -> None:
    runs = data["runs"]
    print("# Quality Suite")
    print()
    print(f"Foods fixture: `{data['foods_csv']}`")
    print()
    print("| scenario | status | planned_kcal | quality |")
    print("|---|---|---:|---|")
    for row in runs:  # type: ignore[assignment]
        print(
            f"| {row['scenario']} | {row['status']} | {row.get('planned_calories_kcal', '-')}"
            f" | {row.get('quality_status_summary', '-')} |"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run quality regression scenarios.")
    parser.add_argument(
        "--foods-csv",
        default=str(Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "foods_tiny.csv"),
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()

    data = run_quality_suite(Path(args.foods_csv))
    if args.format == "json":
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        _print_markdown(data)


if __name__ == "__main__":
    main()
