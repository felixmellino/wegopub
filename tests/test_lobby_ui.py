from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as Obj
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

import data.db as db
from core.friends import transition
from core.lobbies import create_season
from core.models import Lobby, LobbyMembership
from tests.test_scoring_v1 import entry

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ui(monkeypatch):
    monkeypatch.setattr(db, 'list_season_transfers', lambda _: [])
    now = datetime.now(timezone.utc)
    lobbies = [Lobby('old', 'Older lobby', 'OLDER'), Lobby('new', 'Newest lobby', 'NEWEST'),
               Lobby('past', 'Finished lobby', 'PAST'), Lobby('secret', 'Not joined', 'PRIVATE')]
    members = [LobbyMembership('m-' + l.id, 'me', l.id, now) for l in lobbies[:3]]
    seasons = {l.id: [create_season(l.id, '1_week', now - timedelta(days=offset))]
               for l, offset in zip(lobbies, [2, 1, 10, 0])}
    state = dict(lobbies=lobbies, members=members, seasons=seasons, entries=[], names={})
    state['choices'] = {}
    state['save_choice'] = Mock(side_effect=lambda pid, lid: state['choices'].__setitem__(pid, lid))
    monkeypatch.setattr(db, 'save_lobby_choice', state['save_choice'])
    monkeypatch.setattr(db, 'get_lobby_choice', lambda pid: state['choices'].get(pid))
    monkeypatch.setattr('shared.require_login', lambda: 'me')
    monkeypatch.setattr('shared.show_logged_in_as', lambda: None)
    monkeypatch.setattr(db, 'list_memberships_for_player', lambda _, **kwargs: state['members'])
    monkeypatch.setattr(db, 'list_lobbies', lambda: state['lobbies'])
    monkeypatch.setattr(db, 'list_seasons_for_lobby', lambda lid: state['seasons'].get(lid, []))
    monkeypatch.setattr(db, 'list_drink_entries', lambda _: state['entries'])
    monkeypatch.setattr(db, 'membership_display_name', lambda mid, lid: state['names'].get(mid, mid))
    state['lobby_members'] = {l.id: [m for m in members if m.lobby_id == l.id] + [Obj(id='leo', player_id='leo-id', joined_at=now + timedelta(seconds=5))] for l in lobbies}
    state['users'] = [{'id': 'me', 'display_name': 'MyUsername'}, {'id': 'leo-id', 'display_name': 'Leo'}]
    state['relationships'] = []
    monkeypatch.setattr(db, 'list_memberships_for_lobby', lambda lid, **kwargs: state['lobby_members'][lid])
    monkeypatch.setattr(db, 'list_public_usernames', lambda: state['users'])
    monkeypatch.setattr(db, 'list_friendships', lambda pid: [r.copy() for r in state['relationships'] if pid in (r['sender_id'], r['recipient_id'])])
    def change(actor, other, action):
        current = next((r for r in state['relationships'] if {r['sender_id'], r['recipient_id']} == {actor, other}), None)
        row = transition(actor, other, action, current, datetime.now(timezone.utc))
        if current:
            state['relationships'].remove(current)
        state['relationships'].append({**row, 'updated_at': datetime.now(timezone.utc).isoformat()})
    state['change'] = Mock(side_effect=change)
    monkeypatch.setattr(db, 'change_friendship', state['change'])
    state['picture'] = Mock(return_value=None)
    monkeypatch.setattr('lobby_ui.load_picture', state['picture'])
    return state


def page():
    return AppTest.from_file(ROOT / 'pages/2_Lobby.py', default_timeout=10).run()


def cards(at):
    return [item.value for item in at.markdown if '<article class="lobby-card' in item.value]


def click(at, label):
    return next(b for b in at.button if b.label == label).click().run()


def test_joined_lobbies_visible_newest_first_auto_selected_with_no_dropdown(ui):
    at = page()
    assert not at.exception
    shown = cards(at)
    assert 'Newest lobby' in shown[0] and 'Older lobby' in shown[1]
    assert 'lobby-past' in shown[2] and 'Finished lobby' in shown[2]
    assert 'Finished ' in shown[2] and ' left ' in shown[0]
    assert 'No Leader' in shown[2]
    assert all('Not joined' not in s and 'PRIVATE' not in s for s in shown)
    assert at.session_state['current_lobby_id'] == 'new'
    assert at.session_state['current_membership_id'] == 'm-new'
    assert at.session_state['current_season_id'] == ui['seasons']['new'][0].id
    assert not any(s.label in ('Your lobbies', 'View season') for s in at.selectbox)
    assert any(b.label == 'Create a lobby' for b in at.button)
    assert any(b.label == 'Join with a code' for b in at.button)
    assert not any(b.label == 'Start next scoring season' for b in at.button)
    assert len([b for b in at.button if b.label == 'View lobby →']) == 3


