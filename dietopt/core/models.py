"""Core data models shared across modules."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


DEFAULT_OBJECTIVE_WEIGHTS: Dict[str, float] = {
    "calories_kcal": 1.0,
    "protein_g": 1.2,
    "carbs_g": 0.8,
    "fat_g": 0.9,
    "fiber_g": 0.6,
    "sat_fat_g": 0.6,
    "sodium_mg": 0.4,
    "budget_try": 0.5,
}


class MetricBound(BaseModel):
    """Lower/upper bound for a metric."""

    model_config = ConfigDict(extra="forbid")

    min: Optional[float] = None
    max: Optional[float] = None


class FoodBounds(BaseModel):
    """Variable bounds for each food decision variable (grams)."""

    model_config = ConfigDict(extra="forbid")

    min_grams_per_food: float = 0.0
    max_grams_per_food: float = 600.0

    @model_validator(mode="after")
    def _check_bounds(self) -> "FoodBounds":
        if self.min_grams_per_food < 0:
            raise ValueError("min_grams_per_food must be >= 0")
        if self.max_grams_per_food < self.min_grams_per_food:
            raise ValueError("max_grams_per_food must be >= min_grams_per_food")
        return self


class ObjectiveConfig(BaseModel):
    """Objective definition for lexicographic LP."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: Literal["deviation", "linear"]
    targets: List[str] = Field(default_factory=list)
    metric: Optional[str] = None
    sense: Literal["min", "max"] = "min"
    weights: Dict[str, float] = Field(default_factory=dict)
    target_values: Dict[str, float] = Field(default_factory=dict)
    tolerance: float = 0.0
    tolerance_mode: Literal["relative", "absolute"] = "relative"

    @model_validator(mode="after")
    def _validate_shape(self) -> "ObjectiveConfig":
        if self.type == "deviation" and not self.targets:
            raise ValueError("deviation objective requires non-empty targets")
        if self.type == "linear" and not self.metric:
            raise ValueError("linear objective requires metric")
        if self.tolerance < 0:
            raise ValueError("tolerance must be >= 0")
        return self


class DiversityConfig(BaseModel):
    """Anti-monotony LP settings (continuous proxy constraints)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_single_food_calorie_share: float = 0.65
    min_variety_count: int = 2
    variety_min_grams: float = 25.0

    @model_validator(mode="after")
    def _validate_diversity(self) -> "DiversityConfig":
        if not (0.0 < self.max_single_food_calorie_share <= 1.0):
            raise ValueError("max_single_food_calorie_share must be in (0, 1]")
        if self.min_variety_count < 1:
            raise ValueError("min_variety_count must be >= 1")
        if self.variety_min_grams <= 0:
            raise ValueError("variety_min_grams must be > 0")
        return self


class OptimizationConfig(BaseModel):
    """User-scoped optimization config (constraints + objective sequence)."""

    model_config = ConfigDict(extra="forbid")

    horizon_days: int = 1
    constraints: Dict[str, MetricBound] = Field(default_factory=dict)
    objectives_lex: List[ObjectiveConfig] = Field(default_factory=list)
    food_bounds: FoodBounds = Field(default_factory=FoodBounds)
    objective_default_weights: Dict[str, float] = Field(default_factory=lambda: DEFAULT_OBJECTIVE_WEIGHTS.copy())
    diversity: DiversityConfig = Field(default_factory=DiversityConfig)

    @model_validator(mode="after")
    def _validate_config(self) -> "OptimizationConfig":
        if self.horizon_days < 1:
            raise ValueError("horizon_days must be >= 1")
        if not self.objectives_lex:
            raise ValueError("objectives_lex must include at least one objective")
        for metric, bound in self.constraints.items():
            min_v = bound.min
            max_v = bound.max
            if min_v is not None and max_v is not None and min_v > max_v:
                raise ValueError(f"invalid range for {metric}: min cannot exceed max")
        return self


class UserProfile(BaseModel):
    """Deterministic preset input profile."""

    model_config = ConfigDict(extra="forbid")

    age: int
    sex: Literal["male", "female"]
    height_cm: float
    weight_kg: float
    activity_level: Literal["sedentary", "light", "moderate", "active", "very_active"]
    goal: Literal["cut", "maintain", "bulk"]


class FoodRecord(BaseModel):
    """Canonical food record with per-gram nutrient values."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    calories_kcal_g: float
    protein_g_g: float
    carbs_g_g: float
    fat_g_g: float
    fiber_g_g: float
    sat_fat_g_g: float
    sodium_mg_g: float
    cost_try_g: float = 0.0
    preference_score_g: float = 0.0
    source: str = "local"
    source_id: Optional[str] = None
    retrieved_at: Optional[datetime] = None


class ObjectiveStageValue(BaseModel):
    """Result row for one lexicographic stage."""

    stage: int
    name: str
    value: float
    tolerance: float


class ConstraintSlack(BaseModel):
    """Constraint-level trust report row."""

    name: str
    status: Literal["ok", "binding", "violated"]
    slack: float


def config_sanity_warnings(config: OptimizationConfig) -> List[str]:
    """Return non-fatal warnings for suspicious but syntactically valid config."""
    warnings: List[str] = []
    calories = config.constraints.get("calories_kcal")
    if calories is not None:
        if calories.max is not None and calories.max < 1200 * config.horizon_days:
            warnings.append(
                "calories_kcal.max appears very low for the configured horizon; this may cause unrealistic plans."
            )
        if calories.min is not None and calories.min < 900 * config.horizon_days:
            warnings.append(
                "calories_kcal.min appears unusually low for the configured horizon; verify profile/preset strictness."
            )
    if config.diversity.min_variety_count > 10:
        warnings.append("diversity.min_variety_count is high and may increase infeasibility risk.")
    if config.diversity.max_single_food_calorie_share < 0.30:
        warnings.append(
            "diversity.max_single_food_calorie_share is strict; consider >= 0.40 if infeasibility occurs."
        )
    return warnings
