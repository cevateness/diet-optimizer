# docs/AGENT.md - diet-optimizer agent contract

## Mission
Build a deployable B2C MVP that supports daily/weekly logging, continuous LP meal optimization, and transparent trust reporting.

## Non-negotiables
1. Solver must be `scipy.optimize.linprog(method="highs")`.
2. LP model is continuous only for MVP.
3. All constraints/objectives are data-driven via per-user `OptimizationConfig` JSON.
4. Multi-objective optimization is lexicographic via repeated re-solves with tolerance locks.
5. Targets/constraints from profile are deterministic, formula-based, and do not use LLM-generated numbers.
6. Plan responses always include trust-layer fields: objective stages, constraint slacks, and provenance.

## Package boundaries
- `dietopt/core`: pure domain math and models.
- `dietopt/presets`: deterministic profile -> targets -> constraints derivation.
- `dietopt/solver`: LP matrix builder, HiGHS wrapper, lexicographic coordinator.
- `dietopt/store`: SQLite + SQLModel persistence.
- `dietopt/api`: FastAPI routes and DTOs.
- `dietopt/llm`: provider-agnostic interfaces and prompt/tool schemas.
- `dietopt/bot`: Telegram adapter under feature flag.

## Safety boundary for LLM
LLM can parse logs and explain plans, but cannot act as numeric source of truth for nutrients, prices, or constraints.

## Definition of done
- Unit and integration tests pass.
- API contracts are documented.
- Endpoints return trust layer in optimize/plan reads.
- Core optimization logic is deterministic and adapter-independent.
