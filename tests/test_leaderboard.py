from datetime import datetime

from core.leaderboard import season_leader, season_leaderboard
from core.models import DrinkEntry


def make_entry(id_, membership_id, points, ts, territory_id=None):
    return DrinkEntry(
        id=id_,
        membership_id=membership_id,
        season_id="season-1",
        drink_type="shot",
        amount=None,
        photo_ref="photo",
        device_gps=None,
        photo_gps=None,
        territory_id=territory_id,
        location_check_result="outside" if territory_id is None else "matched",
        points_awarded=points,
        submitted_at=ts,
    )


def test_tie_does_not_displace_season_leader():
    entries = [
        make_entry("e1", "A", 10, datetime(2026, 11, 19, 20, 0)),
        make_entry("e2", "B", 10, datetime(2026, 11, 19, 20, 5)),
    ]
    assert season_leader(entries) == "A"


def test_strict_overtake_flips_season_leader():
    entries = [
        make_entry("e1", "A", 10, datetime(2026, 11, 19, 20, 0)),
        make_entry("e2", "B", 10, datetime(2026, 11, 19, 20, 5)),
        make_entry("e3", "B", 1, datetime(2026, 11, 19, 20, 10)),
    ]
    assert season_leader(entries) == "B"


def test_zero_point_entries_are_ignored():
    entries = [
        make_entry("e1", "A", 10, datetime(2026, 11, 19, 20, 0)),
        make_entry("e2", "B", 0, datetime(2026, 11, 19, 20, 5)),  # rejected/unavailable, 0 points
    ]
    leaderboard = season_leaderboard(entries)
    assert ("B", 0) not in leaderboard
    assert leaderboard[0] == ("A", 10)


def test_season_leaderboard_sums_and_sorts():
    entries = [
        make_entry("e1", "A", 10, datetime(2026, 11, 19, 20, 0)),
        make_entry("e2", "A", 5, datetime(2026, 11, 19, 20, 5)),
        make_entry("e3", "B", 8, datetime(2026, 11, 19, 20, 10)),
    ]
    assert season_leaderboard(entries) == [("A", 15), ("B", 8)]
