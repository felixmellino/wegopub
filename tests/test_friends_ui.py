"""Run the real Profile page with a persistent fake repository, no secrets."""
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from streamlit.testing.v1 import AppTest

from core.friends import transition
from core.models import Player

ROOT = Path(__file__).resolve().parents[1]


def button(at, label):
    return next(b for b in at.button if b.label == label)


def test_profile_friend_workflow_and_new_sessions():
    players = [Player(p, p.title(), "PrivateFirst", "PrivateLast", "hash", f"{p}@private.test") for p in ("alice", "bob", "carol")]
    rows = {}

    def save(actor, other, action):
        key = tuple(sorted((actor, other)))
        row = transition(actor, other, action, rows.get(key), datetime.now(timezone.utc))
        rows[key] = {**row, "updated_at": datetime.now(timezone.utc).isoformat()}

    def page(pid):
        at = AppTest.from_file(str(ROOT / "pages/1_Profile.py"))
        at.session_state["player_id"] = pid
        at.session_state["credential_version"] = "hash"
        at.run()
        assert not at.exception
        button(at, "Friends").click().run()
        return at

    with ExitStack() as stack:
        stack.enter_context(patch("data.db.download_profile_picture", return_value=None))
        stack.enter_context(patch("device_login.sync_storage", return_value=None))
        stack.enter_context(patch("data.db.get_player", side_effect=lambda pid: next(p for p in players if p.id == pid)))
        stack.enter_context(patch("data.db.list_public_usernames", return_value=[{"id": p.id, "display_name": p.display_name} for p in players]))
        stack.enter_context(patch("data.db.list_friendships", side_effect=lambda pid: [r.copy() for r in rows.values() if pid in (r["sender_id"], r["recipient_id"])]))
        stack.enter_context(patch("data.db.change_friendship", side_effect=save))
        def open_section(at, section):
            if any(b.key == "close_friends_dialog" for b in at.button):
                button(at, "Close").click().run()
            next(b for b in at.button if b.key == f"open_friends_{section}").click().run()
            assert not at.exception
            return at

        alice = page("alice")
        assert not alice.text_input  # Search lives only in its popup.
        assert [b.label for b in alice.button if str(b.key).startswith("open_friends_")] == [
            "Find players", "Current Friends · 0", "Incoming requests · 0", "Outgoing requests · 0"]
        open_section(alice, "search")
        alice.text_input[0].input("BO").run()
        button(alice, "Send friend request").click().run()
        assert not alice.exception
        assert any("sent" in e.value for e in alice.success)
        assert alice.text_input  # Dialog remains open after writing.
        open_section(alice, "outgoing")
        assert any(b.label == "Cancel request" for b in alice.button)
        bob = open_section(page("bob"), "incoming")
        button(bob, "Accept").click().run()
        assert not bob.exception
        assert any("accepted" in e.value for e in bob.success)
        assert any("No incoming requests" in e.value for e in bob.caption)
        open_section(bob, "accepted")
        assert any(b.label == "Remove friend" for b in bob.button)
        fresh_alice = open_section(page("alice"), "accepted")
        assert any(b.label == "Remove friend" for b in fresh_alice.button)
        carol = page("carol")
        for section in ("incoming", "accepted", "outgoing"):
            open_section(carol, section)
            assert not any(b.label in ("Accept", "Remove friend", "Cancel request") for b in carol.button)
        assert not any("alice@" in str(e.value) for e in carol.text)
        button(fresh_alice, "Remove friend").click().run()
        assert rows[("alice", "bob")]["status"] == "accepted"
        button(fresh_alice, "Keep friend").click().run()
        assert rows[("alice", "bob")]["status"] == "accepted"
        button(fresh_alice, "Remove friend").click().run()
        button(fresh_alice, "Confirm removal").click().run()
        assert any("Friend removed" in e.value for e in fresh_alice.success)
        assert not any(b.label == "Remove friend" for b in open_section(page("bob"), "accepted").button)
        alice = open_section(page("alice"), "search")
        alice.text_input[0].input("bob").run()
        button(alice, "Send friend request").click().run()
        open_section(alice, "outgoing")
        button(alice, "Cancel request").click().run()
        assert any("cancelled" in e.value for e in alice.success)
        assert not any(b.label == "Accept" for b in open_section(page("bob"), "incoming").button)
        open_section(alice, "search")
        alice.text_input[0].input("bob").run()
        button(alice, "Send friend request").click().run()
        bob = open_section(page("bob"), "incoming")
        button(bob, "Decline").click().run()
        assert any("declined" in e.value for e in bob.success)
        alice = open_section(page("alice"), "search")
        alice.text_input[0].input("bob").run()
        button(alice, "Send friend request").click().run()
        assert any("10 minutes" in e.value for e in alice.error)
        assert not alice.exception
        button(alice, "Close").click().run()
        assert "_friends_dialog" not in alice.session_state
        assert not alice.text_input


def test_friend_service_failure_preserves_profile():
    player = Player("alice", "Alice", "Private", "Name", "hash", "private@test.com")
    with patch("data.db.download_profile_picture", return_value=None), patch("device_login.sync_storage", return_value=None), patch("data.db.get_player", return_value=player), patch("data.db.list_public_usernames", side_effect=RuntimeError("missing migration")):
        at = AppTest.from_file(str(ROOT / "pages/1_Profile.py"))
        at.session_state["player_id"] = player.id
        at.session_state["credential_version"] = player.pin_hash
        at.run()
        assert not at.exception
        button(at, "Friends").click().run()
        assert at.error
        button(at, "Back to Profile").click().run()
        assert any(b.label == "Log out" for b in at.button)


# These tests isolate account/profile workflows; lobby restoration is covered
# end-to-end with its own persistent fake repository in test_lobby_selection.
@pytest.fixture(autouse=True)
def isolate_lobby_restoration(monkeypatch):
    monkeypatch.setattr('shared.restore_selection', lambda player_id: None)
