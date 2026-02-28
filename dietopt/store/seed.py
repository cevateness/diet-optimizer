"""Food catalog seeding helpers."""

from __future__ import annotations

import csv
from pathlib import Path

from sqlmodel import Session

from dietopt.core.models import FoodRecord

from .repo import upsert_food, upsert_food_alias


def load_foods_from_csv(session: Session, csv_path: str) -> int:
    """Load canonical food rows from CSV and upsert into DB."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Food CSV not found: {csv_path}")

    inserted = 0
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            food = FoodRecord(
                id=row["id"],
                name=row["name"],
                calories_kcal_g=float(row["calories_kcal_g"]),
                protein_g_g=float(row["protein_g_g"]),
                carbs_g_g=float(row["carbs_g_g"]),
                fat_g_g=float(row["fat_g_g"]),
                fiber_g_g=float(row["fiber_g_g"]),
                sat_fat_g_g=float(row["sat_fat_g_g"]),
                sodium_mg_g=float(row["sodium_mg_g"]),
                cost_try_g=float(row.get("cost_try_g", 0.0) or 0.0),
                preference_score_g=float(row.get("preference_score_g", 0.0) or 0.0),
                source=row.get("source", "local") or "local",
            )
            upsert_food(session, food)
            inserted += 1
    return inserted


def load_food_aliases(
    session: Session,
    aliases: list[tuple[str, str, str]],
) -> int:
    """Load alias tuples `(alias_text, food_id, locale)` into DB."""
    inserted = 0
    for alias_text, food_id, locale in aliases:
        upsert_food_alias(session=session, alias_text=alias_text, food_id=food_id, locale=locale)
        inserted += 1
    return inserted
