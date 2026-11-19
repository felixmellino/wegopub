from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

import data.db as db
from core.scoring_v1 import new_rules, scoring_open, next_opening, create_scored_entry
from core.checkins import CheckinRejected
from tests.test_scoring_v1 import season
from tests.test_checkins import INSIDE, TERRITORY

WEDNESDAY = datetime(2026, 11, 18, 8, tzinfo=timezone.utc)


def qa_season(zone='Europe/Lisbon'):
    return replace(season(zone), starts_at=WEDNESDAY-timedelta(days=1), scoring_rules=new_rules(test_mode=True))


@pytest.mark.parametrize('at,allowed', [(WEDNESDAY-timedelta(microseconds=1), False),
    (WEDNESDAY, True), (WEDNESDAY+timedelta(days=4,hours=10)-timedelta(microseconds=1), True),
    (WEDNESDAY+timedelta(days=4,hours=10), False)])
def test_test_window_boundaries(at, allowed):
    assert scoring_open(at, qa_season()) is allowed


def test_normal_window_and_existing_snapshot_unchanged():
    normal = new_rules()
    qa = new_rules(test_mode=True)
    assert normal['start_weekday'] == 3 and normal['start_hour'] == 18 and not normal.get('test_mode')
    assert qa['test_mode'] is True and qa['start_weekday'] == 2 and qa['start_hour'] == 8
    normal_game = replace(qa_season(), scoring_rules=normal)
    assert not scoring_open(WEDNESDAY, normal_game)
    assert normal == new_rules()


def test_test_window_uses_lobby_timezone_and_next_opening():
    game = qa_season('America/New_York')
    assert not scoring_open(WEDNESDAY, game)  # 03:00 in New York.
    opening = next_opening(WEDNESDAY, game)
    assert opening.hour == 8 and opening.weekday() == 2
    assert scoring_open(opening, game)


def test_wednesday_test_checkin_accepted_but_normal_rejected():
    game = qa_season()
    saved = create_scored_entry('member', game, 'beer', 'small', 'photo.jpg', INSIDE, 10,
        WEDNESDAY, [TERRITORY], [], entry_id='capture')
    assert saved.points_awarded == 1
    with pytest.raises(CheckinRejected, match='scoring_closed'):
        create_scored_entry('member', replace(game, scoring_rules=new_rules()), 'beer', 'small',
            'photo.jpg', INSIDE, 10, WEDNESDAY, [TERRITORY], [], entry_id='normal')


def test_rpc_receives_and_restores_frozen_test_rules(monkeypatch):
    game = qa_season()
    row = {'id':game.id, 'lobby_id':game.lobby_id, 'starts_at':game.starts_at.isoformat(),
           'ends_at':game.ends_at.isoformat(), 'length_choice':game.length_choice,
           'timezone_name':game.timezone_name, 'scoring_version':'v1', 'scoring_rules':game.scoring_rules}
    client = Mock()
    client.rpc.return_value.execute.return_value.data = [row]
    monkeypatch.setattr(db, 'get_client', lambda: client)
    monkeypatch.setattr(db, 'list_seasons_for_lobby', lambda _: [])
    restored = db.start_scoring_season('player', 'lobby', '1_month', 'Europe/Lisbon', test_mode=True)
    sent = client.rpc.call_args.args[1]['frozen_rules']
    assert sent == restored.scoring_rules == game.scoring_rules
    assert scoring_open(WEDNESDAY, restored)
