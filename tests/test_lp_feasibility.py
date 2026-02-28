import csv
from pathlib import Path

from dietopt.core.models import FoodBounds, FoodRecord, MetricBound, ObjectiveConfig, OptimizationConfig
from dietopt.solver import solve_lexicographic


def _load_foods(csv_path: Path) -> list[FoodRecord]:
    foods: list[FoodRecord] = []
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
                    source=row["source"],
                )
            )
    return foods


def test_lp_feasible_on_tiny_dataset() -> None:
    fixture = Path(__file__).parent / "fixtures" / "foods_tiny.csv"
    foods = _load_foods(fixture)

    constraints = {
        "calories_kcal": MetricBound(min=650.0, max=1000.0),
        "protein_g": MetricBound(min=55.0, max=120.0),
        "carbs_g": MetricBound(min=40.0, max=180.0),
        "fat_g": MetricBound(min=10.0, max=70.0),
        "fiber_g": MetricBound(min=7.0),
        "sat_fat_g": MetricBound(max=20.0),
        "sodium_mg": MetricBound(max=2500.0),
        "budget_try": MetricBound(max=200.0),
    }

    config = OptimizationConfig(
        horizon_days=1,
        constraints=constraints,
        objectives_lex=[
            ObjectiveConfig(
                name="min_total_deviation",
                type="deviation",
                targets=["calories_kcal", "protein_g", "carbs_g", "fat_g"],
                target_values={
                    "calories_kcal": 800.0,
                    "protein_g": 80.0,
                    "carbs_g": 90.0,
                    "fat_g": 30.0,
                },
                tolerance=0.01,
            ),
            ObjectiveConfig(name="min_cost", type="linear", metric="cost_try", sense="min"),
        ],
        food_bounds=FoodBounds(min_grams_per_food=0.0, max_grams_per_food=400.0),
    )

    result = solve_lexicographic(foods=foods, config=config, remaining_bounds=constraints)
    assert result.objective_report
    assert result.totals_planned["calories_kcal"] >= 650.0 - 1e-5
    assert result.totals_planned["calories_kcal"] <= 1000.0 + 1e-5
    assert result.totals_planned["protein_g"] >= 55.0 - 1e-5
    assert result.totals_planned["sat_fat_g"] <= 20.0 + 1e-5

