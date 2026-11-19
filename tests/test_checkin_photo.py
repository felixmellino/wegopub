from io import BytesIO
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import ExifTags, Image, TiffImagePlugin

import data.db as db
import core.checkin_photo as checkin_photo
from core.checkin_photo import InvalidCheckinPhoto, prepare_checkin_photo
from core.models import DrinkEntry


def test_camera_photo_preserves_orientation_and_removes_metadata():
    rational = TiffImagePlugin.IFDRational
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = 6
    exif[ExifTags.Base.ImageDescription] = "private camera metadata"
    exif[ExifTags.IFD.GPSInfo] = {
        1: "N", 2: (rational(38), rational(42), rational(18)),
        3: "W", 4: (rational(9), rational(8), rational(42)),
    }
    original = BytesIO()
    Image.new("RGB", (12, 6)).save(original, "JPEG", exif=exif, comment=b"private JPEG comment")

    gps, cleaned = prepare_checkin_photo(original.getvalue())

    assert gps == pytest.approx((38.705, -9.145))
    with Image.open(BytesIO(cleaned)) as saved:
        assert saved.size == (6, 12)
        assert not saved.getexif()
        assert "comment" not in saved.info


def test_unreadable_camera_photo_is_rejected():
    with pytest.raises(InvalidCheckinPhoto):
        prepare_checkin_photo(b"not a camera image")


def test_camera_photo_without_gps_metadata_can_be_prepared():
    original = BytesIO()
    Image.new("RGB", (12, 6)).save(original, "JPEG")

    gps, cleaned = prepare_checkin_photo(original.getvalue())

    assert gps is None
    with Image.open(BytesIO(cleaned)) as saved:
        assert saved.size == (12, 6)
        assert not saved.getexif()


def test_photo_byte_limit_rejects_before_decoding(monkeypatch):
    monkeypatch.setattr(checkin_photo, "MAX_PHOTO_BYTES", 3)
    decoder = Mock()
    monkeypatch.setattr(checkin_photo.Image, "open", decoder)

    with pytest.raises(InvalidCheckinPhoto, match="upload limit"):
        prepare_checkin_photo(b"1234")

    decoder.assert_not_called()


def test_photo_pixel_limit_accepts_boundary_and_rejects_larger_image(monkeypatch):
    original = BytesIO()
    Image.new("RGB", (12, 6)).save(original, "JPEG")
    monkeypatch.setattr(checkin_photo, "MAX_PHOTO_PIXELS", 72)
    assert prepare_checkin_photo(original.getvalue())[1]
    monkeypatch.setattr(checkin_photo, "MAX_PHOTO_PIXELS", 71)
    with pytest.raises(InvalidCheckinPhoto, match="image limit"):
        prepare_checkin_photo(original.getvalue())


def test_database_client_rejects_unencrypted_remote_connection(monkeypatch):
    import streamlit as st

    monkeypatch.setattr(db, "_client", None)
    monkeypatch.setattr(st, "secrets", {"SUPABASE_URL": "http://project.example.com", "SUPABASE_KEY": "test-only"})
    connect = Mock()
    monkeypatch.setattr(db, "create_client", connect)

    with pytest.raises(RuntimeError, match="requires HTTPS"):
        db.get_client()

    connect.assert_not_called()


def test_photo_download_rechecks_membership_after_it_is_removed(monkeypatch):
    monkeypatch.setattr(db, "_photo_audience", lambda *args: lambda row: True)
    membership = SimpleNamespace(lobby_id="photo-lobby")
    memberships = [membership]
    monkeypatch.setattr(db, "list_memberships_for_player", lambda _: list(memberships))
    client = Mock()
    query = client.table.return_value.select.return_value
    query.eq.return_value = query
    query.execute.return_value.data = [{"photo_ref": "photo-lobby/entry.jpg", "seasons": {"ends_at": "2099-01-01T00:00:00+00:00"}}]
    client.storage.get_bucket.return_value.public = False
    client.storage.from_.return_value.download.return_value = b"clean photo"
    monkeypatch.setattr(db, "get_client", lambda: client)

    assert db.download_checkin_photo("reader", "photo-lobby", "entry") == b"clean photo"
    memberships.clear()
    with pytest.raises(PermissionError):
        db.download_checkin_photo("reader", "photo-lobby", "entry")

    client.storage.from_.return_value.download.assert_called_once()


def test_photo_download_rejects_outsider_before_requesting_image(monkeypatch):
    monkeypatch.setattr(db, "list_memberships_for_player", lambda _: [SimpleNamespace(lobby_id="other-lobby")])
    client = Mock()
    get_client = Mock(return_value=client)
    monkeypatch.setattr(db, "get_client", get_client)

    with pytest.raises(PermissionError):
        db.download_checkin_photo("reader", "photo-lobby", "entry")

    get_client.assert_not_called()


