"""LP matrix builder for continuous meal optimization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from dietopt.core.constants import CANONICAL_METRICS
from dietopt.core.models import FoodRecord, MetricBound, ObjectiveConfig, OptimizationConfig
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
    diversity_enabled: bool
    total_calorie_var_index: int | None
    variety_u_indices: Dict[str, int]


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


def _range_scale(bound: MetricBound | object) -> float:
    min_v = getattr(bound, "min", None)
    max_v = getattr(bound, "max", None)
    if min_v is not None and max_v is not None:
        return max(abs(float(max_v) - float(min_v)), 1.0)
    if min_v is not None:
        return max(abs(float(min_v)), 1.0)
    if max_v is not None:
        return max(abs(float(max_v)), 1.0)
    return 1.0


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
    total_calorie_var_index: int | None = None
    variety_u_indices: Dict[str, int] = {}
    dev_var_index: Dict[Tuple[int, str, str], int] = {}

    next_idx = n_food
    if config.diversity.enabled:
        total_calorie_var_index = next_idx
        var_bounds.append((0.0, None))
        next_idx += 1
        for food in foods:
            variety_u_indices[food.id] = next_idx
            var_bounds.append((0.0, 1.0))
            next_idx += 1

    for stage_idx, objective in enumerate(config.objectives_lex):
        if objective.type != "deviation":
            continue
        for metric in objective.targets:
            bound = remaining_bounds.get(metric)
            has_target = metric in objective.target_values
            if has_target:
                dev_var_index[(stage_idx, metric, "pos")] = next_idx
                var_bounds.append((0.0, None))
                next_idx += 1
                dev_var_index[(stage_idx, metric, "neg")] = next_idx
                var_bounds.append((0.0, None))
                next_idx += 1
            else:
                if getattr(bound, "min", None) is not None:
                    dev_var_index[(stage_idx, metric, "hinge_min")] = next_idx
                    var_bounds.append((0.0, None))
                    next_idx += 1
                if getattr(bound, "max", None) is not None:
                    dev_var_index[(stage_idx, metric, "hinge_max")] = next_idx
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
    a_eq_rows: List[np.ndarray] = []
    b_eq_vals: List[float] = []
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

    if config.diversity.enabled and total_calorie_var_index is not None:
        calories_vec = metric_vectors["calories_kcal"]
        # total_calorie variable definition: sum_i cal_i * x_i - total_cal = 0
        total_cal_eq = calories_vec.copy()
        total_cal_eq[total_calorie_var_index] = -1.0
        a_eq_rows.append(total_cal_eq)
        b_eq_vals.append(0.0)

        alpha = config.diversity.max_single_food_calorie_share
        for i, food in enumerate(foods):
            share_row = np.zeros(n_vars)
            share_row[i] = metric_value(food, "calories_kcal")
            share_row[total_calorie_var_index] = -alpha
            a_ub_rows.append(share_row)
            b_ub_vals.append(0.0)

        max_grams = config.food_bounds.max_grams_per_food
        min_grams = config.diversity.variety_min_grams
        for i, food in enumerate(foods):
            u_idx = variety_u_indices[food.id]
            # x_i <= M * u_i
            row_max = np.zeros(n_vars)
            row_max[i] = 1.0
            row_max[u_idx] = -max_grams
            a_ub_rows.append(row_max)
            b_ub_vals.append(0.0)

            # x_i >= m * u_i  ->  -x_i + m * u_i <= 0
            row_min = np.zeros(n_vars)
            row_min[i] = -1.0
            row_min[u_idx] = min_grams
            a_ub_rows.append(row_min)
            b_ub_vals.append(0.0)

        # sum(u_i) >= k
        variety_row = np.zeros(n_vars)
        for food in foods:
            variety_row[variety_u_indices[food.id]] = -1.0
        a_ub_rows.append(variety_row)
        b_ub_vals.append(-float(config.diversity.min_variety_count))

    objective_terms: List[ObjectiveTerm] = []
    for stage_idx, objective in enumerate(config.objectives_lex):
        if objective.type == "deviation":
            expr = np.zeros(n_vars)
            for metric in objective.targets:
                weight = objective.weights.get(metric, config.objective_default_weights.get(metric, 1.0))
                bound = remaining_bounds.get(metric)
                target = objective.target_values.get(metric)

                if target is not None:
                    scale = max(abs(float(target)), 1.0)
                    pos_idx = dev_var_index[(stage_idx, metric, "pos")]
                    neg_idx = dev_var_index[(stage_idx, metric, "neg")]
                    coeff = weight / scale
                    expr[pos_idx] = coeff
                    expr[neg_idx] = coeff

                    eq = np.zeros(n_vars)
                    eq += metric_vectors.get(metric, np.zeros(n_vars))
                    eq[pos_idx] = -1.0
                    eq[neg_idx] = 1.0
                    a_eq_rows.append(eq)
                    b_eq_vals.append(float(target))
                    continue

                # Hinge loss against range constraints: 0 inside [min, max].
                scale = _range_scale(bound) if bound is not None else 1.0
                coeff = weight / scale
                min_v = getattr(bound, "min", None)
                max_v = getattr(bound, "max", None)
                if min_v is not None:
                    h_idx = dev_var_index[(stage_idx, metric, "hinge_min")]
                    expr[h_idx] = coeff
                    row = -metric_vectors.get(metric, np.zeros(n_vars)).copy()
                    row[h_idx] = -1.0
                    a_ub_rows.append(row)
                    b_ub_vals.append(-float(min_v))
                if max_v is not None:
                    h_idx = dev_var_index[(stage_idx, metric, "hinge_max")]
                    expr[h_idx] = coeff
                    row = metric_vectors.get(metric, np.zeros(n_vars)).copy()
                    row[h_idx] = -1.0
                    a_ub_rows.append(row)
                    b_ub_vals.append(float(max_v))

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
        diversity_enabled=config.diversity.enabled,
        total_calorie_var_index=total_calorie_var_index,
        variety_u_indices=variety_u_indices,
    )