def test_leader_uses_existing_tie_rule_public_name_and_private_photo_fallback(ui):
    ui['entries'] = [entry('late', 'mia', 'shot', None, 1, territory=None),
                     entry('early', 'leo', 'shot', None, 0, territory=None)]
    ui['names'] = {'mia': 'Mia', 'leo': 'Leo'}
    at = page()
    assert not at.exception
    assert 'Leader: <strong>Leo</strong>' in cards(at)[0]
    assert 'Winner: <strong>Leo</strong>' in cards(at)[2]
    assert 'lobby-avatar' in cards(at)[0] and '>LE</span>' in cards(at)[0]
    assert 'data:image' not in cards(at)[0]
    assert ui['picture'].call_args.args == ('me', 'leo-id')
    ui['picture'].return_value = b'synthetic-picture'
    at.run()
    assert 'data:image/jpeg;base64,' in cards(at)[0]


def test_finish_refresh_moves_card_and_selects_next_running_lobby(ui):
    at = page()
    ui['seasons']['new'][0].ends_at = datetime.now(timezone.utc)
    at.run()
    assert not at.exception
    assert at.session_state['current_lobby_id'] == 'old'
    assert 'Newest lobby' in next(s for s in cards(at) if 'lobby-past' in s)
    ui['seasons']['old'][0].ends_at = datetime.now(timezone.utc)
    at.run()
    assert not at.exception
    assert 'current_lobby_id' not in at.session_state


def test_service_failure_is_not_displayed_as_no_leader(ui, monkeypatch):
    def fail(_):
        raise RuntimeError('offline')
    monkeypatch.setattr(db, 'list_drink_entries', fail)
    at = page()
    assert not at.exception
    assert all('Standings unavailable' in s and 'No Leader' not in s for s in cards(at))


def test_photo_failure_preserves_leader_and_escaped_text(ui):
    ui['entries'] = [entry('one', 'leo', 'shot', None, 0, territory=None)]
    payload = '<img src=x onerror="alert(1)">'
    ui['names']['leo'] = payload
    ui['lobbies'][1].name = payload
    ui['picture'].side_effect = RuntimeError('offline')
    at = page()
    assert not at.exception
    assert payload not in ''.join(cards(at)) and '&lt;img' in cards(at)[0]
    assert 'Standings unavailable' not in cards(at)[0]


def test_removed_membership_disappears_after_refresh(ui):
    at = page()
    ui['members'] = [m for m in ui['members'] if m.lobby_id != 'new']
    at.run()
    assert not at.exception
    assert all('Newest lobby' not in s for s in cards(at))
    assert at.session_state['current_lobby_id'] == 'old'


def test_join_invalid_code_keeps_lists_and_saves_nothing(ui, monkeypatch):
    save = Mock()
    monkeypatch.setattr(db, 'insert_membership', save)
    at = page()
    click(at, 'Join with a code')
    next(v for v in at.text_input if v.label == 'Invite code').input('badcode')
    click(at, 'Join lobby')
    assert not at.exception and any("doesn't match" in e.value for e in at.error)
    assert len(cards(at)) == 3
    save.assert_not_called()


def test_opening_a_card_shows_members_then_navigates_to_standings(ui, monkeypatch):
    nav = Mock()
    monkeypatch.setattr('lobby_ui.st.switch_page', nav)
    at = page()
    next(b for b in at.button if b.key == 'open_lobby_old').click().run()
    assert not at.exception
    assert at.session_state['current_lobby_id'] == 'old'
    nav.assert_not_called()
    assert {t.value for t in at.text} == {'MyUsername', 'Leo'}
    assert len([b for b in at.button if b.label == 'Add friend']) == 1
    assert len(cards(at)) == 3
    assert any(b.label == 'Create a lobby' for b in at.button)
    assert any(c.value == 'OLDER' for c in at.code)
    assert not any(h.value == 'Top 3 players' for h in at.subheader)
    click(at, 'View leaderboard')
    nav.assert_called_once_with('pages/4_Standings.py')


