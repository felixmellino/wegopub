from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.chug_duel import allowances, component_action, next_reset, night_id, unlimited_plays, validate_invitation, validate_pair
from core.models import Lobby, LobbyMembership
from core.scoring_v1 import can_correct, new_rules, replay_season
from core.leaderboard import season_leaderboard
from tests.test_scoring_v1 import START, entry, season


def pair():
    return (LobbyMembership("a", "pa", "lobby", START),
            LobbyMembership("b", "pb", "lobby", START), Lobby("lobby", "Test", "CODE"))


@pytest.mark.parametrize("at,night", [("2026-11-20T23:59:59+00:00", "2026-11-20"),
    ("2026-11-21T00:00:00+00:00", "2026-11-20"), ("2026-11-21T05:59:59+00:00", "2026-11-20"),
    ("2026-11-21T06:00:00+00:00", "2026-11-21")])
def test_night_rolls_at_six_not_midnight(at, night):
    at = datetime.fromisoformat(at)
    assert night_id(at, "Europe/Lisbon") == night
    assert next_reset(at, "Europe/Lisbon") > at


def test_reset_uses_calendar_time_across_daylight_saving():
    at = datetime(2026, 10, 24, 18, tzinfo=timezone.utc)
    assert next_reset(at, "Europe/Lisbon").isoformat() == "2026-10-25T06:00:00+00:00"
    assert night_id(at.astimezone(timezone(timedelta(hours=8))), "Europe/Lisbon") == "2026-10-24"


def test_separate_incoming_and_outgoing_allowances():
    duel = {"game_night": "2026-11-19", "challenger_id": "a", "opponent_id": "b", "status": "completed"}
    assert allowances("a", "2026-11-19", [duel]) == (False, True)
    assert allowances("b", "2026-11-19", [duel]) == (True, False)
    assert allowances("other-lobby-membership", "2026-11-19", [duel]) == (True, True)
    assert allowances("a", "2026-11-20", [duel]) == (True, True)
    for status in ("invited", "declined", "cancelled", "expired"):
        assert allowances("a", "2026-11-19", [dict(duel, status=status)]) == (True, True)
    for status in ("accepted", "started", "aborted"):
        assert allowances("a", "2026-11-19", [dict(duel, status=status)]) == (False, True)


def test_pair_and_invitation_validation():
    a, b, lobby = pair()
    assert validate_invitation(a, b, lobby, season(), "beer", "large", START, []) == 3
    for opponent in (a, replace(b, player_id=a.player_id), replace(b, lobby_id="other")):
        with pytest.raises(ValueError):
            validate_pair(a, opponent, lobby)
    team = replace(lobby, game_mode="team")
    for opponent in (b, replace(b, team_id="red")):
        with pytest.raises(ValueError):
            validate_pair(replace(a, team_id="red"), opponent, team)
    validate_pair(replace(a, team_id="red"), replace(b, team_id="blue"), team)
    with pytest.raises(ValueError):
        validate_invitation(a, b, lobby, season(), "beer", "large", START - timedelta(seconds=1), [])


@pytest.mark.parametrize("flag,unlimited", [(True, True), (False, False), (None, False), ("true", False), (1, False)])
def test_only_boolean_frozen_test_mode_enables_unlimited_plays(flag, unlimited):
    game = season()
    game.scoring_rules["test_mode"] = flag
    duel = {"game_night": "2026-11-19", "challenger_id": "a", "opponent_id": "b", "status": "completed"}
    assert unlimited_plays(game) is unlimited
    assert allowances("a", "2026-11-19", [duel], season=game) == (unlimited, True)
    assert allowances("b", "2026-11-19", [duel], season=game) == (True, unlimited)


def test_repeated_test_duels_allowed_but_normal_lobby_and_closed_window_rejected():
    a, b, lobby = pair()
    played = [dict(game_night="2026-11-19", challenger_id="a", opponent_id="b", status=status)
              for status in ("completed", "aborted", "completed")]
    qa = replace(season(), scoring_rules=new_rules(test_mode=True))
    assert validate_invitation(a, b, lobby, qa, "beer", "large", START, played) == 3
    with pytest.raises(ValueError, match="already used"):
        validate_invitation(a, b, replace(lobby, name="Test lobby"), season(), "beer", "large", START, played)
    with pytest.raises(ValueError, match="scoring is open"):
        validate_invitation(a, b, lobby, qa, "beer", "large", START + timedelta(days=3), played)


def test_transfer_changes_only_season_and_survives_input_ordering():
    a = replace(entry("a", "ma", "beer", "large", 0, order=1), duel_id="duel")
    b = replace(entry("b", "mb", "beer", "large", 0, order=2), duel_id="duel",
                duel_transfer_to="ma", duel_transfer_order=4)
    normal = entry("c", "mc", "beer", "small", 1, order=3)
    before = replay_season([a, replace(b, duel_transfer_to=None, duel_transfer_order=None), normal])
    after = replay_season([b, normal, a])
    assert after.season_quarters["ma"] == before.season_quarters["ma"] + 12
    assert after.season_quarters["mb"] == before.season_quarters["mb"] - 12
    assert sum(after.season_quarters.values()) == sum(before.season_quarters.values())
    assert after.territory_totals == before.territory_totals
    assert after.owners == before.owners
    assert after.awards == before.awards
    assert not can_correct(a, season(), START + timedelta(seconds=1))


@pytest.mark.parametrize("teams", [False, True])
def test_outside_duel_is_six_zero_in_individual_and_team_standings(teams):
    winner, loser = ("red", "blue") if teams else ("ma", "mb")
    a = replace(entry("a", "ma", "beer", "large", 0, territory=None, order=1),
                duel_id="duel", team_id="red" if teams else None)
    b = replace(entry("b", "mb", "beer", "large", 0, territory=None, order=2),
                duel_id="duel", team_id="blue" if teams else None,
                duel_transfer_to=winner, duel_transfer_order=3)
    assert season_leaderboard([a, b]) == [(winner, Decimal(6)), (loser, Decimal(0))]
    assert replay_season([a, b]).territory_totals == {}


def test_unfinished_duel_keeps_normal_points():
    a = replace(entry("a", "ma", "beer", "large", 0, territory=None, order=1), duel_id="duel")
    b = replace(entry("b", "mb", "beer", "large", 0, territory=None, order=2), duel_id="duel")
    assert dict(season_leaderboard([a, b])) == {"ma": 3, "mb": 3}


def test_component_events_require_current_duel_and_valid_side():
    d = {"id": "d", "challenger_id": "a", "opponent_id": "b", "play_at": None}
    assert component_action({"duel_id": "d", "phase": "ready"}, d) == ("arm", None)
    assert component_action({"duel_id": "other", "phase": "ready"}, d) is None
    assert component_action({"duel_id": "d", "phase": "result", "winner": "challenger"}, d) is None
    d["play_at"] = START.isoformat()
    assert component_action({"duel_id": "d", "phase": "result", "winner": "opponent"}, d) == ("finish", "b")
    assert component_action({"duel_id": "d", "phase": "result", "winner": "outsider"}, d) is None
