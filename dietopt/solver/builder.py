"""LP matrix builder for continuous meal optimization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from dietopt.core.constants import CANONICAL_METRICS
from dietopt.core.models import FoodRecord, ObjectiveConfig, OptimizationConfig
from dietopt.core.nutrition import metric_value


@dataclass(frozen=True)
class ObjectiveTerm:
    """Linear expression for one stage objective."""

    config: ObjectiveConfig
    c_vector: np.ndarray
    expr_vector: np.ndarray
    sense: str


@dataclass(frozen=True)
class LPBuildResult:
    """Built LP artifacts ready for lexicographic re-solves."""

    foods: List[FoodRecord]
    n_food: int
    variable_bounds: List[Tuple[float | None, float | None]]
    A_ub: np.ndarray
    b_ub: np.ndarray
    A_eq: np.ndarray
    b_eq: np.ndarray
    objective_terms: List[ObjectiveTerm]
    metric_vectors: Dict[str, np.ndarray]


def _default_target_for_metric(metric: str, remaining_bounds: Dict[str, object]) -> float:
    bound = remaining_bounds.get(metric)
    if bound is None:
        return 0.0
    min_v = getattr(bound, "min", None)
    max_v = getattr(bound, "max", None)
    if min_v is not None and max_v is not None:
        return (float(min_v) + float(max_v)) / 2.0
    if min_v is not None:
        return float(min_v)
    if max_v is not None:
        return float(max_v)
    return 0.0


def build_lp_problem(
    foods: List[FoodRecord],
    config: OptimizationConfig,
    remaining_bounds: Dict[str, object],
) -> LPBuildResult:
    """Build base LP matrices, including deviation auxiliaries."""
    if not foods:
        raise ValueError("At least one food is required to build LP.")

    n_food = len(foods)
    food_bounds = (
        config.food_bounds.min_grams_per_food,
        config.food_bounds.max_grams_per_food,
    )

    var_bounds: List[Tuple[float | None, float | None]] = [food_bounds for _ in range(n_food)]
    dev_var_index: Dict[Tuple[int, str, str], int] = {}

    next_idx = n_food
    for stage_idx, objective in enumerate(config.objectives_lex):
        if objective.type != "deviation":
            continue
        for metric in objective.targets:
            dev_var_index[(stage_idx, metric, "pos")] = next_idx
            var_bounds.append((0.0, None))
            next_idx += 1
            dev_var_index[(stage_idx, metric, "neg")] = next_idx
            var_bounds.append((0.0, None))
            next_idx += 1

    n_vars = next_idx
    metric_vectors: Dict[str, np.ndarray] = {}
    for metric in CANONICAL_METRICS:
        v = np.zeros(n_vars)
        for i, food in enumerate(foods):
            v[i] = metric_value(food, metric)
        metric_vectors[metric] = v

    a_ub_rows: List[np.ndarray] = []
    b_ub_vals: List[float] = []
    for metric, bound in remaining_bounds.items():
        vec = metric_vectors.get(metric)
        if vec is None:
            continue
        min_v = getattr(bound, "min", None)
        max_v = getattr(bound, "max", None)
        if min_v is not None:
            a_ub_rows.append(-vec.copy())
            b_ub_vals.append(-float(min_v))
        if max_v is not None:
            a_ub_rows.append(vec.copy())
            b_ub_vals.append(float(max_v))

    a_eq_rows: List[np.ndarray] = []
    b_eq_vals: List[float] = []
    objective_terms: List[ObjectiveTerm] = []
    for stage_idx, objective in enumerate(config.objectives_lex):
        if objective.type == "deviation":
            expr = np.zeros(n_vars)
            for metric in objective.targets:
                weight = objective.weights.get(metric, 1.0)
                pos_idx = dev_var_index[(stage_idx, metric, "pos")]
                neg_idx = dev_var_index[(stage_idx, metric, "neg")]
                expr[pos_idx] = weight
                expr[neg_idx] = weight

                eq = np.zeros(n_vars)
                eq += metric_vectors.get(metric, np.zeros(n_vars))
                eq[pos_idx] = -1.0
                eq[neg_idx] = 1.0
                target = objective.target_values.get(metric, _default_target_for_metric(metric, remaining_bounds))
                a_eq_rows.append(eq)
                b_eq_vals.append(float(target))

            objective_terms.append(
                ObjectiveTerm(
                    config=objective,
                    c_vector=expr.copy(),
                    expr_vector=expr.copy(),
                    sense="min",
                )
            )
            continue

        metric_vec = metric_vectors.get(objective.metric or "", np.zeros(n_vars))
        if objective.sense == "min":
            c_vec = metric_vec.copy()
        else:
            c_vec = -metric_vec.copy()
        objective_terms.append(
            ObjectiveTerm(
                config=objective,
                c_vector=c_vec,
                expr_vector=metric_vec.copy(),
                sense=objective.sense,
            )
        )

    if not objective_terms:
        raise ValueError("No objective terms could be built from OptimizationConfig.")

    a_ub = np.vstack(a_ub_rows) if a_ub_rows else np.zeros((0, n_vars))
    b_ub = np.array(b_ub_vals, dtype=float) if b_ub_vals else np.zeros((0,), dtype=float)
    a_eq = np.vstack(a_eq_rows) if a_eq_rows else np.zeros((0, n_vars))
    b_eq = np.array(b_eq_vals, dtype=float) if b_eq_vals else np.zeros((0,), dtype=float)

    return LPBuildResult(
        foods=foods,
        n_food=n_food,
        variable_bounds=var_bounds,
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=a_eq,
        b_eq=b_eq,
        objective_terms=objective_terms,
        metric_vectors=metric_vectors,
    )

