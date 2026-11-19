"""Two independent Streamlit sessions exercise the actual duel widgets."""
from copy import deepcopy
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest

import data.db as db
import minigames_ui as ui
from core.models import Lobby, LobbyMembership
from tests.test_scoring_v1 import START, season

ROOT = Path(__file__).resolve().parents[1]


def notes(page):
    """The small grey lines of a game screen."""
    return " ".join(m.value for m in page.markdown if 'class="game-note"' in m.value)


def button(page, label):
    return next(b for b in page.button if b.label == label)


@pytest.fixture
def service(monkeypatch):
    game = season()
    lobby = Lobby("lobby", "Duel lobby", "CODE")
    members = [LobbyMembership("a", "pa", "lobby", START), LobbyMembership("b", "pb", "lobby", START)]
    state = {"duels": [], "board": None, "photo": None, "location": ((38.7, -9.1), 10, None), "starts": 0}
    monkeypatch.setattr(db, "list_seasons_for_lobby", lambda _: [game])
    monkeypatch.setattr(db, "list_lobbies", lambda: [lobby])
    monkeypatch.setattr(db, "list_memberships_for_lobby", lambda _: members)
    monkeypatch.setattr(db, "list_public_usernames", lambda: [{"id": "pa", "display_name": "Alice"}, {"id": "pb", "display_name": "Bob"}])
    monkeypatch.setattr(db, "list_chug_duels", lambda *args: deepcopy(state["duels"]))
    def pending_invites(player, _season):
        return {"chug": sum(d["status"] == "invited" and d["opponent_id"] == player[-1]
                            for d in state["duels"])}
    monkeypatch.setattr(db, "pending_minigame_invites", pending_invites)
    monkeypatch.setattr("shared.require_login", lambda: __import__("streamlit").session_state["player_id"])
    monkeypatch.setattr("shared.require_active_membership", lambda: (__import__("streamlit").session_state["member"], "lobby", "season"))
    monkeypatch.setattr(ui, "current_time", lambda: START)
    monkeypatch.setattr(ui, "track_location", lambda: None)
    monkeypatch.setattr(ui, "current_location", lambda: state["location"])
    monkeypatch.setattr(ui, "camera_photo", lambda **kwargs: state["photo"])
    monkeypatch.setattr(ui, "duel_board", lambda *args: state["board"])

    def invite(actor, sid, iid, opponent, drink, size):
        assert actor == "pa" and opponent == "b"
        duel = dict(id=iid, season_id=sid, challenger_id="a", opponent_id="b", game_night="2026-11-19",
                    status="invited", drink_type=drink, size=size, play_at=None, created_at=START.isoformat(),
                    accepted_at=None, challenger_entry_id=str(uuid4()), opponent_entry_id=str(uuid4()))
        state["duels"].append(duel)
        return deepcopy(duel)

    def action(actor, did, selected, winner=None):
        d = next(d for d in state["duels"] if d["id"] == did)
        if selected == "accept":
            assert actor == "pb"
            d.update(status="accepted", accepted_at=START.isoformat())
        elif selected == "arm":
            assert actor == "pa"
            d["play_at"] = START.isoformat()
        elif selected == "finish":
            assert actor == "pa" and winner in {"a", "b"}
            d.update(status="completed", winner_id=winner)
        elif selected in {"cancel", "decline", "abort"}:
            d["status"] = "aborted" if d["status"] == "started" else {"cancel": "cancelled", "decline": "declined", "abort": "cancelled"}[selected]
        return deepcopy(d)

    def start(actor, lid, sid, did, photo, at, gps, accuracy):
        assert actor == "pa" and gps == state["location"][0] and photo
        state["starts"] += 1
        d = next(d for d in state["duels"] if d["id"] == did)
        d["status"] = "started"
        return deepcopy(d)

    monkeypatch.setattr(db, "invite_chug_duel", invite)
    monkeypatch.setattr(db, "chug_duel_action", action)
    monkeypatch.setattr(db, "start_chug_duel", start)
    state.update(lobby=lobby, members=members, game=game)
    return state


