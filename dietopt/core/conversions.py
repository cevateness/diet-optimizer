"""Unit conversion helpers."""

from __future__ import annotations


def servings_to_grams(servings: float, grams_per_serving: float) -> float:
    """Convert serving count to grams."""
    if grams_per_serving <= 0:
        raise ValueError("grams_per_serving must be positive")
    return servings * grams_per_serving


def grams_to_servings(grams: float, grams_per_serving: float) -> float:
    """Convert grams to serving count."""
    if grams_per_serving <= 0:
        raise ValueError("grams_per_serving must be positive")
    return grams / grams_per_serving

