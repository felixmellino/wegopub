"""Navigation uses native page switches without dropping the signed-in identity."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import streamlit as st
from httpx import RequestError
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize("label,target", [
    ("Map", "5_Map.py"), ("Ranks", "4_Standings.py"), ("Check in", "3_Check_in.py"),
    ("Games", "7_Minigames.py"), ("Profile", "1_Profile.py"),
])
def test_bottom_navigation_switches_to_the_requested_page(monkeypatch, label, target):
    switch = Mock()
    monkeypatch.setattr(st, "switch_page", switch)
    at = AppTest.from_string("from app_navigation import bottom_navigation\nbottom_navigation('leaderboard')").run()
    assert not at.exception
    assert [button.label for button in at.button] == ["Map", "Ranks", "Check in", "Games", "Profile"]
    at.session_state["player_id"] = "signed-in-player"
    next(button for button in at.button if button.label == label).click().run()
    assert not at.exception
    assert Path(switch.call_args.args[0]) == Path(__file__).resolve().parents[1] / "pages" / target
    assert at.session_state["player_id"] == "signed-in-player"
    assert ('checkin_open_camera' in at.session_state) is (label == 'Check in')
    if label == 'Check in':
        assert at.session_state['checkin_open_camera'] is True


def test_check_in_plus_sits_in_the_middle_of_five_tabs():
    from app_navigation import DESTINATIONS
    assert len(DESTINATIONS) == 5
    assert DESTINATIONS[2][0] == "checkin"


def test_games_invite_badge_follows_the_selected_season_and_hides_at_zero(monkeypatch):
    count = Mock(side_effect=[2, RequestError("service unavailable"), 1, 0])
    monkeypatch.setattr("app_navigation.db.pending_minigame_invite_count", count)
    app = AppTest.from_string(
        "from app_navigation import bottom_navigation, minigame_invite_badge\n"
        "bottom_navigation('map')\nminigame_invite_badge()"
    )
    app.session_state["player_id"] = "player"
    app.session_state["current_season_id"] = "first"
    app.run()
    count.assert_not_called()  # The player must have passed the account check.
    app.session_state["_validated_player"] = SimpleNamespace(id="player")

    app.run()
    assert 'content: "2" / "2 pending minigame invites"' in app.get("html")[0].value
    assert any(button.label == "Games" for button in app.button)
    count.assert_called_with("player", "first")

    app.session_state["current_season_id"] = "second"
    app.run()
    assert not app.exception and not app.get("html")
    count.assert_called_with("player", "second")

    app.run()
    assert 'content: "1" / "1 pending minigame invite"' in app.get("html")[0].value
    app.run()
    assert not app.get("html")


def test_every_tab_icon_exists_in_outline_and_filled_form():
    from app_navigation import DESTINATIONS, icon_url
    for route, _label, _page, icon in DESTINATIONS:
        assert icon_url(icon).startswith("data:image/svg+xml;base64,")
        if route != "checkin":
            assert icon_url(f"{icon}-fill")


def test_lobby_and_photo_history_open_from_the_profile_menu(monkeypatch):
    switch = Mock()
    monkeypatch.setattr(st, "switch_page", switch)
    at = AppTest.from_string(
        "import streamlit as st\nfrom profile_ui import PAGES\n"
        "for key, label, page, icon in PAGES:\n"
        "    if st.button(label, key=key):\n"
        "        st.switch_page(page)").run()
    assert [b.label for b in at.button] == ["Lobbies", "Photo history"]


class Where:
    page = None


@pytest.fixture
def where(monkeypatch):
    import app_navigation
    Where.page = None
    monkeypatch.setattr(app_navigation, "current_page", lambda: Where.page)
    return Where


SCRIPT = "from app_navigation import bottom_navigation\nbottom_navigation('map')"


def back_buttons(at):
    return [b for b in at.button if b.label == "Back"]


def test_back_returns_to_the_previous_page_then_to_the_map(monkeypatch, where):
    switch = Mock()
    monkeypatch.setattr(st, "switch_page", switch)
    where.page = "map"
    at = AppTest.from_string(SCRIPT).run()
    assert not back_buttons(at)                      # nothing to go back to on the start screen
    where.page = "standings"
    at.run()
    assert at.session_state["_nav_history"] == ["map"] and len(back_buttons(at)) == 1
    back_buttons(at)[0].click().run()
    assert Path(switch.call_args.args[0]) == Path(__file__).resolve().parents[1] / "pages" / "5_Map.py"
    assert at.session_state["_nav_history"] == [] and at.session_state["_nav_going_back"] is True
    where.page = "map"                               # the Map has loaded again
    at.run()
    assert at.session_state["_nav_history"] == [] and not back_buttons(at)


def test_back_is_on_every_page_and_falls_back_to_the_map(monkeypatch, where):
    switch = Mock()
    monkeypatch.setattr(st, "switch_page", switch)
    for page in ["profile", "lobby", "check_in", "standings", "check_in_photos", "minigames"]:
        where.page = page
        at = AppTest.from_string(SCRIPT).run()       # fresh session: no history yet
        assert len(back_buttons(at)) == 1, page
        back_buttons(at)[0].click().run()
        assert Path(switch.call_args.args[0]).name == "5_Map.py", page


def test_history_follows_navigation_and_is_capped(monkeypatch, where):
    monkeypatch.setattr(st, "switch_page", Mock())
    at = AppTest.from_string(SCRIPT)
    for page in ["map", "standings", "profile", "lobby", "profile"]:
        where.page = page
        at.run()
    assert at.session_state["_nav_history"] == ["map", "standings", "profile", "lobby"]
    for i in range(30):
        where.page = "map" if i % 2 else "profile"
        at.run()
    assert len(at.session_state["_nav_history"]) == 20


def test_app_opens_on_the_map_once_logged_in(monkeypatch):
    switch = Mock()
    monkeypatch.setattr(st, "switch_page", switch)
    monkeypatch.setattr("shared.require_login", lambda: "player")
    at = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run()
    assert not at.exception
    switch.assert_called_once_with("pages/5_Map.py")
