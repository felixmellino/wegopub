from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock

import pytest
from postgrest.exceptions import APIError
from core.focus_challenge import component_action, enabled, new_focus_rules, test_mode as is_test_mode
from core.scoring_v1 import corrected_entry, format_points, new_rules, replay_season
from tests.test_scoring_v1 import START, entry, season
import data.db as db


def test_focus_configuration_is_frozen_and_not_added_to_old_snapshots():
    game = season()
    assert enabled(game)
    other = season()
    game.scoring_rules['focus_challenge']['memory_length'] = 99
    assert other.scoring_rules['focus_challenge']['memory_length'] == 7
    assert new_focus_rules()['memory_length'] == 7
    old = season()
    old.scoring_rules.pop('focus_challenge')
    assert not enabled(old)
    assert not enabled(replace(old, scoring_version='legacy'))


def test_selected_single_reaction_keeps_mains_longer_random_wait():
    rules=new_focus_rules()
    assert rules['reaction_trials']==1 and rules['reaction_median_ms']==220
    assert rules['reaction_wait_min_ms']==3500 and rules['reaction_wait_max_ms']==6500
    assert rules['flow_version']==2


@pytest.mark.parametrize('flag,expected', [(True,True),(False,False),('true',False),(1,False),(None,False)])
def test_only_explicit_qa_flag_enables_old_seasons_without_changing_the_snapshot(flag,expected):
    game=season()
    game.scoring_rules.pop('focus_challenge')
    game.scoring_rules['test_mode']=flag
    before=deepcopy(game.scoring_rules)
    assert is_test_mode(game) is expected
    assert enabled(game) is expected
    assert game.scoring_rules==before
    assert not enabled(replace(game,scoring_version='legacy'))


def test_legacy_qa_sql_fallback_matches_the_fixed_v1_rules():
    import json
    from pathlib import Path
    sql=Path('migrations/015_focus_test_replays.sql').read_text(encoding='utf-8')
    fallback=sql.split("when public._focus_is_test(s) then '",1)[1].split("'::jsonb",1)[0]
    historical=json.loads(fallback)
    assert historical['reaction_trials']==5 and historical['reaction_median_ms']==350
    current=new_focus_rules()
    assert current['reaction_trials']==1 and current['reaction_median_ms']==220
    assert current['reaction_response_ms']==500 and current['flow_version']==2
    assert {k:v for k,v in historical.items() if not k.startswith('reaction_')} == {
        k:v for k,v in current.items() if not k.startswith('reaction_') and k!='flow_version'}


@pytest.mark.parametrize('value', [None, [], {}, {'attempt_id':'other','revision':2,'action':'ready'},
 {'attempt_id':'a','revision':True,'action':'ready'},
 {'attempt_id':'a','revision':1,'action':'ready'},
 {'attempt_id':'a','revision':2,'action':'win'},
 {'attempt_id':'a','revision':2,'action':'reaction','payload':{'elapsed_ms':True}},
 {'attempt_id':'a','revision':2,'action':'reaction','payload':{'elapsed_ms':-1}},
 {'attempt_id':'a','revision':2,'action':'reaction','payload':{'elapsed_ms':2001}},
 {'attempt_id':'a','revision':2,'action':'memory','payload':{'cell':9}},
 {'attempt_id':'a','revision':2,'action':'memory','payload':{'cell':3.0}},
 {'attempt_id':'a','revision':2,'action':'precision','payload':{'taps':[2,1]}},
 {'attempt_id':'a','revision':2,'action':'precision','payload':{'taps':[1,1]}},
 {'attempt_id':'a','revision':2,'action':'precision','payload':{'taps':[True]}},
 {'attempt_id':'a','revision':2,'action':'precision','payload':{'taps':[12001]}},
 {'attempt_id':'a','revision':2,'action':'precision','payload':{'taps':[]}},
])
def test_untrusted_component_messages_cannot_supply_a_win_or_invalid_evidence(value):
    assert component_action(value, {'id':'a','revision':2}) is None


@pytest.mark.parametrize('action,payload', [('ready',{}),('fail',{}),('reaction',{'elapsed_ms':350}),
 ('memory',{'cell':8}),('precision',{'taps':[100,200,300]})])
def test_current_attempt_accepts_only_bounded_stage_evidence(action,payload):
    value = {'attempt_id':'a','revision':2,'action':action,'payload':payload}
    assert component_action(value, {'id':'a','revision':2}) == (action,payload)


def test_saved_focus_award_replays_exact_income_ownership_and_corrections():
    owner = entry('owner','B','mixed','large',0,order=1)
    boosted = replace(entry('boost','A','beer','small',1,order=2),points_awarded=1.5,focus_attempt_id='won')
    replay = replay_season([owner,boosted])
    assert replay.awards['boost'] == ('B',1.5)
    assert dict(replay.season_rows()) == {'A':1.5,'B':5.375}
    assert replay.territory_totals['territory-a'] == {'B':5,'A':1.5}
    assert format_points(1.125) == '1.125' and format_points(0.375) == '0.375'
    corrected = corrected_entry(boosted,season(),'beer','large',START+timedelta(minutes=1,seconds=30))
    assert corrected.points_awarded == 4.5 and corrected.focus_attempt_id == 'won'
    replay = replay_season([owner,corrected])
    assert dict(replay.season_rows())['B'] == 6.125
    assert replay.owners['territory-a'] == 'B'
    # Further replay never compounds the saved factor or depends on today's time.
    assert replay_season([owner,corrected]) == replay


def test_boosted_team_entry_does_not_boost_its_teammates():
    mine = replace(entry('mine','A','beer','small',0),team_id='team',points_awarded=1.5,focus_attempt_id='won')
    teammate = replace(entry('mate','C','beer','small',1),team_id='team')
    assert dict(replay_season([mine,teammate]).season_rows()) == {'team':2.5}


def test_map_capture_hint_allows_fractional_focus_awards():
    import map_ui
    from tests.test_checkins import TERRITORY
    owner = entry('owner','B','beer','medium',0)
    mine = replace(entry('mine','A','beer','small',1),points_awarded=1.5,focus_attempt_id='won')
    row = map_ui.territory_rows([TERRITORY],[owner,mine],'A',{'A':'Me','B':'Owner'})[0]
    assert row['owner_points'] == 2 and row['my_points'] == 1.5 and row['needed'] == 1


def test_focus_rpc_sends_identity_and_evidence_never_a_score(monkeypatch):
    client = Mock()
    client.rpc.return_value.execute.return_value.data = {'id':'attempt','revision':1}
    monkeypatch.setattr(db,'get_client',lambda:client)
    assert db.focus_status('player','season')['id'] == 'attempt'
    db.start_focus_attempt('player','season','request')
    assert client.rpc.call_args.args == ('start_focus_attempt',{'actor_player':'player','target_season':'season','request_id':'request'})
    db.focus_attempt_action('player','attempt',1,'reaction',{'elapsed_ms':250})
    assert client.rpc.call_args.args[1]['evidence'] == {'elapsed_ms':250}
    assert not any('points' in k or 'boost' in k for k in client.rpc.call_args.args[1])


@pytest.mark.parametrize('reason,code,exception', [('focus_locked','P0001',ValueError),
 ('permission_denied','P0001',PermissionError),('not installed','PGRST202',RuntimeError)])
def test_focus_errors_are_actionable(monkeypatch,reason,code,exception):
    client = Mock()
    client.rpc.return_value.execute.side_effect = APIError({'message':reason,'code':code,'details':None,'hint':None})
    monkeypatch.setattr(db,'get_client',lambda:client)
    with pytest.raises(exception):db.focus_status('player','season')
