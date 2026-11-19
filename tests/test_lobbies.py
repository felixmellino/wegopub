from datetime import datetime

import pytest

from core.lobbies import create_lobby, create_season, join_lobby


def test_join_lobby_with_bad_code_raises():
    lobby = create_lobby("Friends")
    with pytest.raises(ValueError):
        join_lobby("player-1", "WRONGCODE", [lobby], [])


def test_joining_same_lobby_twice_is_idempotent():
    lobby = create_lobby("Friends")
    first = join_lobby("player-1", lobby.invite_code, [lobby], [])
    second = join_lobby("player-1", lobby.invite_code, [lobby], [first])
    assert first.id == second.id


def test_different_players_get_different_memberships():
    lobby = create_lobby("Friends")
    m1 = join_lobby("player-1", lobby.invite_code, [lobby], [])
    m2 = join_lobby("player-2", lobby.invite_code, [lobby], [m1])
    assert m1.id != m2.id


def test_create_season_rejects_unknown_length():
    with pytest.raises(ValueError):
        create_season("lobby-1", "2_years", datetime(2026, 11, 17))


def test_create_season_computes_end_date():
    season = create_season("lobby-1", "1_week", datetime(2026, 11, 17))
    assert (season.ends_at - season.starts_at).days == 7


def test_lobby_creator_is_the_earliest_membership_even_after_leaving():
    from datetime import timedelta, timezone
    from types import SimpleNamespace as M
    from core.lobbies import lobby_creator
    t = datetime(2026, 11, 19, 12, tzinfo=timezone.utc)
    members = [M(id="b", player_id="guest", joined_at=t + timedelta(minutes=5)),
               M(id="a", player_id="creator", joined_at=t, left_at=t + timedelta(hours=1))]
    assert lobby_creator(members) == "creator"
    assert lobby_creator([]) is None
