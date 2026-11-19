"""Fresh Streamlit sessions share account preferences, never session context."""
from pathlib import Path
from unittest.mock import Mock, call

from streamlit.testing.v1 import AppTest
import pytest

import data.db as db
from shared import require_login as real_require_login
from tests.test_lobby_ui import ui, page, open_members, click

real_save_choice = db.save_lobby_choice
real_get_choice = db.get_lobby_choice

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def membership_service(ui, monkeypatch):
    # Match main's joined membership/season lookup using the same fake data.
    def context(player_id, membership_id, lobby_id, season_id):
        member = next((m for m in ui['members'] if m.player_id == player_id
                       and m.id == membership_id and m.lobby_id == lobby_id), None)
        game = next((s for s in ui['seasons'].get(lobby_id, []) if s.id == season_id), None)
        return (member, game) if member else (None, None)
    monkeypatch.setattr(db, 'membership_context', context)


def restored_page(player='me'):
    return AppTest.from_string(f'''
import streamlit as st
from lobby_selection import restore_selection
st.session_state['player_id'] = {player!r}
restore_selection({player!r})
from shared import require_active_membership
require_active_membership()
st.title('Ready: ' + st.session_state['current_lobby_name'])
''').run()


def test_explicit_choice_survives_fresh_sessions_and_other_player_is_separate(ui):
    at = open_members(page(), 'old')
    click(at, 'Close')
    fresh = restored_page()
    assert not fresh.exception
    assert fresh.title[0].value == 'Ready: Older lobby'
    assert fresh.session_state['current_membership_id'] == 'm-old'
    assert fresh.session_state['current_lobby_mode'] == 'individual'
    assert fresh.session_state['current_season_id'] == ui['seasons']['old'][0].id
    assert '_opened_lobby_id' not in fresh.session_state
    ui['choices']['someone-else'] = 'new'
    assert restored_page().session_state['current_lobby_id'] == 'old'
    ui['save_choice'].assert_called_once_with('me', 'old')


def test_finished_choice_falls_back_to_newest_active_without_overwriting(ui):
    ui['choices']['me'] = 'past'
    at = restored_page()
    assert not at.exception and at.session_state['current_lobby_id'] == 'new'
    assert ui['choices']['me'] == 'past'
    ui['save_choice'].assert_not_called()


def test_removed_membership_does_not_restore_or_choose_another_lobby(ui):
    ui['choices']['me'] = 'secret'
    at = restored_page()
    assert not at.exception
    assert 'current_lobby_id' not in at.session_state
    assert not at.title
    assert at.info
    assert at.session_state['_lobby_choice_required']


def test_no_active_alternative_requires_selection(ui):
    ui['choices']['me'] = 'past'
    ui['members'] = ui['members'][2:]
    at = restored_page()
    assert not at.exception and not at.title
    assert 'current_lobby_id' not in at.session_state


def test_no_saved_choice_selects_newest_active(ui):
    at = restored_page()
    assert not at.exception and at.session_state['current_lobby_id'] == 'new'


def test_setup_and_upcoming_saved_lobbies_remain_selected(ui):
    from datetime import datetime, timedelta, timezone
    ui['choices']['me'] = 'old'
    ui['seasons']['old'][0].starts_at = datetime.now(timezone.utc) + timedelta(hours=1)
    assert restored_page().session_state['current_lobby_id'] == 'old'
    ui['seasons']['old'] = []
    at = restored_page()
    assert not at.exception and at.session_state['current_lobby_id'] == 'old'
    assert at.session_state['current_season_id'] is None


def test_save_rejects_nonmember_before_writing(ui, monkeypatch):
    client = Mock()
    monkeypatch.setattr(db, 'get_client', lambda: client)
    with pytest.raises(PermissionError):
        real_save_choice('me', 'secret')
    client.table.assert_not_called()


