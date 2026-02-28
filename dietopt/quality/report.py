"""Deterministic quality rubric for generated plans."""

from __future__ import annotations

from typing import Dict, List, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

from dietopt.core.models import FoodRecord, OptimizationConfig, UserProfile, config_sanity_warnings
from dietopt.presets import derive_targets, safe_default_targets


class QualityCheck(BaseModel):
    """One quality rubric check result."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["pass", "warn", "fail"]
    message: str
    details: Dict[str, float | int | str] = Field(default_factory=dict)


class QualityReport(BaseModel):
    """Plan quality report used by API trust output."""

    model_config = ConfigDict(extra="forbid")

    calorie_realism_check: QualityCheck
    macro_plausibility_check: QualityCheck
    monotony_check: QualityCheck
    portion_sanity_check: QualityCheck
    config_sanity_check: QualityCheck
    warnings: List[str] = Field(default_factory=list)


def _add_totals(consumed: Mapping[str, float], planned: Mapping[str, float]) -> Dict[str, float]:
    keys = set(consumed.keys()) | set(planned.keys())
    totals: Dict[str, float] = {}
    for key in keys:
        totals[key] = float(consumed.get(key, 0.0)) + float(planned.get(key, 0.0))
    return totals


def _calorie_realism(
    total_day: Mapping[str, float],
    expected_targets: Mapping[str, float],
    horizon_days: int,
) -> QualityCheck:
    calories = float(total_day.get("calories_kcal", 0.0))
    target = float(expected_targets.get("calories_kcal", 2200.0)) * max(horizon_days, 1)
    lower = target * 0.85
    upper = target * 1.15
    warn_lower = target * 0.70
    warn_upper = target * 1.30

    if lower <= calories <= upper:
        status = "pass"
        message = "Total calories are close to expected target band."
    elif warn_lower <= calories <= warn_upper:
        status = "warn"
        message = "Total calories are outside preferred band but still plausible."
    else:
        status = "fail"
        message = "Total calories are implausible relative to expected target."
    return QualityCheck(
        status=status,
        message=message,
        details={
            "total_calories_kcal": round(calories, 2),
            "target_calories_kcal": round(target, 2),
            "preferred_min_kcal": round(lower, 2),
            "preferred_max_kcal": round(upper, 2),
        },
    )


def _macro_plausibility(total_day: Mapping[str, float]) -> QualityCheck:
    calories = max(float(total_day.get("calories_kcal", 0.0)), 1.0)
    protein_kcal = max(float(total_day.get("protein_g", 0.0)), 0.0) * 4.0
    carbs_kcal = max(float(total_day.get("carbs_g", 0.0)), 0.0) * 4.0
    fat_kcal = max(float(total_day.get("fat_g", 0.0)), 0.0) * 9.0

    p_ratio = protein_kcal / calories
    c_ratio = carbs_kcal / calories
    f_ratio = fat_kcal / calories
    kcal_from_macros = protein_kcal + carbs_kcal + fat_kcal
    macro_gap = abs(kcal_from_macros - calories) / calories

    strict_ok = (
        0.10 <= p_ratio <= 0.45
        and 0.20 <= c_ratio <= 0.65
        and 0.15 <= f_ratio <= 0.45
        and macro_gap <= 0.15
    )
    loose_ok = (
        0.05 <= p_ratio <= 0.55
        and 0.10 <= c_ratio <= 0.75
        and 0.10 <= f_ratio <= 0.55
        and macro_gap <= 0.30
    )

    if strict_ok:
        return QualityCheck(
            status="pass",
            message="Macro energy split looks plausible.",
            details={
                "protein_ratio": round(p_ratio, 4),
                "carbs_ratio": round(c_ratio, 4),
                "fat_ratio": round(f_ratio, 4),
                "macro_gap_ratio": round(macro_gap, 4),
            },
        )
    if loose_ok:
        return QualityCheck(
            status="warn",
            message="Macro energy split is borderline; review targets and logs.",
            details={
                "protein_ratio": round(p_ratio, 4),
                "carbs_ratio": round(c_ratio, 4),
                "fat_ratio": round(f_ratio, 4),
                "macro_gap_ratio": round(macro_gap, 4),
            },
        )
    return QualityCheck(
        status="fail",
        message="Macro energy split is implausible.",
        details={
            "protein_ratio": round(p_ratio, 4),
            "carbs_ratio": round(c_ratio, 4),
            "fat_ratio": round(f_ratio, 4),
            "macro_gap_ratio": round(macro_gap, 4),
        },
    )


def _monotony_check(
    config: OptimizationConfig,
    food_grams: Mapping[str, float],
    foods_by_id: Mapping[str, FoodRecord],
) -> QualityCheck:
    if not food_grams:
        return QualityCheck(status="warn", message="No planned foods; monotony cannot be evaluated.")

    calories_by_food: Dict[str, float] = {}
    for food_id, grams in food_grams.items():
        food = foods_by_id.get(food_id)
        if food is None:
            continue
        calories_by_food[food_id] = max(0.0, food.calories_kcal_g * float(grams))

    total_cal = sum(calories_by_food.values())
    if total_cal <= 0:
        return QualityCheck(status="warn", message="Planned calories are zero; monotony cannot be evaluated.")

    max_share = max(calories_by_food.values()) / total_cal
    variety_count = sum(1 for grams in food_grams.values() if grams >= config.diversity.variety_min_grams)
    k = config.diversity.min_variety_count
    alpha = config.diversity.max_single_food_calorie_share

    if variety_count >= k and max_share <= alpha + 1e-6:
        status = "pass"
        message = "Plan diversity and calorie concentration are within configured bounds."
    elif variety_count >= max(1, k - 1) and max_share <= min(1.0, alpha + 0.15):
        status = "warn"
        message = "Plan is somewhat repetitive; consider increasing variety."
    else:
        status = "fail"
        message = "Plan is too monotonous under current quality rubric."
    return QualityCheck(
        status=status,
        message=message,
        details={
            "max_single_food_calorie_share": round(max_share, 4),
            "configured_share_cap": round(alpha, 4),
            "variety_count": int(variety_count),
            "configured_min_variety": int(k),
        },
    )


def _portion_sanity_check(config: OptimizationConfig, food_grams: Mapping[str, float]) -> QualityCheck:
    if not food_grams:
        return QualityCheck(status="warn", message="No planned portions to evaluate.")

    max_g = config.food_bounds.max_grams_per_food
    too_large = {food_id: grams for food_id, grams in food_grams.items() if grams > max_g + 1e-6}
    very_small = sum(1 for grams in food_grams.values() if grams < 5.0)
    total_grams = sum(float(grams) for grams in food_grams.values())

    if too_large:
        return QualityCheck(
            status="fail",
            message="One or more portions exceed configured per-food limits.",
            details={"over_limit_items": len(too_large), "total_grams": round(total_grams, 2)},
        )
    if total_grams < 200.0 or total_grams > 4000.0:
        return QualityCheck(
            status="warn",
            message="Total planned grams look unusual; verify bounds and targets.",
            details={"total_grams": round(total_grams, 2), "very_small_portions": int(very_small)},
        )
    return QualityCheck(
        status="pass",
        message="Portion sizes look sane.",
        details={"total_grams": round(total_grams, 2), "very_small_portions": int(very_small)},
    )


def _config_sanity_check(config: OptimizationConfig) -> tuple[QualityCheck, List[str]]:
    warnings = config_sanity_warnings(config)
    invalid_ranges = 0
    for bound in config.constraints.values():
        if bound.min is not None and bound.max is not None and bound.min > bound.max:
            invalid_ranges += 1
    if invalid_ranges > 0:
        return (
            QualityCheck(
                status="fail",
                message="Optimization config contains invalid metric ranges.",
                details={"invalid_ranges": invalid_ranges},
            ),
            warnings,
        )
    if warnings:
        return (
            QualityCheck(
                status="warn",
                message="Optimization config is valid but has suspicious settings.",
                details={"warning_count": len(warnings)},
            ),
            warnings,
        )
    return (QualityCheck(status="pass", message="Optimization config sanity checks passed."), warnings)


def build_quality_report(
    *,
    consumed_totals: Mapping[str, float],
    planned_totals: Mapping[str, float],
    config: OptimizationConfig,
    food_grams: Mapping[str, float],
    foods_by_id: Mapping[str, FoodRecord],
    profile: UserProfile | None = None,
    preset_targets: Mapping[str, float] | None = None,
) -> QualityReport:
    """Build deterministic quality report for the current optimize output."""
    if preset_targets is not None:
        expected_targets = dict(preset_targets)
    elif profile is not None:
        expected_targets = derive_targets(profile)
    else:
        expected_targets = safe_default_targets()

    total_day = _add_totals(consumed=consumed_totals, planned=planned_totals)
    config_check, warnings = _config_sanity_check(config)

    return QualityReport(
        calorie_realism_check=_calorie_realism(
            total_day=total_day,
            expected_targets=expected_targets,
            horizon_days=config.horizon_days,
        ),
        macro_plausibility_check=_macro_plausibility(total_day=total_day),
        monotony_check=_monotony_check(
            config=config,
            food_grams=food_grams,
            foods_by_id=foods_by_id,
        ),
        portion_sanity_check=_portion_sanity_check(config=config, food_grams=food_grams),
        config_sanity_check=config_check,
        warnings=warnings,
    )

