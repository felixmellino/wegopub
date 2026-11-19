"""Consent, direct-download enforcement and historical attribution."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import data.db as db
from core.photo_privacy import can_view_photo
from photo_history_ui import identity_colour
from tests.test_photo_lifecycle import store, photo_page


def member(player, team=None):
    return SimpleNamespace(player_id=player, team_id=team)


@pytest.mark.parametrize("viewer,team,sharing,expected", [
    ("owner", None, {}, True),
    ("other", None, {}, False),
    ("other", None, {"owner": True}, True),
    ("outsider", None, {"owner": True}, False),
    ("mate", "a", {}, True),
    ("other", "a", {"owner": True}, False),
    ("other", "a", {"owner": True, "mate": True}, True),
    ("other", "a", {"owner": False, "mate": True}, False),
    ("other", "missing-team", {"owner": True}, False),
])
def test_audience_matrix(viewer, team, sharing, expected):
    members = [member("owner", "a"), member("mate", "a"), member("other", "b")]
    assert can_view_photo(viewer, "owner", team, members, sharing) is expected


def test_new_and_departing_teammates_recheck_consent_for_existing_photos():
    members = [member("owner", "a"), member("other", "b")]
    sharing = {"owner": True}
    assert can_view_photo("other", "owner", "a", members, sharing)
    members.append(member("new", "a"))
    assert not can_view_photo("other", "owner", "a", members, sharing)
    sharing["new"] = True
    assert can_view_photo("other", "owner", "a", members, sharing)
    # A former uploader's OFF must still protect their old photos.
    members[0].team_id = "b"
    sharing["owner"] = False
    assert not can_view_photo("other", "owner", "a", members, sharing)
    assert can_view_photo("owner", "owner", "a", members, sharing)


def test_off_hides_existing_cards_and_blocks_direct_download_without_changing_points(store, monkeypatch):
    before = deepcopy(store.rows)
    store.preferences.clear()
    assert db.list_checkin_photos("reader", "lobby") == []
    with pytest.raises(PermissionError, match="private"):
        db.download_checkin_photo("reader", "lobby", "entry")
    assert store.downloads == 0
    assert db.list_checkin_photos("author", "lobby")[0]["is_owner"]
    assert db.download_checkin_photo("author", "lobby", "entry") == b"clean photo"
    page = photo_page(monkeypatch, "reader")
    assert not page.exception and page.info and not page.get("html")
    store.preferences["author"] = {"player_id": "author", "share_checkin_photos": True}
    assert db.list_checkin_photos("reader", "lobby")
    assert db.download_checkin_photo("reader", "lobby", "entry") == b"clean photo"
    # A previously listed card grants no permission after revocation.
    store.preferences["author"]["share_checkin_photos"] = False
    with pytest.raises(PermissionError):
        db.download_checkin_photo("reader", "lobby", "entry")
    assert store.rows == before


def test_team_internal_access_and_unanimous_opponent_access(store, monkeypatch):
    store.rows["entry"]["team_id"] = "a"
    store.members[:] = [member("author", "a"), member("guest", "a"), member("reader", "b")]
    monkeypatch.setattr(db, "list_lobby_teams", lambda *args: [SimpleNamespace(id="a", name="Sky Team")])
    store.preferences["guest"]["share_checkin_photos"] = False
    assert db.list_checkin_photos("reader", "lobby") == []
    with pytest.raises(PermissionError):
        db.download_checkin_photo("reader", "lobby", "entry")
    assert db.download_checkin_photo("guest", "lobby", "entry") == b"clean photo"
    card = db.list_checkin_photos("guest", "lobby")[0]
    assert (card["team_id"], card["team_name"], card["player_id"]) == ("a", "Sky Team", "author")
    store.preferences["guest"]["share_checkin_photos"] = True
    assert db.download_checkin_photo("reader", "lobby", "entry") == b"clean photo"
    store.members.append(member("new", "a"))
    assert not db.list_checkin_photos("reader", "lobby")
    with pytest.raises(PermissionError):
        db.download_checkin_photo("reader", "lobby", "entry")


def test_duel_copies_follow_their_owners_independently(store):
    second = deepcopy(store.rows["entry"])
    second.update(id="second", photo_ref="lobby/second.jpg", duel_id="duel")
    second["lobby_memberships"]["player_id"] = "guest"
    store.rows["entry"]["duel_id"] = "duel"
    store.rows["second"] = second
    store.files["lobby/second.jpg"] = {"bytes": b"clean photo"}
    store.preferences["author"]["share_checkin_photos"] = False
    assert [r["id"] for r in db.list_checkin_photos("reader", "lobby")] == ["second"]
    assert db.download_checkin_photo("reader", "lobby", "second") == b"clean photo"
    with pytest.raises(PermissionError):
        db.download_checkin_photo("reader", "lobby", "entry")


def test_consent_read_failure_never_downloads(store, monkeypatch):
    original = db.get_client
    def client():
        service = original()
        table = service.table
        def select(name):
            if name == "player_photo_preferences":
                raise RuntimeError("offline")
            return table(name)
        service.table = select
        return service
    monkeypatch.setattr(db, "get_client", client)
    with pytest.raises(RuntimeError):
        db.download_checkin_photo("reader", "lobby", "entry")
    assert store.downloads == 0


def test_saved_preference_survives_new_client_and_rejects_stale_session(monkeypatch):
    saved = {}
    actor = SimpleNamespace(pin_hash="current")
    monkeypatch.setattr(db, "get_player", lambda _: actor)
    clients = []
    def client():
        service = Mock()
        query = service.table.return_value
        query.select.return_value = query
        query.eq.return_value = query
        query.upsert.side_effect = lambda row, **kwargs: (saved.update(row) or query)
        query.execute.side_effect = lambda: SimpleNamespace(data=[dict(saved)] if saved else [])
        clients.append(service)
        return service
    monkeypatch.setattr(db, "get_client", client)
    assert not db.get_photo_sharing("owner", "current")
    db.save_photo_sharing("owner", "current", True)
    assert db.get_photo_sharing("owner", "current")
    db.save_photo_sharing("owner", "current", False)
    assert not db.get_photo_sharing("owner", "current")
    calls = len(clients)
    with pytest.raises(ValueError, match="sign-in changed"):
        db.save_photo_sharing("owner", "old-password", True)
    with pytest.raises(ValueError):
        db.save_photo_sharing("owner", "current", "true")
    assert len(clients) == calls and saved["share_checkin_photos"] is False


def test_identity_colour_is_stable_for_renames_and_shared_for_teammates():
    entry = {"player_id": "one", "username": "Mia"}
    assert identity_colour(entry) == identity_colour({**entry, "username": "New Mia"})
    assert identity_colour(entry) != identity_colour({**entry, "player_id": "two"})
    assert identity_colour({**entry, "team_id": "a"}) == identity_colour({"username": "Other", "player_id": "two", "team_id": "a"})
