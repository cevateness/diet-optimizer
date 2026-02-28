# docs/GUIDE.md - practical guide for DS/OR users

This guide explains how to use and modify the project without needing full software-engineering background.

## 1) What this repo does
- Tracks food logs (daily/weekly).
- Computes remaining nutrition/budget bounds.
- Builds a continuous LP and solves with HiGHS.
- Returns plan + trust layer:
  - objective values per lexicographic stage,
  - constraint slack/binding report,
  - data provenance.

## 2) The most important files
- `dietopt/presets/derive.py`
  - deterministic formulas from profile -> targets -> constraints.
- `dietopt/solver/builder.py`
  - translates constraints/objectives into LP matrices.
- `dietopt/solver/lexicographic.py`
  - runs lexicographic re-solves and returns trust metrics.
- `dietopt/api/main.py`
  - all FastAPI routes and end-to-end request handling.
- `dietopt/store/models.py`, `dietopt/store/repo.py`
  - SQLite schema and CRUD/query helpers.

## 3) Typical workflow (manual testing)
1. Create user: `POST /v1/users`
2. Set profile: `POST /v1/profile`
3. Derive defaults: `POST /v1/profile/derive-targets`
4. Save config: `PUT /v1/config`
5. Search foods for logging:
   - `POST /v1/logs/search` (returns candidates + `search_id`)
6. Log one candidate:
   - `POST /v1/logs/resolve` with `search_id + candidate_index + grams`
   - or `POST /v1/logs/select` with explicit `food_id`
7. Check progress: `GET /v1/summary/today`
8. Optimize: `POST /v1/plan/optimize`

Use either:
- notebook: `notebooks/01_api_smoke_test.ipynb`
- script: `scripts/demo_flow.py`

## 4) If optimization is infeasible
`POST /v1/plan/optimize` returns `422` with:
- `detail.code = infeasible_plan`
- `detail.suggested_relaxations` list

Read relaxations first; they usually indicate:
- too strict min/max bounds,
- already exceeded max due logged intake,
- or food bounds (`max_grams_per_food`) too low.

## 5) How to change nutrition logic safely
- Edit deterministic formulas in `dietopt/presets/derive.py`.
- Keep units consistent (`kcal`, `g`, `mg`, `try`).
- Add/update tests in `tests/`:
  - preset behavior,
  - LP feasibility/infeasibility,
  - integration flow.

## 6) How alias mapping works
- Alias table in DB maps user terms -> canonical `food_id`.
- Starter aliases live in `dietopt/store/default_aliases.py`.
- Add terms there, restart app, and aliases auto-seed on startup.
- Example aliases: `simit`, `menemen`, `ayran`, `yulaf`.

## 7) Telegram integration status
- `dietopt/bot/telegram.py` parses messages like `"simit 120g"`.
- It calls API flow:
  - `/v1/logs/search`
  - if ambiguous: returns candidate list + `search_id`
  - then callback can use `/v1/logs/resolve`
  - finally summary + optimize endpoints.

This is intentionally thin: business logic stays in API/core, not in bot code.
