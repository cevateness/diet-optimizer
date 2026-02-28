"""Canonical metric names and mappings."""

from __future__ import annotations

from typing import Dict

CANONICAL_METRICS = [
    "calories_kcal",
    "protein_g",
    "carbs_g",
    "fat_g",
    "fiber_g",
    "sat_fat_g",
    "sodium_mg",
    "cost_try",
    "preference_score",
]

FOOD_METRIC_FIELD_MAP: Dict[str, str] = {
    "calories_kcal": "calories_kcal_g",
    "protein_g": "protein_g_g",
    "carbs_g": "carbs_g_g",
    "fat_g": "fat_g_g",
    "fiber_g": "fiber_g_g",
    "sat_fat_g": "sat_fat_g_g",
    "sodium_mg": "sodium_mg_g",
    "cost_try": "cost_try_g",
    "preference_score": "preference_score_g",
}

