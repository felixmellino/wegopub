from datetime import datetime

from core.minigames import can_play, record_attempt

WINDOW = "2026-11-19"


def test_first_play_is_allowed():
    assert can_play("membership-1", WINDOW, []) is True


def test_second_play_same_window_same_membership_is_blocked():
    first = record_attempt("membership-1", "season-1", "arena-1", "beer_pong", WINDOW, datetime.now(), [])
    assert can_play("membership-1", WINDOW, [first]) is False


def test_different_window_resets_the_limit():
    first = record_attempt("membership-1", "season-1", "arena-1", "beer_pong", WINDOW, datetime.now(), [])
    assert can_play("membership-1", "2026-11-26", [first]) is True


def test_different_lobby_membership_is_independent():
    # membership-2 represents the same player in a DIFFERENT lobby.
    first = record_attempt("membership-1", "season-1", "arena-1", "beer_pong", WINDOW, datetime.now(), [])
    assert can_play("membership-2", WINDOW, [first]) is True
