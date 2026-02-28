# docs/ROADMAP.md - MVP roadmap

## Phase 0: Notebook to service
- Extract notebook logic into Python package modules.
- Add FastAPI app, SQLModel persistence, and tests.
- Establish API-first contracts.

Exit criteria:
- `uvicorn dietopt.api.main:app --reload` starts.
- `pytest` passes.

## Phase 1: Core MVP loop
- User + profile management.
- Deterministic target and constraint presets.
- Daily/weekly food logging and summaries.
- Remaining-allowance computation.
- Continuous LP optimization with lexicographic objectives.
- Trust layer outputs.

Exit criteria:
- User can complete: create profile -> derive targets -> set config -> log -> optimize -> read plan.

## Phase 2: Production readiness
- Auth, rate limits, migrations, observability, and idempotency.
- Background jobs for food catalog updates.
- Packaging/deployment baseline.

## Phase 3: Interaction adapters
- LLM parser/explainer adapter (provider-agnostic).
- Telegram bot feature-flagged adapter consuming API.

## Phase 4: B2C UX and B2B2C expansion
- Web dashboard and coach workflows.
- Multi-tenant org controls and export/reporting.
