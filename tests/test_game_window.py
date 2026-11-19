from datetime import datetime

from core.game_window import game_window_id, is_in_game_window

# 2026-11-19 is a Thursday; 2026-11-22 is the following Sunday.


def test_wednesday_night_is_outside():
    assert is_in_game_window(datetime(2026, 11, 18, 23, 59, 59)) is False


def test_thursday_at_exact_start_is_inside():
    assert is_in_game_window(datetime(2026, 11, 19, 12, 0, 0)) is True


def test_thursday_before_start_is_outside():
    assert is_in_game_window(datetime(2026, 11, 19, 11, 59, 59)) is False


def test_sunday_at_exact_end_is_inside():
    assert is_in_game_window(datetime(2026, 11, 22, 23, 59, 59)) is True


def test_monday_midnight_is_outside():
    assert is_in_game_window(datetime(2026, 11, 23, 0, 0, 0)) is False


def test_saturday_afternoon_is_inside():
    assert is_in_game_window(datetime(2026, 11, 21, 15, 0, 0)) is True


def test_same_window_has_same_id():
    thursday_evening = datetime(2026, 11, 19, 20, 0, 0)
    sunday_afternoon = datetime(2026, 11, 22, 15, 0, 0)
    assert game_window_id(thursday_evening) == game_window_id(sunday_afternoon)


def test_different_weeks_have_different_ids():
    this_week = datetime(2026, 11, 19, 20, 0, 0)
    next_week = datetime(2026, 11, 26, 20, 0, 0)
    assert game_window_id(this_week) != game_window_id(next_week)