def open_page(player="pa", member="a", *, selected='chug_duel'):
    page = AppTest.from_file(ROOT / "pages/7_Minigames.py", default_timeout=10)
    page.session_state["player_id"] = player
    page.session_state["member"] = member
    if selected:
        page.session_state['minigame_selected'] = selected
    return page.run()


def test_catalogue_lists_multiple_games_without_starting_a_duel(service, monkeypatch):
    tracking = Mock()
    monkeypatch.setattr(ui, 'track_location', tracking)
    page = open_page(selected=None)
    assert not page.exception
    tiles = '\n'.join(m.value for m in page.markdown if 'class="game-tile' in m.value)
    assert '<strong>Chug Duel</strong>' in tiles and '<strong>Reaction Test</strong>' in tiles
    assert '<strong>Quiz Duel</strong>' in tiles and not button(page, 'Open Quiz Duel').disabled
    assert '<strong>Time Duel</strong>' in tiles and not button(page, 'Open Time Duel').disabled
    assert tiles.count('class="game-tile ') == 6 and tiles.count('Coming soon') == 2
    assert not any(b.label == 'Open New game' for b in page.button)
    assert not button(page, 'Open Reaction Test').disabled
    assert not any(b.label == 'Challenge' for b in page.button)
    assert not page.metric and service['duels'] == []
    tracking.assert_not_called()
    button(page, 'Open Chug Duel').click().run()
    assert not page.exception and button(page, 'Challenge')
    assert tracking.called
    button(page, 'All games').click().run()
    assert not page.exception and not page.metric and service['duels'] == []


def test_catalogue_surfaces_invitations_and_opening_recovers_them(service):
    host = open_page()
    button(host, 'Challenge').click().run()
    guest = open_page('pb', 'b', selected=None)
    assert any('aria-label="1 pending Chug Duel invite">1 invite</span>' in m.value for m in guest.markdown)
    assert not any('game-tile-invite-badge" role=' in m.value for m in open_page(selected=None).markdown)
    assert not any(b.label == 'Accept' for b in guest.button)
    button(guest, 'Open Chug Duel').click().run()
    assert not guest.exception and button(guest, 'Accept')
    button(guest, 'Accept').click().run()
    assert service['duels'][0]['status'] == 'accepted'
    button(guest, 'All games').click().run()
    assert not any('game-tile-invite-badge" role=' in m.value for m in guest.markdown)


def test_catalogue_shows_per_game_badges_and_leaves_invites_pending_until_resolved(service, monkeypatch):
    from tests.test_time_duel_ui import invitation
    time_state = dict(duels=[invitation('time-one', 'a', 'b')], incoming=True, outgoing=True,
                      test_mode=False, open=True)
    monkeypatch.setattr(db, 'time_status', lambda *args: deepcopy(time_state))
    monkeypatch.setattr(db, 'pending_minigame_invites', lambda *_: dict(chug=0, quiz=2, time=len(time_state['duels'])))
    def decline(*args):
        assert args == ('pb', 'time-one', 'decline')
        time_state['duels'] = []
        return dict(status='declined')
    monkeypatch.setattr(db, 'time_action', decline)
    guest = open_page('pb', 'b', selected=None)
    assert not guest.exception
    tiles = [m.value for m in guest.markdown if m.value.startswith('<div class="game-tile')]
    assert [b.label for b in guest.button] == ['Open Chug Duel', 'Open Reaction Test', 'Open Quiz Duel', 'Open Time Duel']
    assert 'aria-label="2 pending Quiz Duel invites">2 invites</span>' in tiles[2]
    assert 'aria-label="1 pending Time Duel invite">1 invite</span>' in tiles[3]
    assert sum('game-tile-invite-badge' in tile for tile in tiles) == 2

    button(guest, 'Open Time Duel').click().run()
    assert not guest.exception and button(guest, 'Accept Time Duel')
    button(guest, 'All games').click().run()
    assert any('aria-label="1 pending Time Duel invite"' in m.value for m in guest.markdown)

    button(guest, 'Open Time Duel').click().run()
    button(guest, 'Decline').click().run()
    button(guest, 'All games').click().run()
    assert not any('pending Time Duel invite' in m.value for m in guest.markdown)
    assert any('aria-label="2 pending Quiz Duel invites"' in m.value for m in guest.markdown)


