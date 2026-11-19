"""Private storage authorization and failure paths without live credentials."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
import uuid
import pytest
import data.db as db
from core.models import Player
from tests.test_profile_photo import picture


@pytest.fixture
def service(monkeypatch):
    client = MagicMock()
    query = client.table.return_value
    for method in ['select', 'eq', 'upsert', 'delete']:
        getattr(query, method).return_value = query
    query.execute.return_value.data = []
    player = Player('owner', 'Owner', 'First', 'Last', 'hash', 'owner@example.test')
    monkeypatch.setattr(db, 'get_client', lambda: client)
    monkeypatch.setattr(db, 'get_player', lambda _: player)
    bucket = MagicMock()
    client.storage.get_bucket.return_value = SimpleNamespace(public=False)
    client.storage.from_.return_value = bucket
    return client, query, bucket, player


def test_owner_save_download_replace_remove(service, monkeypatch):
    client, query, bucket, player = service
    reference = {'path': None}
    monkeypatch.setattr(db, '_profile_picture_row', lambda _: reference['path'])
    def persist(row):
        reference['path'] = row['photo_ref']
        return query
    query.upsert.side_effect = persist
    raw = picture()
    db.save_profile_picture('owner', 'hash', raw)
    first = reference['path']
    assert first.startswith('owner/') and first.endswith('.jpg')
    assert bucket.upload.call_args.args[1] != raw  # normalized JPEG, not original metadata
    bucket.download.return_value = b'authorized bytes'
    assert db.download_profile_picture('owner', 'hash', 'owner') == b'authorized bytes'
    db.save_profile_picture('owner', 'hash', raw)
    assert reference['path'] != first
    bucket.remove.assert_called_with([first])
    current = reference['path']
    db.remove_profile_picture('owner', 'hash')
    bucket.remove.assert_called_with([current])
    assert any(call.args == ('photo_ref', current) for call in query.eq.call_args_list)


def test_outsider_denied_before_reading_storage(service, monkeypatch):
    client, _, bucket, _ = service
    monkeypatch.setattr(db, 'list_friendships', lambda _: [])
    assert db.download_profile_picture('owner', 'hash', 'other') is None
    bucket.download.assert_not_called()
    client.table.assert_not_called()


@pytest.mark.parametrize('status,allowed', [('accepted', True), ('pending', True), ('declined', False)])
def test_friend_status_rechecked_each_download(service, monkeypatch, status, allowed):
    _, query, bucket, _ = service
    monkeypatch.setattr(db, 'list_friendships', lambda _: [{'sender_id': 'owner', 'recipient_id': 'other', 'status': status}])
    monkeypatch.setattr(db, '_profile_picture_row', lambda _: f'other/{uuid.uuid4()}.jpg')
    bucket.download.return_value = b'picture'
    assert db.download_profile_picture('owner', 'hash', 'other') == (b'picture' if allowed else None)


def test_stale_session_and_invalid_upload_never_write(service):
    client, _, bucket, _ = service
    with pytest.raises(ValueError, match='sign-in changed'):
        db.save_profile_picture('owner', 'stale', picture())
    with pytest.raises(ValueError):
        db.save_profile_picture('owner', 'hash', b'invalid')
    client.table.assert_not_called()
    bucket.upload.assert_not_called()


def test_public_bucket_is_rejected(service):
    client, _, bucket, _ = service
    client.storage.get_bucket.return_value.public = True
    with pytest.raises(RuntimeError, match='private'):
        db.save_profile_picture('owner', 'hash', picture())
    bucket.upload.assert_not_called()


def test_upload_or_reference_failure_keeps_old_picture(service, monkeypatch):
    _, query, bucket, _ = service
    old = f'owner/{uuid.uuid4()}.jpg'
    monkeypatch.setattr(db, '_profile_picture_row', lambda _: old)
    bucket.upload.side_effect = RuntimeError('offline')
    with pytest.raises(RuntimeError):
        db.save_profile_picture('owner', 'hash', picture())
    query.upsert.assert_not_called()
    bucket.remove.assert_not_called()
    bucket.upload.side_effect = None
    query.upsert.side_effect = RuntimeError('response lost')
    with pytest.raises(RuntimeError):
        db.save_profile_picture('owner', 'hash', picture())
    bucket.remove.assert_not_called()


def test_wrong_owner_path_cannot_be_read(service, monkeypatch):
    monkeypatch.setattr(db, '_profile_picture_row', lambda _: f'other/{uuid.uuid4()}.jpg')
    with pytest.raises(PermissionError):
        db.download_profile_picture('owner', 'hash', 'owner')
    service[2].download.assert_not_called()


def test_orphan_cleanup_keeps_current_and_recent_uploads(service, monkeypatch):
    _, _, bucket, _ = service
    current, abandoned, recent = [f'{uuid.uuid4()}.jpg' for _ in range(3)]
    now = datetime.now(timezone.utc)
    old_time = (now - timedelta(hours=25)).isoformat()
    rows = [{'name': name, 'id': name, 'updated_at': old_time if name != recent else now.isoformat()}
            for name in [current, abandoned, recent]]
    monkeypatch.setattr(db, '_list_photo_folder', lambda b, folder: [{'name': 'owner', 'id': None}] if not folder else rows)
    monkeypatch.setattr(db, '_profile_picture_row', lambda _: f'owner/{current}')
    assert db.cleanup_profile_pictures() == 1
    bucket.remove.assert_not_called()
    assert db.cleanup_profile_pictures(apply=True) == 1
    bucket.remove.assert_called_once_with([f'owner/{abandoned}'])
