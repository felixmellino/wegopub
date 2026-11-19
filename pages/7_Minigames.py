"""Minigames in the selected lobby; server RPCs recheck every action."""
import streamlit as st
import data.db as db
from minigames_ui import render_minigames, _error, SERVICE_ERRORS
from shared import lobby_button, require_login, require_active_membership, selected_season

player = require_login()
member, lobby_id, season_id = require_active_membership()
try:
    season = selected_season(lobby_id, season_id)
    lobby = next((l for l in db.list_lobbies() if l.id == lobby_id), None)
    if not season or not lobby:
        st.info("Choose a lobby and season on the Lobby page.")
        lobby_button()
    elif season.scoring_version != "v1":
        st.info("Chug Duel requires a lobby with v1 scoring. Historical seasons keep their original rules.")
    else:
        render_minigames(player, member, lobby, season)
except (ValueError, PermissionError) + SERVICE_ERRORS as error:
    _error(error)
