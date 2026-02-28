# docs/ARCHITECTURE.md - system architecture

## High-level flow
1. Create user and profile.
2. Derive deterministic targets and constraints.
3. Persist/override `OptimizationConfig` JSON.
4. Log consumed foods daily/weekly.
5. Compute remaining allowances from consumed totals.
6. Build LP from remaining bounds + objectives.
7. Solve lexicographically using HiGHS.
8. Return/save plan with trust layer.

## Modules
- `dietopt/core`
  - Domain models and nutrient arithmetic.
  - Remaining bounds computation.
- `dietopt/presets`
  - `derive_targets(profile)`
  - `targets_to_constraints(targets, strictness)`
- `dietopt/solver`
  - LP variable and constraint matrix construction.
  - Objective-specific transforms.
  - Lexicographic re-solve engine.
- `dietopt/store`
  - SQLModel tables and repository helpers.
- `dietopt/api`
  - FastAPI routes and response schemas.
- `dietopt/llm`
  - Parse/explain interfaces only.
- `dietopt/bot`
  - Telegram adapter behind feature flag.
- `dietopt/providers`
  - External food providers (first: Open Food Facts).
  - Cache-backed search service and canonical normalization.

## Lexicographic protocol
For objectives `[O1, O2, ... On]`:
1. Solve minimize/maximize `O1(x)`.
2. Add tolerance-lock constraint around the optimal `O1*`.
3. Solve `O2(x)`.
4. Repeat until `On`.

This ensures deterministic priority order without weighted blending.

## Trust layer contract
Every plan payload includes:
- `objective_report`: stage index, objective name, value, tolerance.
- `constraint_report`: constraint name, status (`ok|binding|violated`), slack.
- `provenance`: food source summary, solver id, generation timestamp.

If LP is infeasible, API returns a structured explanation with suggested constraint relaxations instead of opaque errors.
