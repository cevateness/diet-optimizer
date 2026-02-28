import csv
from pathlib import Path

from dietopt.core.models import DiversityConfig, FoodBounds, FoodRecord, MetricBound, ObjectiveConfig, OptimizationConfig, UserProfile
from dietopt.presets import derive_targets, targets_to_constraints
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
                    source=row.get("source", "local"),
                )
            )
    return foods


def test_derived_targets_sanity_for_tall_heavy_moderate_cut() -> None:
    profile = UserProfile(
        age=35,
        sex="male",
        height_cm=195.0,
        weight_kg=109.0,
        activity_level="moderate",
        goal="cut",
    )
    targets = derive_targets(profile)
    constraints = targets_to_constraints(targets, strictness="normal")

    assert targets["calories_kcal"] > 2000.0
    assert constraints["calories_kcal"].max is not None
    assert constraints["calories_kcal"].max > 1900.0


def test_variety_proxy_enforced_when_feasible() -> None:
    fixture = Path(__file__).parent / "fixtures" / "foods_tiny.csv"
    foods = _load_foods(fixture)[:3]
    variety_min_grams = 30.0

    config = OptimizationConfig(
        horizon_days=1,
        constraints={"calories_kcal": MetricBound(min=700.0, max=2000.0)},
        objectives_lex=[
            ObjectiveConfig(
                name="min_dev",
                type="deviation",
                targets=["calories_kcal"],
                target_values={"calories_kcal": 1200.0},
            ),
            ObjectiveConfig(name="min_cost", type="linear", metric="cost_try", sense="min"),
        ],
        food_bounds=FoodBounds(min_grams_per_food=0.0, max_grams_per_food=400.0),
        diversity=DiversityConfig(
            enabled=True,
            min_variety_count=3,
            variety_min_grams=variety_min_grams,
            max_single_food_calorie_share=0.8,
        ),
    )

    result = solve_lexicographic(foods=foods, config=config, remaining_bounds=config.constraints)
    selected_above_min = sum(1 for grams in result.food_grams.values() if grams >= variety_min_grams - 1e-6)
    assert selected_above_min >= 3


def test_calorie_share_cap_respected() -> None:
    fixture = Path(__file__).parent / "fixtures" / "foods_tiny.csv"
    foods = _load_foods(fixture)
    alpha = 0.45

    config = OptimizationConfig(
        horizon_days=1,
        constraints={"calories_kcal": MetricBound(min=800.0, max=1600.0)},
        objectives_lex=[
            ObjectiveConfig(
                name="min_dev",
                type="deviation",
                targets=["calories_kcal", "protein_g"],
                target_values={"calories_kcal": 1200.0, "protein_g": 100.0},
            ),
            ObjectiveConfig(name="min_cost", type="linear", metric="cost_try", sense="min"),
        ],
        food_bounds=FoodBounds(min_grams_per_food=0.0, max_grams_per_food=350.0),
        diversity=DiversityConfig(
            enabled=True,
            min_variety_count=2,
            variety_min_grams=20.0,
            max_single_food_calorie_share=alpha,
        ),
    )

    result = solve_lexicographic(foods=foods, config=config, remaining_bounds=config.constraints)
    total_cal = result.totals_planned["calories_kcal"]
    assert total_cal > 0
    foods_by_id = {food.id: food for food in foods}
    for food_id, grams in result.food_grams.items():
        calories = foods_by_id[food_id].calories_kcal_g * grams
        share = calories / total_cal
        assert share <= alpha + 1e-6