def test_reopening_real_leaderboard_restores_context_during_login(ui, monkeypatch):
    from types import SimpleNamespace
    ui['choices']['me'] = 'old'
    monkeypatch.setattr('shared.require_login', real_require_login)
    monkeypatch.setattr('shared.sync_storage', lambda: '')
    monkeypatch.setattr('shared.ask_for_location', lambda: None)
    navigation = Mock()
    monkeypatch.setattr('shared.bottom_navigation', navigation)
    monkeypatch.setattr(db, 'get_player', lambda pid: SimpleNamespace(id=pid, email='me@example.com', pin_hash='credential'))
    invite_count = Mock(return_value=0)
    monkeypatch.setattr(db, 'pending_minigame_invite_count', invite_count)
    monkeypatch.setattr(db, 'list_players', lambda: [])
    monkeypatch.setattr('shared.get_territories', lambda: [])
    for _ in range(2):  # Discard the entire session, as on another device/restart.
        at = AppTest.from_file(ROOT / 'pages/4_Standings.py')
        at.session_state['player_id'] = 'me'
        at.session_state['credential_version'] = 'credential'
        at.run()
        assert not at.exception
        assert at.session_state['current_lobby_id'] == 'old'
        assert not any('Choose a lobby' in i.value for i in at.info)
        assert any('<h1 class="sr-only">Leaderboard</h1>' in m.value for m in at.markdown)
    assert navigation.call_count == 2  # Once per fresh page, including restoration.
    assert invite_count.call_args_list == [call('me', ui['seasons']['old'][0].id)] * 2


@pytest.mark.parametrize(
    'choice, joined, expected',
    [('past', ('past',), 'past'), ('secret', ('old', 'past'), 'old'),
     (None, (), None), ('past', ('old', 'past'), 'old')],
)
@pytest.mark.parametrize('predeployment_module', [False, True])
def test_leaderboard_first_has_a_board_or_empty_state(ui, monkeypatch, choice, joined, expected, predeployment_module):
    if predeployment_module:
        # Cloud may retain the module imported before the fallback was deployed.
        monkeypatch.delattr('lobby_selection.leaderboard_fallback', raising=False)
    ui['choices']['me'] = choice
    ui['members'] = [member for member in ui['members'] if member.lobby_id in joined]
    monkeypatch.setattr('shared.require_login', real_require_login)
    monkeypatch.setattr('shared.sync_storage', lambda: '')
    monkeypatch.setattr('shared.ask_for_location', lambda: None)
    monkeypatch.setattr('shared.bottom_navigation', lambda: None)
    monkeypatch.setattr(db, 'get_player', lambda pid: Mock(email='me@example.com', pin_hash='credential'))
    monkeypatch.setattr(db, 'list_players', lambda: [])
    monkeypatch.setattr('shared.get_territories', lambda: [])
    records = Mock(return_value=[])
    monkeypatch.setattr(db, 'list_drink_entries', records)

    at = AppTest.from_file(ROOT / 'pages/4_Standings.py')
    at.session_state['player_id'] = 'me'
    at.session_state['credential_version'] = 'credential'
    at.run()

    assert not at.exception
    ui['save_choice'].assert_not_called()
    if expected is None:
        records.assert_not_called()
        assert any('There are no standings' in item.value for item in at.info)
        assert any(button.label == 'Open Lobby' for button in at.button)
    else:
        records.assert_called_once_with(ui['seasons'][expected][0].id)
        assert any('No points logged yet' in item.value for item in at.info)
    assert any('Final standings' in item.value for item in at.caption) == (expected == 'past')
    if (choice, expected) != ('past', 'old'):
        assert 'current_lobby_id' not in at.session_state


def test_database_preference_is_scoped_to_player_and_survives_new_client(ui, monkeypatch):
    from types import SimpleNamespace
    rows = {}
    class Query:
        def __init__(self):
            self.pid = None
        def select(self, fields):
            assert fields == 'lobby_id'
            return self
        def eq(self, field, value):
            assert field == 'player_id'
            self.pid = value
            return self
        def upsert(self, payload, on_conflict):
            assert on_conflict == 'player_id'
            rows[payload['player_id']] = payload.copy()
            return self
        def execute(self):
            return SimpleNamespace(data=[rows[self.pid]] if self.pid in rows else [])
    class Client:
        def table(self, name):
            assert name == 'player_lobby_choices'
            return Query()
    monkeypatch.setattr(db, 'get_client', Client)
    assert real_get_choice('me') is None
    real_save_choice('me', 'old')
    assert real_get_choice('me') == 'old'
    assert real_get_choice('someone-else') is None
    real_save_choice('me', 'new')
    assert real_get_choice('me') == 'new'
    assert len(rows) == 1
