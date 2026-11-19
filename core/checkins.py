"""Legacy check-in creation, preserved for existing seasons.

New seasons use core.scoring_v1.create_scored_entry and database acceptance.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from core.constants import ALLOWED_DRINK_TYPES, AMOUNT_SCALED_DRINK_TYPES, DUPLICATE_WINDOW_SECONDS
from core.game_window import is_in_game_window
from core.location import evaluate_location
from core.models import DrinkEntry, Territory
from core.scoring import calculate_base_points


class CheckinRejected(Exception):
    """A check-in cannot be saved. `reason` identifies the message to show."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def validate_drink_input(drink_type: str, amount: float | None, photo_ref: str | None) -> None:
    if not photo_ref:
        raise CheckinRejected("missing_photo")
    if drink_type not in ALLOWED_DRINK_TYPES:
        raise CheckinRejected("unknown_drink_type")
    if drink_type in AMOUNT_SCALED_DRINK_TYPES and (amount is None or amount <= 0):
        raise CheckinRejected("missing_amount")


def is_duplicate(
    membership_id: str,
    drink_type: str,
    submitted_at: datetime,
    recent_entries: list[DrinkEntry],
) -> bool:
    window = timedelta(seconds=DUPLICATE_WINDOW_SECONDS)
    submitted_at_utc = submitted_at.astimezone(timezone.utc)
    for entry in recent_entries:
        if (
            entry.membership_id == membership_id
            and entry.drink_type == drink_type
            and abs(entry.submitted_at.astimezone(timezone.utc) - submitted_at_utc) < window
        ):
            return True
    return False


def create_drink_entry(
    membership_id: str,
    season_id: str,
    drink_type: str,
    amount: float | None,
    photo_ref: str,
    device_gps: tuple[float, float] | None,
    accuracy_m: float | None,
    submitted_at: datetime,
    territories: list[Territory],
    recent_entries: list[DrinkEntry],
) -> DrinkEntry:
    """Build a drink entry after input, duplicate, and location checks pass."""
    validate_drink_input(drink_type, amount, photo_ref)

    if is_duplicate(membership_id, drink_type, submitted_at, recent_entries):
        raise CheckinRejected("duplicate_check_in")

    location_check_result, territory_id = evaluate_location(device_gps, accuracy_m, territories)
    if location_check_result in ("unavailable", "uncertain"):
        raise CheckinRejected(f"location_{location_check_result}")

    # Game-window boundaries use the submission's local clock time.
    in_window = is_in_game_window(submitted_at.replace(tzinfo=None))
    points_awarded = calculate_base_points(drink_type, amount) if in_window else 0

    return DrinkEntry(
        id=str(uuid.uuid4()),
        membership_id=membership_id,
        season_id=season_id,
        drink_type=drink_type,
        amount=amount,
        photo_ref=photo_ref,
        # The location check uses raw coordinates only as evidence.
        device_gps=None,
        photo_gps=None,
        territory_id=territory_id,
        location_check_result=location_check_result,
        points_awarded=points_awarded,
        submitted_at=submitted_at,
    )
