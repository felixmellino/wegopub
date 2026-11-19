"""Departure preserves history and pauses only personal owner income."""
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from postgrest.exceptions import APIError

import data.db as db
from core.profile_stats import all_time_stats
from core.scoring_v1 import replay_season
from tests.test_scoring_v1 import entry


def test_absence_snapshot_survives_rejoin_and_correction_replay():
    owner = entry('a', 'owner', 'mixed', 'large', 0)
    before = entry('b', 'visitor', 'beer', 'small', 1)
    away = replace(entry('c', 'visitor', 'beer', 'small', 2), absent_member_ids=('owner',))
    returned = entry('d', 'visitor', 'beer', 'small', 3)
    entries = [owner, before, away, returned]
    replay = replay_season(entries)
    assert [replay.awards[e.id] for e in entries] == [(None, 0), ('owner', 1), (None, 0), ('owner', 1)]
    member = SimpleNamespace(id='owner', lobby_id='lobby', left_at=datetime.now(timezone.utc))
    assert all_time_stats([member], entries).points == 5.5
    corrected = replace(owner, points_awarded=4)
    assert replay_season([corrected, before, away, returned]).awards == replay.awards


def test_correction_changes_owner_but_uses_original_absent_roster():
    first = entry('a', 'A', 'beer', 'large', 0)
    second = entry('b', 'B', 'beer', 'medium', 1)
    away = replace(entry('c', 'C', 'beer', 'small', 2), absent_member_ids=('B',))
    assert replay_season([first, second, away]).awards['c'] == ('A', 1)
    assert replay_season([replace(first, points_awarded=1), second, away]).awards['c'] == (None, 0)


def test_individual_departure_does_not_pause_team_income():
    owner = replace(entry('a', 'owner', 'mixed', 'large', 0), team_id='team')
    visitor = replace(entry('b', 'visitor', 'beer', 'small', 1), team_id='other', absent_member_ids=('owner',))
    assert replay_season([owner, visitor]).awards['b'] == ('team', 1)


@pytest.mark.parametrize('method,scope', [('list_memberships_for_player', 'player'), ('list_memberships_for_lobby', 'lobby')])
def test_current_roster_excludes_departed_but_history_includes_them(monkeypatch, method, scope):
    client = Mock()
    rows = [dict(id=mid, player_id='player', lobby_id='lobby', joined_at='2026-11-19T18:00:00+00:00', left_at=left)
            for mid, left in [('current', None), ('departed', '2026-11-19T19:00:00+00:00')]]
    client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = rows
    monkeypatch.setattr(db, 'get_client', lambda: client)
    read = getattr(db, method)
    assert [m.id for m in read(scope)] == ['current']
    assert [m.id for m in read(scope, include_left=True)] == ['current', 'departed']


@pytest.mark.parametrize('reason,expected', [('permission_denied', PermissionError), ('minigame_active', ValueError), ('time_busy', ValueError)])
def test_departure_errors_are_actionable(monkeypatch, reason, expected):
    client = Mock()
    client.rpc.return_value.execute.side_effect = APIError(dict(message=reason, code='P0001', details=None, hint=None))
    monkeypatch.setattr(db, 'get_client', lambda: client)
    with pytest.raises(expected):
        db.leave_lobby('player', 'lobby')
    client.rpc.assert_called_once_with('leave_lobby', {'actor_player': 'player', 'target_lobby': 'lobby'})


def test_deleted_lobbies_are_hidden_everywhere(monkeypatch):
    client = Mock()
    client.table.return_value.select.return_value.execute.return_value.data = [
        dict(id='a', name='Live', invite_code='LIVE'),
        dict(id='b', name='Gone', invite_code='GONE', deleted_at='2026-11-19T20:00:00+00:00')]
    monkeypatch.setattr(db, 'get_client', lambda: client)
    assert [l.id for l in db.list_lobbies()] == ['a']


@pytest.mark.parametrize('reason,expected', [('permission_denied', PermissionError), ('other', APIError)])
def test_delete_lobby_errors_are_actionable(monkeypatch, reason, expected):
    client = Mock()
    client.rpc.return_value.execute.side_effect = APIError(dict(message=reason, code='P0001', details=None, hint=None))
    monkeypatch.setattr(db, 'get_client', lambda: client)
    with pytest.raises(expected):
        db.delete_lobby('player', 'lobby')
    client.rpc.assert_called_once_with('delete_lobby', {'actor_player': 'player', 'target_lobby': 'lobby'})
