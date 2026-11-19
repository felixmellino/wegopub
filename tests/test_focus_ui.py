from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock
import pytest
import focus_challenge_ui as focus_ui
from tests.test_chug_duel_ui import service, open_page, button
from tests.test_scoring_v1 import START
from core.focus_challenge import new_focus_rules

@pytest.fixture
def focus(service, monkeypatch):
    attempt = dict(id='attempt',status='running',phase='reaction_ready',revision=0,step=0,
      config=new_focus_rules(),server_now=START.isoformat(),deadline=(START+timedelta(seconds=30)).isoformat(),
      expires_at=(START+timedelta(minutes=3)).isoformat(),signal_at=None,reaction_ms=[],precision_taps=[])
    state = {'count':4,'threshold':5,'won':False,'boost_ends_at':None,'attempt':None,'board':None}
    monkeypatch.setattr(focus_ui,'current_time',lambda:START)
    monkeypatch.setattr(focus_ui,'focus_board',lambda a: state['board'])
    monkeypatch.setattr(focus_ui.db,'focus_status',lambda *args:deepcopy({k:v for k,v in state.items() if k!='board'}))
    start = Mock(side_effect=lambda *args: state.update(attempt=deepcopy(attempt)) or deepcopy(attempt))
    monkeypatch.setattr(focus_ui.db,'start_focus_attempt',start)
    action = Mock(side_effect=lambda *args: state['attempt'].update(revision=1,phase='reaction') or deepcopy(state['attempt']))
    monkeypatch.setattr(focus_ui.db,'focus_attempt_action',action)
    return state,start,action,service


def test_hub_opens_focus_with_a_locked_start_and_no_location_access(focus, monkeypatch):
    state,start,action,_ = focus
    import minigames_ui as ui
    gps = Mock()
    monkeypatch.setattr(ui,'track_location',gps)
    page = open_page(selected=None)
    button(page,'Open Reaction Test').click().run()
    assert not page.exception and button(page,'Start').disabled
    assert any('4 / 5' in p.text for p in page.get('progress'))
    assert not start.called and not action.called and not gps.called
    state['count']=5
    page.run()
    assert not button(page,'Start').disabled
    button(page,'Start').click().run()
    assert not page.exception and start.call_count==1 and button(page,'Back to games')
    assert not any(b.label=='Start' for b in page.button)


def test_saved_attempt_resumes_after_a_fresh_app_session_and_leaving_does_not_reset_it(focus):
    state,start,action,_ = focus
    state['count']=5
    page = open_page(selected='focus')
    button(page,'Start').click().run()
    saved=deepcopy(state['attempt'])
    button(page,'Back to games').click().run()
    assert not page.exception and state['attempt']==saved
    reopened=open_page(selected='focus')
    assert not reopened.exception and button(reopened,'Back to games')
    assert start.call_count==1 and state['attempt']==saved


def test_component_action_uses_saved_revision_and_cannot_award_points(focus):
    state,start,action,_ = focus
    state['count']=5
    page=open_page(selected='focus')
    button(page,'Start').click().run()
    state['board']={'attempt_id':'attempt','revision':0,'action':'ready','payload':{}}
    page.run()
    assert not page.exception and action.call_count==1
    assert action.call_args.args==('pa','attempt',0,'ready',{})
    page.run()
    assert action.call_count==1,'Stale ready replies cannot advance a second time'


def test_old_snapshot_disables_focus_without_database_calls(focus):
    state,start,action,service = focus
    service['game'].scoring_rules.pop('focus_challenge')
    page=open_page(selected=None)
    assert not page.exception and button(page,'Open Reaction Test').disabled
    assert not start.called and not action.called


def test_lost_start_reply_recovers_and_does_not_reuse_its_request_for_a_later_attempt(focus):
    from httpx import ReadTimeout
    state,start,action,_ = focus
    state['count']=5
    save = start.side_effect
    def lose_reply(*args):
        save(*args)
        raise ReadTimeout('Reply lost after committed start')
    start.side_effect = lose_reply
    page = open_page(selected='focus')
    button(page,'Start').click().run()
    assert not page.exception and page.error
    first_request = start.call_args.args[2]
    page.run()
    assert button(page,'Back to games') and 'focus_start_request' not in page.session_state
    state['attempt']['status']='failed'
    state['count']=7
    state['threshold']=7
    page.run()
    button(page,'Back to games').click().run()
    button(page,'Open Reaction Test').click().run()
    start.side_effect=save
    button(page,'Start').click().run()
    assert not page.exception and start.call_count==2
    assert start.call_args.args[2] != first_request


@pytest.mark.parametrize('previous', [None,'failed','passed'])
def test_existing_qa_season_plays_without_uploads_even_after_winning(focus,previous):
    state,start,action,service=focus
    service['game'].scoring_rules.pop('focus_challenge')
    service['game'].scoring_rules['test_mode']=True
    state.update(count=0,threshold=0,unlimited=True,won=previous=='passed')
    if previous:
        state['attempt']={'id':'previous','status':previous}
    if previous=='passed':
        state['boost_ends_at']=(START+timedelta(minutes=30)).isoformat()
    page=open_page(selected=None)
    assert not page.exception and not button(page,'Open Reaction Test').disabled
    button(page,'Open Reaction Test').click().run()
    assert not page.exception and not button(page,'Start').disabled
    assert not page.get('progress')
    button(page,'Start').click().run()
    assert not page.exception and start.call_count==1 and button(page,'Back to games')


def test_qa_can_play_outside_weekly_window_but_not_after_season_ends(focus,monkeypatch):
    state,start,action,service=focus
    game=service['game']
    game.scoring_rules['test_mode']=True
    state.update(count=0,threshold=0,unlimited=True)
    monkeypatch.setattr(focus_ui,'current_time',lambda:START+timedelta(days=4))
    page=open_page(selected='focus')
    assert not page.exception and not button(page,'Start').disabled
    monkeypatch.setattr(focus_ui,'current_time',lambda:game.ends_at)
    page.run()
    assert not page.exception and button(page,'Start').disabled
    assert not start.called


def test_qa_with_only_migration_014_shows_the_required_upgrade(focus):
    state,start,action,service=focus
    service['game'].scoring_rules['test_mode']=True
    page=open_page(selected='focus')
    assert not page.exception and any('migration 015' in e.value for e in page.error)
    assert not start.called


def test_server_qa_status_handles_a_stale_season_snapshot_without_dividing_by_zero(focus):
    state,start,action,service=focus
    # The page still has a normal-looking snapshot while the authoritative RPC
    # reports QA. Only the server can permit an actual start or grant an award.
    assert 'test_mode' not in service['game'].scoring_rules
    state.update(count=0,threshold=0,unlimited=True)
    page=open_page(selected='focus')
    assert not page.exception
    assert not page.get('progress')
    assert not button(page,'Start').disabled
    button(page,'Start').click().run()
    assert not page.exception and start.call_count==1


@pytest.mark.parametrize('threshold',[0,-1,None,True])
def test_invalid_normal_unlock_threshold_shows_reload_message_without_crashing_or_starting(focus,threshold):
    state,start,action,_=focus
    state.update(count=0,threshold=threshold,unlimited=False)
    page=open_page(selected='focus')
    assert not page.exception
    assert any('Reload' in e.value for e in page.error)
    assert not any(b.label=='Start' for b in page.button)
    assert not start.called and not action.called
