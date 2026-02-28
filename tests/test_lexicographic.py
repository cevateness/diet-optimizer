from dietopt.core.models import FoodBounds, FoodRecord, ObjectiveConfig, OptimizationConfig
from dietopt.solver import solve_lexicographic


def test_lexicographic_picks_lower_cost_after_deviation_lock() -> None:
    foods = [
        FoodRecord(
            id="expensive_protein",
            name="Expensive Protein",
            calories_kcal_g=1.0,
            protein_g_g=0.1,
            carbs_g_g=0.0,
            fat_g_g=0.0,
            fiber_g_g=0.0,
            sat_fat_g_g=0.0,
            sodium_mg_g=0.0,
            cost_try_g=1.0,
        ),
        FoodRecord(
            id="cheap_protein",
            name="Cheap Protein",
            calories_kcal_g=1.0,
            protein_g_g=0.1,
            carbs_g_g=0.0,
            fat_g_g=0.0,
            fiber_g_g=0.0,
            sat_fat_g_g=0.0,
            sodium_mg_g=0.0,
            cost_try_g=0.2,
        ),
    ]

    config = OptimizationConfig(
        horizon_days=1,
        constraints={},
        objectives_lex=[
            ObjectiveConfig(
                name="match_protein",
                type="deviation",
                targets=["protein_g"],
                target_values={"protein_g": 10.0},
            ),
            ObjectiveConfig(
                name="min_cost",
                type="linear",
                metric="cost_try",
                sense="min",
            ),
        ],
        food_bounds=FoodBounds(min_grams_per_food=0.0, max_grams_per_food=200.0),
    )

    result = solve_lexicographic(foods=foods, config=config, remaining_bounds={})
    assert len(result.objective_report) == 2
    assert result.objective_report[0].value <= 1e-7
    assert result.food_grams.get("cheap_protein", 0.0) >= 99.99
    assert result.food_grams.get("expensive_protein", 0.0) <= 1e-4

