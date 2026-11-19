"""Allowed, rejected and boundary profile edits never replace identity."""
from dataclasses import replace
from unittest.mock import MagicMock
import pytest
from core.auth import hash_password, verify_password
from core.models import Player
from core.profile import edit_profile, change_password
import data.db as db


@pytest.fixture
def player():
    return Player('self', 'Mia', 'Mia', 'Silva', hash_password('password8'), 'mia@example.test')


def test_edit_preserves_identity_and_credentials(player):
    updated = edit_profile(player, ' New ', ' Name ', ' mia ', [{'id': player.id, 'display_name': 'Mia'}])
    assert (updated.first_name, updated.last_name, updated.display_name) == ('New', 'Name', 'mia')
    assert (updated.id, updated.email, updated.pin_hash) == (player.id, player.email, player.pin_hash)
    assert player.first_name == 'Mia'
    assert len(edit_profile(player, 'a', 'b', 'c' * 100, []).display_name) == 100


@pytest.mark.parametrize('first,last,username', [(' ', 'b', 'c'), ('a', '', 'c'), ('a', 'b', ''), ('a', 'b', 'c' * 101)])
def test_invalid_names(player, first, last, username):
    with pytest.raises(ValueError):
        edit_profile(player, first, last, username, [])


def test_duplicate_name(player):
    with pytest.raises(ValueError, match='already taken'):
        edit_profile(player, 'a', 'b', ' OTHER ', [{'id': 'other', 'display_name': 'other'}])


@pytest.mark.parametrize('current,new,confirm', [('wrong', 'newpass8', 'newpass8'), ('password8', 'short', 'short'), ('password8', 'newpass8', 'mismatch'), ('password8', 'password8', 'password8')])
def test_invalid_password_change(player, current, new, confirm):
    with pytest.raises(ValueError):
        change_password(player, current, new, confirm)
    assert verify_password('password8', player.pin_hash)


def test_password_hash_and_identity(player):
    updated = change_password(player, 'password8', 'newpass8', 'newpass8')
    assert verify_password('newpass8', updated.pin_hash)
    assert not verify_password('password8', updated.pin_hash)
    assert replace(updated, pin_hash=player.pin_hash) == player


def test_stale_credentials_cannot_write(player, monkeypatch):
    monkeypatch.setattr(db, 'get_player', lambda _: player)
    client = MagicMock()
    monkeypatch.setattr(db, 'get_client', lambda: client)
    with pytest.raises(ValueError, match='sign-in changed'):
        db.update_profile(player.id, 'old hash', 'a', 'b', 'new')
    client.table.assert_not_called()


def test_save_updates_only_selected_fields_and_checks_credential_version(player, monkeypatch):
    from dataclasses import asdict
    client = MagicMock()
    query = client.table.return_value.update.return_value
    query.eq.return_value = query
    updated = replace(player, display_name='New')
    query.execute.return_value.data = [asdict(updated)]
    monkeypatch.setattr(db, 'get_client', lambda: client)
    monkeypatch.setattr(db, 'get_player', lambda _: player)
    monkeypatch.setattr(db, 'list_public_usernames', lambda: [])
    assert db.update_profile(player.id, player.pin_hash, player.first_name, player.last_name, 'New') == updated
    client.table.return_value.update.assert_called_once_with({'first_name': 'Mia', 'last_name': 'Silva', 'display_name': 'New'})
    assert query.eq.call_args_list[0].args == ('id', player.id)
    assert query.eq.call_args_list[1].args == ('pin_hash', player.pin_hash)
    query.execute.return_value.data = []
    with pytest.raises(ValueError, match='sign-in changed'):
        db.update_profile(player.id, player.pin_hash, 'Mia', 'Silva', 'New')


@pytest.mark.parametrize('allowed,current', [(False, 'password8'), (True, 'wrong')])
def test_throttled_or_wrong_current_password_never_writes(player, monkeypatch, allowed, current):
    monkeypatch.setattr(db, 'get_player', lambda _: player)
    monkeypatch.setattr(db, 'allow_login_attempt', lambda _: allowed)
    client = MagicMock()
    monkeypatch.setattr(db, 'get_client', lambda: client)
    with pytest.raises(ValueError):
        db.update_password(player.id, player.pin_hash, current, 'newpass8', 'newpass8')
    client.table.assert_not_called()
