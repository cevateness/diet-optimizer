from dietopt.core.models import MetricBound
from dietopt.core.nutrition import compute_remaining_bounds


def test_remaining_bounds_floor_min_and_allow_negative_max() -> None:
    constraints = {
        "protein_g": MetricBound(min=100.0, max=180.0),
        "sodium_mg": MetricBound(max=2300.0),
    }
    consumed = {
        "protein_g": 120.0,
        "sodium_mg": 2500.0,
    }

    remaining = compute_remaining_bounds(constraints=constraints, consumed_totals=consumed)
    assert remaining["protein_g"].min == 0.0
    assert remaining["protein_g"].max == 60.0
    assert remaining["sodium_mg"].max == -200.0

