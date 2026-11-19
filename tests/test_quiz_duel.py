"""User decisions, stake replay and untrusted component input."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from random import Random
import pytest
from core.models import SeasonTransfer, LobbyMembership
from core.quiz_duel import CONFIG, allowances, available, component_action, outcome, round_winner, validate_stake
from core.scoring_v1 import replay_season
from core.leaderboard import season_leader
from core.profile_stats import all_time_stats
from data.quiz_questions import prepare_duel_deck
from tests.test_scoring_v1 import START, entry, season


@pytest.mark.parametrize("stake", [3,4,5,6,7,8,9,10])
def test_allowed_stake(stake):
    assert validate_stake(stake) == stake


@pytest.mark.parametrize("stake", [None,True,False,2,11,3.0,"3",[],{}])
def test_rejected_stake(stake):
    with pytest.raises(ValueError):
        validate_stake(stake)


@pytest.mark.parametrize("a,b,winner", [
    (None,None,None), ((False,1),(False,2),None), ((True,1),(True,1),None),
    ((True,2),(True,1),'opponent'), ((True,1),(True,2),'challenger'),
    ((False,1),(True,2),'opponent'), ((True,2),None,'challenger')])
def test_round_outcomes(a,b,winner):
    assert round_winner(a,b) == winner


@pytest.mark.parametrize("round_no,a,b,result", [
    (0,1,0,'next'),(1,2,0,'challenger'),(1,0,2,'opponent'),(1,1,1,'next'),
    (2,1,0,'challenger'),(2,1,1,'next'),(3,2,1,'challenger'),
    (4,0,0,'next'),(5,0,0,'draw')])
def test_match_resolution(round_no,a,b,result):
    assert outcome(round_no,a,b) == result


def test_private_deck_has_same_order_and_unique_deciders():
    deck = prepare_duel_deck('duel', Random(123))
    assert [q['category'] for q in deck] == ['general','math','logic','general','general','general']
    assert len({q['id'] for q in deck}) == 6
    assert all(len(q['options']) == 4 for q in deck)


def test_roles_reserve_on_accept_release_before_start_and_consume_after_start():
    d=dict(challenger_id='a',opponent_id='b',game_night='2026-11-19',status='invited',started_at=None)
    assert allowances('a', d['game_night'], [d]) == (True,True)
    d['status']='accepted'
    assert allowances('a', d['game_night'], [d]) == (False,True)
    assert allowances('b', d['game_night'], [d]) == (True,False)
    d['status']='cancelled'
    assert allowances('a', d['game_night'], [d]) == (True,True)
    d.update(status='draw',started_at=START.isoformat())
    assert allowances('a', d['game_night'], [d]) == (False,True)
    assert allowances('a', '2026-11-20', [d]) == (True,True)
    assert allowances('a', d['game_night'], [d], test_mode=True) == (True,True)


def test_qa_can_play_outside_scoring_window_only_while_season_active():
    s=season()
    monday=START+timedelta(days=4)
    assert not available(s,monday)
    s.scoring_rules['test_mode']=True
    assert available(s,monday)
    assert not available(s,s.ends_at)
    assert not available(s,s.starts_at-timedelta(seconds=1))


def test_ledger_changes_season_and_personal_points_but_no_territory_or_drink_counts():
    entries=[entry('a','a','mixed','large',0,order=1),entry('b','b','mixed','large',1,order=2)]
    transfer=SeasonTransfer('duel','season','a','b','a','b',3,3,START)
    before=replay_season(entries);after=replay_season(entries,[transfer])
    assert after.season_quarters == {'a':13,'b':32}  # a receives 1.25 owner income
    assert after.awards == before.awards
    assert after.territory_totals == before.territory_totals
    assert after.owners == before.owners
    assert season_leader(entries,[transfer]) == 'b'
    memberships=[LobbyMembership('a','player','lobby',START)]
    stats=all_time_stats(memberships,entries,transfers=[transfer],finished_season_ids=['season'])
    assert stats.points == Decimal('3.25')
    assert stats.drinks == 1 and stats.wins == 0


def test_team_stake_is_not_added_to_personal_profile_points():
    entries=[replace(entry('a','a','mixed','large',0,order=1),team_id='t1'),
             replace(entry('b','b','mixed','large',1,order=2),team_id='t2')]
    transfer=SeasonTransfer('duel','season','t1','t2','a','b',3,3,START)
    me=[LobbyMembership('b','player','lobby',START,team_id='t2')]
    assert all_time_stats(me,entries,transfers=[transfer],finished_season_ids=['season']).wins == 1
    assert all_time_stats(me,entries,transfers=[transfer]).points == 5


def test_mixed_seasons_and_bad_transfer_rejected():
    t=SeasonTransfer('duel','other','a','b','a','b',3,3,START)
    with pytest.raises(ValueError):replay_season([entry('a','a','beer','large',0)], [t])
    with pytest.raises(ValueError):replay_season([], [replace(t, points=True)])


@pytest.mark.parametrize("bad", [None,{},dict(duel_id='other'),dict(duel_id='duel',event_id=True,action='ready'),
    dict(duel_id='duel',event_id='e',action='answer',round_no=0,choice=True),
    dict(duel_id='duel',event_id='e',action='answer',round_no=1,choice=0),
    dict(duel_id='duel',event_id='e',action='finish',winner='me')])
def test_browser_cannot_declare_winner_or_send_bad_answer(bad):
    assert component_action(bad,dict(id='duel',round_no=0)) is None


def test_valid_component_action():
    assert component_action(dict(duel_id='duel',event_id='e',action='answer',round_no=0,choice=3),
                            dict(id='duel',round_no=0)) == ('answer',0,3)
