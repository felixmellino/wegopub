"""Preserve legacy seasons. The new fixed table/replay is in test_scoring_v1."""
import pytest

from core.constants import BEER_POINTS_PER_UNIT, LONGDRINK_POINTS, SHOT_POINTS, WINE_POINTS_PER_UNIT
from core.scoring import apply_owner_modifier, calculate_base_points


def test_beer_scales_with_amount():
    assert calculate_base_points("beer", 2) == BEER_POINTS_PER_UNIT * 2


def test_wine_scales_with_amount():
    assert calculate_base_points("wine", 3) == WINE_POINTS_PER_UNIT * 3


def test_shot_is_flat():
    assert calculate_base_points("shot", None) == SHOT_POINTS


def test_longdrink_is_flat():
    assert calculate_base_points("longdrink", None) == LONGDRINK_POINTS


def test_beer_without_amount_raises():
    with pytest.raises(ValueError):
        calculate_base_points("beer", None)


def test_unknown_drink_type_raises():
    with pytest.raises(ValueError):
        calculate_base_points("cocktail", 1)


def test_owner_modifier_is_a_true_noop():
    assert apply_owner_modifier(100, "territory-1", "owner-1", "drinker-1") == 100
    assert apply_owner_modifier(100, None, None, "drinker-1") == 100