def test_past_only_and_incomplete_setup_have_no_invented_active_lobby(ui):
    ui['members'] = ui['members'][2:]
    at = page()
    assert not at.exception and len(cards(at)) == 1
    assert 'current_lobby_id' not in at.session_state
    ui['seasons']['past'] = []
    at.run()
    assert not at.exception and 'Setup incomplete' in cards(at)[0]
    open_members(at, 'past')
    assert any(b.label == 'Start lobby' for b in at.button)


def test_last_membership_removed_clears_selection(ui):
    at = page()
    ui['members'] = []
    at.run()
    assert not at.exception and not cards(at)
    assert 'current_lobby_id' not in at.session_state


def test_joining_valid_code_updates_the_visible_list_once(ui, monkeypatch):
    def insert(m):
        ui['members'].append(m)
        ui['lobby_members'][m.lobby_id].append(m)
    save = Mock(side_effect=insert)
    monkeypatch.setattr(db, 'insert_membership', save)
    at = page()
    click(at, 'Join with a code')
    next(v for v in at.text_input if v.label == 'Invite code').input('private')
    click(at, 'Join lobby')
    assert not at.exception
    assert any('Not joined' in s for s in cards(at))
    assert at.session_state['current_lobby_id'] == 'secret'
    assert save.call_count == 1
    assert any('Joined Not joined' in n.value for n in at.success)
    click(at, 'Close')
    click(at, 'Join with a code')
    next(v for v in at.text_input if v.label == 'Invite code').input('private')
    click(at, 'Join lobby')
    assert not at.exception and save.call_count == 1


def test_invite_codes_visible_and_escaped(ui):
    ui['lobbies'][0].invite_code = '<script>bad</script>'
    at = page()
    assert not at.exception
    assert 'Invite code: <strong>NEWEST</strong>' in cards(at)[0]
    assert 'Invite code: <strong>PAST</strong>' in cards(at)[2]
    assert '&lt;script&gt;bad&lt;/script&gt;' in cards(at)[1]


def open_members(at, lid='new'):
    return next(b for b in at.button if b.key == f'open_lobby_{lid}').click().run()


def test_request_sent_persists_across_fresh_pages_and_recipient_can_accept(ui, monkeypatch):
    at = open_members(page())
    click(at, 'Add friend')
    assert not at.exception
    ui['change'].assert_called_once_with('me', 'leo-id', 'request')
    fresh = open_members(page())
    assert any(c.value == 'Request sent' for c in fresh.caption)
    assert not any(b.label in ('Add friend', 'Accept', 'Decline') for b in fresh.button)
    monkeypatch.setattr('shared.require_login', lambda: 'leo-id')
    ui['members'] = [LobbyMembership('leo', 'leo-id', 'new', datetime.now(timezone.utc))]
    recipient = open_members(page())
    assert any(c.value == 'Incoming friend request' for c in recipient.caption)
    click(recipient, 'Accept')
    assert not recipient.exception
    assert any(c.value == 'Friends' for c in recipient.caption)
    assert not any(b.label in ('Add friend', 'Accept', 'Decline') for b in recipient.button)


def test_decline_and_cooldown_leave_request_unchanged(ui):
    ui['relationships'] = [{'sender_id': 'leo-id', 'recipient_id': 'me', 'status': 'pending'}]
    at = open_members(page())
    click(at, 'Decline')
    assert not at.exception
    assert ui['relationships'][0]['status'] == 'declined'
    click(at, 'Add friend')
    assert not at.exception
    assert any('10 minutes' in e.value for e in at.error)
    assert ui['relationships'][0]['status'] == 'declined'


def test_members_service_failure_and_friend_service_failure(ui, monkeypatch):
    def fail(*args):
        raise RuntimeError('offline')
    monkeypatch.setattr(db, 'list_friendships', fail)
    at = open_members(page())
    assert not at.exception
    assert {t.value for t in at.text} == {'MyUsername', 'Leo'}
    assert at.warning and not any(b.label == 'Add friend' for b in at.button)
    monkeypatch.setattr(db, 'list_public_usernames', fail)
    at.run()
    assert not at.exception
    assert any('members could not be loaded' in e.value for e in at.error)


