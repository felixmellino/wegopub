"""Exercise the menu, saved profile, security and stats through Streamlit."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from streamlit.testing.v1 import AppTest
from core.models import Player
from core.auth import hash_password
from core.profile import edit_profile, change_password

ROOT = Path(__file__).resolve().parents[1]


def click(at, label):
    [b for b in at.button if b.label == label][-1].click().run()
    assert not at.exception
    return at


@pytest.fixture
def repo(monkeypatch):
    monkeypatch.setattr('data.db.list_season_transfers', lambda _: [])
    # Profile fixtures have no lobby repository; restoration has its own tests.
    monkeypatch.setattr('shared.restore_selection', lambda player_id: None)
    monkeypatch.setattr('data.db.download_profile_picture', lambda *args: None)
    state = {'player': Player('self', 'Mia', 'Mia', 'Silva', hash_password('password8'), 'mia@example.test')}
    state['sharing'] = False
    monkeypatch.setattr('data.db.get_photo_sharing', lambda *args: state['sharing'])
    def save_sharing(pid, version, enabled):
        state['sharing'] = enabled
    monkeypatch.setattr('data.db.save_photo_sharing', save_sharing)
    monkeypatch.setattr('device_login._browser_storage', lambda **c: {'request_id': c['request_id'], 'token': '', 'available': True})
    monkeypatch.setattr('data.db.get_player', lambda _: state['player'])
    def save(pid, version, first, last, username):
        state['player'] = edit_profile(state['player'], first, last, username, [])
        return state['player']
    monkeypatch.setattr('data.db.update_profile', save)
    def password(pid, version, current, new, confirm):
        state['player'] = change_password(state['player'], current, new, confirm)
        return state['player']
    monkeypatch.setattr('data.db.update_password', password)
    return state


def page(repo):
    at = AppTest.from_file(ROOT / 'pages/1_Profile.py')
    at.session_state['player_id'] = repo['player'].id
    at.session_state['credential_version'] = repo['player'].pin_hash
    return at.run()


def test_menu_edit_and_saved_profile_in_new_session(repo):
    at = page(repo)
    assert not at.exception
    labels = [b.label for b in at.button]
    assert labels[-5:] == ['Edit profile', 'Friends', 'My stats', 'Account & security', 'Log out']
    assert not at.text_input
    click(at, 'Edit profile')
    for field, value in zip(at.text_input, ['NewMia', 'New', 'Name']):
        field.input(value)
    click(at, 'Save changes')
    assert at.success
    assert at.session_state['player_display_name'] == 'NewMia'
    click(at, 'Back to Profile')
    fresh = page(repo)
    click(fresh, 'Edit profile')
    assert [f.value for f in fresh.text_input] == ['NewMia', 'New', 'Name']
    assert repo['player'].id == 'self'


def test_invalid_edit_and_password_change(repo):
    at = page(repo)
    click(at, 'Edit profile')
    at.text_input[0].input(' ')
    click(at, 'Save changes')
    assert at.error and repo['player'].display_name == 'Mia'
    click(at, 'Back to Profile')
    click(at, 'Account & security')
    click(at, 'Change password')
    original = repo['player'].pin_hash
    for field, value in zip(at.text_input, ['wrong', 'newpass8', 'newpass8']):
        field.input(value)
    click(at, 'Change password')
    assert at.error and repo['player'].pin_hash == original
    for field, value in zip(at.text_input, ['password8', 'newpass8', 'newpass8']):
        field.input(value)
    click(at, 'Change password')
    assert 'player_id' not in at.session_state
    assert repo['player'].pin_hash != original
    assert any('Password changed' in s.value for s in at.success)


def stats_text(at):
    from html import unescape
    import re
    return ' '.join(unescape(re.sub('<[^>]+>', ' ', ''.join(m.value for m in at.markdown if '<section class="profile-stats"' in m.value))).split())


def test_stats_all_lobbies_without_selection_and_fresh_session(repo, monkeypatch):
    from tests.test_scoring_v1 import entry
    now = datetime.now(timezone.utc)
    memberships = [SimpleNamespace(id=f'm{i}', lobby_id=f'l{i}') for i in range(6)]
    monkeypatch.setattr('data.db.list_memberships_for_player', lambda _, **kwargs: memberships)
    def seasons(lid):
        end = now + timedelta(days=1) if lid == 'l5' else now - timedelta(days=1)
        return [SimpleNamespace(id=lid, ends_at=end)]
    monkeypatch.setattr('data.db.list_seasons_for_lobby', seasons)
    def entries(sid):
        i = int(sid[1:])
        return [replace(entry(sid, f'm{i}', 'beer', 'small', 0), season_id=sid, points_awarded=11)]
    monkeypatch.setattr('data.db.list_drink_entries', entries)
    at = page(repo)
    click(at, 'My stats')
    text = stats_text(at)
    assert 'Total points 66' in text and 'Drinks 6' in text
    assert 'Lobbies played 6' in text and 'Total Wins 5' in text
    at.session_state['current_lobby_id'] = 'l5'
    at.run()
    assert stats_text(at) == text
    fresh = page(repo)
    click(fresh, 'My stats')
    assert stats_text(fresh) == text


def test_stats_empty_and_load_failure(repo, monkeypatch):
    monkeypatch.setattr('data.db.list_memberships_for_player', lambda _, **kwargs: [])
    at = page(repo)
    click(at, 'My stats')
    assert 'Total points 0' in stats_text(at) and 'Total Wins 0' in stats_text(at)
    assert at.info
    monkeypatch.setattr('data.db.list_memberships_for_player', lambda _, **kwargs: [SimpleNamespace(id='me', lobby_id='lobby')])
    monkeypatch.setattr('data.db.list_seasons_for_lobby', lambda _: [])
    at.run()
    assert 'Total points 0' in stats_text(at)
    def unavailable(_):
        raise RuntimeError('offline')
    monkeypatch.setattr('data.db.list_seasons_for_lobby', unavailable)
    at.run()
    assert not at.exception and at.error and not stats_text(at)


def test_stats_reads_new_accepted_checkins_and_rejects_invalid_attempts(repo, monkeypatch):
    from core.checkins import CheckinRejected
    from core.scoring_v1 import create_scored_entry
    from tests.test_checkins import INSIDE, OUTSIDE, TERRITORY
    from tests.test_scoring_v1 import START, season

    game = replace(season(), ends_at=datetime.now(timezone.utc) + timedelta(days=1))
    saved = []
    monkeypatch.setattr('data.db.list_memberships_for_player',
                        lambda _, **kwargs: [SimpleNamespace(id='me', lobby_id=game.lobby_id)])
    monkeypatch.setattr('data.db.list_seasons_for_lobby', lambda _: [game])
    monkeypatch.setattr('data.db.list_drink_entries', lambda _: list(saved))
    at = page(repo)
    click(at, 'My stats')
    assert 'Total points 0' in stats_text(at) and 'Drinks 0' in stats_text(at)

    accepted = create_scored_entry('me', game, 'beer', 'large', 'photo', INSIDE, 10,
                                  START, [TERRITORY], [], entry_id='first')
    saved.append(accepted)
    at.run()
    assert 'Total points 3' in stats_text(at) and 'Drinks 1' in stats_text(at)
    assert 'Total Wins 0' in stats_text(at)

    for gps, when, reason in [(INSIDE, START, 'cooldown'),
                              (None, START + timedelta(minutes=2), 'location_unavailable')]:
        with pytest.raises(CheckinRejected, match=reason):
            create_scored_entry('me', game, 'beer', 'large', 'photo', gps, 10,
                                when, [TERRITORY], saved, entry_id='rejected')
    at.run()
    assert 'Total points 3' in stats_text(at) and 'Drinks 1' in stats_text(at)

    saved.append(create_scored_entry('me', game, 'beer', 'small', 'photo', OUTSIDE, 10,
                                    START + timedelta(minutes=2), [TERRITORY], saved,
                                    entry_id='second'))
    # Expired photos must not erase accepted scoring history.
    saved[0] = replace(saved[0], photo_ref=None)
    at.run()
    text = stats_text(at)
    assert 'Total points 4' in text and 'Drinks 2' in text and 'Lobbies played 1' in text
    fresh = page(repo)
    click(fresh, 'My stats')
    assert stats_text(fresh) == text


def test_save_failure_keeps_form_and_identity(repo, monkeypatch):
    def unavailable(*args):
        raise RuntimeError('offline')
    monkeypatch.setattr('data.db.update_profile', unavailable)
    at = page(repo)
    click(at, 'Edit profile')
    at.text_input[0].input('NewMia')
    click(at, 'Save changes')
    assert at.error
    assert at.text_input[0].value == 'NewMia'
    assert repo['player'].display_name == 'Mia'
    assert at.session_state['player_id'] == 'self'


def test_photo_sharing_toggle_saves_across_fresh_app_sessions(repo):
    at = page(repo)
    click(at, 'Account & security')
    click(at, 'Photo privacy')
    assert not at.toggle[0].value
    at.toggle[0].set_value(True)
    click(at, 'Save photo privacy')
    assert repo['sharing'] and at.success
    fresh = page(repo)
    click(fresh, 'Account & security')
    click(fresh, 'Photo privacy')
    assert fresh.toggle[0].value
    fresh.toggle[0].set_value(False)
    click(fresh, 'Save photo privacy')
    assert not repo['sharing']


def test_privacy_save_failure_shows_no_success_and_preserves_saved_value(repo, monkeypatch):
    def fail(*args):
        raise RuntimeError('offline')
    monkeypatch.setattr('data.db.save_photo_sharing', fail)
    at = page(repo)
    click(at, 'Account & security')
    click(at, 'Photo privacy')
    at.toggle[0].set_value(True)
    click(at, 'Save photo privacy')
    assert not at.exception and at.error and not at.success
    assert not repo['sharing']
    assert any(b.label == 'Change password' for b in at.button)


def test_stats_keep_departed_lobby_in_a_fresh_session(repo, monkeypatch):
    from tests.test_scoring_v1 import entry
    departed = SimpleNamespace(id='me', lobby_id='left', left_at=datetime.now(timezone.utc))
    def read(pid, *, include_left=False):
        assert include_left, 'Personal statistics must request historical memberships'
        return [departed]
    monkeypatch.setattr('data.db.list_memberships_for_player', read)
    monkeypatch.setattr('data.db.list_seasons_for_lobby', lambda _: [SimpleNamespace(id='season', ends_at=datetime.now(timezone.utc)+timedelta(days=1))])
    monkeypatch.setattr('data.db.list_drink_entries', lambda _: [entry('a', 'me', 'beer', 'large', 0)])
    at = page(repo)
    click(at, 'My stats')
    assert 'Total points 3' in stats_text(at) and 'Lobbies played 1' in stats_text(at)
    fresh = page(repo)
    click(fresh, 'My stats')
    assert stats_text(fresh) == stats_text(at)


def test_security_overview_and_close_discards_unsaved_changes(repo):
    at = page(repo)
    click(at, 'Account & security')
    assert not at.text_input and not at.toggle
    assert any('mia@example.test' in t.value for t in at.text)
    assert [b.label for b in at.button if str(b.key).startswith('open_security_')] == [
        'Photo privacy', 'Change password']

    click(at, 'Photo privacy')
    assert len(at.toggle) == 1 and not at.text_input
    at.toggle[0].set_value(True).run()
    click(at, 'Close')
    assert not at.toggle and not repo['sharing']
    assert '_security_dialog' not in at.session_state
    click(at, 'Photo privacy')
    assert not at.toggle[0].value
    click(at, 'Close')

    click(at, 'Change password')
    assert len(at.text_input) == 3 and not at.toggle
    at.text_input[0].input('do-not-retain').run()
    click(at, 'Close')
    assert not at.text_input
    click(at, 'Change password')
    assert all(f.value == '' for f in at.text_input)
    click(at, 'Close')
    click(at, 'Back to Profile')
    click(at, 'Account & security')
    assert not at.text_input and not at.toggle


def test_password_dialog_service_failure_keeps_account_signed_in(repo, monkeypatch):
    def unavailable(*args):
        raise RuntimeError('offline')
    monkeypatch.setattr('data.db.update_password', unavailable)
    at = page(repo)
    click(at, 'Account & security')
    click(at, 'Change password')
    original = repo['player'].pin_hash
    for field, value in zip(at.text_input, ['password8', 'newpass8', 'newpass8']):
        field.input(value)
    click(at, 'Change password')
    assert at.error and not at.success
    assert repo['player'].pin_hash == original
    assert at.session_state['player_id'] == 'self'
    assert at.session_state['_security_dialog'] == 'password'
    assert len(at.text_input) == 3
