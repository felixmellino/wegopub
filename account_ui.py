"""The account screen shared by the first visit and Profile page."""

from pathlib import Path

import streamlit as st
from postgrest.exceptions import APIError
from httpx import RequestError

import data.db as db
import theme
from core.auth import authenticate
from core.password_recovery import RESET_MESSAGE
from core.lobbies import create_player
from device_login import finish_login

_CSS = Path(__file__).parent / "assets" / "account.css"


def show_error(error):
    if isinstance(error, ValueError):
        st.error(str(error))
    elif isinstance(error, APIError) and error.code == "23505":
        st.error("That username or email is already registered.")
    else:
        st.error("Account service is unavailable. Please try again later.")


def show_accounts():
    st.markdown(f"<style>{_CSS.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    with st.container(key="account_scene"):
        theme.wordmark()
        st.caption("Track drinks, claim territory, win the season.")
        action = st.radio("Choose an action", ["Create account", "Log in"], horizontal=True,
                           key="account_action", label_visibility="collapsed")
        if action == "Create account":
            st.caption("Only your username is public. Your name and email stay private.")
            with st.form("create_account"):
                first = st.text_input("First name")
                last = st.text_input("Surname")
                username = st.text_input("Username")
                email = st.text_input("Email")
                password = st.text_input("Password", type="password", help="At least 8 characters")
                confirmation = st.text_input("Confirm password", type="password")
                submitted = st.form_submit_button("Create account")
            if submitted:
                try:
                    player = create_player(username, first, last, email, password, confirmation, db.list_players())
                    db.insert_player(player)
                    finish_login(player)
                except (ValueError, APIError, RuntimeError, OSError, RequestError) as exc:
                    show_error(exc)

        else:
            if st.session_state.get("_password_recovery"):
                show_password_recovery()
                return
            with st.form("login"):
                email = st.text_input("Email", key="login_email")
                password = st.text_input("Password", type="password", key="login_password")
                remember = st.checkbox("Remember password", help="Keep me signed in on this device for 30 days.")
                submitted = st.form_submit_button("Log in")
            if submitted:
                try:
                    players = db.list_players()
                    candidate = next((p for p in players if p.email and p.email == email.strip().lower()), None)
                    if candidate and not db.allow_login_attempt(candidate.id):
                        raise ValueError("Too many login attempts. Try again in 15 minutes.")
                    player = authenticate(email, password, players)
                    if player:
                        finish_login(player, remember)
                    else:
                        st.error("Email or password is incorrect.")
                except (ValueError, APIError, RuntimeError, OSError, RequestError) as exc:
                    show_error(exc)
            if st.button("Forgot password?"):
                st.session_state["_password_recovery"] = True
                st.rerun()


def show_password_recovery():
    st.subheader("Forgot password")
    st.caption("Request a code at your registered email address, then enter it below. Codes expire after 15 minutes.")
    with st.form("request_password_reset"):
        email = st.text_input("Registered email", max_chars=254)
        requested = st.form_submit_button("Send reset code")
    if requested:
        try:
            db.request_password_reset(email)
            st.session_state["_recovery_email"] = email.strip().lower()
            st.info(RESET_MESSAGE)
        except (ValueError, APIError, RuntimeError, OSError, RequestError) as exc:
            show_error(exc)
    with st.form("reset_password", clear_on_submit=True):
        reset_email = st.text_input("Account email", value=st.session_state.get("_recovery_email", ""), max_chars=254)
        code = st.text_input("Reset code", max_chars=40, help="Paste the code from your email, including or excluding hyphens.")
        password = st.text_input("New password", type="password", max_chars=1024, help="At least 8 characters; choose a different password.")
        confirmation = st.text_input("Confirm new password", type="password", max_chars=1024)
        submitted = st.form_submit_button("Reset password")
    if submitted:
        try:
            db.reset_password(reset_email, code, password, confirmation)
            st.success("Password reset. Use Back to log in to sign in with your new password. Previous sign-ins are no longer valid.")
        except (ValueError, APIError, RuntimeError, OSError, RequestError) as exc:
            show_error(exc)
    if st.button("Back to log in"):
        st.session_state.pop("_password_recovery", None)
        st.session_state.pop("_recovery_email", None)
        st.rerun()