def test_removed_membership_hides_open_members_and_actions(ui):
    at = open_members(page())
    ui['members'] = [m for m in ui['members'] if m.lobby_id != 'new']
    at.run()
    assert not at.exception
    assert not at.text and '_opened_lobby_id' not in at.session_state
    assert not any(b.label == 'Add friend' for b in at.button)


def test_stale_membership_fails_closed(ui):
    ui['lobby_members']['new'] = [Obj(id='leo', player_id='leo-id', joined_at=datetime.now(timezone.utc))]
    at = open_members(page())
    assert not at.exception and any('no longer a member' in e.value for e in at.error)
    assert not at.text and not any(b.label == 'Add friend' for b in at.button)


def test_other_lobby_members_and_unrelated_relationships_are_private(ui):
    ui['users'].append({'id': 'outsider', 'display_name': 'OutsideUsername'})
    ui['relationships'] = [{'sender_id': 'outsider', 'recipient_id': 'leo-id', 'status': 'accepted'}]
    at = open_members(page())
    assert not at.exception
    assert 'OutsideUsername' not in {t.value for t in at.text}
    assert not any(c.value == 'Friends' for c in at.caption)
    assert any(b.label == 'Add friend' for b in at.button)


def test_concurrent_request_error_is_visible_without_crashing(ui):
    from postgrest.exceptions import APIError
    ui['change'].side_effect = APIError({'code': '40001', 'message': 'changed', 'details': None, 'hint': None})
    at = open_members(page())
    click(at, 'Add friend')
    assert not at.exception
    assert any('Refresh lobbies' in e.value for e in at.error)
    assert not ui['relationships']


def test_switching_open_lobbies_shows_only_one_member_list(ui):
    at = open_members(page(), 'old')
    assert at.session_state['current_lobby_id'] == 'old'
    at.run()
    assert at.session_state['current_lobby_id'] == 'old'
    click(at, 'Close')
    open_members(at, 'new')
    assert not at.exception
    assert at.session_state['current_lobby_id'] == 'new'
    assert len([h for h in at.subheader if h.value == 'Lobby members']) == 1
    click(at, 'Close')
    assert not at.exception
    assert not at.text


def test_overview_forms_are_hidden_until_opened_and_cancel_saves_nothing(ui, monkeypatch):
    save_lobby, save_member = Mock(), Mock()
    monkeypatch.setattr(db, 'insert_lobby', save_lobby)
    monkeypatch.setattr(db, 'insert_membership', save_member)
    at = page()
    assert not at.text_input and not at.radio and not at.tabs
    click(at, 'Create a lobby')
    assert not at.exception
    assert any(v.label == 'Lobby name' for v in at.text_input)
    assert not any(v.label == 'Invite code' for v in at.text_input)
    click(at, 'Cancel')
    assert not at.exception and not at.text_input
    click(at, 'Join with a code')
    assert any(v.label == 'Invite code' for v in at.text_input)
    click(at, 'Cancel')
    assert not at.exception and not at.text_input
    save_lobby.assert_not_called()
    save_member.assert_not_called()


def test_create_empty_name_keeps_dialog_open_and_writes_nothing(ui, monkeypatch):
    save = Mock()
    monkeypatch.setattr(db, 'insert_lobby', save)
    at = page()
    click(at, 'Create a lobby')
    [b for b in at.button if b.label == 'Create lobby'][-1].click().run()
    assert not at.exception and any('name is required' in e.value for e in at.error)
    assert any(v.label == 'Lobby name' for v in at.text_input)
    save.assert_not_called()


def test_create_success_opens_details_and_keeps_duration_timezone_and_test_mode(ui, monkeypatch):
    monkeypatch.setattr(db, 'insert_lobby', ui['lobbies'].append)
    def save_member(m):
        ui['members'].append(m)
        ui['lobby_members'][m.lobby_id] = [m]
    monkeypatch.setattr(db, 'insert_membership', save_member)
    def start(pid, lid, length, zone, **options):
        game = create_season(lid, length, datetime.now(timezone.utc), zone, **options)
        ui['seasons'][lid] = [game]
        return game
    start_mock = Mock(side_effect=start)
    monkeypatch.setattr(db, 'start_scoring_season', start_mock)
    at = page()
    click(at, 'Create a lobby')
    next(v for v in at.text_input if v.label == 'Lobby name').input('My new lobby')
    next(r for r in at.radio if r.label == 'Lobby duration').set_value('3_months')
    at.selectbox[0].set_value('America/New_York')
    at.checkbox[0].check()
    [b for b in at.button if b.label == 'Create lobby'][-1].click().run()
    assert not at.exception
    created = ui['lobbies'][-1]
    start_mock.assert_called_once_with('me', created.id, '3_months', 'America/New_York', test_mode=True)
    assert at.session_state['_opened_lobby_id'] == created.id
    assert len(cards(at)) == 4 and any('My new lobby' in card for card in cards(at))
    assert any('Lobby created!' in e.value for e in at.success)
    assert not at.text_input and any(b.label == 'Close' for b in at.button)


