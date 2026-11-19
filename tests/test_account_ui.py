"""Exercise real Streamlit forms without external credentials."""
from pathlib import Path
from unittest.mock import patch

import pytest

from streamlit.testing.v1 import AppTest

from core.lobbies import create_player

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def allow_attempts():
    def browser(**command):
        return {"request_id": command["request_id"], "token": command.get("token", ""), "available": True}
    with patch("data.db.download_profile_picture", return_value=None), patch("data.db.allow_login_attempt", return_value=True), patch("device_login._browser_storage", side_effect=browser), \
         patch("data.db.list_public_usernames", return_value=[]), patch("data.db.list_friendships", return_value=[]):
        yield


def form(at, label):
    return next(button for button in at.button if button.label == label)


def fill(at, label, value):
    next(field for field in at.text_input if field.label == label).input(value)


def test_first_visit_and_direct_game_page_require_account():
    for path in [
        "app.py", "pages/2_Lobby.py", "pages/3_Check_in.py",
        "pages/4_Standings.py", "pages/6_Check_in_photos.py",
    ]:
        at = AppTest.from_file(str(ROOT / path)).run()
        assert not at.exception
        assert at.radio(key="account_action").options == ["Create account", "Log in"]
        assert not at.tabs
        assert not at.table
        assert not any(button.label == "Create lobby" for button in at.button)


def test_registration_login_logout_and_progress_identity():
    players = []
    with patch("data.db.list_players", side_effect=lambda: players), \
         patch("data.db.insert_player", side_effect=players.append), \
         patch("data.db.get_player", side_effect=lambda pid: next((p for p in players if p.id == pid), None)):
        at = AppTest.from_file(str(ROOT / "pages/1_Profile.py")).run()
        for label, value in [("First name", "Mia"), ("Surname", "Silva"), ("Username", "mia"),
                             ("Email", "MIA@example.com"), ("Password", "password8"), ("Confirm password", "password8")]:
            fill(at, label, value)
        form(at, "Create account").click().run()
        assert not at.exception
        pid = at.session_state["player_id"]
        assert players[0].id == pid
        form(at, "Log out").click().run()
        # New Streamlit process/session still signs into the stored player ID.
        at = AppTest.from_file(str(ROOT / "pages/1_Profile.py")).run()
        at.radio(key="account_action").set_value("Log in").run()
        at.text_input(key="login_email").input("mia@example.com")
        at.text_input(key="login_password").input("password8")
        form(at, "Log in").click().run()
        assert not at.exception
        assert at.session_state["player_id"] == pid


def test_invalid_registration_creates_nothing():
    with patch("data.db.list_players", return_value=[]), patch("data.db.insert_player") as insert:
        at = AppTest.from_file(str(ROOT / "app.py")).run()
        form(at, "Create account").click().run()
        assert at.error
        insert.assert_not_called()
        assert "player_id" not in at.session_state


@pytest.mark.parametrize("path", ["app.py", "pages/1_Profile.py", "pages/2_Lobby.py"])
def test_login_offers_password_recovery(path):
    at = AppTest.from_file(str(ROOT / path)).run()
    at.radio(key="account_action").set_value("Log in").run()
    assert not at.exception
    assert not at.expander
    assert [field.label for field in at.text_input] == ["Email", "Password"]
    assert [button.label for button in at.button] == ["Log in", "Forgot password?"]
    assert [box.label for box in at.checkbox] == ["Remember password"]


def test_incorrect_password_does_not_authenticate_or_change_account():
    player = create_player("mia", "Mia", "Silva", "mia@example.com", "password8", "password8", [])
    original_hash = player.pin_hash
    with patch("data.db.list_players", return_value=[player]), \
         patch("data.db.insert_player") as insert:
        at = AppTest.from_file(str(ROOT / "app.py")).run()
        at.radio(key="account_action").set_value("Log in").run()
        at.text_input(key="login_email").input(player.email)
        at.text_input(key="login_password").input("wrong-password")
        form(at, "Log in").click().run()
        assert not at.exception
        assert any("Email or password is incorrect" in msg.value for msg in at.error)
        assert "player_id" not in at.session_state
        assert player.pin_hash == original_hash
        insert.assert_not_called()


