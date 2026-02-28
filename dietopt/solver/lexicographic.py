"""Lexicographic LP solve wrapper built on SciPy HiGHS."""

from __future__ import annotations

from typing import Dict, List

import numpy as np
from pydantic import BaseModel
from scipy.optimize import linprog

from dietopt.core.constants import CANONICAL_METRICS
from dietopt.core.models import ConstraintSlack, FoodRecord, ObjectiveStageValue, OptimizationConfig
from dietopt.core.nutrition import build_constraint_report

from .builder import LPBuildResult, ObjectiveTerm, build_lp_problem


class LPInfeasibleError(ValueError):
    """Raised when the LP model is infeasible for the active objective stage."""

    def __init__(self, stage: int, objective_name: str, solver_message: str) -> None:
        super().__init__(solver_message)
        self.stage = stage
        self.objective_name = objective_name
        self.solver_message = solver_message


class LexicographicSolveResult(BaseModel):
    """Output of the lexicographic optimization sequence."""

    food_grams: Dict[str, float]
    totals_planned: Dict[str, float]
    objective_report: List[ObjectiveStageValue]
    constraint_report: List[ConstraintSlack]


def _abs_tolerance(obj: ObjectiveTerm, value: float) -> float:
    tol = obj.config.tolerance
    if tol <= 0:
        return 0.0
    if obj.config.tolerance_mode == "absolute":
        return tol
    return abs(value) * tol


def _run_single_stage(
    build: LPBuildResult,
    c_vec: np.ndarray,
    a_ub: np.ndarray,
    b_ub: np.ndarray,
    stage: int,
    objective_name: str,
) -> np.ndarray:
    res = linprog(
        c=c_vec,
        A_ub=a_ub if a_ub.size else None,
        b_ub=b_ub if b_ub.size else None,
        A_eq=build.A_eq if build.A_eq.size else None,
        b_eq=build.b_eq if build.b_eq.size else None,
        bounds=build.variable_bounds,
        method="highs",
    )
    if not res.success or res.x is None:
        if res.status == 2:
            raise LPInfeasibleError(stage=stage, objective_name=objective_name, solver_message=res.message)
        raise ValueError(f"LP solve failed: {res.message}")
    return res.x


def _add_lock_constraint(
    a_ub: np.ndarray,
    b_ub: np.ndarray,
    objective: ObjectiveTerm,
    value: float,
    tol_abs: float,
) -> tuple[np.ndarray, np.ndarray]:
    if objective.sense == "max":
        row = -objective.expr_vector.copy()
        rhs = -(value - tol_abs)
    else:
        row = objective.expr_vector.copy()
        rhs = value + tol_abs

    if a_ub.size == 0:
        return row.reshape(1, -1), np.array([rhs], dtype=float)
    return np.vstack([a_ub, row]), np.append(b_ub, rhs)


def _extract_food_grams(foods: List[FoodRecord], solution: np.ndarray) -> Dict[str, float]:
    grams: Dict[str, float] = {}
    for i, food in enumerate(foods):
        value = float(solution[i])
        if value > 1e-6:
            grams[food.id] = value
    return grams


def solve_lexicographic(
    foods: List[FoodRecord],
    config: OptimizationConfig,
    remaining_bounds: Dict[str, object],
) -> LexicographicSolveResult:
    """Solve a sequence of LP objectives using tolerance-locked lexicographic stages."""
    build = build_lp_problem(foods=foods, config=config, remaining_bounds=remaining_bounds)

    a_ub = build.A_ub.copy()
    b_ub = build.b_ub.copy()
    objective_rows: List[ObjectiveStageValue] = []
    last_solution = None

    for idx, obj_term in enumerate(build.objective_terms, start=1):
        solution = _run_single_stage(
            build=build,
            c_vec=obj_term.c_vector,
            a_ub=a_ub,
            b_ub=b_ub,
            stage=idx,
            objective_name=obj_term.config.name,
        )
        value = float(np.dot(obj_term.expr_vector, solution))
        tol_abs = _abs_tolerance(obj_term, value)
        objective_rows.append(
            ObjectiveStageValue(
                stage=idx,
                name=obj_term.config.name,
                value=value,
                tolerance=tol_abs,
            )
        )
        last_solution = solution

        if idx < len(build.objective_terms):
            a_ub, b_ub = _add_lock_constraint(
                a_ub=a_ub,
                b_ub=b_ub,
                objective=obj_term,
                value=value,
                tol_abs=tol_abs,
            )

    if last_solution is None:
        raise ValueError("No lexicographic stages executed.")

    food_grams = _extract_food_grams(foods=foods, solution=last_solution)
    totals_planned: Dict[str, float] = {}
    for metric in CANONICAL_METRICS:
        metric_vec = build.metric_vectors.get(metric)
        totals_planned[metric] = float(np.dot(metric_vec, last_solution)) if metric_vec is not None else 0.0

    constraint_report = build_constraint_report(
        planned_totals=totals_planned,
        bounds=remaining_bounds,
    )

    return LexicographicSolveResult(
        food_grams=food_grams,
        totals_planned=totals_planned,
        objective_report=objective_rows,
        constraint_report=constraint_report,
    )
