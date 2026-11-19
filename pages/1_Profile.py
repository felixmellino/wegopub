"""Private account menu; each option opens a focused view."""
import streamlit as st
from httpx import RequestError
from postgrest.exceptions import APIError
from profile_ui import show_profile
from shared import require_login, authenticated_player

player_id = require_login()
try:
    show_profile(authenticated_player())
except (APIError, RequestError, RuntimeError, OSError):
    st.error("Profile is unavailable. Please try again later.")
