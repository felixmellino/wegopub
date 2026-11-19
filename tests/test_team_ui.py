from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as Obj
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

import data.db as db
from core.lobbies import create_season
from core.models import Lobby, LobbyMembership, Team
from tests.test_teams import drink

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ui(monkeypatch):
    monkeypatch.setattr(db, 'list_season_transfers', lambda _: [])
    now = datetime.now(timezone.utc)
    lobby = Lobby('lobby','Team lobby','CODE','team',2,2,'manual')
    me = LobbyMembership('m1','me','lobby',now)
    members = [me,LobbyMembership('m2','other','lobby',now,team_id='t1')]
    teams = [Team('t1','lobby',1,'Team 1'),Team('t2','lobby',2,'Team 2')]
    season = create_season('lobby','1_week',now-timedelta(days=1))
    state = dict(lobby=lobby,me=me,members=members,teams=teams,season=season,entries=[])
    monkeypatch.setattr('shared.require_login',lambda:'me')
    monkeypatch.setattr('shared.show_logged_in_as',lambda:None)
    monkeypatch.setattr(db,'list_memberships_for_player',lambda _, **kwargs: [me])
    monkeypatch.setattr(db,'list_lobbies',lambda:[lobby])
    monkeypatch.setattr(db,'list_seasons_for_lobby',lambda _: [state['season']] if state['season'] else [])
    monkeypatch.setattr(db,'list_memberships_for_lobby',lambda _, **kwargs:members)
    monkeypatch.setattr(db,'list_lobby_teams',lambda *_:teams)
    monkeypatch.setattr(db,'list_public_usernames',lambda:[{'id':'me','display_name':'Myself'},{'id':'other','display_name':'Someone'}])
    monkeypatch.setattr(db,'list_drink_entries',lambda _:state['entries'])
    monkeypatch.setattr('team_ui.load_picture',lambda *_:None)
    return state


def page():
    return AppTest.from_file(ROOT/'pages/2_Lobby.py',default_timeout=10).run()


def open_lobby(at):
    return next(b for b in at.button if b.key=='open_lobby_lobby').click().run()


def test_creation_dialog_reacts_to_mode_and_saves_team_configuration(ui,monkeypatch):
    saved=[]
    monkeypatch.setattr(db,'insert_lobby',saved.append)
    monkeypatch.setattr(db,'insert_membership',lambda _:None)
    monkeypatch.setattr(db,'start_scoring_season',lambda *_:ui['season'])
    at=page()
    at.button(key='open_create_lobby').click().run()
    next(r for r in at.radio if r.label=='Competition mode').set_value('team').run()
    next(n for n in at.number_input if n.label=='Number of teams').set_value(4)
    next(n for n in at.number_input if n.label=='Players per team').set_value(3)
    next(r for r in at.radio if r.label=='Team assignment').set_value('random').run()
    next(t for t in at.text_input if t.label=='Lobby name').input('New teams')
    next(b for b in at.button if b.label=='Create lobby' and b.key!='open_create_lobby').click().run()
    assert not at.exception
    assert saved[0].game_mode=='team' and saved[0].team_count==4 and saved[0].team_capacity==3
    assert saved[0].team_assignment=='random'


def test_manual_cards_join_and_only_own_team_editable(ui,monkeypatch):
    def join(actor,lid,tid):
        ui['me'].team_id=tid
    save=Mock(side_effect=join)
    monkeypatch.setattr(db,'choose_lobby_team',save)
    at=open_lobby(page())
    assert not at.exception
    assert any('Join a team below' in i.value for i in at.info)
    assert any(t.value=='Team 1' for t in at.text)
    assert not any(t.label=="Team name" for t in at.text_input)
    at.button(key='join_team_t1').click().run()
    assert not at.exception
    save.assert_called_once_with('me','lobby','t1')
    assert any(t.label=='Team name' for t in at.text_input)
    assert len([t for t in at.text_input if t.label=='Team name'])==1
    assert any(c.label=='Take team picture' for c in at.get('camera_input'))
    edit=Mock()
    monkeypatch.setattr(db,'edit_lobby_team',edit)
    next(t for t in at.text_input if t.label=='Team name').input('Winners')
    next(b for b in at.button if b.label=='Save team').click().run()
    assert not at.exception
    edit.assert_called_once_with('me','t1','Winners',None,remove_photo=False)


def test_full_team_and_scoring_lock_disable_join(ui):
    ui['members'].append(LobbyMembership('m3','third','lobby',datetime.now(timezone.utc),'t1'))
    at=open_lobby(page())
    assert at.button(key='join_team_t1').disabled
    ui['me'].team_id='t2'
    ui['entries']=[replace(drink('d','m1','t2',4,1),season_id=ui['season'].id)]
    at.run()
    assert not at.exception and at.button(key='join_team_t1').disabled


def test_random_assignment_has_no_manual_join_buttons(ui):
    ui['lobby'].team_assignment='random'
    ui['me'].team_id='t2'
    at=open_lobby(page())
    assert not at.exception
    assert not any((b.key or '').startswith('join_team_') for b in at.button)


