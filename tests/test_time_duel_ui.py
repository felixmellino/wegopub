"""Player-facing failures keep saved rounds intact and offer useful messages."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from streamlit.testing.v1 import AppTest
import data.db as db
import time_duel_ui as ui


@pytest.fixture
def service(monkeypatch):
    state=dict(duels=[],outgoing=True,incoming=True,test_mode=True,open=True,boost_ends_at=None)
    monkeypatch.setattr(db,'time_status',lambda *args:deepcopy(state))
    action=Mock()
    monkeypatch.setattr(db,'time_action',action)
    board=Mock(return_value=None)
    monkeypatch.setattr(ui,'time_board',board)
    return state,action,board


def page():
    return AppTest.from_string('''
import streamlit as st
from time_duel_ui import render_time
from core.models import Lobby,LobbyMembership
from tests.test_scoring_v1 import START,season
@st.fragment
def app():
    render_time('pa','a',Lobby('lobby','Local','TEST'),season(),
        [LobbyMembership('a','pa','lobby',START),LobbyMembership('b','pb','lobby',START)],
        {'a':'Alice','b':'Bob'})
app()
''').run()


def test_invite_retry_reuses_request_id_and_keeps_form(service,monkeypatch):
    calls=[]
    def invite(*args):
        calls.append(args)
        raise RuntimeError('Connection interrupted; retry this invitation.')
    monkeypatch.setattr(db,'invite_time_duel',invite)
    app=page()
    for _ in range(2):
        next(b for b in app.button if b.label=='Send Time Duel challenge').click().run()
        assert not app.exception and 'retry' in app.error[0].value
    assert len(calls)==2 and calls[0][2]==calls[1][2]


def test_rejected_stop_keeps_board_and_shows_error_inside_stage(service):
    state,action,board=service
    state['duels']=[dict(id='duel',status='playing',round_no=0)]
    board.return_value=dict(duel_id='duel',event_id='event',action='stop',round_no=0,elapsed_ms=8000)
    action.side_effect=ValueError('The timing result could not be accepted.')
    app=page()
    assert not app.exception and len(app.error)==1
    stage=next(c for c in app.get('flex_container') if c.proto.id.endswith('time_stage'))
    assert stage.error[0].value=='The timing result could not be accepted.'
    action.assert_called_once_with('pa','duel','stop',0,8000)


def test_stale_round_never_calls_rpc(service):
    state,action,board=service
    state['duels']=[dict(id='duel',status='playing',round_no=1)]
    board.return_value=dict(duel_id='duel',event_id='event',action='stop',round_no=0,elapsed_ms=8000)
    assert not page().exception
    action.assert_not_called()


def test_missing_migration_has_actionable_message_and_back_button(service,monkeypatch):
    def missing(*args):raise RuntimeError('Time Duel needs database migration 017 before it can open.')
    monkeypatch.setattr(db,'time_status',missing)
    app=page()
    assert not app.exception and '017' in app.error[0].value
    assert any(b.label=='All games' for b in app.button)


def invitation(id='invite', challenger='a', opponent='b', status='invited'):
    return dict(id=id, challenger_id=challenger, opponent_id=opponent, status=status,
                expires_at='2026-11-19T20:10:00+00:00', server_now='2026-11-19T20:00:00+00:00')


def click(app, label):
    return next(b for b in app.button if b.label == label).click().run()


def test_pending_box_disables_send_and_survives_new_session(service, monkeypatch):
    state, action, _ = service
    state['duels'] = [invitation()]
    send = Mock()
    monkeypatch.setattr(db, 'invite_time_duel', send)
    for app in (page(), page()):
        assert not app.exception
        assert any('Pending Challenge invite' in m.value for m in app.markdown)
        assert any('Expires in 10:00' in c.value for c in app.caption)
        assert next(b for b in app.button if b.label == 'Send Time Duel challenge').disabled
    send.assert_not_called()
    action.side_effect = lambda *args: state.update(duels=[]) or dict(status='cancelled')
    app = click(app, 'Cancel invitation')
    assert not app.exception
    action.assert_called_once_with('pa', 'invite', 'cancel')
    assert not next(b for b in app.button if b.label == 'Send Time Duel challenge').disabled


def test_multiple_incoming_requires_confirmation_and_can_back_out(service):
    state, action, _ = service
    state['duels'] = [invitation('one', 'b', 'a'), invitation('two', 'c', 'a')]
    app = page()
    app = click(app, 'Accept Time Duel')
    action.assert_not_called()
    assert 'other invites for this minigame will be declined' in app.warning[0].value
    app = click(app, 'Keep invitations')
    action.assert_not_called()
    assert not app.warning
    app = click(app, 'Accept Time Duel')
    action.side_effect = lambda *args: state.update(duels=[]) or dict(status='accepted')
    app = click(app, 'Confirm acceptance')
    assert not app.exception
    action.assert_called_once_with('pa', 'one', 'accept')
    assert app.session_state['minigame_selected'] == 'time'


def test_decline_clears_invitation(service):
    state, action, _ = service
    state['duels'] = [invitation('one', 'b', 'a')]
    action.side_effect = lambda *args: state.update(duels=[]) or dict(status='declined')
    app = click(page(), 'Decline')
    assert not app.exception and not any(b.label == 'Accept Time Duel' for b in app.button)
    action.assert_called_once_with('pa', 'one', 'decline')


def test_expired_invite_disappears_on_refresh(service):
    state, action, _ = service
    state['duels'] = [invitation()]
    app = page()
    state['duels'][0]['status'] = 'expired'
    app.run()
    assert not app.exception
    assert not any('Pending Challenge invite' in m.value for m in app.markdown)
    assert not next(b for b in app.button if b.label == 'Send Time Duel challenge').disabled
    action.assert_not_called()
