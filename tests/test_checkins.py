from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from core.checkins import CheckinRejected, create_drink_entry
from core.models import Territory

TERRITORY = Territory(
    id="territory-a",
    name="Bairro Alto",
    boundary={
        "type": "Polygon",
        "coordinates": [
            [[-9.15, 38.70], [-9.14, 38.70], [-9.14, 38.71], [-9.15, 38.71], [-9.15, 38.70]]
        ],
    },
)
INSIDE = (38.705, -9.145)
OUTSIDE = (38.80, -9.00)
# 2026-11-19 is a Thursday, inside the game window (starts 12:00).
IN_WINDOW_TS = datetime(2026, 11, 19, 20, 0, 0)
OUTSIDE_WINDOW_TS = datetime(2026, 11, 17, 20, 0, 0)  # a Tuesday


def test_valid_check_in_scores_full_points():
    entry = create_drink_entry(
        "membership-1", "season-1", "beer", 2, "photo-1", INSIDE, 10.0, IN_WINDOW_TS, [TERRITORY], []
    )
    assert entry.points_awarded > 0
    assert entry.location_check_result == "matched"
    assert entry.territory_id == TERRITORY.id
    assert entry.device_gps is None
    assert entry.photo_gps is None


def test_missing_photo_is_rejected():
    with pytest.raises(CheckinRejected) as exc:
        create_drink_entry("membership-1", "season-1", "beer", 2, "", INSIDE, None, IN_WINDOW_TS, [TERRITORY], [])
    assert exc.value.reason == "missing_photo"


def test_missing_amount_for_beer_is_rejected():
    with pytest.raises(CheckinRejected) as exc:
        create_drink_entry(
            "membership-1", "season-1", "beer", None, "photo-1", INSIDE, None, IN_WINDOW_TS, [TERRITORY], []
        )
    assert exc.value.reason == "missing_amount"


@pytest.mark.parametrize(
    "submitted_at",
    [IN_WINDOW_TS, IN_WINDOW_TS.replace(hour=12, tzinfo=timezone(timedelta(hours=1)))],
    ids=["local-time", "explicit-offset-at-game-window-start"],
)
def test_duplicate_with_stored_utc_timestamp_is_rejected(submitted_at):
    first = create_drink_entry(
        "membership-1", "season-1", "beer", 1, "photo-1", INSIDE, None, submitted_at, [TERRITORY], []
    )
    assert first.points_awarded > 0
    saved_entry = replace(first, submitted_at=first.submitted_at.astimezone(timezone.utc))
    second_ts = submitted_at + timedelta(minutes=1)
    with pytest.raises(CheckinRejected) as exc:
        create_drink_entry(
            "membership-1", "season-1", "beer", 1, "photo-2", INSIDE, None, second_ts, [TERRITORY], [saved_entry]
        )
    assert exc.value.reason == "duplicate_check_in"


def test_same_drink_at_duplicate_window_boundary_is_allowed():
    first = create_drink_entry(
        "membership-1", "season-1", "beer", 1, "photo-1", INSIDE, None, IN_WINDOW_TS, [TERRITORY], []
    )
    saved_entry = replace(first, submitted_at=first.submitted_at.astimezone(timezone.utc))
    later_ts = IN_WINDOW_TS + timedelta(minutes=2)
    second = create_drink_entry(
        "membership-1", "season-1", "beer", 1, "photo-2", INSIDE, None, later_ts, [TERRITORY], [saved_entry]
    )
    assert second.points_awarded > 0


def test_different_drink_type_within_window_is_allowed():
    first = create_drink_entry(
        "membership-1", "season-1", "beer", 1, "photo-1", INSIDE, None, IN_WINDOW_TS, [TERRITORY], []
    )
    second_ts = IN_WINDOW_TS + timedelta(seconds=30)
    second = create_drink_entry(
        "membership-1", "season-1", "wine", 1, "photo-2", INSIDE, None, second_ts, [TERRITORY], [first]
    )
    assert second.points_awarded > 0


def test_outside_every_territory_still_scores_total_points():
    entry = create_drink_entry(
        "membership-1", "season-1", "shot", None, "photo-1", OUTSIDE, None, IN_WINDOW_TS, [TERRITORY], []
    )
    assert entry.points_awarded > 0
    assert entry.territory_id is None
    assert entry.location_check_result == "outside"


def test_outside_game_window_scores_zero_but_does_not_raise():
    entry = create_drink_entry(
        "membership-1", "season-1", "shot", None, "photo-1", INSIDE, None, OUTSIDE_WINDOW_TS, [TERRITORY], []
    )
    assert entry.points_awarded == 0


@pytest.mark.parametrize(
    ("device_gps", "accuracy_m", "reason"),
    [
        (None, None, "location_unavailable"),
        (None, 10.0, "location_unavailable"),
        (INSIDE, 120.0, "location_uncertain"),
        (OUTSIDE, 120.0, "location_uncertain"),
    ],
    ids=["missing-location", "accuracy-but-no-location", "inaccurate-inside", "inaccurate-outside"],
)
def test_failed_location_verification_rejects_check_in(device_gps, accuracy_m, reason):
    with pytest.raises(CheckinRejected) as exc:
        create_drink_entry(
            "membership-1", "season-1", "shot", None, "photo-1", device_gps, accuracy_m, IN_WINDOW_TS, [TERRITORY], []
        )
    assert exc.value.reason == reason
