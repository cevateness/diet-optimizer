# docs/API.md - B2C MVP API contracts (v1)

## Conventions
- JSON request/response bodies.
- Canonical nutrient units:
  - calories: `kcal`
  - protein/carbs/fat/fiber/sat_fat: `g`
  - sodium: `mg`
  - price: `try`
- Foods are normalized per gram internally.
- LP is continuous only and solved with HiGHS.

## Endpoints

### POST /v1/users
Create a user.

Request:
```json
{
  "name": "optional display name"
}
```

Response:
```json
{
  "user_id": "uuid",
  "status": "ok"
}
```

### POST /v1/profile
Create or update the profile used for deterministic target derivation.

Request:
```json
{
  "user_id": "uuid",
  "age": 29,
  "sex": "male",
  "height_cm": 180,
  "weight_kg": 86,
  "activity_level": "moderate",
  "goal": "cut"
}
```

Response:
```json
{ "status": "ok" }
```

### POST /v1/profile/derive-targets
Derive deterministic targets and default constraints from `UserProfile`.

Request:
```json
{
  "user_id": "uuid",
  "strictness": "normal"
}
```

Response:
```json
{
  "targets": {
    "calories_kcal": 2300,
    "protein_g": 165,
    "carbs_g": 235,
    "fat_g": 77,
    "fiber_g": 30,
    "sat_fat_g": 20,
    "sodium_mg": 2300
  },
  "constraints": {
    "calories_kcal": { "min": 2185, "max": 2415 },
    "protein_g": { "min": 149, "max": 182 },
    "carbs_g": { "min": 200, "max": 270 },
    "fat_g": { "min": 65, "max": 88 },
    "fiber_g": { "min": 30 },
    "sat_fat_g": { "max": 20 },
    "sodium_mg": { "max": 2300 },
    "budget_try": { "max": 250 }
  }
}
```

### PUT /v1/config
Set optimization config JSON per user. This is the only source for objective and constraint configuration.

Request:
```json
{
  "user_id": "uuid",
  "config": {
    "horizon_days": 1,
    "constraints": {
      "calories_kcal": { "min": 2185, "max": 2415 },
      "protein_g": { "min": 149, "max": 182 },
      "carbs_g": { "min": 200, "max": 270 },
      "fat_g": { "min": 65, "max": 88 },
      "fiber_g": { "min": 30 },
      "sat_fat_g": { "max": 20 },
      "sodium_mg": { "max": 2300 },
      "budget_try": { "max": 250 }
    },
    "objectives_lex": [
      {
        "name": "min_total_deviation",
        "type": "deviation",
        "targets": ["calories_kcal", "protein_g", "carbs_g", "fat_g"],
        "tolerance": 0.005
      },
      {
        "name": "min_cost",
        "type": "linear",
        "metric": "cost_try",
        "sense": "min",
        "tolerance": 0.0
      }
    ],
    "food_bounds": {
      "min_grams_per_food": 0,
      "max_grams_per_food": 600
    }
  }
}
```

Response:
```json
{ "status": "ok" }
```

### POST /v1/logs
Log consumed foods.

Request:
```json
{
  "user_id": "uuid",
  "timestamp": "2026-02-28T09:30:00+03:00",
  "items": [
    { "food_id": "uuid-food-1", "grams": 120 },
    { "food_id": "uuid-food-2", "grams": 80 }
  ]
}
```

Response:
```json
{ "status": "ok" }
```

### POST /v1/logs/search
Search food candidates for logging (local alias/name first, then provider fallback).

Request:
```json
{
  "query": "simit",
  "limit": 5,
  "provider": "openfoodfacts"
}
```

Response:
```json
{
  "candidates": [
    {
      "food_id": "simit",
      "name": "Simit",
      "source": "local",
      "source_id": null,
      "match_type": "alias",
      "matched_alias": "simit",
      "calories_kcal_g": 2.72,
      "protein_g_g": 0.08,
      "carbs_g_g": 0.53,
      "fat_g_g": 0.07,
      "fiber_g_g": 0.03,
      "sat_fat_g_g": 0.012,
      "sodium_mg_g": 4.1
    }
  ],
  "selection_required": false,
  "recommended_food_id": "simit",
  "search_id": "uuid-search-id",
  "expires_at": "2026-02-28T12:30:00+00:00"
}
```

### POST /v1/logs/select
Log grams for one chosen candidate from search.

Request:
```json
{
  "user_id": "uuid",
  "timestamp": "2026-02-28T09:30:00+03:00",
  "food_id": "simit",
  "grams": 90
}
```

### POST /v1/logs/resolve
Resolve a search session by `candidate_index` and log grams.
Useful for Telegram button callbacks where you want to avoid sending raw `food_id` back from the client.

Request:
```json
{
  "user_id": "uuid",
  "timestamp": "2026-02-28T09:30:00+03:00",
  "search_id": "uuid-search-id",
  "candidate_index": 0,
  "grams": 90
}
```

Response:
```json
{
  "status": "ok",
  "resolved_from_search_id": "uuid-search-id",
  "candidate_index": 0,
  "logged": {
    "food_id": "simit",
    "food_name": "Simit",
    "grams": 90,
    "timestamp": "2026-02-28T09:30:00+03:00"
  }
}
```

