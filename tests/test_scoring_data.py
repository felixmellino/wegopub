from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from postgrest.exceptions import APIError

import data.db as db
from core.checkins import CheckinRejected
from tests.test_scoring_v1 import START, entry, season


def test_pagination_loads_more_than_postgrest_default_row_limit():
    records = [{"id": str(index)} for index in range(1201)]
    query = Mock()
    bounds = []
    def page(start,end):
        bounds.append((start,end))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=records[start:end+1]))
    query.range.side_effect = page
    assert db._all_rows(query) == records
    assert bounds == [(0,499),(500,999),(1000,1499)]


@pytest.mark.parametrize("reason,exception", [("permission_denied",PermissionError), ("cooldown",CheckinRejected),
    ("correction_closed",CheckinRejected), ("correction_conflict",CheckinRejected),
    ("lobby_already_started",CheckinRejected), ("scoring_setup_required",RuntimeError)])
def test_rpc_errors_become_safe_actionable_errors(monkeypatch,reason,exception):
    client=Mock()
    client.rpc.return_value.execute.side_effect = APIError({"code":"P0001","message":reason,"details":None,"hint":None})
    monkeypatch.setattr(db,"get_client",lambda:client)
    with pytest.raises(exception):
        db._scoring_rpc("test",{})


def test_correction_does_not_call_rpc_for_another_players_entry(monkeypatch):
    query=Mock()
    query.eq.return_value=query
    query.execute.return_value.data=[{"lobby_memberships":{"player_id":"another-player"}}]
    monkeypatch.setattr(db,"_lobby_photo_query",lambda *args:query)
    rpc=Mock()
    monkeypatch.setattr(db,"_scoring_rpc",rpc)
    with pytest.raises(PermissionError):
        db.correct_checkin("viewer","lobby","entry","beer","small",0)
    rpc.assert_not_called()


def test_database_rows_preserve_scoring_order_and_revision_metadata():
    model=replace(entry("one","Mia","wine","small",0),photo_captured_at=START,
        event_order=42,owner_membership_id="Leo",owner_bonus_quarters=1,corrected_at=START+timedelta(seconds=60),revision=1)
    row=db._drink_entry_row(model)
    row.update(event_order=42,owner_membership_id="Leo",owner_bonus_quarters=1,
               corrected_at=model.corrected_at.isoformat(),revision=1)
    assert db._row_to_drink_entry(row)==model


def test_legacy_season_rows_are_not_silently_upgraded():
    game=season()
    row={"id":game.id,"lobby_id":game.lobby_id,"starts_at":game.starts_at.isoformat(),
         "ends_at":game.ends_at.isoformat(),"length_choice":game.length_choice}
    loaded=db._row_to_season(row)
    assert loaded.scoring_version=="legacy" and loaded.scoring_rules is None


def test_v1_cannot_bypass_transaction_functions_through_legacy_insert_helpers(monkeypatch):
    client=Mock()
    get_client=Mock(return_value=client)
    monkeypatch.setattr(db,"get_client",get_client)
    with pytest.raises(RuntimeError,match="start_scoring_season"):
        db.insert_season(season())
    with pytest.raises(RuntimeError,match="save_drink_entry_photo"):
        db.insert_drink_entry(entry("one","Mia","shot",None,0))
    get_client.assert_not_called()


def test_finished_lobby_cannot_start_another_competition(monkeypatch):
    # An existing competition prevents renewal even after its finish date.
    monkeypatch.setattr(db, "list_seasons_for_lobby", lambda _: [season()])
    rpc = Mock()
    monkeypatch.setattr(db, "_scoring_rpc", rpc)
    with pytest.raises(CheckinRejected, match="lobby_already_started"):
        db.start_scoring_season("player", "lobby", "1_week", "Europe/Lisbon")
    rpc.assert_not_called()