def test_password_change_invalidates_existing_session():
    old = create_player("mia", "Mia", "Silva", "mia@example.com", "password8", "password8", [])
    changed = create_player("mia", "Mia", "Silva", "mia@example.com", "newpass8", "newpass8", [])
    with patch("data.db.get_player", return_value=changed):
        at = AppTest.from_file(str(ROOT / "pages/2_Lobby.py"))
        at.session_state["player_id"] = old.id
        at.session_state["credential_version"] = old.pin_hash
        at.session_state["current_lobby_id"] = "old-lobby"
        at.run()
        assert not at.exception
        assert "player_id" not in at.session_state
        assert "current_lobby_id" not in at.session_state
        assert "Log in" in at.radio(key="account_action").options


def test_throttled_login_does_not_authenticate():
    player = create_player("mia", "Mia", "Silva", "mia@example.com", "password8", "password8", [])
    with patch("data.db.list_players", return_value=[player]), \
         patch("data.db.allow_login_attempt", return_value=False):
        at = AppTest.from_file(str(ROOT / "app.py")).run()
        at.radio(key="account_action").set_value("Log in").run()
        at.text_input(key="login_email").input(player.email)
        at.text_input(key="login_password").input("password8")
        form(at, "Log in").click().run()
        assert any("Too many login attempts" in msg.value for msg in at.error)
        assert "player_id" not in at.session_state


def test_remember_checkbox_creates_device_token_and_restores_after_new_session():
    player = create_player("mia", "Mia", "Silva", "mia@example.com", "password8", "password8", [])
    token = "random-device-token"
    with patch("data.db.list_players", return_value=[player]), \
         patch("data.db.get_player", return_value=player), \
         patch("data.db.create_remembered_session", return_value=token) as create, \
         patch("data.db.revoke_remembered_session") as revoke:
        at = AppTest.from_file(str(ROOT / "pages/1_Profile.py")).run()
        at.radio(key="account_action").set_value("Log in").run()
        at.text_input(key="login_email").input(player.email)
        at.text_input(key="login_password").input("password8")
        next(box for box in at.checkbox if box.label == "Remember password").check()
        form(at, "Log in").click().run()
        assert not at.exception
        create.assert_called_once_with(player)
        assert at.session_state["_device_token"] == token
        form(at, "Log out").click().run()
        revoke.assert_called_once_with(token)
        assert "player_id" not in at.session_state

    with patch("device_login._browser_storage", side_effect=lambda **c: {"request_id": c["request_id"], "token": token, "available": True}), \
         patch("data.db.get_remembered_player", return_value=player), \
         patch("data.db.get_player", return_value=player):
        fresh = AppTest.from_file(str(ROOT / "pages/1_Profile.py")).run()
        assert not fresh.exception
        assert fresh.session_state["player_id"] == player.id
        assert not fresh.text_input
        form(fresh, "Friends").click().run()
        assert not fresh.text_input
        form(fresh, "Find players").click().run()
        assert [field.label for field in fresh.text_input] == ["Search usernames"]


def test_unchecked_remember_does_not_create_persistent_access():
    player = create_player("mia", "Mia", "Silva", "mia@example.com", "password8", "password8", [])
    with patch("data.db.list_players", return_value=[player]), \
         patch("data.db.get_player", return_value=player), \
         patch("data.db.create_remembered_session") as create:
        at = AppTest.from_file(str(ROOT / "app.py")).run()
        at.radio(key="account_action").set_value("Log in").run()
        at.text_input(key="login_email").input(player.email)
        at.text_input(key="login_password").input("password8")
        form(at, "Log in").click().run()
        assert not at.exception
        assert at.session_state["player_id"] == player.id
        create.assert_not_called()


def test_invalid_saved_token_is_cleared_without_access():
    def browser(**command):
        token = "invalid-token" if command["action"] == "read" else ""
        return {"request_id": command["request_id"], "token": token, "available": True}
    with patch("device_login._browser_storage", side_effect=browser), \
         patch("data.db.get_remembered_player", return_value=None):
        at = AppTest.from_file(str(ROOT / "app.py")).run()
        assert not at.exception
        assert "player_id" not in at.session_state
        assert at.radio(key="account_action").options == ["Create account", "Log in"]


