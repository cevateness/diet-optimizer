"""Deterministic formulas for profile targets and constraints."""

from __future__ import annotations

from typing import Dict, Literal

from dietopt.core.models import (
    DiversityConfig,
    MetricBound,
    ObjectiveConfig,
    OptimizationConfig,
    UserProfile,
)

Strictness = Literal["tight", "normal", "relaxed"]

_ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

_GOAL_CALORIE_ADJUST = {
    "cut": -0.20,
    "maintain": 0.0,
    "bulk": 0.10,
}

_GOAL_PROTEIN_G_PER_KG = {
    "cut": 2.0,
    "maintain": 1.6,
    "bulk": 1.8,
}

_GOAL_FAT_G_PER_KG = {
    "cut": 0.8,
    "maintain": 0.9,
    "bulk": 1.0,
}

_STRICTNESS_PCT = {
    "tight": 0.03,
    "normal": 0.05,
    "relaxed": 0.10,
}

_MIN_CALORIES_BY_SEX = {
    "male": 1500.0,
    "female": 1200.0,
}

_SAFE_DEFAULT_TARGETS = {
    "calories_kcal": 2200.0,
    "protein_g": 120.0,
    "carbs_g": 250.0,
    "fat_g": 75.0,
    "fiber_g": 30.0,
    "sat_fat_g": 24.0,
    "sodium_mg": 2300.0,
    "budget_try": 220.0,
}


def _bmr_mifflin_st_jeor(profile: UserProfile) -> float:
    sex_term = 5 if profile.sex == "male" else -161
    return (10.0 * profile.weight_kg) + (6.25 * profile.height_cm) - (5.0 * profile.age) + sex_term


def derive_targets(profile: UserProfile) -> Dict[str, float]:
    """Derive deterministic daily macro and health targets."""
    bmr = _bmr_mifflin_st_jeor(profile)
    tdee = bmr * _ACTIVITY_FACTORS[profile.activity_level]
    calories = tdee * (1.0 + _GOAL_CALORIE_ADJUST[profile.goal])
    calories = max(_MIN_CALORIES_BY_SEX[profile.sex], calories)

    protein_g = profile.weight_kg * _GOAL_PROTEIN_G_PER_KG[profile.goal]
    fat_g = profile.weight_kg * _GOAL_FAT_G_PER_KG[profile.goal]
    carb_kcal = max(0.0, calories - (protein_g * 4.0) - (fat_g * 9.0))
    carbs_g = carb_kcal / 4.0

    fiber_g = max(30.0, (calories / 1000.0) * 14.0)
    sat_fat_g = (calories * 0.10) / 9.0

    return {
        "calories_kcal": round(calories, 2),
        "protein_g": round(protein_g, 2),
        "carbs_g": round(carbs_g, 2),
        "fat_g": round(fat_g, 2),
        "fiber_g": round(fiber_g, 2),
        "sat_fat_g": round(sat_fat_g, 2),
        "sodium_mg": 2300.0,
        "budget_try": round(max(120.0, calories * 0.10), 2),
    }


def safe_default_targets() -> Dict[str, float]:
    """Fallback target set when no profile exists."""
    return _SAFE_DEFAULT_TARGETS.copy()


def targets_to_constraints(
    targets: Dict[str, float], strictness: Strictness = "normal"
) -> Dict[str, MetricBound]:
    """Convert targets into optimization bounds."""
    pct = _STRICTNESS_PCT[strictness]
    constraints: Dict[str, MetricBound] = {}

    ranged_metrics = ("calories_kcal", "protein_g", "carbs_g", "fat_g")
    for metric in ranged_metrics:
        center = targets[metric]
        if metric == "calories_kcal":
            center = max(1700.0, center)
        constraints[metric] = MetricBound(min=center * (1.0 - pct), max=center * (1.0 + pct))

    constraints["fiber_g"] = MetricBound(min=targets["fiber_g"], max=None)
    constraints["sat_fat_g"] = MetricBound(min=None, max=targets["sat_fat_g"])
    constraints["sodium_mg"] = MetricBound(min=None, max=targets["sodium_mg"])
    constraints["budget_try"] = MetricBound(min=None, max=targets["budget_try"])

    return constraints


def build_optimization_config(
    targets: Dict[str, float],
    constraints: Dict[str, MetricBound],
    horizon_days: int = 1,
) -> OptimizationConfig:
    """Create a deterministic baseline OptimizationConfig from targets."""
    deviation_targets = ["calories_kcal", "protein_g", "carbs_g", "fat_g", "fiber_g"]
    target_values = {metric: float(targets[metric]) for metric in deviation_targets if metric in targets}
    return OptimizationConfig(
        horizon_days=horizon_days,
        constraints=constraints,
        objectives_lex=[
            ObjectiveConfig(
                name="min_normalized_deviation",
                type="deviation",
                targets=deviation_targets,
                target_values=target_values,
                tolerance=0.01,
                tolerance_mode="relative",
            ),
            ObjectiveConfig(name="min_cost", type="linear", metric="cost_try", sense="min"),
        ],
        diversity=DiversityConfig(
            enabled=True,
            max_single_food_calorie_share=0.65,
            min_variety_count=3,
            variety_min_grams=20.0,
        ),
    )


def derive_config_from_profile(
    profile: UserProfile,
    strictness: Strictness = "normal",
    horizon_days: int = 1,
) -> tuple[Dict[str, float], Dict[str, MetricBound], OptimizationConfig]:
    """Derive targets + constraints + config from profile in one deterministic call."""
    targets = derive_targets(profile)
    constraints = targets_to_constraints(targets, strictness=strictness)
    config = build_optimization_config(targets=targets, constraints=constraints, horizon_days=horizon_days)
    return targets, constraints, config
