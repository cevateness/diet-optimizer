# docs/DEV.md - developer setup and workflows

## Prerequisites
- Python 3.10+
- `pip`

## Setup
```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -e ".[dev]"
```

## Run API
```bash
uvicorn dietopt.api.main:app --reload
```

Windows PowerShell (if global user-site packages interfere):
```powershell
$env:PYTHONNOUSERSITE = "1"
.\.venv\Scripts\python -s -m uvicorn dietopt.api.main:app --reload
```

## Run tests
```bash
pytest
```

Windows PowerShell:
```powershell
$env:PYTHONNOUSERSITE = "1"
.\.venv\Scripts\python -m pytest -q
```

## Demo flow
Run deterministic end-to-end API demo (non-notebook):
```bash
python scripts/demo_flow.py --base-url http://127.0.0.1:8000
```

## Notebook kernel setup (Windows)
If kernel disappears or switches to global Python:

```powershell
$env:PYTHONNOUSERSITE = "1"
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
.\.venv\Scripts\python -s -m ipykernel install --user --name dietopt-venv --display-name "dietopt (.venv)"
```

Then in VS Code:
1. Command Palette -> `Python: Select Interpreter` -> choose `.venv\\Scripts\\python.exe`
2. Command Palette -> `Developer: Reload Window`
3. Open notebook -> `Select Kernel` -> choose `dietopt (.venv)`

Avoid `--user` installs with global interpreter (for example `Python311\\python.exe -m pip install ... --user`) for this repo.

## CI
- GitHub Actions workflow: `.github/workflows/ci.yml`
- Triggered on push/PR to `main`
- Runs test suite on Python 3.10, 3.11, 3.12

## Notes
- Default DB is SQLite at `./dietopt.db` (`DIETOPT_DB_URL` to override).
- Default local foods are seeded from `dietopt/api/default_foods.csv`.
- External provider search uses Open Food Facts and caches results in SQLite.
- LLM outputs are never used as numeric nutrient truth.
