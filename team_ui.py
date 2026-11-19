"""Team cards in a lobby dialog. Rules and atomic writes stay in core/data."""
import base64
from html import escape

import streamlit as st
from httpx import RequestError
from postgrest.exceptions import APIError

import data.db as db
from core.profile_photo import initials
from core.scoring_v1 import format_points
from core.leaderboard import season_leaderboard
from profile_picture_ui import load_picture, PICTURE_ERRORS

ERRORS = (APIError, RequestError, RuntimeError, PermissionError, ValueError)


def avatar(name, photo=None):
    content = (f'<img src="data:image/jpeg;base64,{escape(photo, quote=True)}" alt="Team picture" style="width:64px;height:64px;border-radius:50%;object-fit:cover">'
               if photo else f'<span style="display:inline-grid;place-items:center;background:#d4e9de;border-radius:50%;width:64px;height:64px;font-size:24px">{escape(initials(name))}</span>')
    st.markdown(content, unsafe_allow_html=True)


def dismiss_lobby_dialog():
    st.session_state.pop('_lobby_dialog', None)
    st.session_state.pop('_opened_lobby_id', None)


@st.dialog("Lobby teams", width="large", on_dismiss=dismiss_lobby_dialog)
def open_team_lobby(player_id, lobby, season, *, finished=False):
    notice = st.session_state.pop('_team_notice', None) or st.session_state.pop('_lobby_notice', None)
    if notice:
        st.success(notice)
    try:
        teams = db.list_lobby_teams(player_id, lobby.id)
        members = db.list_memberships_for_lobby(lobby.id, include_left=True)
        me = next((m for m in members if m.player_id == player_id and m.left_at is None), None)
        names = {p['id']: p['display_name'] for p in db.list_public_usernames()}
        entries = db.list_drink_entries(season.id) if season else []
        transfers = db.list_season_transfers(season.id) if season else []
    except ERRORS:
        st.error('Teams could not be loaded. Close and reopen the lobby to try again.')
        return
    if me is None:
        dismiss_lobby_dialog()
        st.error('Your lobby membership is no longer available. Close this window and refresh your lobbies.')
        return
    st.text(lobby.name)
    st.code(lobby.invite_code, language=None)
    locked = any(e.membership_id == me.id for e in entries)
    totals = dict(season_leaderboard(entries, transfers))
    st.caption(f'{lobby.team_count} teams · {lobby.team_capacity} players per team · ' +
               ('Random assignment' if lobby.team_assignment == 'random' else 'Choose your team'))
    if not me.team_id:
        st.info('Join a team below before checking in. Your team locks after your first scored check-in.')
    elif locked:
        st.caption('Your team is locked because you have scored. Team members can still edit its name and picture.')
    for index, team in enumerate(teams):
        if index % 2 == 0:
            columns = st.columns(2)
        teammates = [m for m in members if m.team_id == team.id]
        own = me.team_id == team.id
        with columns[index % 2].container(border=True):
            avatar(team.name, team.photo_base64)
            if own:
                with st.popover(team.name, help='Edit your team name and picture'):
                    st.caption('Only members of this team can edit it.')
                    with st.form(f'edit_team_{team.id}'):
                        name = st.text_input('Team name', value=team.name, max_chars=40)
                        uploaded = st.file_uploader('Upload team picture', type=['jpg', 'jpeg', 'png', 'webp'], max_upload_size=10)
                        captured = st.camera_input('Take team picture')
                        remove = st.checkbox('Remove team picture')
                        saved = st.form_submit_button('Save team')
                    if saved:
                        try:
                            if remove and (captured or uploaded):
                                raise ValueError('Choose a new picture or remove the current one.')
                            picture = captured or uploaded
                            db.edit_lobby_team(player_id, team.id, name, picture.getvalue() if picture else None, remove_photo=remove)
                        except ERRORS as error:
                            st.error(str(error) if isinstance(error, ValueError) else 'The team could not be saved. Try again.')
                        else:
                            st.session_state['_team_notice'] = 'Team updated.'
                            st.rerun()
            else:
                st.text(team.name)
            st.caption(f'Team {team.number} · {len(teammates)}/{lobby.team_capacity} members · {format_points(totals.get(team.id, 0))} points' + (' · YOUR TEAM' if own else ''))
            for member in teammates:
                label = names.get(member.player_id, 'Lobby member')
                try:
                    picture = load_picture(player_id, member.player_id)
                except PICTURE_ERRORS:
                    picture = None
                # Existing profile-picture privacy remains authoritative.
                if picture:
                    st.markdown(f'<img src="data:image/jpeg;base64,{base64.b64encode(picture).decode("ascii")}" alt="Member picture" style="width:28px;height:28px;border-radius:50%">', unsafe_allow_html=True)
                st.text((label if picture else f'{initials(label)} · {label}') + (' · Left (slot reserved)' if member.left_at else ''))
            if not teammates:
                st.caption('No members yet')
            if lobby.team_assignment == 'manual' and not own:
                if st.button('Team full' if len(teammates) >= lobby.team_capacity else 'Join team', key=f'join_team_{team.id}',
                             disabled=finished or locked or len(teammates) >= lobby.team_capacity):
                    try:
                        db.choose_lobby_team(player_id, lobby.id, team.id)
                    except ERRORS as error:
                        st.error(str(error) if isinstance(error, ValueError) else 'Could not join this team. Try again.')
                    else:
                        st.session_state['_team_notice'] = 'Team joined.'
                        st.rerun()
    if season and st.button('View leaderboard', width='stretch'):
        dismiss_lobby_dialog()
        st.switch_page('pages/4_Standings.py')
    if season is None:
        from lobby_ui import retry_setup
        retry_setup(player_id, lobby)
    from lobby_ui import delete_lobby_controls, leave_lobby_controls
    leave_lobby_controls(player_id, lobby)
    delete_lobby_controls(player_id, lobby)
    if st.button('Close', key='close_lobby_teams'):
        dismiss_lobby_dialog()
        st.rerun()