def test_changing_lobby_context_returns_to_catalogue(service):
    page = open_page()
    page.session_state['minigames_context'] = ('other-member', 'other-lobby', 'other-season')
    page.run()
    assert not page.exception and not page.metric
    assert 'minigame_selected' not in page.session_state


def test_invite_accept_on_other_session_shared_capture_and_result(service):
    host, guest = open_page(), open_page("pb", "b")
    assert not host.exception and not guest.exception
    button(host, "Challenge").click().run()
    guest.run()
    assert not guest.exception and button(guest, "Accept")
    button(guest, "Accept").click().run()
    host.run()
    assert not any(b.label == "Start duel" for b in host.button)
    photo = BytesIO()
    Image.new("RGB", (4, 4)).save(photo, "JPEG")
    service["photo"] = photo
    host.run()
    assert not host.exception and button(host, "Start duel")
    service["location"] = (None, None, "denied")
    host.run()
    assert button(host, "Start duel").disabled
    assert service["starts"] == 0
    service["location"] = ((38.7, -9.1), 10, None)
    host.run()
    button(host, "Start duel").click().run()
    assert not host.exception and service["starts"] == 1
    assert not host.metric and not any(b.label == "Refresh duels" for b in host.button)
    guest.run()
    assert "phone" in notes(guest)
    did = service["duels"][0]["id"]
    service["board"] = {"duel_id": did, "phase": "ready"}
    host.run()
    assert service["duels"][0]["play_at"]
    assert host.session_state["chug_focused_duel"] == did
    assert not host.metric and button(host, "End without winner")
    service["board"] = {"duel_id": did, "phase": "result", "winner": "opponent"}
    host.run()
    guest.run()
    assert not host.exception and not guest.exception
    assert any("Bob won" in item.value for item in guest.success)
    assert host.session_state["chug_focused_duel"] == did
    assert button(host, "Back to Minigames")
    assert not any(b.label == "End without winner" for b in host.button)
    button(host, "Back to Minigames").click().run()
    assert not host.exception and any("Bob won" in item.value for item in host.success)
    assert "chug_focused_duel" not in host.session_state
    # A fresh session recovers the saved outcome instead of opening a new game.
    reopened = open_page("pb", "b")
    assert any("Bob won" in item.value for item in reopened.success)


def test_decline_releases_allowance_and_host_can_invite_again(service):
    host = open_page()
    button(host, "Challenge").click().run()
    guest = open_page("pb", "b")
    button(guest, "Decline").click().run()
    host.run()
    assert button(host, "Challenge")
    button(host, "Challenge").click().run()
    assert len(service["duels"]) == 2
    assert service["duels"][0]["status"] == "declined"


def test_outage_and_membership_denial_show_actionable_errors(service, monkeypatch):
    monkeypatch.setattr(db, "list_chug_duels", Mock(side_effect=RuntimeError("Chug Duel setup is not complete. Please contact the app organizer.")))
    page = open_page()
    assert not page.exception and any("setup" in item.value for item in page.error)
    assert not any(b.label == "Challenge" for b in page.button)
    monkeypatch.setattr(db, "list_memberships_for_lobby", lambda _: [])
    page.run()
    assert not page.exception and any("membership" in item.value for item in page.error)


def test_team_opponent_choices_exclude_own_team(service):
    service["lobby"].game_mode = "team"
    for member in service["members"]:
        member.team_id = "red"
    page = open_page()
    assert not page.exception and not any(b.label == "Challenge" for b in page.button)
    assert "rival team" in notes(page)


