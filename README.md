# diet-optimizer

Diet Optimizer is a B2C MVP web service for:
- daily food logging,
- deterministic target derivation from user profile,
- continuous LP meal planning with SciPy HiGHS,
- lexicographic multi-objective optimization,
- trust-layer reporting (objective stages, constraint slacks, provenance).

## Run API

```bash
uvicorn dietopt.api.main:app --reload
```

## Test

```bash
pytest
```

## Quick Smoke Flows
- Notebook: `notebooks/01_api_smoke_test.ipynb`
- Script: `python scripts/demo_flow.py --base-url http://127.0.0.1:8000`

## Main docs
- `docs/AGENT.md`
- `docs/ROADMAP.md`
- `docs/DATA.md`
- `docs/API.md`
- `docs/DEV.md`
- `docs/GUIDE.md`
- `docs/VALUE_PROPOSITION.md`
- `docs/ARCHITECTURE.md`