Response:
```json
{
  "status": "ok",
  "logged": {
    "food_id": "simit",
    "food_name": "Simit",
    "grams": 90,
    "timestamp": "2026-02-28T09:30:00+03:00"
  }
}
```

### POST /v1/foods/search
Search food candidates (local alias/name + provider) and cache provider results.

Request:
```json
{
  "query": "greek yogurt",
  "provider": "openfoodfacts",
  "limit": 5
}
```

Response:
```json
{
  "cached": false,
  "selection_required": true,
  "items": [
    {
      "food_id": "off:1234567890",
      "name": "Greek Yogurt",
      "source": "openfoodfacts",
      "source_id": "1234567890",
      "match_type": "provider",
      "matched_alias": null,
      "calories_kcal_g": 0.97,
      "protein_g_g": 0.1,
      "carbs_g_g": 0.036,
      "fat_g_g": 0.04,
      "fiber_g_g": 0.0,
      "sat_fat_g_g": 0.025,
      "sodium_mg_g": 3.6
    }
  ]
}
```

### GET /v1/summary/today?user_id=...
Return consumed totals and remaining bounds for today.

Response:
```json
{
  "consumed": {
    "calories_kcal": 950,
    "protein_g": 55,
    "carbs_g": 90,
    "fat_g": 25,
    "fiber_g": 10,
    "sat_fat_g": 7,
    "sodium_mg": 1200,
    "cost_try": 65
  },
  "remaining_bounds": {
    "calories_kcal": { "min": 1235, "max": 1465 },
    "protein_g": { "min": 94, "max": 127 },
    "carbs_g": { "min": 110, "max": 180 },
    "fat_g": { "min": 40, "max": 63 },
    "fiber_g": { "min": 20 },
    "sat_fat_g": { "max": 13 },
    "sodium_mg": { "max": 1100 },
    "budget_try": { "max": 185 }
  }
}
```

### POST /v1/plan/optimize
Run lexicographic LP optimization for the remaining horizon.

Request:
```json
{
  "user_id": "uuid",
  "horizon_days": 1,
  "meal_slots": ["lunch", "dinner", "snack"]
}
```

Success response:
```json
{
  "plan": [
    { "food_id": "uuid-food-10", "food_name": "Chicken breast", "grams": 220.0 },
    { "food_id": "uuid-food-11", "food_name": "Rice", "grams": 150.0 }
  ],
  "totals_planned": {
    "calories_kcal": 1350,
    "protein_g": 105,
    "carbs_g": 150,
    "fat_g": 40,
    "fiber_g": 22,
    "sat_fat_g": 10,
    "sodium_mg": 900,
    "cost_try": 120
  },
  "constraint_report": [
    { "name": "protein_g_min", "status": "binding", "slack": 0.0 },
    { "name": "sat_fat_g_max", "status": "ok", "slack": 3.0 },
    { "name": "budget_try_max", "status": "ok", "slack": 65.0 }
  ],
  "objective_report": [
    { "stage": 1, "name": "min_total_deviation", "value": 12.45, "tolerance": 0.005 },
    { "stage": 2, "name": "min_cost", "value": 120.0, "tolerance": 0.0 }
  ],
  "provenance": {
    "foods_considered": 34,
    "sources": ["local"],
    "solver": "scipy.optimize.linprog(method=highs)",
    "generated_at": "2026-02-28T10:05:00+03:00"
  },
  "today_plan_summary": "Plan includes 2 foods: Chicken breast 220g, Rice 150g. Totals: 1350 kcal, 105.0g protein, 150.0g carbs, 40.0g fat. Stage-1 objective=12.450. Binding constraints=1.",
  "meal_slots": [
    {
      "slot": "lunch",
      "items": [
        { "food_id": "uuid-food-10", "food_name": "Chicken breast", "grams": 220.0 }
      ]
    },
    {
      "slot": "dinner",
      "items": [
        { "food_id": "uuid-food-11", "food_name": "Rice", "grams": 150.0 }
      ]
    }
  ],
  "substitutions": [
    {
      "constraint": "sat_fat_g_max",
      "from_food_id": "uuid-food-10",
      "from_food_name": "Chicken breast",
      "to_food_id": "uuid-food-20",
      "to_food_name": "Lentils",
      "reason": "Reduce sat_fat_g pressure on sat_fat_g_max by replacing a high-contribution food."
    }
  ]
}
```

Infeasible response (`422`):
```json
{
  "detail": {
    "code": "infeasible_plan",
    "summary": "Optimization infeasible for the current remaining bounds and food limits.",
    "stage": 1,
    "objective": "min_total_deviation",
    "solver_message": "The problem is infeasible.",
    "suggested_relaxations": [
      {
        "constraint": "protein_g",
        "issue": "min_unreachable",
        "current_min": 180,
        "recommended_min": 130,
        "delta": 50,
        "reason": "Minimum required total is above best-case capacity under current food bounds."
      }
    ]
  }
}
```

### GET /v1/plan/today?user_id=...
Return the latest saved plan for the user for the current day.
