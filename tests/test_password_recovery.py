"""Recovery validation, delivery boundary and database integration contract."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

import data.db as db
import password_email
from core.auth import verify_password
from core.lobbies import create_player
from core.password_recovery import RESET_ERROR, new_reset_code, reset_code_hash


@pytest.fixture
def player():
    return create_player("mia", "Mia", "Silva", "mia@example.com", "password8", "password8", [])


@pytest.fixture
def backend(player, monkeypatch):
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = True
    monkeypatch.setattr(db, "get_client", lambda: client)
    monkeypatch.setattr(db, "_player_by_email", lambda _: player)
    monkeypatch.setattr(db, "allow_login_attempt", lambda _: True)
    monkeypatch.setattr(password_email, "email_settings", lambda: {"configured": True})
    return client


def test_random_codes_and_normalization():
    code = new_reset_code()
    assert len(code) == 19
    assert code != new_reset_code()
    hashed = reset_code_hash(code, "credential")
    assert hashed == reset_code_hash(" " + code.lower().replace("-", " ") + " ", "credential")
    assert hashed != reset_code_hash(code, "changed credential")
    assert code not in hashed


@pytest.mark.parametrize("code", ["", "123456", "G" * 16, "A" * 17, "A" * 10000])
def test_invalid_codes(code):
    with pytest.raises(ValueError, match="incorrect"):
        reset_code_hash(code, "credential")


def test_request_normalizes_email_and_stores_only_hash(backend, player):
    with patch("password_email.send_reset_email") as send:
        db.request_password_reset(" MIA@EXAMPLE.COM ")
    email, code, settings = send.call_args.args
    assert email == player.email
    args = backend.rpc.call_args.args
    assert args == ("issue_password_reset", {"target_player": player.id,
                     "new_code_hash": reset_code_hash(code, player.pin_hash)})
    assert code not in str(backend.mock_calls)


@pytest.mark.parametrize("unknown,throttled,issued", [(True, False, True), (False, True, True), (False, False, False)])
def test_request_unknown_throttled_or_cooldown_sends_nothing(backend, monkeypatch, unknown, throttled, issued):
    if unknown:
        monkeypatch.setattr(db, "_player_by_email", lambda _: None)
    monkeypatch.setattr(db, "allow_login_attempt", lambda _: not throttled)
    backend.rpc.return_value.execute.return_value.data = issued
    with patch("password_email.send_reset_email") as send:
        assert db.request_password_reset("mia@example.com") is None
    send.assert_not_called()


def test_failed_delivery_removes_only_its_code(backend, player):
    with patch("password_email.send_reset_email", side_effect=RuntimeError("private provider response")):
        assert db.request_password_reset(player.email) is None
    stored = backend.rpc.call_args.args[1]["new_code_hash"]
    delete = backend.table.return_value.delete.return_value
    delete.eq.assert_called_once_with("player_id", player.id)
    delete.eq.return_value.eq.assert_called_once_with("code_hash", stored)


def test_reset_hashes_password_and_calls_atomic_consume(backend, player):
    db.reset_password(" MIA@EXAMPLE.COM ", "ABCD-1234-ABCD-1234", "newpass8", "newpass8")
    name, args = backend.rpc.call_args.args
    assert name == "consume_password_reset"
    assert args["target_email"] == player.email
    assert args["supplied_code_hash"] == reset_code_hash("ABCD1234ABCD1234", player.pin_hash)
    assert verify_password("newpass8", args["new_password_hash"])
    assert not verify_password("password8", args["new_password_hash"])
    assert player.email == "mia@example.com"  # No identity/game writes.
    backend.table.assert_not_called()


def test_database_rejected_code_never_reports_success(backend):
    # The atomic RPC owns expiry, replacement and single-use enforcement.
    backend.rpc.return_value.execute.return_value.data = False
    with pytest.raises(ValueError, match="incorrect"):
        db.reset_password("mia@example.com", "ABCD1234ABCD1234", "newpass8", "newpass8")


@pytest.mark.parametrize("password,confirmation", [("short", "short"), ("newpass8", "mismatch"), ("password8", "password8")])
def test_invalid_or_unchanged_password_never_consumes_code(backend, password, confirmation):
    with pytest.raises(ValueError):
        db.reset_password("mia@example.com", "ABCD1234ABCD1234", password, confirmation)
    backend.rpc.assert_not_called()


@pytest.mark.parametrize("unknown", [True, False])
def test_unknown_or_throttled_reset_has_same_error(backend, monkeypatch, unknown):
    if unknown:
        monkeypatch.setattr(db, "_player_by_email", lambda _: None)
    else:
        monkeypatch.setattr(db, "allow_login_attempt", lambda _: False)
    with pytest.raises(ValueError) as error:
        db.reset_password("mia@example.com", "ABCD1234ABCD1234", "newpass8", "newpass8")
    assert str(error.value) == RESET_ERROR
    backend.rpc.assert_not_called()


def test_mail_payload_has_html_plaintext_and_no_external_tracking():
    payload = password_email.reset_email("ABCD-1234-ABCD-1234")
    assert payload["subject"] == "WeGoPub — Reset your password"
    for key in ("textContent", "htmlContent"):
        assert "ABCD-1234-ABCD-1234" in payload[key]
        assert "15 minutes" in payload[key]
        assert "only be used once" in payload[key]
        assert "password has not changed" in payload[key]
    assert "<img" not in payload["htmlContent"]
    assert "<script" not in payload["htmlContent"]
    assert "&lt;test&gt;" in password_email.reset_email("<test>")["htmlContent"]


def test_brevo_request_uses_server_key_and_fixed_https_endpoint(monkeypatch):
    response = MagicMock()
    response.__enter__.return_value = SimpleNamespace(status=201)
    with patch("password_email.urlopen", return_value=response) as post:
        password_email.send_reset_email("mia@example.com", "ABCD1234ABCD1234", {
            "BREVO_API_KEY": "private-key", "BREVO_SENDER_EMAIL": "wegopub@outlook.com"})
    request = post.call_args.args[0]
    assert request.full_url == "https://api.brevo.com/v3/smtp/email"
    assert request.get_header("Api-key") == "private-key"
    assert post.call_args.kwargs["timeout"] == 10
    assert b"private-key" not in request.data


@pytest.mark.parametrize("error", [URLError("secret"), TimeoutError("secret"),
    HTTPError("https://api.brevo.com", 429, "private recipient", {}, None)])
def test_provider_failures_hide_details(error):
    with patch("password_email.urlopen", side_effect=error):
        with pytest.raises(RuntimeError, match="^Email delivery failed.$"):
            password_email.send_reset_email("mia@example.com", "ABCD1234ABCD1234", {
                "BREVO_API_KEY": "private-key", "BREVO_SENDER_EMAIL": "wegopub@outlook.com"})
