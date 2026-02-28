from dietopt.core.conversions import grams_to_servings, servings_to_grams


def test_servings_to_grams_and_back() -> None:
    grams = servings_to_grams(2.5, 30.0)
    assert grams == 75.0
    servings = grams_to_servings(grams, 30.0)
    assert servings == 2.5

