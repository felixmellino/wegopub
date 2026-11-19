"""Database wrapper contracts; PostgreSQL itself needs a live integration check."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import data.db as db


def client_with_rows(rows):
    client = MagicMock()
    query = client.table.return_value
    query.select.return_value = query
    query.eq.return_value = query
    query.execute.return_value.data = rows
    return client


def test_response_uses_current_version_for_atomic_write():
    row = {"sender_id": "a", "recipient_id": "b", "status": "pending", "version": "v1"}
    client = client_with_rows([row])
    with patch("data.db.get_client", return_value=client):
        db.change_friendship("b", "a", "accept")
    client.rpc.assert_called_once_with("save_friendship", {
        "sender": "a", "recipient": "b", "next_status": "accepted", "expected_version": "v1"})


def test_first_request_expects_no_existing_version():
    client = client_with_rows([])
    with patch("data.db.get_client", return_value=client):
        db.change_friendship("a", "b", "request")
    assert client.rpc.call_args.args[1]["expected_version"] is None


@pytest.mark.parametrize("action", ["accept", "decline", "request"])
def test_rejected_action_does_not_write(action):
    row = {"sender_id": "a", "recipient_id": "b", "status": "declined",
           "updated_at": datetime.now(timezone.utc).isoformat(), "version": "v1"}
    client = client_with_rows([row])
    with patch("data.db.get_client", return_value=client), pytest.raises(ValueError):
        db.change_friendship("a", "b", action)
    client.rpc.assert_not_called()


def test_search_fetches_public_columns_only_and_paginates():
    client = MagicMock()
    query = client.table.return_value
    for method in ("select", "order", "range"):
        getattr(query, method).return_value = query
    query.execute.side_effect = [MagicMock(data=[{"id": str(i), "display_name": str(i)} for i in range(1000)]), MagicMock(data=[{"id": "last", "display_name": "Last"}])]
    with patch("data.db.get_client", return_value=client):
        users = db.list_public_usernames()
    assert len(users) == 1001
    assert all(call.args == ("id,display_name",) for call in query.select.call_args_list)
    assert query.range.call_args_list[-1].args == (1000, 1999)
