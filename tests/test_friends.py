"""Allowed, rejected and boundary cases for private friendships."""
from datetime import datetime, timedelta, timezone

import pytest

from core.friends import search_usernames, transition

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)


def relationship(status="pending"):
    return {"sender_id": "a", "recipient_id": "b", "status": status,
            "updated_at": NOW.isoformat(), "version": "v1"}


def test_request_accept_and_remove_from_either_side():
    pending = transition("a", "b", "request", None, NOW)
    accepted = transition("b", "a", "accept", pending, NOW)
    assert accepted["status"] == "accepted"
    for actor, other in [("a", "b"), ("b", "a")]:
        assert transition(actor, other, "remove", accepted, NOW)["status"] == "removed"


@pytest.mark.parametrize("action", ["accept", "decline"])
def test_only_recipient_can_respond(action):
    with pytest.raises(ValueError, match="Only the recipient"):
        transition("a", "b", action, relationship(), NOW)
    assert transition("b", "a", action, relationship(), NOW)["status"] in ("accepted", "declined")


def test_cancellation_and_request_again():
    cancelled = transition("a", "b", "cancel", relationship(), NOW)
    assert cancelled["status"] == "cancelled"
    assert transition("a", "b", "request", cancelled, NOW)["status"] == "pending"
    with pytest.raises(ValueError, match="Only the sender"):
        transition("b", "a", "cancel", relationship(), NOW)


@pytest.mark.parametrize("actor,other", [("a", "b"), ("b", "a")])
def test_duplicate_and_crossed_requests_do_not_auto_accept(actor, other):
    with pytest.raises(ValueError, match="already pending"):
        transition(actor, other, "request", relationship(), NOW)
    with pytest.raises(ValueError, match="already friends"):
        transition(actor, other, "request", relationship("accepted"), NOW)


@pytest.mark.parametrize("actor,other", [("a", "b"), ("b", "a")])
def test_decline_wait_exact_boundary(actor, other):
    declined = relationship("declined")
    with pytest.raises(ValueError, match="10 minutes"):
        transition(actor, other, "request", declined, NOW + timedelta(minutes=10, microseconds=-1))
    assert transition(actor, other, "request", declined, NOW + timedelta(minutes=10))["status"] == "pending"


def test_self_unknown_and_nonparticipant_actions_rejected():
    with pytest.raises(ValueError, match="yourself"):
        transition("a", "a", "request", None, NOW)
    with pytest.raises(ValueError, match="other players"):
        transition("c", "a", "accept", relationship(), NOW)
    for action in ("accept", "decline", "cancel", "remove"):
        with pytest.raises(ValueError):
            transition("a", "b", action, None, NOW)
    with pytest.raises(ValueError, match="Unknown"):
        transition("a", "b", "invalid", relationship(), NOW)
    with pytest.raises(ValueError):
        transition("b", "a", "accept", relationship("accepted"), NOW)
    with pytest.raises(ValueError):
        transition("a", "b", "remove", relationship(), NOW)


def test_search_partial_case_insensitive_private_and_bounded():
    users = [{"id": str(i), "display_name": f"Mia{i:02}", "email": "private", "first_name": "private"} for i in range(25)]
    results = search_usernames("  mIA ", users, "0")
    assert len(results) == 20
    assert all(set(r) == {"id", "display_name"} and r["id"] != "0" for r in results)
    assert search_usernames(" ", users, "0") == []
    assert search_usernames("%", users, "0") == []
    assert search_usernames("unknown", users, "0") == []
