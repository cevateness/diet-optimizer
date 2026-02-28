"""Database configuration and session utilities."""

from __future__ import annotations

import os
from functools import lru_cache

from sqlmodel import Session, SQLModel, create_engine


def _resolve_db_url(db_url: str | None = None) -> str:
    return db_url or os.getenv("DIETOPT_DB_URL", "sqlite:///./dietopt.db")


@lru_cache(maxsize=8)
def get_engine(db_url: str | None = None):
    """Create and cache SQLModel engine."""
    resolved = _resolve_db_url(db_url)
    connect_args = {"check_same_thread": False} if resolved.startswith("sqlite") else {}
    return create_engine(resolved, echo=False, connect_args=connect_args)


def create_db_and_tables(engine) -> None:
    """Initialize all SQLModel tables."""
    SQLModel.metadata.create_all(engine)


def get_session(engine) -> Session:
    """Yield a new SQLModel session."""
    return Session(engine)

