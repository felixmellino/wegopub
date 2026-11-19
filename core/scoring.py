"""Historical scoring for legacy seasons. New frozen rules are in scoring_v1."""

from __future__ import annotations

from core.constants import (
    ALLOWED_DRINK_TYPES,
    AMOUNT_SCALED_DRINK_TYPES,
    BEER_POINTS_PER_UNIT,
    LONGDRINK_POINTS,
    SHOT_POINTS,
    WINE_POINTS_PER_UNIT,
)

_FLAT_POINTS = {
    "shot": SHOT_POINTS,
    "longdrink": LONGDRINK_POINTS,
}
_POINTS_PER_UNIT = {
    "beer": BEER_POINTS_PER_UNIT,
    "wine": WINE_POINTS_PER_UNIT,
}


def calculate_base_points(drink_type: str, amount: float | None) -> int:
    if drink_type not in ALLOWED_DRINK_TYPES:
        raise ValueError(f"unknown drink type: {drink_type}")

    if drink_type in AMOUNT_SCALED_DRINK_TYPES:
        if amount is None or amount <= 0:
            raise ValueError(f"{drink_type} requires a positive amount")
        return round(_POINTS_PER_UNIT[drink_type] * amount)

    return _FLAT_POINTS[drink_type]


def apply_owner_modifier(
    base_points: int,
    territory_id: str | None,
    current_owner_membership_id: str | None,
    drinking_membership_id: str,
) -> int:
    """No-op hook for the territory owner advantage (D-01), which the team
    has not decided yet. Returns base_points unchanged. A real rule can
    replace this body later without touching any caller."""
    return base_points
