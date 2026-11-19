"""Photo privacy checks with stateful database/storage doubles, without secrets."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import data.db as db
from core.checkin_photo import photo_expires_at
from storage3.utils import StorageException
from streamlit.testing.v1 import AppTest

NOW = datetime(2026, 12, 17, 20, tzinfo=timezone.utc)
END = NOW - timedelta(days=30)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


@pytest.fixture
def store(monkeypatch):
    rows = {
        "entry": {
            "id": "entry", "photo_ref": "lobby/entry.jpg", "points_awarded": 5,
            "submitted_at": END.isoformat(), "photo_captured_at": END.isoformat(),
            "location_check_result": "matched", "territories": {"name": "Shortys"},
            "seasons": {"lobby_id": "lobby", "ends_at": (END + timedelta(seconds=1)).isoformat()},
            "lobby_memberships": {"lobby_id": "lobby", "player_id": "author", "players": {"display_name": "Mia"}},
        },
    }
    files = {"lobby/entry.jpg": {"bytes": b"clean photo", "updated_at": END.isoformat()}}
    members = [SimpleNamespace(player_id=p, team_id=None) for p in ("author", "reader", "guest")]
    preferences = {p: {"player_id": p, "share_checkin_photos": True} for p in ("author", "guest")}
    state = SimpleNamespace(rows=rows, files=files, members=members, preferences=preferences,
                            downloads=0, removes=0, fail_remove=False, fail_update=False)

    class Query:
        def __init__(self, table):
            self.table = table
            self.filters = {}
            self.in_filters = {}
            self.changes = None

        def select(self, _):
            return self

        def eq(self, key, value):
            self.filters[key] = value
            return self

        def in_(self, key, values):
            self.in_filters[key] = values
            return self

        def range(self, *args):
            return self

        def order(self, *args, **kwargs):
            return self

        def update(self, changes):
            self.changes = changes
            return self

        def execute(self):
            matching = []
            source = preferences if self.table == "player_photo_preferences" else rows
            for row in source.values():
                def value(key):
                    parts = key.split(".")
                    result = row
                    for part in parts:
                        result = result[part]
                    return result
                if (all(value(key) == expected for key, expected in self.filters.items())
                        and all(value(key) in values for key, values in self.in_filters.items())):
                    if self.changes:
                        if state.fail_update:
                            raise RuntimeError("Database unavailable after file removal")
                        row.update(self.changes)
                    matching.append(deepcopy(row))
            return SimpleNamespace(data=matching)

    class Bucket:
        def download(self, path):
            state.downloads += 1
            if path not in files:
                raise StorageException("Photo not found")
            return files[path]["bytes"]

        def remove(self, paths):
            if state.fail_remove:
                raise RuntimeError("Storage unavailable")
            state.removes += 1
            for path in paths:
                files.pop(path, None)
            return []

        def list(self, path, options):
            if path == "":
                entries = [{"name": folder, "id": None} for folder in sorted({key.split("/")[0] for key in files})]
            else:
                entries = [
                    {"name": key.split("/")[1], "id": key, "updated_at": obj.get("updated_at")}
                    for key, obj in sorted(files.items()) if key.startswith(path + "/")
                ]
            return entries[options["offset"]:options["offset"] + options["limit"]]

    bucket = Bucket()
    monkeypatch.setattr(db, "datetime", Clock)
    monkeypatch.setattr(db, "_private_photo_bucket", lambda: bucket)
    monkeypatch.setattr(db, "get_client", lambda: SimpleNamespace(table=Query))
    monkeypatch.setattr(db, "list_memberships_for_player", lambda player: [] if player == "outsider" else [SimpleNamespace(lobby_id="lobby")])
    monkeypatch.setattr(db, "list_memberships_for_lobby", lambda _: list(members))
    return state


@pytest.mark.parametrize("offset,available", [(-1, True), (0, False), (1, False)])
def test_expiry_at_exact_boundary_denies_download_even_before_cleanup(store, offset, available):
    store.rows["entry"]["seasons"]["ends_at"] = (END - timedelta(seconds=offset)).isoformat()
    assert bool(db.list_checkin_photos("reader", "lobby")) is available
    assert (db.download_checkin_photo("reader", "lobby", "entry") is not None) is available
    assert store.downloads == int(available)
    assert "lobby/entry.jpg" in store.files
    assert store.rows["entry"]["points_awarded"] == 5


def test_expiry_normalizes_offsets_and_legacy_naive_season_dates():
    assert photo_expires_at(END.replace(tzinfo=None)) == NOW
    assert photo_expires_at(END.astimezone(timezone(timedelta(hours=2)))) == NOW


def test_owner_deletes_image_and_preserves_score_on_repeated_request(store):
    assert db.list_checkin_photos("author", "lobby")[0]["is_owner"]
    before = deepcopy(store.rows["entry"])
    db.delete_checkin_photo("author", "lobby", "entry")
    db.delete_checkin_photo("author", "lobby", "entry")
    assert not store.files
    assert store.rows["entry"] == {**before, "photo_ref": "deleted"}
    assert db.download_checkin_photo("reader", "lobby", "entry") is None
    assert store.removes == 1


@pytest.mark.parametrize("player", ["reader", "outsider"])
def test_another_player_cannot_delete_the_photo(store, player):
    with pytest.raises(PermissionError):
        db.delete_checkin_photo(player, "lobby", "entry")
    assert "lobby/entry.jpg" in store.files
    assert store.rows["entry"]["photo_ref"] == "lobby/entry.jpg"
    assert store.removes == 0


def test_cross_lobby_entry_cannot_be_opened_or_deleted(store):
    store.rows["entry"]["seasons"]["lobby_id"] = "another-lobby"
    assert db.list_checkin_photos("author", "lobby") == []
    assert db.download_checkin_photo("author", "lobby", "entry") is None
    with pytest.raises(PermissionError):
        db.delete_checkin_photo("author", "lobby", "entry")
    assert store.downloads == store.removes == 0


def test_failed_storage_deletion_leaves_reference_and_score_for_retry(store):
    store.fail_remove = True
    with pytest.raises(RuntimeError):
        db.delete_checkin_photo("author", "lobby", "entry")
    assert "lobby/entry.jpg" in store.files
    assert store.rows["entry"]["photo_ref"] == "lobby/entry.jpg"
    assert store.rows["entry"]["points_awarded"] == 5
    store.fail_remove = False
    db.delete_checkin_photo("author", "lobby", "entry")
    assert not store.files


def test_deletion_retries_when_database_fails_after_file_is_removed(store):
    store.fail_update = True
    with pytest.raises(RuntimeError):
        db.delete_checkin_photo("author", "lobby", "entry")
    assert not store.files
    store.fail_update = False
    db.delete_checkin_photo("author", "lobby", "entry")
    assert store.rows["entry"]["photo_ref"] == "deleted"
    assert store.rows["entry"]["points_awarded"] == 5


def test_cleanup_dry_run_apply_and_repeat_keep_active_and_recent_uploads(store):
    # The linked file expires exactly now. New uploads have time to retry.
    store.rows["entry"]["seasons"]["ends_at"] = END.isoformat()
    store.files["lobby/abandoned.jpg"] = {"updated_at": (NOW - timedelta(hours=24)).isoformat()}
    store.files["lobby/retrying.jpg"] = {"updated_at": (NOW - timedelta(hours=24) + timedelta(seconds=1)).isoformat()}
    store.files["lobby/unknown-age.jpg"] = {}
    active = deepcopy(store.rows["entry"])
    active.update(id="active", photo_ref="lobby/active.jpg")
    active["seasons"]["ends_at"] = NOW.isoformat()
    store.rows["active"] = active
    store.files["lobby/active.jpg"] = {"updated_at": END.isoformat()}
    before_rows, before_files = deepcopy(store.rows), deepcopy(store.files)

    assert db.cleanup_checkin_photos() == {"expired": 1, "unlinked": 1}
    assert store.rows == before_rows and store.files == before_files
    assert db.cleanup_checkin_photos(apply=True) == {"expired": 1, "unlinked": 1}
    assert set(store.files) == {"lobby/active.jpg", "lobby/retrying.jpg", "lobby/unknown-age.jpg"}
    assert store.rows["entry"] == {**before_rows["entry"], "photo_ref": "expired"}
    assert store.rows["active"] == active
    assert db.cleanup_checkin_photos(apply=True) == {"expired": 0, "unlinked": 0}


def test_cleanup_reads_all_pages_without_skipping_deleted_objects(store):
    for number in range(205):
        store.files[f"lobby/orphan-{number:03d}.jpg"] = {"updated_at": END.isoformat()}
    assert db.cleanup_checkin_photos(apply=True) == {"expired": 0, "unlinked": 205}
    assert set(store.files) == {"lobby/entry.jpg"}


def test_cleanup_failure_can_be_retried_without_changing_score(store):
    store.rows["entry"]["seasons"]["ends_at"] = END.isoformat()
    store.fail_remove = True
    with pytest.raises(RuntimeError):
        db.cleanup_checkin_photos(apply=True)
    assert store.rows["entry"]["photo_ref"] == "lobby/entry.jpg"
    assert store.rows["entry"]["points_awarded"] == 5
    store.fail_remove = False
    assert db.cleanup_checkin_photos(apply=True) == {"expired": 1, "unlinked": 0}


def photo_page(monkeypatch, player="author"):
    monkeypatch.setattr("shared.require_login", lambda: player)
    monkeypatch.setattr("shared.require_active_membership", lambda: ("member", "lobby", "season"))
    monkeypatch.setattr("shared.show_logged_in_as", lambda: None)
    return AppTest.from_file(str(Path(__file__).resolve().parents[1] / "pages/6_Check_in_photos.py")).run()


def delete_button(page):
    return next(button for button in page.button if button.label == "Delete my photo")


def test_owner_can_confirm_deletion_through_photo_page(store, monkeypatch):
    page = photo_page(monkeypatch)
    assert not page.exception
    assert delete_button(page).disabled
    page.checkbox[0].check().run()
    assert not delete_button(page).disabled
    delete_button(page).click().run()
    assert not page.exception
    assert any("score is unchanged" in message.value for message in page.success)
    assert not page.get("html")
    assert store.rows["entry"]["points_awarded"] == 5
    assert not store.files


def test_other_member_can_view_but_has_no_delete_button(store, monkeypatch):
    page = photo_page(monkeypatch, "reader")
    assert not page.exception
    assert len(page.get("html")) == 1
    assert not page.button and not page.checkbox


def test_legacy_photo_detail_displays_the_original_drink_and_points(store, monkeypatch):
    store.rows["entry"]["drink_type"] = "beer"
    page = photo_page(monkeypatch)
    assert not page.exception
    markup = "\n".join(item.value for item in page.markdown)
    assert "Beer" in markup and "+5 season pts" in markup
    assert store.rows["entry"]["points_awarded"] == 5


def test_photo_context_treats_usernames_and_territories_as_text(store, monkeypatch):
    payload = '<img src=x onerror="alert(1)">'
    store.rows["entry"]["lobby_memberships"]["players"]["display_name"] = payload
    store.rows["entry"]["territories"]["name"] = payload
    page = photo_page(monkeypatch)
    assert not page.exception
    markup = "\n".join(element.value for element in page.markdown)
    assert payload not in markup
    assert "&lt;img" in markup


def test_owner_can_delete_when_photo_download_service_fails(store, monkeypatch):
    def unavailable(*args):
        raise RuntimeError("Download unavailable")
    monkeypatch.setattr(db, "download_checkin_photo", unavailable)
    page = photo_page(monkeypatch)
    assert not page.exception and page.error
    page.checkbox[0].check().run()
    delete_button(page).click().run()
    assert not page.exception
    assert any("score is unchanged" in message.value for message in page.success)
    assert not store.files
    assert store.rows["entry"]["points_awarded"] == 5


def test_photo_page_can_retry_deletion_after_file_removed_and_database_failed(store, monkeypatch):
    page = photo_page(monkeypatch)
    page.checkbox[0].check().run()
    store.fail_update = True
    delete_button(page).click().run()
    assert not page.exception and page.error
    assert not store.files
    store.fail_update = False
    delete_button(page).click().run()
    assert not page.exception
    assert any("score is unchanged" in message.value for message in page.success)
    assert store.rows["entry"]["photo_ref"] == "deleted"
    assert store.rows["entry"]["points_awarded"] == 5
