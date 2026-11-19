"""Allowed, rejected and scoring-boundary behavior for Time Duel."""
from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock
import pytest
from postgrest.exceptions import APIError
import data.db as db
from core.time_duel import outcome, component_action
from core.scoring_v1 import replay_season, corrected_entry
from tests.test_scoring_v1 import entry, season, START


@pytest.mark.parametrize('a,b,winner', [
    ([7900,8100,8000],[8300,8000,8000],'challenger'),
    ([7800,8000,8000],[8000,8000,8000],'opponent'),
    ([7900,8100,8000],[8100,7900,8000],'both'),
    ([None,8000,8000],[12000,12000,12000],'opponent'),
    ([None,7900,8000],[None,8100,8200],'challenger'),
    ([None,8000,8000],[None,8000,8000],'none'),
    ([None,None,None],[None,None,None],'none'),
])
def test_winner_counts_abandonments_before_absolute_error(a,b,winner):
    assert outcome([8000]*3,a,b)==winner


@pytest.mark.parametrize('ms', [True, -1, 30001, 1.5, '8000', None])
def test_bad_evidence_cannot_cross_component_bridge(ms):
    d={'id':'d','round_no':1}
    assert component_action(dict(duel_id='d',event_id='e',action='stop',round_no=1,elapsed_ms=ms),d) is None


def test_stale_event_cannot_start_next_round():
    d={'id':'d','round_no':1}
    assert component_action(dict(duel_id='d',event_id='e',action='start',round_no=0),d) is None
    assert component_action(dict(duel_id='d',event_id='e',action='stop',round_no=1,elapsed_ms=8000),d)==('stop',1,8000)


def test_season_bonus_does_not_change_territories_or_owner_income():
    owner=entry('owner','B','mixed','large',0,order=1)
    drink=replace(entry('drink','A','beer','small',1,order=2),time_duel_id='win',time_bonus=.25)
    replay=replay_season([owner,drink])
    assert dict(replay.season_rows())=={'B':Decimal('5.25'),'A':Decimal('1.25')}
    assert dict(replay.territory_rows('territory-a'))=={'B':5,'A':1}
    assert replay.awards['drink']==('B',1)
    corrected=corrected_entry(drink,season(),'beer','large',drink.submitted_at)
    assert corrected.points_awarded==3 and corrected.time_bonus==.75
    assert replay_season([owner,corrected]).awards['drink']==('B',3)


def test_focus_is_higher_without_stacking_and_personal_lifetime_is_unchanged():
    from core.models import LobbyMembership
    from core.profile_stats import all_time_stats
    drink=replace(entry('a','A','beer','small',0),time_duel_id='win',time_bonus=.25)
    assert all_time_stats([LobbyMembership('A','p','lobby',START)],[drink]).points==1
    focus=replace(drink,focus_attempt_id='focus',points_awarded=1.5,time_bonus=0)
    changed=corrected_entry(focus,season(),'beer','large',focus.submitted_at)
    assert changed.points_awarded==4.5 and changed.time_bonus==0


def test_team_bonus_only_uses_winners_own_entries():
    mine=replace(entry('a','A','beer','small',0),team_id='team',time_bonus=.25,time_duel_id='win')
    teammate=replace(entry('b','B','beer','small',1),team_id='team')
    assert dict(replay_season([mine,teammate]).season_rows())=={'team':Decimal('2.25')}
    assert dict(replay_season([mine,teammate]).territory_rows('territory-a'))=={'team':2}


def test_rpc_sends_evidence_never_winner(monkeypatch):
    client=Mock();client.rpc.return_value.execute.return_value.data={'id':'saved'}
    monkeypatch.setattr(db,'get_client',lambda:client)
    assert db.time_action('p','d','stop',1,8000)=={'id':'saved'}
    assert client.rpc.call_args.args==('time_action',dict(actor_player='p',target_duel='d',selected_action='stop',expected_round=1,elapsed=8000))
    client.rpc.return_value.execute.side_effect=APIError(dict(code='PGRST202',message='missing',details='',hint=''))
    with pytest.raises(RuntimeError,match='017'):db.time_status('p','s')
