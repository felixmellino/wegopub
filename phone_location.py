"""Automatic phone location for the Check-in and Map pages (R-L01, R-L04).

track_location() mounts an invisible browser component that follows the
phone's GPS while the page is open and keeps the newest reading in this
session only. current_location() returns that reading after checking it
(core/location.py's parse_phone_reading): valid numbers, accuracy, age.
Nothing here is written to the database.
"""

import time
from pathlib import Path

import streamlit as st
from streamlit.components.v1 import declare_component

from core.location import parse_phone_reading

_phone_location = declare_component(
    "phone_location", path=str(Path(__file__).parent / "components" / "phone_location")
)

_READING_KEY = "live_location_reading"


def track_location() -> None:
    """Start following the phone's position on this page. The browser asks
    for permission once per site; after that it runs without any button."""
    value = _phone_location(key="live_location_tracker", default=None)
    if value is not None:
        st.session_state[_READING_KEY] = value


def ask_for_location() -> None:
    """Ask for the phone's location once per login session, right after
    login, so the browser's permission prompt appears straight away. After
    the browser has answered (allowed or blocked), other pages don't ask
    again; only Check-in and Map keep following the location."""
    if st.session_state.get("_location_asked"):
        return
    value = _phone_location(once=True, key="location_permission", default=None)
    if value is not None:
        st.session_state[_READING_KEY] = value
        st.session_state["_location_asked"] = True


def current_location():
    """(device_gps, accuracy_m, problem) for the newest reading in this
    session; problem is None when the reading can be used."""
    return parse_phone_reading(st.session_state.get(_READING_KEY), now_ms=time.time() * 1000)
