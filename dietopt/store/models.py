"""SQLModel table definitions."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)


class UserProfileRow(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, unique=True)
    age: int
    sex: str
    height_cm: float
    weight_kg: float
    activity_level: str
    goal: str
    updated_at: datetime = Field(default_factory=_utcnow)


class UserConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, unique=True)
    config_json: str
    updated_at: datetime = Field(default_factory=_utcnow)


class Food(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str = Field(index=True)
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


class FoodLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    food_id: str = Field(index=True)
    timestamp: datetime = Field(index=True)
    grams: float


class Plan(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    plan_date: date = Field(index=True)
    payload_json: str
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class FoodSearchCache(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(index=True)
    query_text: str = Field(index=True)
    payload_json: str
    retrieved_at: datetime = Field(default_factory=_utcnow, index=True)


class FoodAlias(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    alias_text: str = Field(index=True)
    alias_norm: str = Field(index=True)
    food_id: str = Field(index=True)
    locale: str = Field(default="tr_TR", index=True)


class LogSearchSession(SQLModel, table=True):
    search_id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    query_text: str = Field(index=True)
    provider: str = Field(index=True)
    candidates_json: str
    created_at: datetime = Field(default_factory=_utcnow, index=True)
