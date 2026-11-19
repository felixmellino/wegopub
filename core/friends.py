"""Friendship rules. Only public usernames leave the search function."""
from __future__ import annotations

from datetime import datetime, timedelta

DECLINE_WAIT = timedelta(minutes=10)


def search_usernames(query: str, usernames: list[dict], player_id: str) -> list[dict]:
    query = query.strip().casefold()
    if not query:
        return []
    return sorted(
        [{"id": p["id"], "display_name": p["display_name"]} for p in usernames
         if p["id"] != player_id and query in p["display_name"].casefold()],
        key=lambda p: (p["display_name"].casefold(), p["id"]),
    )[:20]


def transition(actor: str, other: str, action: str, current: dict | None, now: datetime) -> dict:
    """Validate an action and return the next relationship, without saving it."""
    if actor == other:
        raise ValueError("You cannot send yourself a friend request.")
    if current and {actor, other} != {current["sender_id"], current["recipient_id"]}:
        raise ValueError("This friendship belongs to other players.")
    status = current["status"] if current else None
    if action == "request":
        if status == "pending":
            raise ValueError("A request is already pending. Check incoming or outgoing requests.")
        if status == "accepted":
            raise ValueError("You are already friends.")
        if status == "declined" and now < datetime.fromisoformat(current["updated_at"]) + DECLINE_WAIT:
            raise ValueError("Wait 10 minutes after a declined request before requesting again.")
        return {"sender_id": actor, "recipient_id": other, "status": "pending"}
    if not current:
        raise ValueError("No friendship request exists.")
    if action in ("accept", "decline"):
        if status != "pending" or actor != current["recipient_id"]:
            raise ValueError("Only the recipient can accept or decline a pending request.")
        next_status = "accepted" if action == "accept" else "declined"
    elif action == "cancel":
        if status != "pending" or actor != current["sender_id"]:
            raise ValueError("Only the sender can cancel a pending request.")
        next_status = "cancelled"
    elif action == "remove":
        if status != "accepted":
            raise ValueError("Only an accepted friend can be removed.")
        next_status = "removed"
    else:
        raise ValueError("Unknown friendship action.")
    return {"sender_id": current["sender_id"], "recipient_id": current["recipient_id"], "status": next_status}
