"""Joined lobby overview and dedicated lobby detail views."""
import streamlit as st

from lobby_ui import show_lobbies
from shared import require_login, show_logged_in_as

player_id = require_login()
show_logged_in_as()
st.title("Lobby")
show_lobbies(player_id)