def test_delayed_browser_read_waits_then_restores_without_login_form():
    player = create_player("mia", "Mia", "Silva", "mia@example.com", "password8", "password8", [])
    requests = []

    def delayed_browser(**command):
        requests.append(command["request_id"])
        if len(requests) == 1:
            return None
        return {"request_id": command["request_id"], "token": "saved-token", "available": True}

    with patch("device_login._browser_storage", side_effect=delayed_browser), \
         patch("data.db.get_remembered_player", return_value=player) as restore, \
         patch("data.db.get_player", return_value=player):
        at = AppTest.from_file(str(ROOT / "app.py")).run()
        assert not at.exception
        assert not at.radio
        assert not at.text_input
        assert "player_id" not in at.session_state
        restore.assert_not_called()
        at.run()
        assert not at.exception
        assert at.session_state["player_id"] == player.id
        assert requests[0] == requests[1]
        assert not at.text_input


def test_surviving_browser_bridge_restores_after_server_state_is_lost():
    player = create_player("mia", "Mia", "Silva", "mia@example.com", "password8", "password8", [])
    # Model an iframe that remembers the last request even after the server
    # loses its widget state. It will not send the same request twice.
    last_request = None
    requests = []

    def surviving_browser(**command):
        nonlocal last_request
        requests.append(command["request_id"])
        if command["request_id"] == last_request:
            return None
        last_request = command["request_id"]
        return {"request_id": last_request, "token": "saved-token", "available": True}

    script = '''
import streamlit as st
from shared import require_login
require_login()
if st.button("Lose server session"):
    st.session_state.clear()
    st.rerun()
'''
    with patch("device_login._browser_storage", side_effect=surviving_browser), \
         patch("data.db.get_remembered_player", return_value=player) as restore, \
         patch("data.db.get_player", return_value=player):
        at = AppTest.from_string(script).run()
        assert not at.exception
        assert at.session_state["player_id"] == player.id
        form(at, "Lose server session").click().run()
        assert not at.exception
        assert at.session_state["player_id"] == player.id
        assert requests[0] != requests[-1]
        assert restore.call_count == 2
        assert not at.text_input


def recovery_screen():
    at = AppTest.from_file(str(ROOT / "app.py")).run()
    at.radio(key="account_action").set_value("Log in").run()
    form(at, "Forgot password?").click().run()
    assert not at.exception
    return at


def test_recovery_request_and_return_to_login():
    with patch("data.db.request_password_reset") as request:
        at = recovery_screen()
        fill(at, "Registered email", "mia@example.com")
        form(at, "Send reset code").click().run()
        request.assert_called_once_with("mia@example.com")
        assert not at.exception
        assert "If an account exists" in at.info[0].value
        form(at, "Back to log in").click().run()
        assert not at.exception
        assert any(field.label == "Password" for field in at.text_input)


def test_recovery_success_does_not_sign_in():
    with patch("data.db.reset_password") as reset:
        at = recovery_screen()
        for label, value in [("Account email", "mia@example.com"), ("Reset code", "ABCD1234ABCD1234"),
                             ("New password", "newpass8"), ("Confirm new password", "newpass8")]:
            fill(at, label, value)
        form(at, "Reset password").click().run()
        reset.assert_called_once_with("mia@example.com", "ABCD1234ABCD1234", "newpass8", "newpass8")
        assert not at.exception
        assert at.success
        assert "player_id" not in at.session_state


def test_recovery_failure_remains_usable():
    with patch("data.db.reset_password", side_effect=ValueError("The reset code is incorrect or expired.")):
        at = recovery_screen()
        form(at, "Reset password").click().run()
        assert not at.exception
        assert at.error
        assert not at.success
        assert "player_id" not in at.session_state


# These tests isolate account/profile workflows; lobby restoration is covered
# end-to-end with its own persistent fake repository in test_lobby_selection.
@pytest.fixture(autouse=True)
def isolate_lobby_restoration(monkeypatch):
    monkeypatch.setattr('shared.restore_selection', lambda player_id: None)
