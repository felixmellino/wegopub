"""Exercise the installed SDK parsers against HTTP fixtures, without secrets."""
from types import SimpleNamespace

import httpx
import pytest
from storage3 import SyncStorageClient
from storage3.utils import StorageException
from postgrest import SyncPostgrestClient
from postgrest.exceptions import APIError

import data.db as db


@pytest.mark.parametrize('public', [False, True])
def test_live_bucket_response_with_versioning_status(monkeypatch, public):
    payload = {
        'id': 'check-in-photos', 'name': 'check-in-photos', 'owner': '',
        'public': public, 'created_at': '2026-11-18T00:00:00Z',
        'updated_at': '2026-11-18T00:00:00Z', 'file_size_limit': None,
        'allowed_mime_types': None, 'versioning_status': 'DISABLED',
    }
    def request(client, method, url, **kwargs):
        return httpx.Response(200, json=payload, request=httpx.Request(method, str(url)))
    monkeypatch.setattr(httpx.Client, 'request', request)
    storage = SyncStorageClient('https://storage.example.invalid/', {})
    monkeypatch.setattr(db, 'get_client', lambda: SimpleNamespace(storage=storage))
    if public:
        with pytest.raises(RuntimeError, match='private storage bucket'):
            db._private_photo_bucket()
    else:
        assert db._private_photo_bucket() is not None


def test_storage_http_error_matches_existing_handlers(monkeypatch):
    def request(client, method, url, **kwargs):
        return httpx.Response(403, json={'statusCode': '403', 'error': 'Forbidden',
            'message': 'Permission denied'}, request=httpx.Request(method, str(url)))
    monkeypatch.setattr(httpx.Client, 'request', request)
    storage = SyncStorageClient('https://storage.example.invalid/', {})
    monkeypatch.setattr(db, 'get_client', lambda: SimpleNamespace(storage=storage))
    with pytest.raises(StorageException):
        db._private_photo_bucket()


def test_postgrest_wire_error_reaches_scoring_translation():
    def respond(request):
        return httpx.Response(400, json={'code': 'P0001', 'message': 'cooldown',
            'details': None, 'hint': None})
    from core.checkins import CheckinRejected
    from unittest.mock import patch
    with SyncPostgrestClient('https://database.example.invalid') as client:
        with httpx.Client(transport=httpx.MockTransport(respond),
                          base_url='https://database.example.invalid') as session:
            client.session = session
            with patch.object(db, 'get_client', return_value=client):
                with pytest.raises(CheckinRejected, match='cooldown'):
                    db._scoring_rpc('accept_scoring_checkin', {})


def test_postgrest_error_attributes_used_by_app():
    error = APIError({'code': 'PGRST202', 'message': 'Missing function', 'details': None, 'hint': None})
    assert error.code == 'PGRST202' and error.message == 'Missing function'
