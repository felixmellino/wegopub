"""The season ranking and territory accounts, using the core's existing order."""

import streamlit as st
from httpx import RequestError
from postgrest.exceptions import APIError

import data.db as db
from parallel import run_parallel
from core.leaderboard import season_leaderboard
from core.lobby_overview import lobby_status
from core.scoring_v1 import current_time, replay_season
from core.territories import territory_owner, territory_standings
from drink_entry_ui import page_header
from leaderboard_context import leaderboard_fallback
import standings_ui
from shared import get_territories, require_active_membership, require_login, show_logged_in_as

player_id = require_login()
show_logged_in_as()

page_header("Leaderboard", hide_title=True)
standings_ui.load_styles()

try:
    if st.session_state.get("current_membership_id") and st.session_state.get("current_season_id"):
        membership_id, lobby_id, season_id = require_active_membership()
        lobby_mode = st.session_state.get("current_lobby_mode")
        season = st.session_state.get("_validated_season")
    else:
        fallback = leaderboard_fallback(player_id)
        if fallback is None:
            st.info("There are no standings to show yet. Join a lobby with a season to see its leaderboard.")
            if st.button("Open Lobby"):
                st.switch_page("pages/2_Lobby.py")
            st.stop()
        lobby, member, season = fallback
        membership_id, lobby_id, season_id = member.id, lobby.id, season.id
        member, season = db.membership_context(player_id, membership_id, lobby_id, season_id)
        if member is None or season is None:
            st.warning("That lobby or season is no longer available. Reload the page to try again.")
            st.stop()
        lobby_mode = lobby.game_mode
    entries, transfers, memberships, players = run_parallel(
        lambda: db.list_drink_entries(season_id),
        lambda: db.list_season_transfers(season_id),
        lambda: db.list_memberships_for_lobby(lobby_id, include_left=True),
        db.list_players)
    players_by_id = {p.id: p.display_name for p in players}
except (APIError, RequestError, RuntimeError):
    st.error("We couldn't load the standings. Reload the page to try again.")
    st.stop()

names = {m.id: players_by_id.get(m.player_id, "Unknown player") for m in memberships}
team_mode = lobby_mode == "team" or any(e.team_id for e in entries)
if team_mode:
    try:
        teams = db.list_lobby_teams(player_id, lobby_id)
    except (APIError, RequestError, RuntimeError, PermissionError):
        st.error("Teams could not be loaded. Reload the page to try again.")
        st.stop()
    names = {t.id: t.name for t in teams}
    membership_id = next((m.team_id for m in memberships if m.id == membership_id), None)
    if not membership_id:
        st.info("Open this lobby on the Lobby page and join a team before checking in.")
snapshot = replay_season(entries, transfers) if transfers or any(e.rule_version == "v1" for e in entries) else None
leaderboard = snapshot.season_rows() if snapshot else season_leaderboard(entries)
status = lobby_status(season, current_time()) if season else "active"
if status == "past":
    st.caption("Finished season · Final standings")
elif status == "upcoming":
    st.caption("Upcoming season")

# Reuse the same territory accounts for the pills. A territory service
# failure must not hide a successfully loaded season ranking.
territory_data = []
territories_available = True
try:
    for territory in get_territories():
        owner = snapshot.owners.get(territory.id) if snapshot else territory_owner(entries, territory.id)
        rows = snapshot.territory_rows(territory.id) if snapshot else territory_standings(entries, territory.id)
        territory_data.append((territory, owner, rows))
except (APIError, RequestError, RuntimeError):
    territories_available = False
    territory_data = []

if not leaderboard:
    st.info("No points logged yet this season.")
else:
    standings_ui.leaderboard(leaderboard, names, membership_id, team_mode=team_mode)

if not territories_available:
    st.warning("Territory standings are unavailable. Reload the page to try again.")
elif not territory_data:
    st.info("No territories have been set up yet.")
else:
    standings_ui.territory_pills(territory_data, names, membership_id)
