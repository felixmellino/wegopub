from dataclasses import replace
from io import BytesIO
from unittest.mock import Mock

import pytest
from PIL import Image
from postgrest.exceptions import APIError

import data.db as db
from core.models import LobbyMembership
from core.checkins import CheckinRejected
from tests.test_scoring_v1 import START, season
from tests.test_photo_lifecycle import store


@pytest.fixture
def service(monkeypatch):
    duel = dict(id="d", challenger_id="a", opponent_id="b", challenger_entry_id="ea", opponent_entry_id="eb",
                drink_type="beer", size="large", status="accepted", accepted_at=START.isoformat())
    monkeypatch.setattr(db, "list_chug_duels", lambda *args: [duel])
    monkeypatch.setattr(db, "list_memberships_for_player", lambda _: [LobbyMembership("a", "pa", "lobby", START)])
    monkeypatch.setattr(db, "list_seasons_for_lobby", lambda _: [season()])
    monkeypatch.setattr(db, "list_drink_entries_for_membership", lambda _: [])
    monkeypatch.setattr("core.scoring_v1.current_time", lambda: START)
    monkeypatch.setattr("data.territory_file.load_territories", lambda: [])
    monkeypatch.setattr(db, "upsert_territories", lambda _: None)
    bucket, rpc = Mock(), Mock(return_value=[dict(duel, status="started")])
    monkeypatch.setattr(db, "_private_photo_bucket", lambda: bucket)
    monkeypatch.setattr(db, "_duel_rpc", rpc)
    image = BytesIO()
    exif = Image.Exif()
    exif[270] = "private metadata"
    Image.new("RGB", (8, 8)).save(image, "JPEG", exif=exif)
    return duel, bucket, rpc, image.getvalue()


def start(raw):
    return db.start_chug_duel("pa", "lobby", "season", "d", raw, START, (38.7, -9.1), 10)


def test_shared_capture_sanitized_for_two_authorized_paths_no_gps_sent(service):
    _, bucket, rpc, image = service
    assert start(image)["status"] == "started"
    assert [call.args[0] for call in bucket.upload.call_args_list] == ["lobby/ea.jpg", "lobby/eb.jpg"]
    for call in bucket.upload.call_args_list:
        with Image.open(BytesIO(call.args[1])) as cleaned:
            assert not cleaned.getexif()
    parameters = rpc.call_args.args[1]
    assert parameters["location_result"] == "outside"
    assert not any("gps" in key or "accuracy" in key for key in parameters)


def test_recover_committed_start_without_reupload(service):
    duel, bucket, rpc, image = service
    duel["status"] = "started"
    assert start(image)["status"] == "started"
    bucket.upload.assert_not_called()
    rpc.assert_not_called()


def test_unauthorized_host_and_invalid_gps_never_upload(service, monkeypatch):
    _, bucket, rpc, image = service
    with pytest.raises(CheckinRejected):
        db.start_chug_duel("pa", "lobby", "season", "d", image, START, None, None)
    bucket.upload.assert_not_called()
    monkeypatch.setattr(db, "list_memberships_for_player", lambda _: [])
    with pytest.raises(PermissionError):
        start(image)
    bucket.upload.assert_not_called()
    rpc.assert_not_called()


@pytest.mark.parametrize("reason,code,expected", [("permission_denied", "P0001", PermissionError),
    ("duel_limit", "P0001", ValueError), ("duel_early", "P0001", ValueError),
    ("missing function", "PGRST202", RuntimeError)])
def test_database_errors_are_safe_and_actionable(monkeypatch, reason, code, expected):
    client = Mock()
    client.rpc.return_value.execute.side_effect = APIError({"message": reason, "code": code, "details": None, "hint": None})
    monkeypatch.setattr(db, "get_client", lambda: client)
    with pytest.raises(expected):
        db.chug_duel_action("player", "duel", "accept")


def test_photo_history_shows_transfer_and_deletion_only_removes_own_copy(store):
    from copy import deepcopy
    game = season()
    template = deepcopy(store.rows["entry"])
    game_row = dict(id=game.id, lobby_id=game.lobby_id, starts_at=game.starts_at.isoformat(),
        ends_at=game.ends_at.isoformat(), length_choice=game.length_choice, timezone_name=game.timezone_name,
        scoring_version=game.scoring_version, scoring_rules=game.scoring_rules)
    store.rows.clear()
    store.files.clear()
    for eid, mid, actor, order in (("winner", "ma", "author", 1), ("loser", "mb", "guest", 2)):
        row = deepcopy(template)
        row.update(id=eid, membership_id=mid, season_id=game.id, drink_type="beer", size="large",
            rule_version="v1", points_awarded=3, duel_id="duel", event_order=order,
            photo_ref=f"lobby/{eid}.jpg", seasons=game_row)
        row["lobby_memberships"]["player_id"] = actor
        if eid == "loser":
            row.update(duel_transfer_to="ma", duel_transfer_order=3)
        store.rows[eid] = row
        store.files[row["photo_ref"]] = {"bytes": b"shared pixels"}
    cards = {card["id"]: card for card in db.list_checkin_photos("reader", "lobby")}
    assert cards["winner"]["duel_season_points"] == 6
    assert cards["loser"]["duel_season_points"] == 0
    assert all(card["entry"].points_awarded == 3 for card in cards.values())
    db.delete_checkin_photo("author", "lobby", "winner")
    assert "lobby/winner.jpg" not in store.files and "lobby/loser.jpg" in store.files
    cards = {card["id"]: card for card in db.list_checkin_photos("reader", "lobby")}
    assert cards["winner"]["duel_season_points"] == 6
    assert cards["loser"]["duel_season_points"] == 0
