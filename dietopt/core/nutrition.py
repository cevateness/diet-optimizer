"""Pure nutrient and constraint arithmetic."""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from .constants import CANONICAL_METRICS, FOOD_METRIC_FIELD_MAP
from .models import ConstraintSlack, FoodRecord, MetricBound


def metric_value(food: FoodRecord, metric: str) -> float:
    """Return a food's per-gram value for a canonical metric."""
    field_name = FOOD_METRIC_FIELD_MAP.get(metric)
    if field_name is None:
        return 0.0
    return float(getattr(food, field_name, 0.0))


def compute_totals_for_plan(
    food_grams: Dict[str, float], foods_by_id: Dict[str, FoodRecord]
) -> Dict[str, float]:
    """Aggregate totals for selected grams per food."""
    totals = {metric: 0.0 for metric in CANONICAL_METRICS}
    for food_id, grams in food_grams.items():
        food = foods_by_id.get(food_id)
        if food is None:
            continue
        for metric in CANONICAL_METRICS:
            totals[metric] += metric_value(food, metric) * grams
    return totals


def compute_consumed_totals(
    log_items: Iterable[Tuple[str, float]], foods_by_id: Dict[str, FoodRecord]
) -> Dict[str, float]:
    """Aggregate consumed totals from `(food_id, grams)` events."""
    food_grams: Dict[str, float] = {}
    for food_id, grams in log_items:
        food_grams[food_id] = food_grams.get(food_id, 0.0) + grams
    return compute_totals_for_plan(food_grams=food_grams, foods_by_id=foods_by_id)


def compute_remaining_bounds(
    constraints: Dict[str, MetricBound], consumed_totals: Dict[str, float]
) -> Dict[str, MetricBound]:
    """Compute remaining min/max bounds for the optimization horizon."""
    remaining: Dict[str, MetricBound] = {}
    for metric, bound in constraints.items():
        consumed = consumed_totals.get(metric, 0.0)
        min_remaining = None
        max_remaining = None
        if bound.min is not None:
            min_remaining = max(0.0, float(bound.min) - consumed)
        if bound.max is not None:
            max_remaining = float(bound.max) - consumed
        remaining[metric] = MetricBound(min=min_remaining, max=max_remaining)
    return remaining


def build_constraint_report(
    planned_totals: Dict[str, float], bounds: Dict[str, MetricBound], eps: float = 1e-6
) -> List[ConstraintSlack]:
    """Build trust-layer slack report for lower and upper bounds."""
    rows: List[ConstraintSlack] = []
    for metric, bound in bounds.items():
        total = planned_totals.get(metric, 0.0)
        if bound.min is not None:
            slack = total - float(bound.min)
            status = "binding" if abs(slack) <= eps else ("violated" if slack < 0 else "ok")
            rows.append(ConstraintSlack(name=f"{metric}_min", status=status, slack=slack))
        if bound.max is not None:
            slack = float(bound.max) - total
            status = "binding" if abs(slack) <= eps else ("violated" if slack < 0 else "ok")
            rows.append(ConstraintSlack(name=f"{metric}_max", status=status, slack=slack))
    return rows