def test_arm_failure_keeps_focused_board_and_abort_restores_the_lobby(service, monkeypatch):
    host = open_page()
    button(host, "Challenge").click().run()
    duel = service["duels"][0]
    duel["status"] = "started"
    host.run()
    did = duel["id"]
    assert host.session_state["chug_focused_duel"] == did
    service["board"] = {"duel_id": did, "phase": "ready"}
    original = db.chug_duel_action
    def fail_arm(actor, did, action, winner=None):
        if action == "arm":
            raise RuntimeError("Duel service temporarily unavailable. Retry shortly.")
        return original(actor, did, action, winner)
    monkeypatch.setattr(db, "chug_duel_action", fail_arm)
    host.run()
    assert not host.exception and host.error
    assert host.session_state["chug_focused_duel"] == did
    assert not host.metric and button(host, "End without winner")
    button(host, "End without winner").click().run()
    assert not host.exception and duel["status"] == "aborted"
    assert button(host, "Back to Minigames")
    button(host, "Back to Minigames").click().run()
    assert not host.exception and "already challenged" in notes(host)


def test_test_season_allows_repeated_challenges_and_acceptances_in_new_sessions(service):
    from core.scoring_v1 import new_rules
    service["game"].scoring_rules = new_rules(test_mode=True)
    host = open_page()
    for status in ("completed", "aborted", "completed"):
        assert not host.exception and button(host, "Challenge")
        button(host, "Challenge").click().run()
        guest = open_page("pb", "b")
        assert not button(guest, "Accept").disabled
        button(guest, "Accept").click().run()
        duel = service["duels"][-1]
        duel["status"] = "started"
        host.run()
        duel.update(status=status, winner_id="a" if status == "completed" else None)
        host.run()
        button(host, "Back to Minigames").click().run()
    assert len(service["duels"]) == 3
    reopened = open_page()
    assert not reopened.exception and button(reopened, "Challenge")
    assert "already challenged" not in notes(reopened)


def test_normal_season_still_blocks_used_challenge_even_with_test_in_lobby_name(service):
    service["lobby"].name = "Test lobby"
    host = open_page()
    button(host, "Challenge").click().run()
    duel = service["duels"][0]
    duel.update(status="completed", winner_id="a")
    host.run()
    assert not host.exception
    assert not any(b.label == "Challenge" for b in host.button)
    assert "already challenged" in notes(host)


# -- Quiz Duel: one short screen, challenge in as few taps as possible --------

def quiz_state(**overrides):
    return {"duels": [], "available_points": 20, "outgoing": True, "incoming": True, "open": True,
            "test_mode": False, **overrides}


def open_quiz(service, monkeypatch, **overrides):
    monkeypatch.setattr(db, "quiz_status", lambda *args: quiz_state(**overrides))
    invite = Mock()
    monkeypatch.setattr(db, "invite_quiz_duel", invite)
    return open_page(selected="quiz"), invite


def test_quiz_screen_challenges_the_only_opponent_in_one_tap(service, monkeypatch):
    page, invite = open_quiz(service, monkeypatch)
    assert not page.exception
    assert not button(page, "Challenge").disabled           # one opponent: already chosen, stake 3
    button(page, "Challenge").click().run()
    invite.assert_called_once()
    assert invite.call_args.args[0] == "pa" and invite.call_args.args[3:] == ("b", 3)


def test_quiz_stake_is_one_tap_and_too_little_points_disable_the_button(service, monkeypatch):
    page, invite = open_quiz(service, monkeypatch, available_points=4)
    assert not button(page, "Challenge").disabled
    page.radio(key="pill_radio_quiz_stake").set_value(7).run()
    assert button(page, "Challenge").disabled
    assert not invite.called


def test_quiz_screen_is_short(service, monkeypatch):
    page, _ = open_quiz(service, monkeypatch)
    import re
    visible = " ".join(re.sub(r"<[^>]+>", " ", m.value) for m in page.markdown if "<style>" not in m.value).split()
    assert len(visible) < 25, visible and not page.metric and not page.caption and not page.info


def test_quiz_used_tonight_hides_the_form(service, monkeypatch):
    page, _ = open_quiz(service, monkeypatch, outgoing=False)
    assert not any(b.label == "Challenge" for b in page.button)
    assert "already challenged" in notes(page)
