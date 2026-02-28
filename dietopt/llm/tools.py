"""Tool schemas that an LLM adapter can call."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FoodSearchToolInput(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)


class FoodResolveToolInput(BaseModel):
    candidate_id: str
    grams: float = Field(gt=0)