def test_team_standings_use_team_identity(ui,monkeypatch):
    ui['me'].team_id='t1'
    ui['entries']=[drink('d1','m1','t1',5,1),drink('d2','m2','t1',6,2),drink('d3','m3','t2',10,3)]
    monkeypatch.setattr('shared.require_active_membership',lambda:('m1','lobby','season'))
    monkeypatch.setattr(db,'list_players',lambda:[Obj(id='me',display_name='Myself')])
    from tests.test_checkins import TERRITORY
    monkeypatch.setattr('shared.get_territories',lambda:[replace(TERRITORY,id='territory-a')])
    at=AppTest.from_file(ROOT/'pages/4_Standings.py')
    at.session_state['current_membership_id']='m1'
    at.session_state['current_season_id']='season'
    at.run()
    assert not at.exception
    board=''.join(m.value for m in at.markdown)
    assert 'Team 1' in board and 'Team 2' in board and 'YOUR TEAM' in board
    assert '13.5' in board and '10' in board
    assert 'Myself' not in board


@pytest.mark.parametrize('finished', [False, True])
def test_team_profile_stats_show_personal_points_and_completed_team_win(ui,monkeypatch,finished):
    ui['me'].team_id='t1'
    end = datetime.now(timezone.utc) + timedelta(days=-1 if finished else 1)
    ui['season'] = replace(ui['season'], id='season', ends_at=end)
    ui['entries']=[drink('d1','m1','t1',5,1),drink('d2','m2','t1',6,2),drink('d3','m3','t2',10,3)]
    at=AppTest.from_string("from profile_ui import show_stats\nshow_stats('me')").run()
    assert not at.exception
    from tests.test_profile_ui import stats_text
    text=stats_text(at)
    assert 'Total points 5' in text and 'Drinks 1' in text
    assert f'Total Wins {int(finished)}' in text


def test_team_map_shows_combined_capture_gap(ui,monkeypatch):
    ui['me'].team_id='t2'
    ui['members'].append(LobbyMembership('m3','third','lobby',datetime.now(timezone.utc),'t1'))
    ui['entries']=[drink('d1','m2','t1',5,1),drink('d2','m3','t1',6,2),drink('d3','m1','t2',10,3)]
    monkeypatch.setattr('shared.require_active_membership',lambda:('m1','lobby','season'))
    monkeypatch.setattr(db,'list_players',lambda:[Obj(id='me',display_name='Myself')])
    from tests.test_checkins import TERRITORY
    monkeypatch.setattr('shared.get_territories',lambda:[replace(TERRITORY,id='territory-a')])
    monkeypatch.setattr('phone_location.track_location',lambda:None)
    monkeypatch.setattr('phone_location.current_location',lambda:(None,None,'waiting'))
    render=Mock()
    monkeypatch.setattr('map_ui.render_map',render)
    at=AppTest.from_file(ROOT/'pages/5_Map.py').run()
    assert not at.exception
    row=render.call_args.args[0][0]
    assert row['owner']=='Team 1' and row['my_points']==10 and row['needed']==2


def test_membership_revoked_between_team_reads_shows_error(ui):
    ui['members'].remove(ui['me'])
    at=open_lobby(page())
    assert not at.exception
    assert any('membership is no longer available' in error.value for error in at.error)
    assert not any((b.key or '').startswith('join_team_') for b in at.button)


def test_team_popup_switches_to_create_and_stays_closed_after_cancel(ui):
    at=open_lobby(page())
    assert any((b.key or '').startswith('join_team_') for b in at.button)
    at.button(key='open_create_lobby').click().run()
    assert not at.exception and '_opened_lobby_id' not in at.session_state
    assert any(t.label=='Lobby name' for t in at.text_input)
    assert not any((b.key or '').startswith('join_team_') for b in at.button)
    next(b for b in at.button if b.label=='Cancel').click().run()
    at.run()
    assert not at.exception and not at.text_input
    assert not any((b.key or '').startswith('join_team_') for b in at.button)


def test_team_popup_close_and_leaderboard_clear_open_state(ui,monkeypatch):
    at=open_lobby(page())
    at.button(key='close_lobby_teams').click().run()
    at.run()
    assert not at.exception and '_opened_lobby_id' not in at.session_state
    assert not any((b.key or '').startswith('join_team_') for b in at.button)
    nav=Mock()
    monkeypatch.setattr('team_ui.st.switch_page',nav)
    open_lobby(at)
    next(b for b in at.button if b.label=='View leaderboard').click().run()
    assert not at.exception
    assert '_opened_lobby_id' not in at.session_state
    assert at.session_state['current_lobby_mode']=='team'
    nav.assert_called_once_with('pages/4_Standings.py')


def test_incomplete_team_lobby_retains_retry_setup(ui):
    ui['season']=None
    at=open_lobby(page())
    assert not at.exception
    assert any(b.label=='Start lobby' for b in at.button)
    assert any((b.key or '').startswith('join_team_') for b in at.button)


def test_departed_teammate_slot_is_visible_and_full(ui):
    ui['members'][1].left_at = datetime.now(timezone.utc)
    ui['lobby'].team_capacity = 1
    at = page()
    open_lobby(at)
    assert not at.exception
    assert any('Left (slot reserved)' in text.value for text in at.text)
    assert at.button(key='join_team_t1').disabled
    assert any(b.label == 'Leave lobby' for b in at.button)
