# docs/DATA.md - data contracts and provenance

## Canonical nutrient schema
All food nutrients are represented per gram:
- `calories_kcal_g`
- `protein_g_g`
- `carbs_g_g`
- `fat_g_g`
- `fiber_g_g`
- `sat_fat_g_g`
- `sodium_mg_g`
- `cost_try_g`

Optional fields:
- `preference_score_g`
- `sugar_g_g`

## Data sources
- Local curated dataset is primary for MVP.
- External free APIs can enrich catalog later.
- First provider implementation: Open Food Facts (OFF) search.
- Every external record must keep provenance metadata.

## Provenance fields
Each food or plan response must be traceable with:
- `source`
- `source_id` (if applicable)
- `retrieved_at`
- `generated_at` for plans
- `solver` identifier for optimized outputs

## Provider caching
- Provider search responses are cached in SQLite by `(provider, query_text)`.
- Cache rows include raw canonical results JSON plus `retrieved_at`.
- Cached foods are upserted into the canonical `foods` table with:
  - `source=openfoodfacts`
  - `source_id=<provider code>`
  - `retrieved_at=<provider fetch time>`

## Logging contract
Food logs are immutable events:
- `user_id`
- `timestamp`
- `food_id`
- `grams`

Totals and remaining allowances are derived from events and current config.

## Alias mapping
- Local alias table links query phrases to canonical `food_id`.
- Starter Turkish aliases include `simit`, `menemen`, `ayran`, `yulaf`.
- Alias search runs before external provider search for low-latency local resolution.

## Trust-layer principle
Optimization outputs always include:
- objective stage values
- constraint slack report
- provenance summary