def test_member_popup_keeps_overview_and_has_no_ranking_preview(ui):
    ui['entries'] = [entry('1', 'leo', 'shot', None, 0, territory=None)]
    ui['names'] = {'leo': 'Leo'}
    at = open_members(page())
    assert not at.exception
    assert len(cards(at)) == 3
    assert {t.value for t in at.text} == {'MyUsername', 'Leo'}
    assert not any(h.value == 'Top 3 players' for h in at.subheader)
    assert not any(t.value.endswith(' pts') for t in at.text)
    assert any(c.value == 'NEWEST' for c in at.code)
    assert any(b.label == 'View leaderboard' for b in at.button)


def test_member_popup_works_when_standings_are_unavailable(ui, monkeypatch):
    def fail(_):
        raise RuntimeError('offline')
    monkeypatch.setattr(db, 'list_drink_entries', fail)
    at = open_members(page())
    assert not at.exception
    assert any(b.label == 'Add friend' for b in at.button)
    assert {t.value for t in at.text} == {'MyUsername', 'Leo'}


def test_join_service_failure_stays_in_dialog(ui, monkeypatch):
    at = page()
    click(at, 'Join with a code')
    def fail():
        raise RuntimeError('offline')
    monkeypatch.setattr(db, 'list_lobbies', fail)
    click(at, 'Join lobby')
    assert not at.exception and any('Could not load lobbies' in e.value for e in at.error)
    assert any(v.label == 'Invite code' for v in at.text_input)


def test_close_member_popup_stays_closed_on_refresh(ui):
    at = open_members(page())
    click(at, 'Close')
    at.run()
    assert not at.exception and not at.text
    assert '_opened_lobby_id' not in at.session_state
    assert len(cards(at)) == 3


def test_switching_from_members_to_create_opens_only_one_dialog(ui):
    at = open_members(page())
    click(at, 'Create a lobby')
    assert not at.exception
    assert '_opened_lobby_id' not in at.session_state
    assert any(v.label == 'Lobby name' for v in at.text_input)
    assert not any(b.label == 'Close' for b in at.button)


def test_top_actions_open_separate_dialogs_and_hide_forms_until_clicked(ui):
    at = page()
    assert not at.exception and not at.tabs and not at.text_input
    assert [button.key for button in at.button[:2]] == ['open_create_lobby', 'open_join_lobby']
    at.button(key='open_create_lobby').click().run()
    assert not at.exception
    assert any(field.label == 'Lobby name' for field in at.text_input)
    assert not any(field.label == 'Invite code' for field in at.text_input)
    click(at, 'Cancel')
    at.button(key='open_join_lobby').click().run()
    assert not at.exception
    assert any(field.label == 'Invite code' for field in at.text_input)
    assert not any(field.label == 'Lobby name' for field in at.text_input)


def test_shared_create_dialog_opens_saved_team_lobby(ui, monkeypatch):
    from core.models import Team
    teams = {}
    def insert_lobby(lobby):
        ui['lobbies'].append(lobby)
        teams[lobby.id] = [Team(f'{lobby.id}-{i}', lobby.id, i, f'Team {i}') for i in range(1, lobby.team_count + 1)]
    monkeypatch.setattr(db, 'insert_lobby', insert_lobby)
    def save_member(member):
        ui['members'].append(member)
        ui['lobby_members'][member.lobby_id] = [member]
    monkeypatch.setattr(db, 'insert_membership', save_member)
    def start(pid, lid, length, zone, **options):
        game = create_season(lid, length, datetime.now(timezone.utc), zone, **options)
        ui['seasons'][lid] = [game]
        return game
    monkeypatch.setattr(db, 'start_scoring_season', start)
    monkeypatch.setattr(db, 'list_lobby_teams', lambda actor, lid: teams[lid])
    at = page()
    at.button(key='open_create_lobby').click().run()
    next(r for r in at.radio if r.label == 'Competition mode').set_value('team').run()
    next(t for t in at.text_input if t.label == 'Lobby name').input('Shared team dialog')
    next(b for b in at.button if b.label == 'Create lobby').click().run()
    assert not at.exception
    created = ui['lobbies'][-1]
    assert created.game_mode == 'team' and created.team_count == 2
    assert at.session_state['_opened_lobby_id'] == created.id
    assert at.session_state['current_lobby_mode'] == 'team'
    assert any('Lobby created!' in s.value for s in at.success)
    assert any('Join a team below' in i.value for i in at.info)
    assert len([b for b in at.button if (b.key or '').startswith('join_team_')]) == 2
    assert not any(h.value == 'Lobby members' for h in at.subheader)


