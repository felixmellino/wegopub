"""The selected scoring rules, including exact quarters and correction replay."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from core.checkins import CheckinRejected
from core.leaderboard import season_leaderboard, season_leader
from core.models import DrinkEntry, Season
from core.scoring_v1 import (base_points, can_correct, cooldown_remaining, corrected_entry,
    create_scored_entry, new_rules, next_opening, replay_season, scoring_open, window_bounds)
from core.territories import territory_owner, territory_standings
from tests.test_checkins import INSIDE, OUTSIDE, TERRITORY

START = datetime(2026, 11, 19, 18, tzinfo=timezone.utc)


def season(zone="Europe/Lisbon"):
    return Season("season", "lobby", START - timedelta(days=1), START + timedelta(days=30),
                  "1_month", zone, "v1", new_rules())


def entry(id_, member, kind, size, minute, *, territory="territory-a", order=None):
    return DrinkEntry(id_, member, "season", kind, None, "photo", None, None, territory,
        "matched" if territory else "outside", base_points(kind, size, new_rules()),
        START + timedelta(minutes=minute), size=size, rule_version="v1", event_order=order)


@pytest.mark.parametrize("kind,size,expected", [
    ("beer", "small", 1), ("beer", "medium", 2), ("beer", "large", 3),
    ("wine", "small", 1), ("wine", "medium", 2), ("wine", "large", 4),
    ("mixed", "small", 2), ("mixed", "medium", 3), ("mixed", "large", 5), ("shot", None, 4)])
def test_exact_fixed_point_table(kind, size, expected):
    assert base_points(kind, size, new_rules()) == expected


@pytest.mark.parametrize("kind,size", [("cider", "small"), ("beer", 1), ("wine", None),
                                       ("shot", "large"), ("mixed", "enormous"), ("beer", [])])
def test_unsupported_values_rejected(kind, size):
    with pytest.raises(ValueError):
        base_points(kind, size, new_rules())


def test_frozen_snapshot_is_independent_of_new_seasons_and_mutable_defaults():
    first, second = season(), season()
    first.scoring_rules["points"]["beer"]["small"] = 9
    assert second.scoring_rules["points"]["beer"]["small"] == 1
    assert new_rules()["points"]["beer"]["small"] == 1


@pytest.mark.parametrize("offset,opened", [(-1, False), (0, True), (3600, True),
    (3 * 86400 - 1, True), (3 * 86400, False), (4 * 86400, False)])
def test_weekly_boundaries(offset, opened):
    assert scoring_open(START + timedelta(seconds=offset), season()) is opened


def test_shared_timezone_not_phone_offset_controls_window():
    # New York is five hours behind Lisbon on this date.
    game = season("America/New_York")
    assert not scoring_open(START, game)
    assert scoring_open(START + timedelta(hours=5), game)
    assert scoring_open((START + timedelta(hours=5)).astimezone(ZoneInfo("Asia/Tokyo")), game)


def test_named_zone_handles_dst_week_without_fixed_72_hour_assumption():
    game = replace(season(), starts_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
                   ends_at=datetime(2026, 4, 1, tzinfo=timezone.utc))
    start, end = window_bounds(datetime(2026, 3, 27, tzinfo=timezone.utc), game)
    assert (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds() == 71 * 3600
    assert not scoring_open(end, game)


def test_active_season_start_and_end_intersect_weekly_window():
    game = replace(season(), starts_at=START + timedelta(hours=1), ends_at=START + timedelta(hours=2))
    assert not scoring_open(START, game)
    assert scoring_open(START + timedelta(hours=1), game)
    assert not scoring_open(START + timedelta(hours=2), game)
    assert next_opening(START, game) == game.starts_at
    assert next_opening(START + timedelta(hours=2), game) is None


def test_next_opening_after_sunday_close_is_next_thursday():
    assert next_opening(START + timedelta(days=3), season()) == START + timedelta(days=7)


def test_new_entry_checks_window_cooldown_and_location_and_discards_gps():
    game = season()
    accepted = create_scored_entry("A", game, "beer", "small", "photo", INSIDE, 10.0,
                                   START, [TERRITORY], [], entry_id="one")
    assert accepted.points_awarded == 1 and accepted.amount == 250
    assert accepted.device_gps is None and accepted.photo_gps is None
    assert accepted.territory_id == TERRITORY.id and accepted.size == "small"
    for kind, size in [("beer", "large"), ("shot", None), ("mixed", "medium")]:
        with pytest.raises(CheckinRejected, match="cooldown"):
            create_scored_entry("A", game, kind, size, "photo", INSIDE, None,
                START + timedelta(seconds=119), [TERRITORY], [accepted], entry_id="two")
    assert cooldown_remaining("A", START + timedelta(seconds=119), [accepted]) == 1
    assert cooldown_remaining("B", START, [accepted]) == 0
    assert create_scored_entry("A", game, "shot", None, "photo", OUTSIDE, None,
        START + timedelta(seconds=120), [TERRITORY], [accepted], entry_id="two").location_check_result == "outside"
    with pytest.raises(CheckinRejected, match="scoring_closed"):
        create_scored_entry("A", game, "shot", None, "photo", INSIDE, None,
                            START + timedelta(days=3), [TERRITORY], [], entry_id="late")
    with pytest.raises(CheckinRejected, match="location_unavailable"):
        create_scored_entry("A", game, "shot", None, "photo", None, None,
                            START, [TERRITORY], [], entry_id="gps")


def test_full_capture_sequence_and_no_self_income():
    events = [entry("1", "Mia", "beer", "large", 0), entry("2", "Leo", "shot", None, 1),
              entry("3", "Mia", "mixed", "medium", 2), entry("4", "Leo", "beer", "medium", 3),
              entry("5", "Mia", "wine", "medium", 4)]
    result = replay_season(events)
    assert result.season_rows() == [("Mia", Decimal("9.5")), ("Leo", Decimal("6.75"))]
    assert result.territory_rows(TERRITORY.id) == [("Mia", 8), ("Leo", 6)]
    assert result.awards == {"1": (None, 0), "2": ("Mia", 4), "3": ("Leo", 3), "4": ("Mia", 2), "5": (None, 0)}
    assert territory_owner(events, TERRITORY.id) == "Mia"
    assert season_leader(events) == "Mia"
    assert season_leaderboard(events) == result.season_rows()
    assert territory_standings(events, TERRITORY.id) == result.territory_rows(TERRITORY.id)


def test_correction_replays_later_owner_income_and_ownership_without_compounding():
    events = [entry("1", "Mia", "beer", "large", 0), entry("2", "Leo", "beer", "medium", 1),
              entry("3", "Leo", "wine", "large", 3), entry("4", "Eva", "shot", None, 3.25)]
    before = replay_season(events)
    assert before.season_quarters == {"Mia": 18, "Leo": 28, "Eva": 16}
    changed = corrected_entry(events[2], season(), "wine", "small", START + timedelta(minutes=4))
    assert changed.id == events[2].id and changed.submitted_at == events[2].submitted_at
    events[2] = changed
    after = replay_season(events)
    assert after.season_quarters == {"Mia": 19, "Leo": 12, "Eva": 16}
    assert after.owners[TERRITORY.id] == "Eva"
    assert after.awards["4"] == ("Mia", 4)
    assert replay_season(events) == after  # running again adds no income


def test_same_event_season_tie_keeps_previously_higher_ranked_owner():
    # Mia 3, Leo 0; Leo's shot gives Mia 1 and Leo 4, both reach 4 together.
    events = [entry("1", "Mia", "beer", "large", 0), entry("2", "Leo", "shot", None, 1)]
    assert season_leaderboard(events) == [("Mia", Decimal(4)), ("Leo", Decimal(4))]


def test_event_order_overrides_equal_display_timestamps_and_input_order():
    first = entry("z", "first", "shot", None, 0, order=1)
    second = entry("a", "second", "shot", None, 0, order=2)
    assert replay_season([second, first]).owners[TERRITORY.id] == "first"


def test_outside_and_legacy_events_do_not_generate_income_and_zero_does_not_claim():
    outside = entry("1", "A", "shot", None, 0, territory=None)
    zero = replace(entry("2", "B", "shot", None, 1), points_awarded=0)
    result = replay_season([outside, zero])
    assert result.owners == {} and result.season_quarters == {"A": 16}


def test_correction_deadline_weekly_closure_and_season_end():
    last = replace(entry("one", "A", "beer", "small", 0), submitted_at=START + timedelta(days=3, seconds=-30))
    assert can_correct(last, season(), last.submitted_at + timedelta(seconds=119))
    assert not can_correct(last, season(), last.submitted_at + timedelta(seconds=120))
    assert not can_correct(last, replace(season(), ends_at=last.submitted_at + timedelta(seconds=30)), last.submitted_at + timedelta(seconds=30))
    assert not can_correct(last, season(), last.submitted_at - timedelta(seconds=1))


def test_replay_cannot_mix_seasons():
    with pytest.raises(ValueError, match="one season"):
        replay_season([entry("1", "A", "shot", None, 0), replace(entry("2", "B", "shot", None, 1), season_id="other")])


@pytest.mark.parametrize("gps", [(float('nan'), 0), (0, float('inf')), (91, 0), (0, -181), (1,), ('x', 2)])
def test_invalid_coordinates_do_not_become_verified_outside_entries(gps):
    with pytest.raises(CheckinRejected, match="location_uncertain"):
        create_scored_entry("A", season(), "shot", None, "photo", gps, None, START, [TERRITORY], [], entry_id="invalid")


@pytest.mark.parametrize("accuracy", [80.0, 50.1, float("nan"), float("inf"), -1.0])
def test_inaccurate_or_invalid_gps_accuracy_is_rejected(accuracy):
    """R-L02: a reading worse than 50 m (or a malformed accuracy) is uncertain."""
    with pytest.raises(CheckinRejected, match="location_uncertain"):
        create_scored_entry("A", season(), "shot", None, "photo", INSIDE, accuracy, START, [TERRITORY], [], entry_id="acc")


def test_gps_accuracy_of_exactly_50_m_is_accepted():
    entry = create_scored_entry("A", season(), "shot", None, "photo", INSIDE, 50.0, START, [TERRITORY], [], entry_id="ok")
    assert entry.location_check_result == "matched"
