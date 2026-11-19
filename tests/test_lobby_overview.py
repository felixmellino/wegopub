from dataclasses import replace
from datetime import datetime, timedelta, timezone

from core.lobbies import create_season
from core.lobby_overview import latest_season, lobby_status, time_left

NOW = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)


def test_lifecycle_has_exact_finish_and_start_boundaries():
    season = create_season('lobby', '1_week', NOW)
    assert lobby_status(None, NOW) == 'setup'
    assert lobby_status(season, NOW - timedelta(seconds=1)) == 'upcoming'
    assert lobby_status(season, NOW) == 'active'
    assert lobby_status(season, season.ends_at - timedelta(microseconds=1)) == 'active'
    assert lobby_status(season, season.ends_at) == 'past'
    assert lobby_status(season, season.ends_at + timedelta(days=1)) == 'past'


def test_latest_season_keeps_legacy_history_and_accepts_unsorted_dates():
    first = create_season('lobby', '1_week', NOW)
    last = replace(first, id='last', starts_at=NOW + timedelta(days=10))
    assert latest_season([last, first]) == last
    assert latest_season([]) is None


def test_countdown_is_nonnegative_and_rounds_up_subminute_remainder():
    assert time_left(NOW + timedelta(days=2, hours=3, minutes=4), NOW) == '2d 3h 4m'
    assert time_left(NOW + timedelta(seconds=1), NOW) == '0h 1m'
    assert time_left(NOW + timedelta(microseconds=1), NOW) == '0h 1m'
    assert time_left(NOW, NOW) == '0h 0m'
    assert time_left(NOW - timedelta(days=1), NOW) == '0h 0m'