def test_close_and_refresh_keep_explicit_choice_without_resaving(ui):
    at = open_members(page(), 'old')
    click(at, 'Close')
    at.run()
    assert not at.exception
    assert at.session_state['current_lobby_id'] == 'old'
    assert '_opened_lobby_id' not in at.session_state
    assert ui['choices'] == {'me': 'old'}
    ui['save_choice'].assert_called_once_with('me', 'old')


def test_failed_preference_save_keeps_selection_and_can_retry(ui):
    ui['save_choice'].side_effect = RuntimeError('offline')
    at = open_members(page(), 'old')
    assert not at.exception and at.session_state['current_lobby_id'] == 'old'
    assert any('could not be saved' in w.value for w in at.warning)
    ui['save_choice'].side_effect = lambda pid, lid: ui['choices'].__setitem__(pid, lid)
    at.run()
    assert not at.exception and ui['choices']['me'] == 'old'


def test_rechoosing_same_lobby_overrides_another_devices_choice(ui):
    at = open_members(page(), 'old')
    click(at, 'Close')
    ui['choices']['me'] = 'new'  # Another device selected a different lobby.
    open_members(at, 'old')
    assert not at.exception and ui['choices']['me'] == 'old'
    assert ui['save_choice'].call_count == 2


def test_leave_confirmation_cancellation_and_retained_scores(ui, monkeypatch):
    saved = entry('earned', 'm-new', 'beer', 'large', 0)
    ui['entries'] = [saved]
    leave = Mock()
    def depart(pid, lid):
        assert (pid, lid) == ('me', 'new')
        ui['members'] = [m for m in ui['members'] if m.lobby_id != lid]
        ui['lobby_members'][lid] = [m for m in ui['lobby_members'][lid] if m.player_id != pid]
    leave.side_effect = depart
    monkeypatch.setattr(db, 'leave_lobby', leave)
    at = page()
    at.button(key='open_lobby_new').click().run()
    click(at, 'Leave lobby')
    assert any('earned points' in w.value for w in at.warning)
    leave.assert_not_called()
    click(at, 'Stay in lobby')
    leave.assert_not_called()
    assert not any(b.label == 'Confirm leave' for b in at.button)
    click(at, 'Leave lobby')
    click(at, 'Confirm leave')
    assert not at.exception
    leave.assert_called_once_with('me', 'new')
    assert all('Newest lobby' not in s for s in cards(at))
    assert at.session_state['current_lobby_id'] == 'old'
    assert ui['entries'] == [saved]
    assert any('earned points are kept' in s.value for s in at.success)


@pytest.mark.parametrize('error', [ValueError('Finish your active duel first.'), RuntimeError('offline'), PermissionError('Access denied.')])
def test_leave_failure_keeps_lobby_and_selection(ui, monkeypatch, error):
    leave = Mock(side_effect=error)
    monkeypatch.setattr(db, 'leave_lobby', leave)
    at = page()
    at.button(key='open_lobby_new').click().run()
    click(at, 'Leave lobby')
    click(at, 'Confirm leave')
    assert not at.exception and at.error
    assert at.session_state['current_lobby_id'] == 'new'
    assert len(ui['members']) == 3


