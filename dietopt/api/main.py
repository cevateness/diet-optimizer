"""FastAPI app for diet optimizer MVP."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
from typing import Dict, Generator, List, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from dietopt.core.models import FoodRecord, OptimizationConfig, UserProfile, config_sanity_warnings
from dietopt.core.nutrition import compute_consumed_totals, compute_remaining_bounds, metric_value
from dietopt.presets import (
    build_optimization_config,
    derive_config_from_profile,
    derive_targets,
    safe_default_targets,
    targets_to_constraints,
)
from dietopt.providers import OpenFoodFactsProvider, ProviderUnavailableError, search_and_cache_foods
from dietopt.quality import build_quality_report
from dietopt.solver import LPInfeasibleError, solve_lexicographic
from dietopt.store import (
    DEFAULT_FOOD_ALIASES,
    add_logs,
    create_log_search_session,
    create_db_and_tables,
    create_user,
    get_engine,
    get_food_records,
    get_foods,
    get_latest_plan_for_date,
    get_log_search_session,
    get_logs_between,
    get_profile,
    get_session,
    get_user,
    get_user_config,
    load_food_aliases,
    load_foods_from_csv,
    normalize_alias_text,
    save_plan,
    search_food_aliases,
    upsert_profile,
    upsert_user_config,
)

from .schemas import (
    CreateUserRequest,
    CreateUserResponse,
    DeriveTargetsRequest,
    DeriveTargetsResponse,
    FoodSearchItem,
    FoodSearchRequest,
    FoodSearchResponse,
    InfeasibilityResponse,
    LogRequest,
    LogSearchRequest,
    LogSearchResponse,
    LogResolveRequest,
    LogResolveResponse,
    LogSelectRequest,
    LogSelectResponse,
    LoggedSelection,
    MealSlotAssignment,
    OptimizeRequest,
    OptimizeResponse,
    PlanItem,
    PlanProvenance,
    ProfileUpsertRequest,
    PutConfigRequest,
    RelaxationSuggestion,
    StatusResponse,
    SubstitutionSuggestion,
    SummaryResponse,
)


def _to_utc_naive(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts
    return ts.astimezone(timezone.utc).replace(tzinfo=None)


def _day_window(day: date, horizon_days: int = 1) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    end = start + timedelta(days=horizon_days)
    return start, end


def _food_item(
    food: FoodRecord,
    match_type: Literal["alias", "name", "provider"],
    matched_alias: str | None = None,
) -> FoodSearchItem:
    return FoodSearchItem(
        food_id=food.id,
        name=food.name,
        source=food.source,
        source_id=food.source_id,
        match_type=match_type,
        matched_alias=matched_alias,
        calories_kcal_g=food.calories_kcal_g,
        protein_g_g=food.protein_g_g,
        carbs_g_g=food.carbs_g_g,
        fat_g_g=food.fat_g_g,
        fiber_g_g=food.fiber_g_g,
        sat_fat_g_g=food.sat_fat_g_g,
        sodium_mg_g=food.sodium_mg_g,
    )


def _search_candidates_local(
    session: Session,
    query: str,
    limit: int,
) -> list[FoodSearchItem]:
    foods = get_food_records(session)
    foods_by_id = {food.id: food for food in foods}
    normalized = normalize_alias_text(query)
    if not normalized:
        return []

    dedup: dict[str, FoodSearchItem] = {}

    alias_rows = search_food_aliases(session=session, query=normalized, limit=limit * 5)
    alias_rows = sorted(alias_rows, key=lambda row: (0 if row.alias_norm == normalized else 1, len(row.alias_norm)))
    for alias_row in alias_rows:
        food = foods_by_id.get(alias_row.food_id)
        if food is None or food.id in dedup:
            continue
        dedup[food.id] = _food_item(food=food, match_type="alias", matched_alias=alias_row.alias_text)
        if len(dedup) >= limit:
            return list(dedup.values())

    for food in foods:
        if food.id in dedup:
            continue
        if normalized in normalize_alias_text(food.name):
            dedup[food.id] = _food_item(food=food, match_type="name")
            if len(dedup) >= limit:
                break
    return list(dedup.values())


def _search_candidates(
    session: Session,
    providers: dict[str, object],
    query: str,
    limit: int,
    provider_name: str,
) -> tuple[list[FoodSearchItem], bool]:
    local_items = _search_candidates_local(session=session, query=query, limit=limit)
    if local_items:
        return local_items[:limit], False

    provider = providers.get(provider_name)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"unknown provider: {provider_name}")

    provider_limit = max(1, limit)
    try:
        provider_foods, cached = search_and_cache_foods(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            query=query,
            limit=provider_limit,
        )
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    dedup: dict[str, FoodSearchItem] = {}
    for food in provider_foods:
        if food.id in dedup:
            continue
        dedup[food.id] = _food_item(food=food, match_type="provider")
        if len(dedup) >= limit:
            break
    return list(dedup.values()), cached


def _resolve_or_create_config(
    session: Session,
    user_id: str,
) -> tuple[OptimizationConfig, dict[str, float], list[str], str]:
    config = get_user_config(session, user_id)
    profile = get_profile(session, user_id)

    if config is not None:
        if profile is not None:
            targets = derive_targets(profile)
        else:
            targets = safe_default_targets()
        return config, targets, config_sanity_warnings(config), "existing"

    if profile is not None:
        targets, _constraints, derived = derive_config_from_profile(profile=profile, strictness="normal")
        upsert_user_config(session=session, user_id=user_id, config=derived)
        return derived, targets, config_sanity_warnings(derived), "profile_derived"

    targets = safe_default_targets()
    constraints = targets_to_constraints(targets, strictness="relaxed")
    fallback = build_optimization_config(targets=targets, constraints=constraints, horizon_days=1)
    upsert_user_config(session=session, user_id=user_id, config=fallback)
    return fallback, targets, config_sanity_warnings(fallback), "safe_default"


def _infeasibility_suggestions(
    foods: list[FoodRecord],
    config: OptimizationConfig,
    remaining_bounds: dict[str, object],
) -> list[RelaxationSuggestion]:
    suggestions: list[RelaxationSuggestion] = []
    eps = 1e-6
    min_g = config.food_bounds.min_grams_per_food
    max_g = config.food_bounds.max_grams_per_food

    for metric, bound in remaining_bounds.items():
        min_bound = getattr(bound, "min", None)
        max_bound = getattr(bound, "max", None)

        if min_bound is not None and max_bound is not None and min_bound > max_bound + eps:
            suggestions.append(
                RelaxationSuggestion(
                    constraint=metric,
                    issue="min_gt_max",
                    current_min=float(min_bound),
                    current_max=float(max_bound),
                    recommended_min=float(max_bound),
                    recommended_max=float(max_bound),
                    delta=float(min_bound - max_bound),
                    reason="Remaining lower bound exceeds remaining upper bound.",
                )
            )
            continue

        min_capacity = sum(min_g * metric_value(food, metric) for food in foods)
        max_capacity = sum(max_g * metric_value(food, metric) for food in foods)

        if max_bound is not None and max_bound < 0:
            suggestions.append(
                RelaxationSuggestion(
                    constraint=metric,
                    issue="already_exceeded_max",
                    current_max=float(max_bound),
                    recommended_max=0.0,
                    delta=float(abs(max_bound)),
                    reason="Logged intake already exceeds this max bound in the active horizon.",
                )
            )
            continue

        if min_bound is not None and min_bound > max_capacity + eps:
            suggestions.append(
                RelaxationSuggestion(
                    constraint=metric,
                    issue="min_unreachable",
                    current_min=float(min_bound),
                    recommended_min=float(max_capacity),
                    delta=float(min_bound - max_capacity),
                    reason="Minimum required total is above best-case capacity under current food bounds.",
                )
            )

        if max_bound is not None and max_bound < min_capacity - eps:
            suggestions.append(
                RelaxationSuggestion(
                    constraint=metric,
                    issue="max_too_strict",
                    current_max=float(max_bound),
                    recommended_max=float(min_capacity),
                    delta=float(min_capacity - max_bound),
                    reason="Maximum allowed total is below unavoidable minimum under current food bounds.",
                )
            )

    if config.diversity.enabled:
        n_food = len(foods)
        k = config.diversity.min_variety_count
        alpha = config.diversity.max_single_food_calorie_share
        if k > n_food:
            suggestions.append(
                RelaxationSuggestion(
                    constraint="diversity.min_variety_count",
                    issue="variety_gt_food_universe",
                    current_min=float(k),
                    recommended_min=float(n_food),
                    delta=float(k - n_food),
                    reason="Required variety exceeds number of available foods.",
                )
            )
        if alpha < (1.0 / max(float(k), 1.0)) - eps:
            suggestions.append(
                RelaxationSuggestion(
                    constraint="diversity.max_single_food_calorie_share",
                    issue="share_cap_too_strict",
                    current_max=float(alpha),
                    recommended_max=round(1.0 / max(float(k), 1.0), 4),
                    delta=round((1.0 / max(float(k), 1.0)) - float(alpha), 4),
                    reason="Share cap is mathematically tighter than the minimum implied by variety requirement.",
                )
            )
        if config.diversity.variety_min_grams > max_g:
            suggestions.append(
                RelaxationSuggestion(
                    constraint="diversity.variety_min_grams",
                    issue="variety_min_gt_food_max",
                    current_min=float(config.diversity.variety_min_grams),
                    recommended_min=float(max_g),
                    delta=float(config.diversity.variety_min_grams - max_g),
                    reason="Variety minimum grams per food exceeds max_grams_per_food.",
                )
            )

    if suggestions:
        return suggestions[:8]

    return [
        RelaxationSuggestion(
            constraint="global",
            issue="generic_infeasible",
            reason="Try relaxing calorie/protein bounds, increasing budget, or increasing max_grams_per_food.",
        )
    ]


def _assign_meal_slots(plan_items: list[PlanItem], requested_slots: list[str] | None) -> list[MealSlotAssignment]:
    slots = [s.strip() for s in (requested_slots or ["breakfast", "lunch", "dinner", "snack"]) if s.strip()]
    if not slots:
        slots = ["meal"]
    bucket: dict[str, list[PlanItem]] = {slot: [] for slot in slots}
    ordered_items = sorted(plan_items, key=lambda item: item.grams, reverse=True)
    for idx, item in enumerate(ordered_items):
        slot = slots[idx % len(slots)]
        bucket[slot].append(item)
    return [MealSlotAssignment(slot=slot, items=bucket[slot]) for slot in slots]


def _build_today_plan_summary(
    plan_items: list[PlanItem],
    totals: dict[str, float],
    objective_report: list[object],
    constraint_report: list[object],
) -> str:
    if not plan_items:
        return "No foods selected for the current optimization horizon."
    top_items = ", ".join(f"{item.food_name} {item.grams:.0f}g" for item in plan_items[:3])
    first_obj = objective_report[0].value if objective_report else 0.0
    binding_count = sum(1 for row in constraint_report if getattr(row, "status", "") == "binding")
    return (
        f"Plan includes {len(plan_items)} foods: {top_items}. "
        f"Totals: {totals.get('calories_kcal', 0.0):.0f} kcal, "
        f"{totals.get('protein_g', 0.0):.1f}g protein, "
        f"{totals.get('carbs_g', 0.0):.1f}g carbs, "
        f"{totals.get('fat_g', 0.0):.1f}g fat. "
        f"Stage-1 objective={first_obj:.3f}. Binding constraints={binding_count}."
    )


def _constraint_metric(name: str) -> tuple[str, str] | None:
    if name.endswith("_max"):
        return name[:-4], "max"
    if name.endswith("_min"):
        return name[:-4], "min"
    return None


def _suggest_substitutions(
    foods: list[FoodRecord],
    food_grams: dict[str, float],
    constraint_report: list[object],
    consumed_totals: dict[str, float] | None = None,
    planned_totals: dict[str, float] | None = None,
    preset_targets: dict[str, float] | None = None,
) -> list[SubstitutionSuggestion]:
    foods_by_id = {food.id: food for food in foods}
    suggestions: list[SubstitutionSuggestion] = []
    eps = 1e-6
    total_day_calories = float((consumed_totals or {}).get("calories_kcal", 0.0)) + float(
        (planned_totals or {}).get("calories_kcal", 0.0)
    )
    preset_calories = float((preset_targets or {}).get("calories_kcal", 0.0))
    low_vs_preset = preset_calories > 0.0 and total_day_calories < (preset_calories * 0.90)
    raised_cap_hint = False

    for row in constraint_report:
        status = getattr(row, "status", "")
        name = getattr(row, "name", "")
        slack = float(getattr(row, "slack", 0.0))
        parsed = _constraint_metric(name)
        if parsed is None:
            continue
        metric, direction = parsed
        if status not in ("binding", "violated"):
            continue
        if direction == "max" and slack > eps:
            continue
        if direction == "min" and slack > eps:
            continue
        if metric == "calories_kcal" and direction == "max" and low_vs_preset and not raised_cap_hint:
            suggestions.append(
                SubstitutionSuggestion(
                    constraint=name,
                    from_food_id="__policy__",
                    from_food_name="calorie cap",
                    to_food_id="__policy__",
                    to_food_name="higher calorie allowance",
                    reason=(
                        "calories_max is binding while total-day calories are below preset target. "
                        "Increase calories_max or use a looser preset strictness."
                    ),
                )
            )
            raised_cap_hint = True
            continue

        contributors: list[tuple[str, float]] = []
        for food_id, grams in food_grams.items():
            food = foods_by_id.get(food_id)
            if food is None:
                continue
            contributors.append((food_id, metric_value(food, metric) * grams))
        contributors = [c for c in contributors if c[1] > eps]
        if not contributors:
            continue
        contributors.sort(key=lambda item: item[1], reverse=True)
        from_food_id = contributors[0][0]
        from_food = foods_by_id[from_food_id]
        from_metric = metric_value(from_food, metric)

        candidates = [f for f in foods if f.id != from_food_id]
        if direction == "max":
            candidates = [f for f in candidates if metric_value(f, metric) + eps < from_metric]
            candidates.sort(
                key=lambda f: (
                    metric_value(f, metric) / max(metric_value(f, "calories_kcal"), eps),
                    f.cost_try_g,
                )
            )
            reason = f"Reduce {metric} pressure on {name} by replacing a high-contribution food."
        else:
            candidates = [f for f in candidates if metric_value(f, metric) > from_metric + eps]
            candidates.sort(
                key=lambda f: (
                    -metric_value(f, metric) / max(metric_value(f, "calories_kcal"), eps),
                    f.cost_try_g,
                )
            )
            reason = f"Increase {metric} contribution for {name} using a denser alternative."

        if not candidates:
            continue
        to_food = candidates[0]
        suggestions.append(
            SubstitutionSuggestion(
                constraint=name,
                from_food_id=from_food.id,
                from_food_name=from_food.name,
                to_food_id=to_food.id,
                to_food_name=to_food.name,
                reason=reason,
            )
        )
        if len(suggestions) >= 3:
            break

    return suggestions


def create_app(db_url: str | None = None, seed_defaults: bool = True) -> FastAPI:
    engine = get_engine(db_url)
    providers = {"openfoodfacts": OpenFoodFactsProvider()}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        create_db_and_tables(engine)
        with get_session(engine) as session:
            if seed_defaults:
                default_csv = Path(__file__).with_name("default_foods.csv")
                # Always upsert defaults so newly added starter foods are available
                # even when an existing DB already has older seed data.
                if default_csv.exists():
                    load_foods_from_csv(session, str(default_csv))
            load_food_aliases(session, DEFAULT_FOOD_ALIASES)
        yield

    app = FastAPI(title="Diet Optimizer API", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.providers = providers

    def db_session() -> Generator[Session, None, None]:
        with get_session(engine) as session:
            yield session

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    @app.post("/v1/users", response_model=CreateUserResponse)
    def create_user_route(
        req: CreateUserRequest,
        session: Session = Depends(db_session),
    ) -> CreateUserResponse:
        user = create_user(session=session, name=req.name)
        return CreateUserResponse(user_id=user.id)

    @app.post("/v1/profile", response_model=StatusResponse)
    def upsert_profile_route(
        req: ProfileUpsertRequest,
        session: Session = Depends(db_session),
    ) -> StatusResponse:
        if get_user(session, req.user_id) is None:
            raise HTTPException(status_code=404, detail="user not found")
        profile = UserProfile(
            age=req.age,
            sex=req.sex,
            height_cm=req.height_cm,
            weight_kg=req.weight_kg,
            activity_level=req.activity_level,
            goal=req.goal,
        )
        upsert_profile(session=session, user_id=req.user_id, profile=profile)
        return StatusResponse()

    @app.post("/v1/profile/derive-targets", response_model=DeriveTargetsResponse)
    def derive_targets_route(
        req: DeriveTargetsRequest,
        session: Session = Depends(db_session),
    ) -> DeriveTargetsResponse:
        profile = get_profile(session, req.user_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="profile not found")
        targets = derive_targets(profile)
        constraints = targets_to_constraints(targets, strictness=req.strictness)
        return DeriveTargetsResponse(targets=targets, constraints=constraints)

    @app.put("/v1/config", response_model=StatusResponse)
    def put_config_route(
        req: PutConfigRequest,
        session: Session = Depends(db_session),
    ) -> StatusResponse:
        if get_user(session, req.user_id) is None:
            raise HTTPException(status_code=404, detail="user not found")
        upsert_user_config(session=session, user_id=req.user_id, config=req.config)
        return StatusResponse(warnings=config_sanity_warnings(req.config))

    @app.post("/v1/logs", response_model=StatusResponse)
    def post_logs_route(
        req: LogRequest,
        session: Session = Depends(db_session),
    ) -> StatusResponse:
        if get_user(session, req.user_id) is None:
            raise HTTPException(status_code=404, detail="user not found")
        if not req.items:
            raise HTTPException(status_code=400, detail="at least one log item required")

        foods = get_food_records(session)
        food_ids = {f.id for f in foods}
        for item in req.items:
            if item.food_id not in food_ids:
                raise HTTPException(status_code=404, detail=f"food not found: {item.food_id}")

        ts = _to_utc_naive(req.timestamp)
        add_logs(
            session=session,
            user_id=req.user_id,
            timestamp=ts,
            items=[(i.food_id, i.grams) for i in req.items],
        )
        return StatusResponse()

    @app.post("/v1/logs/search", response_model=LogSearchResponse)
    def log_search_route(
        req: LogSearchRequest,
        session: Session = Depends(db_session),
    ) -> LogSearchResponse:
        items, _cached = _search_candidates(
            session=session,
            providers=app.state.providers,
            query=req.query,
            limit=req.limit,
            provider_name=req.provider,
        )
        recommended = items[0].food_id if items else None
        search_session = create_log_search_session(
            session=session,
            query_text=req.query,
            provider=req.provider,
            candidates=[item.model_dump(mode="json") for item in items],
        )
        created_at = search_session.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return LogSearchResponse(
            candidates=items,
            selection_required=len(items) > 1,
            recommended_food_id=recommended,
            search_id=search_session.search_id,
            expires_at=created_at + timedelta(minutes=30),
        )

    @app.post("/v1/logs/select", response_model=LogSelectResponse)
    def log_select_route(
        req: LogSelectRequest,
        session: Session = Depends(db_session),
    ) -> LogSelectResponse:
        if get_user(session, req.user_id) is None:
            raise HTTPException(status_code=404, detail="user not found")

        foods = get_food_records(session)
        foods_by_id = {food.id: food for food in foods}
        food = foods_by_id.get(req.food_id)
        if food is None:
            raise HTTPException(status_code=404, detail=f"food not found: {req.food_id}")

        ts = _to_utc_naive(req.timestamp)
        add_logs(
            session=session,
            user_id=req.user_id,
            timestamp=ts,
            items=[(req.food_id, req.grams)],
        )
        return LogSelectResponse(
            logged=LoggedSelection(
                food_id=req.food_id,
                food_name=food.name,
                grams=req.grams,
                timestamp=req.timestamp,
            )
        )

    @app.post("/v1/logs/resolve", response_model=LogResolveResponse)
    def log_resolve_route(
        req: LogResolveRequest,
        session: Session = Depends(db_session),
    ) -> LogResolveResponse:
        if get_user(session, req.user_id) is None:
            raise HTTPException(status_code=404, detail="user not found")

        search_session = get_log_search_session(session=session, search_id=req.search_id, max_age_minutes=30)
        if search_session is None:
            raise HTTPException(status_code=404, detail="search_id not found or expired")

        try:
            candidates = json.loads(search_session.candidates_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail="stored search candidates are invalid") from exc

        if not isinstance(candidates, list) or req.candidate_index >= len(candidates):
            raise HTTPException(status_code=400, detail="candidate_index out of range")

        selected = candidates[req.candidate_index]
        food_id = selected.get("food_id")
        if not isinstance(food_id, str) or not food_id:
            raise HTTPException(status_code=500, detail="selected candidate has no food_id")

        foods = get_food_records(session)
        foods_by_id = {food.id: food for food in foods}
        food = foods_by_id.get(food_id)
        if food is None:
            raise HTTPException(status_code=404, detail=f"food not found: {food_id}")

        ts = _to_utc_naive(req.timestamp)
        add_logs(
            session=session,
            user_id=req.user_id,
            timestamp=ts,
            items=[(food_id, req.grams)],
        )

        return LogResolveResponse(
            resolved_from_search_id=req.search_id,
            candidate_index=req.candidate_index,
            logged=LoggedSelection(
                food_id=food_id,
                food_name=food.name,
                grams=req.grams,
                timestamp=req.timestamp,
            ),
        )

    @app.post("/v1/foods/search", response_model=FoodSearchResponse)
    def search_foods_route(
        req: FoodSearchRequest,
        session: Session = Depends(db_session),
    ) -> FoodSearchResponse:
        items, cached = _search_candidates(
            session=session,
            providers=app.state.providers,
            query=req.query,
            limit=req.limit,
            provider_name=req.provider,
        )
        return FoodSearchResponse(items=items, cached=cached, selection_required=len(items) > 1)

    @app.get("/v1/summary/today", response_model=SummaryResponse)
    def summary_today_route(
        user_id: str = Query(...),
        session: Session = Depends(db_session),
    ) -> SummaryResponse:
        if get_user(session, user_id) is None:
            raise HTTPException(status_code=404, detail="user not found")

        config, preset_targets, _cfg_warnings, _cfg_source = _resolve_or_create_config(session=session, user_id=user_id)
        profile = get_profile(session, user_id)
        today = datetime.utcnow().date()
        start, end = _day_window(today, 1)

        foods = get_food_records(session)
        foods_by_id: Dict[str, FoodRecord] = {f.id: f for f in foods}
        logs = get_logs_between(session, user_id=user_id, start=start, end=end)
        consumed = compute_consumed_totals(
            [(row.food_id, row.grams) for row in logs],
            foods_by_id=foods_by_id,
        )

        remaining = compute_remaining_bounds(config.constraints, consumed)
        quality_report = build_quality_report(
            consumed_totals=consumed,
            planned_totals={},
            config=config,
            food_grams={},
            foods_by_id=foods_by_id,
            profile=profile,
            preset_targets=preset_targets,
        )
        return SummaryResponse(consumed=consumed, remaining_bounds=remaining, quality_report=quality_report)

    @app.post(
        "/v1/plan/optimize",
        response_model=OptimizeResponse,
        responses={422: {"model": InfeasibilityResponse}},
    )
    def optimize_plan_route(
        req: OptimizeRequest,
        session: Session = Depends(db_session),
    ) -> OptimizeResponse:
        if get_user(session, req.user_id) is None:
            raise HTTPException(status_code=404, detail="user not found")

        config, preset_targets, _cfg_warnings, _config_source = _resolve_or_create_config(
            session=session,
            user_id=req.user_id,
        )
        profile = get_profile(session, req.user_id)

        runtime_config: OptimizationConfig = config.model_copy(deep=True)
        if req.horizon_days is not None:
            runtime_config.horizon_days = req.horizon_days

        foods = get_food_records(session)
        if not foods:
            raise HTTPException(status_code=400, detail="no foods available for optimization")
        foods_by_id = {f.id: f for f in foods}

        today = datetime.utcnow().date()
        start, end = _day_window(today, runtime_config.horizon_days)
        logs = get_logs_between(session, user_id=req.user_id, start=start, end=end)
        consumed = compute_consumed_totals(
            [(row.food_id, row.grams) for row in logs],
            foods_by_id=foods_by_id,
        )
        remaining = compute_remaining_bounds(runtime_config.constraints, consumed)

        try:
            solved = solve_lexicographic(
                foods=foods,
                config=runtime_config,
                remaining_bounds=remaining,
            )
        except LPInfeasibleError as exc:
            infeasible_payload = InfeasibilityResponse(
                summary="Optimization infeasible for the current remaining bounds and food limits.",
                stage=exc.stage,
                objective=exc.objective_name,
                solver_message=exc.solver_message,
                suggested_relaxations=_infeasibility_suggestions(
                    foods=foods,
                    config=runtime_config,
                    remaining_bounds=remaining,
                ),
            )
            raise HTTPException(status_code=422, detail=infeasible_payload.model_dump(mode="json")) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        plan_items: List[PlanItem] = []
        for food_id, grams in solved.food_grams.items():
            food = foods_by_id[food_id]
            plan_items.append(PlanItem(food_id=food_id, food_name=food.name, grams=grams))
        plan_items.sort(key=lambda item: item.grams, reverse=True)

        meal_slots = _assign_meal_slots(plan_items=plan_items, requested_slots=req.meal_slots)
        substitutions = _suggest_substitutions(
            foods=foods,
            food_grams=solved.food_grams,
            constraint_report=solved.constraint_report,
            consumed_totals=consumed,
            planned_totals=solved.totals_planned,
            preset_targets=preset_targets,
        )
        summary_text = _build_today_plan_summary(
            plan_items=plan_items,
            totals=solved.totals_planned,
            objective_report=solved.objective_report,
            constraint_report=solved.constraint_report,
        )
        quality_report = build_quality_report(
            consumed_totals=consumed,
            planned_totals=solved.totals_planned,
            config=runtime_config,
            food_grams=solved.food_grams,
            foods_by_id=foods_by_id,
            profile=profile,
            preset_targets=preset_targets,
        )

        payload = OptimizeResponse(
            plan=plan_items,
            totals_planned=solved.totals_planned,
            constraint_report=solved.constraint_report,
            objective_report=solved.objective_report,
            provenance=PlanProvenance(
                foods_considered=len(foods),
                sources=sorted({f.source for f in foods}),
                solver="scipy.optimize.linprog(method=highs)",
                generated_at=datetime.now(timezone.utc),
            ),
            today_plan_summary=summary_text,
            meal_slots=meal_slots,
            substitutions=substitutions,
            quality_report=quality_report,
        )

        save_plan(
            session=session,
            user_id=req.user_id,
            plan_date=today,
            payload=payload.model_dump(mode="json"),
        )
        return payload

    @app.get("/v1/plan/today", response_model=OptimizeResponse)
    def get_today_plan_route(
        user_id: str = Query(...),
        session: Session = Depends(db_session),
    ) -> OptimizeResponse:
        if get_user(session, user_id) is None:
            raise HTTPException(status_code=404, detail="user not found")

        today = datetime.utcnow().date()
        payload = get_latest_plan_for_date(session=session, user_id=user_id, plan_date=today)
        if payload is None:
            raise HTTPException(status_code=404, detail="no plan found for today")
        return OptimizeResponse.model_validate(payload)

    return app


app = create_app()