def test_photo_download_rejects_public_bucket(monkeypatch):
    monkeypatch.setattr(db, "_photo_audience", lambda *args: lambda row: True)
    monkeypatch.setattr(db, "list_memberships_for_player", lambda _: [SimpleNamespace(lobby_id="photo-lobby")])
    client = Mock()
    query = client.table.return_value.select.return_value
    query.eq.return_value = query
    query.execute.return_value.data = [{"photo_ref": "photo-lobby/entry.jpg", "seasons": {"ends_at": "2099-01-01T00:00:00+00:00"}}]
    client.storage.get_bucket.return_value.public = True
    monkeypatch.setattr(db, "get_client", lambda: client)

    with pytest.raises(RuntimeError, match="private storage bucket"):
        db.download_checkin_photo("reader", "photo-lobby", "entry")

    client.storage.from_.assert_not_called()


def test_save_retry_recovers_committed_entry_without_uploading_again(monkeypatch):
    timestamp = datetime(2026, 11, 19, 20, tzinfo=timezone.utc)
    entry = DrinkEntry(
        id="capture", membership_id="member", season_id="season", drink_type="beer",
        amount=1, photo_ref="lobby/capture.jpg", device_gps=None, photo_gps=None,
        territory_id="shortys", location_check_result="matched", points_awarded=5,
        submitted_at=timestamp, photo_captured_at=timestamp,
    )
    monkeypatch.setattr(db, "list_memberships_for_player", lambda _: [SimpleNamespace(id="member", lobby_id="lobby")])
    monkeypatch.setattr(db, "list_seasons_for_lobby", lambda _: [SimpleNamespace(id="season")])
    client = Mock()
    client.storage.get_bucket.return_value.public = False
    table = client.table.return_value
    query = table.select.return_value
    query.eq.return_value = query
    row = db._drink_entry_row(entry)
    query.execute.side_effect = [SimpleNamespace(data=[]), SimpleNamespace(data=[row])]
    table.upsert.return_value.execute.side_effect = RuntimeError("Response lost after saving")
    monkeypatch.setattr(db, "get_client", lambda: client)

    with pytest.raises(RuntimeError, match="Response lost"):
        db.save_drink_entry_photo("player", "lobby", entry, b"clean photo")
    recovered = db.save_drink_entry_photo("player", "lobby", replace(entry, points_awarded=15), b"clean photo")

    assert recovered.points_awarded == 5
    assert recovered.photo_captured_at == timestamp
    table.upsert.assert_called_once()
    client.storage.from_.return_value.upload.assert_called_once()


def test_database_serialization_discards_exact_coordinates():
    from tests.test_checkins import IN_WINDOW_TS, INSIDE, TERRITORY
    from core.checkins import create_drink_entry

    entry = create_drink_entry(
        "member", "season", "beer", 1, "photo", INSIDE, None, IN_WINDOW_TS, [TERRITORY], []
    )
    row = db._drink_entry_row(replace(entry, device_gps=INSIDE, photo_gps=INSIDE))
    assert all(row[key] is None for key in ("device_gps_lat", "device_gps_lng", "photo_gps_lat", "photo_gps_lng"))
    assert row["points_awarded"] == entry.points_awarded
    assert row["territory_id"] == entry.territory_id


def test_failed_upload_does_not_record_points(monkeypatch):
    from tests.test_checkins import IN_WINDOW_TS, INSIDE, TERRITORY
    from core.checkins import create_drink_entry
    from storage3.utils import StorageException

    entry = create_drink_entry(
        "member", "season", "beer", 1, "photo", INSIDE, None, IN_WINDOW_TS, [TERRITORY], []
    )
    monkeypatch.setattr(db, "list_memberships_for_player", lambda _: [SimpleNamespace(id="member", lobby_id="lobby")])
    monkeypatch.setattr(db, "list_seasons_for_lobby", lambda _: [SimpleNamespace(id="season")])
    client = Mock()
    client.storage.get_bucket.return_value.public = False
    client.storage.from_.return_value.upload.side_effect = StorageException("Upload failed")
    table = client.table.return_value
    query = table.select.return_value
    query.eq.return_value = query
    query.execute.return_value.data = []
    monkeypatch.setattr(db, "get_client", lambda: client)

    with pytest.raises(StorageException):
        db.save_drink_entry_photo("player", "lobby", entry, b"clean photo")

    table.upsert.assert_not_called()
