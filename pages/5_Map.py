"""Map: the 12 territories coloured by owner, the points needed to take each
one, and where you are right now (followed automatically, R-L01/R-L04).
Only the current lobby's season counts."""

import streamlit as st
import base64
from functools import partial
from httpx import RequestError
from postgrest.exceptions import APIError

import data.db as db
import map_ui
from profile_picture_ui import load_picture, PICTURE_ERRORS
from core.constants import MAX_GPS_ACCURACY_M
from core.location import evaluate_location
from parallel import run_parallel
from phone_location import current_location, track_location
from shared import get_territories, require_active_membership, require_login, show_logged_in_as

player_id = require_login()
show_logged_in_as()
membership_id, lobby_id, season_id = require_active_membership()

map_ui.load_styles()

track_location()
try:
    territories = get_territories()
    entries, memberships, players = run_parallel(
        lambda: db.list_drink_entries(season_id),
        lambda: db.list_memberships_for_lobby(lobby_id, include_left=True),
        db.list_players)
    players_by_id = {p.id: p.display_name for p in players}
except (APIError, RequestError, RuntimeError):
    st.error("We couldn't load the map. Reload the page to try again.")
    st.stop()

names = {m.id: players_by_id.get(m.player_id, "Unknown player") for m in memberships}
team_mode = False
teams = []
if st.session_state.get("current_lobby_mode") == "team" or any(e.team_id for e in entries):
    team_mode = True
    try:
        teams = db.list_lobby_teams(player_id, lobby_id)
        names = {t.id: t.name for t in teams}
    except (APIError, RequestError, RuntimeError, PermissionError):
        st.error("Teams could not be loaded. Reload to try again.")
        st.stop()
    membership_id = next((m.team_id for m in memberships if m.id == membership_id), None)
rows = map_ui.territory_rows(territories, entries, membership_id, names)

# Load only owners' pictures, using the existing audience checks on every render.
owner_ids = {row["owner_id"] for row in rows if row["owner_id"]}
pictures = {}
if team_mode:
    for team in teams:
        if team.id in owner_ids and team.photo_base64:
            try:
                pictures[team.id] = base64.b64decode(team.photo_base64, validate=True)
            except ValueError:
                pass  # A missing/unreadable photo still has an initials badge.
else:
    def fetch_picture(member):
        try:
            return member.id, load_picture(player_id, member.player_id)
        except (*PICTURE_ERRORS, PermissionError):
            return None  # A missing/unreadable photo still has an initials badge.
    if st.session_state.get("credential_version"):
        fetched = run_parallel(*[partial(fetch_picture, m) for m in memberships if m.id in owner_ids])
        pictures = dict(result for result in fetched if result)

# Where am I? Decides the bottom card and whether "Me" is offered.
location, accuracy_m, problem = current_location()
usable_location = location is not None and accuracy_m <= MAX_GPS_ACCURACY_M
here, status = None, "waiting"
if usable_location:
    result, territory_id = evaluate_location(location, accuracy_m, territories)
    here = next((row for row in rows if row["id"] == territory_id), None)
    status = "matched" if result == "matched" and here else "outside"
elif location is not None:
    status = "inaccurate"
elif problem == "denied":
    status = "denied"

# HUD floating over the top of the map: lobby, score, quick zoom.
with st.container(key="game_hud"):
    map_ui.hud(st.session_state.get("current_lobby_name", "Your lobby"), rows)
    options = ([map_ui.ME] if usable_location else []) + list(map_ui.AREAS) + [map_ui.ALL]
    focus = st.segmented_control("Show", options, default=options[0], key="map_focus",
                                 label_visibility="collapsed") or options[0]
    if focus not in options:  # e.g. "Me" was picked but the location is gone now
        focus = options[0]

with st.container(key="game_map"):
    map_ui.render_map(rows, location if usable_location else None, accuracy_m, focus,
                      pictures=pictures,
                      context=f"{lobby_id}:{season_id}:{membership_id}")

# Slim sheet over the bottom of the map: where you are, and the full
# territory list (opens upwards inside the sheet). Checking in is the + tab.
with st.container(key="game_card"):
    map_ui.location_card(here, status, accuracy_m)
    with st.expander("All territories"):
        if team_mode:
            st.caption("Team territories · Points and capture gaps combine all team members’ drinks.")
        map_ui.territory_list(rows)
