import hashlib

import pytest

from core.auth import (authenticate, hash_password, new_token, normalize_email,
                       token_hash, validate_password, verify_password)
from core.lobbies import create_player
from core.models import Player


@pytest.fixture
def player():
    return create_player("mia", "Mia", "Silva", "mia@example.com", "password8", "password8", [])


def test_password_hash_is_salted_and_verifies():
    first, second = hash_password("password8"), hash_password("password8")
    assert first != second
    assert "password8" not in first
    assert verify_password("password8", first)
    assert not verify_password("wrong-password", first)


@pytest.mark.parametrize("stored", ["", "corrupt", "x:y", "999999999:a:b", "a:b:c:d"])
def test_malformed_hash_is_rejected(stored):
    assert not verify_password("password8", stored)


def test_email_login_ignores_case_and_whitespace(player):
    assert authenticate(" MIA@EXAMPLE.COM ", "password8", [player]) == player
    assert authenticate("mia", "password8", [player]) is None
    assert authenticate(player.email, "wrong", [player]) is None
    assert authenticate("unknown@example.com", "password8", [player]) is None


@pytest.mark.parametrize("password,confirmation", [("1234567", "1234567"), ("password8", "different"), ("        ", "        "), ("x" * 1025, "x" * 1025)])
def test_invalid_passwords_rejected(password, confirmation):
    with pytest.raises(ValueError):
        validate_password(password, confirmation)


def test_exactly_eight_characters_allowed():
    validate_password("abc12345", "abc12345")


@pytest.mark.parametrize("email", ["", "a", "a@b", "a b@example.com", "a@example.com\nBcc:evil@example.com"])
def test_invalid_emails_rejected(email):
    with pytest.raises(ValueError):
        normalize_email(email)


def test_create_normalizes_fields():
    p = create_player(" Mia ", " Mia ", " Silva ", " MIA@EXAMPLE.COM ", "password8", "password8", [])
    assert (p.display_name, p.first_name, p.last_name, p.email) == ("Mia", "Mia", "Silva", "mia@example.com")


@pytest.mark.parametrize("username,email", [("MIA", "other@example.com"), ("other", "MIA@EXAMPLE.COM")])
def test_duplicate_accounts_rejected(player, username, email):
    with pytest.raises(ValueError):
        create_player(username, "A", "B", email, "password8", "password8", [player])


@pytest.mark.parametrize("first,last,username", [(" ", "B", "C"), ("A", " ", "C"), ("A", "B", " ")])
def test_empty_names_rejected(first, last, username):
    with pytest.raises(ValueError):
        create_player(username, first, last, "a@example.com", "password8", "password8", [])


def legacy_player():
    salt = bytes.fromhex("ab" * 16)
    digest = hashlib.pbkdf2_hmac("sha256", b"1234", salt, 200_000)
    return Player("original-player-id", "mia", "Mia", "Silva", f"{salt.hex()}:{digest.hex()}")


def test_legacy_player_cannot_log_in_without_email():
    old = legacy_player()
    assert verify_password("1234", old.pin_hash)
    assert authenticate("mia@example.com", "1234", [old]) is None


def test_device_tokens_are_random_and_only_hash_is_stored():
    code, stored = new_token()
    other, _ = new_token()
    assert code != other
    assert len(code) >= 40
    assert code != stored
    assert token_hash(code) == stored
    assert token_hash(" " + code + " ") == stored
