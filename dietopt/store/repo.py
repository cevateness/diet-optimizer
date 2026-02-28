"""Repository-style DB helpers."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Tuple

from sqlmodel import Session, select

from dietopt.core.models import FoodRecord, OptimizationConfig, UserProfile

from .models import Food, FoodAlias, FoodLog, FoodSearchCache, LogSearchSession, Plan, User, UserConfig, UserProfileRow


def normalize_alias_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def create_user(session: Session, name: str | None = None) -> User:
    user = User(name=name)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def get_user(session: Session, user_id: str) -> User | None:
    return session.get(User, user_id)


def upsert_profile(session: Session, user_id: str, profile: UserProfile) -> UserProfileRow:
    existing = session.exec(select(UserProfileRow).where(UserProfileRow.user_id == user_id)).first()
    if existing is None:
        existing = UserProfileRow(user_id=user_id, **profile.model_dump())
    else:
        for key, value in profile.model_dump().items():
            setattr(existing, key, value)
        existing.updated_at = datetime.now(timezone.utc)
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return existing


def get_profile(session: Session, user_id: str) -> UserProfile | None:
    row = session.exec(select(UserProfileRow).where(UserProfileRow.user_id == user_id)).first()
    if row is None:
        return None
    return UserProfile(
        age=row.age,
        sex=row.sex,
        height_cm=row.height_cm,
        weight_kg=row.weight_kg,
        activity_level=row.activity_level,
        goal=row.goal,
    )


def upsert_user_config(session: Session, user_id: str, config: OptimizationConfig) -> UserConfig:
    payload = config.model_dump_json()
    existing = session.exec(select(UserConfig).where(UserConfig.user_id == user_id)).first()
    if existing is None:
        existing = UserConfig(user_id=user_id, config_json=payload)
    else:
        existing.config_json = payload
        existing.updated_at = datetime.now(timezone.utc)
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return existing


def get_user_config(session: Session, user_id: str) -> OptimizationConfig | None:
    row = session.exec(select(UserConfig).where(UserConfig.user_id == user_id)).first()
    if row is None:
        return None
    return OptimizationConfig.model_validate_json(row.config_json)


def upsert_food(session: Session, food: FoodRecord) -> Food:
    existing = session.get(Food, food.id)
    if existing is None:
        existing = Food(**food.model_dump())
    else:
        for key, value in food.model_dump().items():
            setattr(existing, key, value)
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return existing


def get_foods(session: Session) -> List[Food]:
    return list(session.exec(select(Food)))


def get_food_records(session: Session) -> List[FoodRecord]:
    foods = get_foods(session)
    return [
        FoodRecord(
            id=f.id,
            name=f.name,
            calories_kcal_g=f.calories_kcal_g,
            protein_g_g=f.protein_g_g,
            carbs_g_g=f.carbs_g_g,
            fat_g_g=f.fat_g_g,
            fiber_g_g=f.fiber_g_g,
            sat_fat_g_g=f.sat_fat_g_g,
            sodium_mg_g=f.sodium_mg_g,
            cost_try_g=f.cost_try_g,
            preference_score_g=f.preference_score_g,
            source=f.source,
            source_id=f.source_id,
            retrieved_at=f.retrieved_at,
        )
        for f in foods
    ]


def add_logs(
    session: Session, user_id: str, timestamp: datetime, items: Iterable[Tuple[str, float]]
) -> List[FoodLog]:
    created: List[FoodLog] = []
    for food_id, grams in items:
        row = FoodLog(user_id=user_id, timestamp=timestamp, food_id=food_id, grams=grams)
        session.add(row)
        created.append(row)
    session.commit()
    for row in created:
        session.refresh(row)
    return created


def upsert_food_alias(session: Session, alias_text: str, food_id: str, locale: str = "tr_TR") -> FoodAlias:
    normalized = normalize_alias_text(alias_text)
    existing = session.exec(
        select(FoodAlias)
        .where(FoodAlias.alias_norm == normalized)
        .where(FoodAlias.food_id == food_id)
        .where(FoodAlias.locale == locale)
    ).first()
    if existing is None:
        existing = FoodAlias(alias_text=alias_text, alias_norm=normalized, food_id=food_id, locale=locale)
    else:
        existing.alias_text = alias_text
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return existing


def search_food_aliases(
    session: Session,
    query: str,
    locale: str | None = None,
    limit: int = 10,
) -> List[FoodAlias]:
    normalized = normalize_alias_text(query)
    if not normalized:
        return []
    stmt = select(FoodAlias).where(FoodAlias.alias_norm.contains(normalized))
    if locale:
        stmt = stmt.where(FoodAlias.locale == locale)
    stmt = stmt.order_by(FoodAlias.alias_norm.asc())
    rows = list(session.exec(stmt))
    return rows[: max(limit, 1)]


def get_logs_between(session: Session, user_id: str, start: datetime, end: datetime) -> List[FoodLog]:
    stmt = (
        select(FoodLog)
        .where(FoodLog.user_id == user_id)
        .where(FoodLog.timestamp >= start)
        .where(FoodLog.timestamp < end)
    )
    return list(session.exec(stmt))


def save_plan(session: Session, user_id: str, plan_date: date, payload: Dict[str, object]) -> Plan:
    row = Plan(user_id=user_id, plan_date=plan_date, payload_json=json.dumps(payload))
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_latest_plan_for_date(session: Session, user_id: str, plan_date: date) -> Dict[str, object] | None:
    stmt = (
        select(Plan)
        .where(Plan.user_id == user_id)
        .where(Plan.plan_date == plan_date)
        .order_by(Plan.created_at.desc())
    )
    row = session.exec(stmt).first()
    if row is None:
        return None
    return json.loads(row.payload_json)


def get_cached_food_search(
    session: Session,
    provider: str,
    query_text: str,
    max_age_hours: int = 24,
) -> List[FoodRecord] | None:
    stmt = (
        select(FoodSearchCache)
        .where(FoodSearchCache.provider == provider)
        .where(FoodSearchCache.query_text == query_text)
        .order_by(FoodSearchCache.retrieved_at.desc())
    )
    row = session.exec(stmt).first()
    if row is None:
        return None

    retrieved_at = row.retrieved_at
    if retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - retrieved_at
    if age > timedelta(hours=max_age_hours):
        return None

    payload = json.loads(row.payload_json)
    return [FoodRecord.model_validate(item) for item in payload]


def set_cached_food_search(
    session: Session,
    provider: str,
    query_text: str,
    foods: List[FoodRecord],
) -> FoodSearchCache:
    payload = [food.model_dump(mode="json") for food in foods]
    row = FoodSearchCache(
        provider=provider,
        query_text=query_text,
        payload_json=json.dumps(payload),
        retrieved_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def create_log_search_session(
    session: Session,
    query_text: str,
    provider: str,
    candidates: List[Dict[str, object]],
) -> LogSearchSession:
    row = LogSearchSession(
        query_text=query_text,
        provider=provider,
        candidates_json=json.dumps(candidates),
        created_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_log_search_session(
    session: Session,
    search_id: str,
    max_age_minutes: int = 30,
) -> LogSearchSession | None:
    row = session.get(LogSearchSession, search_id)
    if row is None:
        return None
    created_at = row.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created_at > timedelta(minutes=max_age_minutes):
        return None
    return row
