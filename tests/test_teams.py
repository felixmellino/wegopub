from dataclasses import replace
from decimal import Decimal

import pytest

from core.lobbies import create_lobby
from core.teams import team_name
from core.scoring_v1 import replay_season
from core.leaderboard import season_leaderboard
from core.territories import territory_owner, territory_standings, capture_status
from core.checkin_feedback import captured_territory
from tests.test_scoring_v1 import entry


def drink(id, member, team, points, order, territory='territory-a'):
    return replace(entry(id, member, 'beer', 'small', order, territory=territory, order=order),
                   team_id=team, points_awarded=points)


def test_team_totals_and_territories_combine_members_not_strongest_player():
    entries = [drink('a','a1','A',5,1), drink('b','a2','A',6,2), drink('c','b1','B',10,3)]
    assert territory_owner(entries, 'territory-a') == 'A'
    assert territory_standings(entries, 'territory-a') == [('A',11),('B',10)]
    assert season_leaderboard(entries) == [('A',Decimal('13.5')),('B',Decimal('10'))]
    assert capture_status(territory_standings(entries,'territory-a'),'A','B') == ('theirs',2)
    assert replay_season(entries).awards['b'] == (None,0)
    assert replay_season(entries).awards['c'] == ('A',10)


def test_team_ties_captures_outside_and_correction_replay():
    entries = [drink('a','a1','A',5,1), drink('b','b1','B',5,2), drink('c','b2','B',1,3)]
    assert territory_owner(entries[:2],'territory-a') == 'A'
    assert captured_territory('b',entries) is None
    assert captured_territory('c',entries) == 'territory-a'
    corrected = [replace(entries[0],points_awarded=7),*entries[1:]]
    assert territory_owner(corrected,'territory-a') == 'A'
    assert captured_territory('c',corrected) is None
    outside = drink('out','b1','B',10,4,territory=None)
    assert territory_owner(corrected+[outside],'territory-a') == 'A'
    assert replay_season(corrected+[outside]).awards['out'] == (None,0)
    assert season_leaderboard(corrected+[outside])[0][0] == 'B'


def test_same_team_never_pays_itself_and_season_ties_use_first_reached():
    entries = [drink('a','a1','A',5,1,None), drink('b','a2','A',6,2,None), drink('c','b1','B',11,3,None)]
    assert season_leaderboard(entries) == [('A',Decimal(11)),('B',Decimal(11))]
    assert all(bonus == 0 for _,bonus in replay_season(entries).awards.values())


@pytest.mark.parametrize('mode,count,capacity,assignment', [
    ('bad',None,None,None),('team',1,2,'manual'),('team',17,2,'manual'),
    ('team',2,0,'manual'),('team',2,21,'manual'),('team',True,2,'random'),
    ('team',2,2,'bad'),('individual',2,2,'manual')])
def test_invalid_settings_rejected(mode,count,capacity,assignment):
    with pytest.raises(ValueError):
        create_lobby('Test',mode,team_count=count,team_capacity=capacity,team_assignment=assignment)


def test_settings_and_names():
    assert create_lobby('Original').game_mode == 'individual'
    assert create_lobby('Teams','team',team_count=4,team_capacity=2,team_assignment='manual').team_count == 4
    assert team_name('  Tigers  ') == 'Tigers'
    for bad in (' ', 'x'*41,'bad\nname'):
        with pytest.raises(ValueError):
            team_name(bad)
