"""Check token lifetime, password changes, and revocation against a fake data service."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import data.db as db
from core.auth import token_hash
from core.lobbies import create_player


class FakeClient:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        assert name == "remembered_sessions"
        return Query(self.rows)


class Query:
    def __init__(self, rows):
        self.rows, self.filters = rows, {}
        self.operation, self.payload = "select", None

    def select(self, fields):
        return self

    def insert(self, payload):
        self.operation, self.payload = "insert", payload
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def eq(self, name, value):
        self.filters[name] = value
        return self

    def execute(self):
        if self.operation == "insert":
            self.rows.append(self.payload.copy())
            return SimpleNamespace(data=[self.payload])
        matches = [r for r in self.rows if all(r[k] == v for k, v in self.filters.items())]
        if self.operation == "delete":
            self.rows[:] = [r for r in self.rows if r not in matches]
        return SimpleNamespace(data=matches)


@pytest.fixture
def service():
    player = create_player("mia", "Mia", "Silva", "mia@example.com", "password8", "password8", [])
    rows = []
    with patch("data.db.get_client", side_effect=lambda: FakeClient(rows)), \
         patch("data.db.get_player", return_value=player):
        yield player, rows


def test_remembered_token_survives_new_client_and_is_not_plaintext(service):
    player, rows = service
    token = db.create_remembered_session(player)
    assert token not in str(rows)
    assert "password8" not in str(rows)
    assert rows[0]["token_hash"] == token_hash(token)
    assert rows[0]["credential_version"] != player.pin_hash
    assert datetime.fromisoformat(rows[0]["expires_at"]) > datetime.now(timezone.utc) + timedelta(days=29)
    # Each operation receives a new client, as after an app restart.
    assert db.get_remembered_player(token) == player


def test_unknown_and_tampered_token_cannot_authenticate(service):
    player, _ = service
    token = db.create_remembered_session(player)
    assert db.get_remembered_player(token[:-1] + ("x" if token[-1] != "x" else "y")) is None
    assert db.get_remembered_player("forged") is None
    assert db.get_remembered_player("") is None


def test_expired_token_is_rejected_and_removed(service):
    _, rows = service
    token = db.create_remembered_session(service[0])
    rows[0]["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    assert db.get_remembered_player(token) is None
    assert not rows


def test_password_change_invalidates_remembered_device(service):
    player, rows = service
    token = db.create_remembered_session(player)
    with patch("data.db.get_player", return_value=replace(player, pin_hash="changed-credential")):
        assert db.get_remembered_player(token) is None
    assert not rows


def test_logout_revokes_only_this_device(service):
    player, rows = service
    first, other = db.create_remembered_session(player), db.create_remembered_session(player)
    db.revoke_remembered_session(first)
    assert db.get_remembered_player(first) is None
    assert db.get_remembered_player(other) == player
    assert len(rows) == 1
