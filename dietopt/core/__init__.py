"""Core domain models and pure computations."""

from .conversions import grams_to_servings, servings_to_grams
from .models import (
    FoodBounds,
    FoodRecord,
    MetricBound,
    ObjectiveConfig,
    OptimizationConfig,
    UserProfile,
)
from .nutrition import (
    build_constraint_report,
    compute_consumed_totals,
    compute_remaining_bounds,
)

__all__ = [
    "FoodBounds",
    "FoodRecord",
    "MetricBound",
    "ObjectiveConfig",
    "OptimizationConfig",
    "UserProfile",
    "grams_to_servings",
    "servings_to_grams",
    "build_constraint_report",
    "compute_consumed_totals",
    "compute_remaining_bounds",
]