def test_rejoin_restores_existing_membership_without_insert(ui, monkeypatch):
    member = ui['members'][1]
    member.left_at = datetime.now(timezone.utc)
    def memberships(pid, *, include_left=False):
        return ui['members'] if include_left else [m for m in ui['members'] if m.left_at is None]
    monkeypatch.setattr(db, 'list_memberships_for_player', memberships)
    rejoin = Mock(side_effect=lambda *_: setattr(member, 'left_at', None))
    insert = Mock()
    monkeypatch.setattr(db, 'rejoin_lobby', rejoin)
    monkeypatch.setattr(db, 'insert_membership', insert)
    at = page()
    click(at, 'Join with a code')
    at.text_input[0].input('NEWEST')
    click(at, 'Join lobby')
    assert not at.exception
    rejoin.assert_called_once_with('me', 'new')
    insert.assert_not_called()
    assert at.session_state['current_membership_id'] == member.id


def test_creator_can_delete_a_lobby_after_a_second_click(ui, monkeypatch):
    delete = Mock()
    def remove(pid, lid):
        assert (pid, lid) == ('me', 'new')
        ui['lobbies'] = [l for l in ui['lobbies'] if l.id != lid]
        ui['members'] = [m for m in ui['members'] if m.lobby_id != lid]
    delete.side_effect = remove
    monkeypatch.setattr(db, 'delete_lobby', delete)
    at = page()
    at.button(key='open_lobby_new').click().run()
    click(at, 'Delete lobby')
    assert any('deletes the lobby for everyone' in w.value for w in at.warning)
    delete.assert_not_called()
    click(at, 'Keep lobby')
    delete.assert_not_called()
    click(at, 'Delete lobby')
    click(at, 'Yes, delete lobby')
    assert not at.exception
    delete.assert_called_once_with('me', 'new')
    assert all('Newest lobby' not in s for s in cards(at))
    assert any('was deleted' in s.value for s in at.success)


def test_only_the_creator_sees_delete(ui):
    ui['lobby_members']['new'] = [Obj(id='leo', player_id='leo-id', joined_at=datetime(2020, 1, 1, tzinfo=timezone.utc)),
                                  *ui['lobby_members']['new'][:1]]
    at = page()
    at.button(key='open_lobby_new').click().run()
    assert not at.exception
    assert any(b.label == 'Leave lobby' for b in at.button)
    assert not any(b.label == 'Delete lobby' for b in at.button)


@pytest.mark.parametrize('error', [PermissionError('Only the person who created this lobby can delete it.'), RuntimeError('offline')])
def test_delete_failure_keeps_the_lobby(ui, monkeypatch, error):
    monkeypatch.setattr(db, 'delete_lobby', Mock(side_effect=error))
    at = page()
    at.button(key='open_lobby_new').click().run()
    click(at, 'Delete lobby')
    click(at, 'Yes, delete lobby')
    assert not at.exception and at.error
    assert at.session_state['current_lobby_id'] == 'new'
    assert len(ui['members']) == 3


def test_every_lobby_card_has_a_trash_button(ui):
    at = page()
    assert not at.exception
    for lobby_id in ('old', 'new', 'past'):
        assert at.button(key=f'remove_{lobby_id}').label == 'Remove from my lobbies'
    assert not any(b.key == 'remove_secret' for b in at.button)       # not joined: no card


def test_trash_removes_the_lobby_for_me_after_a_second_click(ui, monkeypatch):
    leave = Mock()
    def depart(pid, lid):
        assert (pid, lid) == ('me', 'new')
        ui['members'] = [m for m in ui['members'] if m.lobby_id != lid]
    leave.side_effect = depart
    monkeypatch.setattr(db, 'leave_lobby', leave)
    at = page()
    at.button(key='remove_new').click().run()
    assert any('Remove Newest lobby from your lobbies' in w.value for w in at.warning)
    leave.assert_not_called()
    at.button(key='confirm_remove_no_new').click().run()
    leave.assert_not_called()
    assert not any(b.key == 'confirm_remove_yes_new' for b in at.button)
    at.button(key='remove_new').click().run()
    at.button(key='confirm_remove_yes_new').click().run()
    assert not at.exception
    leave.assert_called_once_with('me', 'new')
    assert all('Newest lobby' not in s for s in cards(at))
    assert any('earned points are kept' in s.value for s in at.success)


def test_trash_failure_keeps_the_lobby(ui, monkeypatch):
    monkeypatch.setattr(db, 'leave_lobby', Mock(side_effect=ValueError('Finish your active duel first.')))
    at = page()
    at.button(key='remove_new').click().run()
    at.button(key='confirm_remove_yes_new').click().run()
    assert not at.exception and any('active duel' in e.value for e in at.error)
    assert len(ui['members']) == 3
