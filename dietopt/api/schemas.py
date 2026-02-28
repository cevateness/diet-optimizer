"""API DTOs for v1 endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from dietopt.core.models import ConstraintSlack, MetricBound, ObjectiveStageValue, OptimizationConfig
from dietopt.quality import QualityReport


class StatusResponse(BaseModel):
    status: str = "ok"
    warnings: List[str] = Field(default_factory=list)


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = None


class CreateUserResponse(StatusResponse):
    user_id: str


class ProfileUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    age: int
    sex: Literal["male", "female"]
    height_cm: float
    weight_kg: float
    activity_level: Literal["sedentary", "light", "moderate", "active", "very_active"]
    goal: Literal["cut", "maintain", "bulk"]


class DeriveTargetsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    strictness: Literal["tight", "normal", "relaxed"] = "normal"


class DeriveTargetsResponse(BaseModel):
    targets: Dict[str, float]
    constraints: Dict[str, MetricBound]


class PutConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    config: OptimizationConfig


class LogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    food_id: str
    grams: float = Field(gt=0)


class LogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    timestamp: datetime
    items: List[LogItem]


class SummaryResponse(BaseModel):
    consumed: Dict[str, float]
    remaining_bounds: Dict[str, MetricBound]
    quality_report: Optional[QualityReport] = None


class OptimizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    horizon_days: Optional[int] = None
    meal_slots: Optional[List[str]] = None


class PlanItem(BaseModel):
    food_id: str
    food_name: str
    grams: float


class PlanProvenance(BaseModel):
    foods_considered: int
    sources: List[str]
    solver: str
    generated_at: datetime


class MealSlotAssignment(BaseModel):
    slot: str
    items: List["PlanItem"]


class SubstitutionSuggestion(BaseModel):
    constraint: str
    from_food_id: str
    from_food_name: str
    to_food_id: str
    to_food_name: str
    reason: str


class OptimizeResponse(BaseModel):
    plan: List[PlanItem]
    totals_planned: Dict[str, float]
    constraint_report: List[ConstraintSlack]
    objective_report: List[ObjectiveStageValue]
    provenance: PlanProvenance
    today_plan_summary: Optional[str] = None
    meal_slots: List[MealSlotAssignment] = Field(default_factory=list)
    substitutions: List[SubstitutionSuggestion] = Field(default_factory=list)
    quality_report: Optional[QualityReport] = None


class FoodSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    provider: Literal["openfoodfacts"] = "openfoodfacts"
    limit: int = Field(default=5, ge=1, le=20)


class FoodSearchItem(BaseModel):
    food_id: str
    name: str
    source: str
    source_id: Optional[str]
    match_type: Literal["alias", "name", "provider"] = "provider"
    matched_alias: Optional[str] = None
    calories_kcal_g: float
    protein_g_g: float
    carbs_g_g: float
    fat_g_g: float
    fiber_g_g: float
    sat_fat_g_g: float
    sodium_mg_g: float


class FoodSearchResponse(BaseModel):
    items: List[FoodSearchItem]
    cached: bool
    selection_required: bool = False


class LogSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)
    provider: Literal["openfoodfacts"] = "openfoodfacts"


class LogSearchResponse(BaseModel):
    candidates: List[FoodSearchItem]
    selection_required: bool
    recommended_food_id: Optional[str] = None
    search_id: str
    expires_at: datetime


class LogSelectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    timestamp: datetime
    food_id: str
    grams: float = Field(gt=0)


class LoggedSelection(BaseModel):
    food_id: str
    food_name: str
    grams: float
    timestamp: datetime


class LogSelectResponse(StatusResponse):
    logged: LoggedSelection


class LogResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    timestamp: datetime
    search_id: str
    candidate_index: int = Field(ge=0)
    grams: float = Field(gt=0)


class LogResolveResponse(LogSelectResponse):
    resolved_from_search_id: str
    candidate_index: int


class RelaxationSuggestion(BaseModel):
    constraint: str
    issue: str
    current_min: Optional[float] = None
    current_max: Optional[float] = None
    recommended_min: Optional[float] = None
    recommended_max: Optional[float] = None
    delta: Optional[float] = None
    reason: str


class InfeasibilityResponse(BaseModel):
    code: Literal["infeasible_plan"] = "infeasible_plan"
    summary: str
    stage: int
    objective: str
    solver_message: str
    suggested_relaxations: List[RelaxationSuggestion]
