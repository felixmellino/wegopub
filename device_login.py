"""Remember a device using an opaque token, never the player's password."""
from __future__ import annotations

from pathlib import Path
import uuid

import streamlit as st
from streamlit.components.v1 import declare_component

import data.db as db

_browser_storage = declare_component(
    "remember_device", path=str(Path(__file__).parent / "components" / "remember_device")
)


def queue_storage(action: str, token: str = "") -> None:
    st.session_state["_device_command"] = {
        "action": action, "token": token, "request_id": str(uuid.uuid4()),
    }


def sync_storage() -> str | None:
    """Mount the browser bridge; None means its first read has not returned yet."""
    # The iframe can outlive the server session (for example after reconnecting).
    # A constant read ID would be ignored by its lastRequest deduplication after
    # Python has lost the previous result. Keep a fresh ID for each session,
    # stable across reruns while waiting for the browser's reply.
    if "_device_read_id" not in st.session_state:
        st.session_state["_device_read_id"] = str(uuid.uuid4())
    command = st.session_state.get("_device_command", {
        "action": "read", "request_id": st.session_state["_device_read_id"], "token": "",
    })
    result = _browser_storage(**command, key="remember_device", default=None)
    if not isinstance(result, dict) or result.get("request_id") != command["request_id"]:
        if "_device_command" in st.session_state:
            st.info("Updating your sign-in preference…")
            st.stop()
        return None
    st.session_state.pop("_device_command", None)
    if not result.get("available"):
        st.caption("This browser blocks device storage. You can still log in for this visit.")
    token = result.get("token", "")
    return token if isinstance(token, str) else ""


def set_identity(player) -> None:
    st.session_state.update({
        "player_id": player.id,
        "player_display_name": player.display_name,
        "player_first_name": player.first_name,
        "player_last_name": player.last_name,
        "credential_version": player.pin_hash,
    })


def finish_login(player, remember: bool = False) -> None:
    # Create the persistent record before authenticating: a database failure
    # must leave the form usable and must not create a half-saved preference.
    token = db.create_remembered_session(player) if remember else ""
    st.session_state.clear()
    set_identity(player)
    st.session_state["_remember_attempted"] = True
    st.session_state["_device_token"] = token
    queue_storage("write" if remember else "clear", token)
    st.rerun()


def log_out() -> None:
    token = st.session_state.get("_device_token", "")
    if token:
        db.revoke_remembered_session(token)
    st.session_state.clear()
    st.session_state["_remember_attempted"] = True
    queue_storage("clear")
    st.rerun()
