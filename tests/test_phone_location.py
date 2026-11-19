"""The location prompt after login and the session reading it stores."""
import time

from streamlit.testing.v1 import AppTest


def run(monkeypatch, browser_reply):
    monkeypatch.setattr("phone_location._phone_location", lambda **kwargs: browser_reply(kwargs))

    def page():
        import streamlit as st
        from phone_location import ask_for_location, current_location
        ask_for_location()
        st.write(repr(current_location()))

    return AppTest.from_function(page).run()


def test_login_asks_once_and_stores_the_reading(monkeypatch):
    calls = []

    def reply(kwargs):
        calls.append(kwargs)
        return {"lat": 38.6782, "lng": -9.3259, "accuracy_m": 15, "taken_at_ms": time.time() * 1000}

    page = run(monkeypatch, reply)
    assert not page.exception
    assert calls[0]["once"] is True and calls[0]["key"] == "location_permission"
    assert "(38.6782, -9.3259), 15.0, None" in page.markdown[0].value


def test_blocked_location_is_reported(monkeypatch):
    page = run(monkeypatch, lambda kwargs: {"error": "denied"})
    assert "'denied'" in page.markdown[0].value


def test_nothing_yet_while_the_browser_is_asking(monkeypatch):
    page = run(monkeypatch, lambda kwargs: None)
    assert "'waiting'" in page.markdown[0].value


def test_asks_only_once_per_session(monkeypatch):
    calls = []

    def reply(kwargs):
        calls.append(kwargs)
        return {"lat": 38.6782, "lng": -9.3259, "accuracy_m": 15, "taken_at_ms": time.time() * 1000}

    page = run(monkeypatch, reply)
    page.run()
    page.run()
    assert len(calls) == 1


def test_keeps_asking_until_the_browser_has_answered(monkeypatch):
    calls = []

    def reply(kwargs):
        calls.append(kwargs)
        return None  # the prompt is still open

    page = run(monkeypatch, reply)
    page.run()
    assert len(calls) == 2
