"""Deterministic formulas for profile targets and constraints."""

from __future__ import annotations

from typing import Dict, Literal

from dietopt.core.models import MetricBound, UserProfile

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


def _bmr_mifflin_st_jeor(profile: UserProfile) -> float:
    sex_term = 5 if profile.sex == "male" else -161
    return (10.0 * profile.weight_kg) + (6.25 * profile.height_cm) - (5.0 * profile.age) + sex_term


def derive_targets(profile: UserProfile) -> Dict[str, float]:
    """Derive deterministic daily macro and health targets."""
    bmr = _bmr_mifflin_st_jeor(profile)
    tdee = bmr * _ACTIVITY_FACTORS[profile.activity_level]
    calories = tdee * (1.0 + _GOAL_CALORIE_ADJUST[profile.goal])

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


def targets_to_constraints(
    targets: Dict[str, float], strictness: Strictness = "normal"
) -> Dict[str, MetricBound]:
    """Convert targets into optimization bounds."""
    pct = _STRICTNESS_PCT[strictness]
    constraints: Dict[str, MetricBound] = {}

    ranged_metrics = ("calories_kcal", "protein_g", "carbs_g", "fat_g")
    for metric in ranged_metrics:
        center = targets[metric]
        constraints[metric] = MetricBound(min=center * (1.0 - pct), max=center * (1.0 + pct))

    constraints["fiber_g"] = MetricBound(min=targets["fiber_g"], max=None)
    constraints["sat_fat_g"] = MetricBound(min=None, max=targets["sat_fat_g"])
    constraints["sodium_mg"] = MetricBound(min=None, max=targets["sodium_mg"])
    constraints["budget_try"] = MetricBound(min=None, max=targets["budget_try"])

    return constraints

