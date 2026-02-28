# docs/VALUE_PROPOSITION.md - product value

## Positioning
Diet Optimizer is a constraint-aware planning engine, not a generic chat nutrition assistant.

## Core value
1. Closed-loop planning:
   - User logs real intake.
   - System recomputes remaining allowances.
   - Optimizer updates the remaining horizon.
2. Deterministic optimization:
   - Same inputs produce same outputs.
   - Explicit objective ordering via lexicographic solves.
3. Transparent trust layer:
   - Objective stage scores.
   - Constraint slack/binding report.
   - Data provenance in every plan.
4. Safe LLM usage:
   - LLM assists interaction and explanation only.
   - Numerical truth remains in datasets + LP solver.

## Why not plain ChatGPT
Chat tools can suggest meals, but they generally do not enforce strict constraints, compute LP feasibility, or provide auditable slack/objective traces.

## MVP promise
A user can do:
- log food,
- see today/weekly status,
- optimize remaining meals,
- inspect exactly how and why the plan satisfies constraints.
