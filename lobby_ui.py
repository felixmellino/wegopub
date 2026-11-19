"""Joined lobby cards. Existing ranking and picture access remain authoritative."""
import base64
from datetime import datetime, timezone
from functools import partial
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
from httpx import RequestError
from postgrest.exceptions import APIError

import data.db as db
from core.checkins import CheckinRejected
from core.leaderboard import season_leader
from core.lobby_overview import latest_season, lobby_status, time_left
from core.profile_photo import initials
from core.scoring_v1 import utc
from profile_picture_ui import PICTURE_ERRORS, load_picture
from friends_ui import friendship_action
from parallel import run_parallel
from core.lobbies import lobby_creator
from theme import button_icons
from lobby_selection import clear_selection, select_lobby, remember_choice
from lobby_forms_ui import create_dialog, join_dialog, dismiss_dialog

LOAD_ERRORS = (APIError, RequestError, RuntimeError)


def finish_label(season):
    return utc(season.ends_at).astimezone(ZoneInfo(season.timezone_name)).strftime('%d %b %Y, %H:%M %Z')


def card(lobby, season, status, now, leader_name=None, photo=None, ranking_available=True):
    name = escape(leader_name or 'No Leader')
    avatar = ''
    if status == 'active' and leader_name:
        picture = (f'<img src="data:image/jpeg;base64,{base64.b64encode(photo).decode("ascii")}" alt="Leader profile picture">'
                   if photo else escape(initials(leader_name)))
        avatar = f'<span class="lobby-avatar">{picture}</span>'
    label = 'Winner' if status == 'past' else 'Leader'
    result = (f'{label}: <strong>{name}</strong>' if leader_name else name) if ranking_available else 'Standings unavailable'
    meta = {'active': 'Running', 'past': 'Finished', 'setup': 'Setup incomplete', 'upcoming': 'Upcoming'}[status]
    if season and season.scoring_rules and season.scoring_rules.get('test_mode'):
        meta += ' · Test season (Wed 08:00–Sun 18:00)'
    if lobby.game_mode == 'team':
        meta += f' · Team mode · {lobby.team_count} × {lobby.team_capacity}'
    timing = (f'Finished {finish_label(season)}' if status == 'past' else
              f'{time_left(season.ends_at, now)} left · Ends {finish_label(season)}' if status == 'active' else
              'Competition has not started yet' if status == 'upcoming' else 'No competition dates yet')
    progress = ''
    if status == 'active':
        total = (utc(season.ends_at) - utc(season.starts_at)).total_seconds()
        elapsed = (utc(now) - utc(season.starts_at)).total_seconds()
        fraction = max(0.0, min(1.0, elapsed / total)) if total > 0 else 1.0
        progress = f'<div class="lobby-progress"><span style="width:{fraction:.1%}"></span></div>'
    st.markdown(f'<article class="lobby-card lobby-{status}"><p class="lobby-meta">{meta}</p>'
                f'<h3>{escape(lobby.name)}</h3><div class="lobby-person">{avatar}<span>{result}</span></div>'
                f'<p class="lobby-countdown">{escape(timing)}</p>{progress}'
                f'<p>Invite code: <strong>{escape(lobby.invite_code)}</strong></p></article>', unsafe_allow_html=True)


def show_lobby_members(player_id, lobby_id):
    """Show public usernames and only the viewer's own friendship state."""
    st.subheader('Lobby members')
    try:
        members = db.list_memberships_for_lobby(lobby_id)
        if not any(m.player_id == player_id for m in members):
            st.error('You are no longer a member of this lobby.')
            return
        names = {p['id']: p['display_name'] for p in db.list_public_usernames()}
    except (*LOAD_ERRORS, OSError):
        st.error('Lobby members could not be loaded. Use Refresh lobbies to try again.')
        return
    try:
        relationships = db.list_friendships(player_id)
    except (*LOAD_ERRORS, OSError):
        relationships = None
        st.warning('Friend requests are unavailable. Use Refresh lobbies to try again.')
    by_other = {r['recipient_id'] if r['sender_id'] == player_id else r['sender_id']: r
                for r in relationships or []}
    for other in sorted({m.player_id for m in members},
                        key=lambda pid: (names.get(pid, '').casefold(), pid)):
        username, controls = st.columns([2, 3])
        with username:
            st.text(names.get(other, 'Unknown player'))
        with controls:
            relationship = by_other.get(other, {})
            status = relationship.get('status')
            if other == player_id:
                st.caption('You')
            elif relationships is None:
                st.caption('Friend status unavailable')
            elif status == 'accepted':
                st.caption('Friends')
            elif status == 'pending' and relationship['recipient_id'] == player_id:
                st.caption('Incoming friend request')
                accept, decline = st.columns(2)
                with accept:
                    friendship_action(player_id, 'Accept', other, 'accept',
                                      key_prefix=f'lobby_{lobby_id}', refresh_label='Refresh lobbies')
                with decline:
                    friendship_action(player_id, 'Decline', other, 'decline',
                                      key_prefix=f'lobby_{lobby_id}', refresh_label='Refresh lobbies')
            elif status == 'pending':
                st.caption('Request sent')
            else:
                if status == 'declined':
                    st.caption('After a decline, wait 10 minutes before sending another request.')
                friendship_action(player_id, 'Add friend', other, 'request',
                                  key_prefix=f'lobby_{lobby_id}', refresh_label='Refresh lobbies')


def show_overview_actions(player_id):
    create, join = st.columns(2)
    with create:
        if st.button('Create a lobby', key='open_create_lobby', icon=':material/add:', type='primary', width='stretch'):
            dismiss_members()
            st.session_state['_lobby_dialog'] = 'create'
    with join:
        if st.button('Join with a code', key='open_join_lobby', icon=':material/login:', width='stretch'):
            dismiss_members()
            st.session_state['_lobby_dialog'] = 'join'

    if st.session_state.get('_lobby_dialog') == 'create':
        create_dialog(player_id)
    elif st.session_state.get('_lobby_dialog') == 'join':
        join_dialog(player_id)


def show_summary(player_id, lobby, season, status, now):
    leader_name, photo, available = None, None, True
    entries = []
    if season:
        try:
            entries, transfers = run_parallel(lambda: db.list_drink_entries(season.id),
                                              lambda: db.list_season_transfers(season.id))
            leader = season_leader(entries, transfers)
            if leader:
                if lobby.game_mode == 'team':
                    teams = db.list_lobby_teams(player_id, lobby.id)
                    winning = next((team for team in teams if team.id == leader), None)
                    leader_name = winning.name if winning else 'Team'
                    photo = base64.b64decode(winning.photo_base64) if winning and winning.photo_base64 else None
                else:
                    leader_name = db.membership_display_name(leader, lobby.id)
                if status == 'active' and lobby.game_mode == 'individual':
                    members = db.list_memberships_for_lobby(lobby.id)
                    owner = next((m.player_id for m in members if m.id == leader), None)
                    if owner:
                        try:
                            photo = load_picture(player_id, owner)
                        except PICTURE_ERRORS:
                            pass
        except LOAD_ERRORS:
            available = False
    card(lobby, season, status, now, leader_name, photo, available)
    return entries, available


def retry_setup(player_id, lobby):
    with st.expander('Retry lobby setup'):
        with st.form(f'retry_setup_{lobby.id}'):
            duration = st.radio('Lobby duration', ['1_week', '1_month', '3_months'],
                                format_func=lambda value: value.replace('_', ' '), horizontal=True)
            zone = st.text_input('Lobby timezone', value='Europe/Lisbon')
            test_mode = st.checkbox('Test season: Wednesday 08:00–Sunday 18:00',
                                    key=f'retry_test_season_{lobby.id}')
            retry = st.form_submit_button('Start lobby')
        if retry:
            try:
                db.start_scoring_season(player_id, lobby.id, duration, zone,
                                        **({'test_mode': True} if test_mode else {}))
            except (PermissionError, CheckinRejected, *LOAD_ERRORS):
                st.error('Lobby setup failed. Check the timezone and database setup, then refresh.')
            else:
                st.rerun()


def dismiss_members():
    st.session_state.pop('_opened_lobby_id', None)


def depart(player_id, lobby, key):
    """Leave a lobby for this player only (history is kept, rejoin with the invite code).
    Shared by the Leave lobby button in the dialogs and the trash icon on the cards."""
    try:
        db.leave_lobby(player_id, lobby.id)
    except (PermissionError, ValueError) as error:
        st.error(str(error))
    except LOAD_ERRORS:
        st.error('Could not confirm departure. Refresh lobbies to check your membership before retrying.')
    else:
        dismiss_members()
        st.session_state.pop(key, None)
        st.session_state.pop('_lobby_choice_pending', None)
        st.session_state.pop('_saved_lobby_choice', None)
        if st.session_state.get('current_lobby_id') == lobby.id:
            clear_selection()
        st.session_state['_left_lobby_notice'] = f'You left {lobby.name}. Your earned points are kept.'
        st.rerun()


LEAVE_WARNING = ('Your earned points stay in this lobby and your profile. You lose lobby access '
                 'and personal territory-owner income while away. You can rejoin with the invite code; '
                 'your history, limits and team slot are kept.')


def leave_lobby_controls(player_id, lobby):
    """Shared by individual and team dialogs; require a deliberate second click."""
    key = f'confirm_leave_{lobby.id}'
    if st.button('Leave lobby', key=f'leave_{lobby.id}', icon=':material/logout:', width='stretch'):
        st.session_state[key] = True
    if not st.session_state.get(key):
        return
    st.warning(LEAVE_WARNING)
    confirm, cancel = st.columns(2)
    with confirm:
        if st.button('Confirm leave', key=f'confirm_{lobby.id}', width='stretch'):
            depart(player_id, lobby, key)
    with cancel:
        if st.button('Stay in lobby', key=f'cancel_leave_{lobby.id}', width='stretch'):
            st.session_state.pop(key, None)
            st.rerun()


def remove_lobby_button(player_id, lobby):
    """A trash icon next to a lobby card: removes the lobby from this player's list only."""
    key = f'confirm_remove_{lobby.id}'
    button_icons({f'remove_{lobby.id}': 'trash'})
    if st.button('Remove from my lobbies', key=f'remove_{lobby.id}', help='Remove from my lobbies'):
        st.session_state[key] = True
    return key


def remove_lobby_confirm(player_id, lobby, key):
    """Second click, shown under the card; the same departure as Leave lobby."""
    if not st.session_state.get(key):
        return
    st.warning(f'Remove {lobby.name} from your lobbies? Your points are kept; you can rejoin with the invite code.')
    confirm, cancel = st.columns(2)
    with confirm:
        if st.button('Remove', key=f'confirm_remove_yes_{lobby.id}', type='primary', width='stretch'):
            depart(player_id, lobby, key)
    with cancel:
        if st.button('Keep', key=f'confirm_remove_no_{lobby.id}', width='stretch'):
            st.session_state.pop(key, None)
            st.rerun()


def delete_lobby_controls(player_id, lobby):
    """Only the creator sees this; two deliberate clicks. Shared by both lobby dialogs."""
    try:
        creator = lobby_creator(db.list_memberships_for_lobby(lobby.id, include_left=True))
    except LOAD_ERRORS:
        return
    if creator != player_id:
        return
    key = f'confirm_delete_{lobby.id}'
    if st.button('Delete lobby', key=f'delete_{lobby.id}', icon=':material/delete:', width='stretch'):
        st.session_state[key] = True
    if not st.session_state.get(key):
        return
    st.warning('This deletes the lobby for everyone. Nobody can open it again. '
               'Points and history stay saved in the database.')
    confirm, cancel = st.columns(2)
    with confirm:
        if st.button('Yes, delete lobby', key=f'confirm_delete_btn_{lobby.id}', type='primary', width='stretch'):
            try:
                db.delete_lobby(player_id, lobby.id)
            except PermissionError as error:
                st.error(str(error))
            except (*LOAD_ERRORS, ValueError):
                st.error('Could not delete the lobby. Refresh lobbies and try again.')
            else:
                dismiss_members()
                st.session_state.pop(key, None)
                st.session_state.pop('_lobby_choice_pending', None)
                st.session_state.pop('_saved_lobby_choice', None)
                if st.session_state.get('current_lobby_id') == lobby.id:
                    clear_selection()
                st.session_state['_left_lobby_notice'] = f'{lobby.name} was deleted.'
                st.rerun()
    with cancel:
        if st.button('Keep lobby', key=f'cancel_delete_{lobby.id}', width='stretch'):
            st.session_state.pop(key, None)
            st.rerun()


def close_members_button():
    if st.button('Close', key='close_lobby_members'):
        dismiss_members()
        st.rerun()


@st.dialog('Lobby members', dismissible=True, on_dismiss=dismiss_members)
def show_lobby_details(player_id, lobby, membership, season):
    # Recheck on each dialog interaction, including friendship reruns.
    try:
        if not any(m.player_id == player_id for m in db.list_memberships_for_lobby(lobby.id)):
            st.error('You are no longer a member of this lobby.')
            close_members_button()
            return
    except LOAD_ERRORS:
        st.error('Lobby access could not be checked. Close and refresh lobbies to try again.')
        close_members_button()
        return
    select_lobby(lobby, membership, season)
    notice = st.session_state.pop('_lobby_notice', None)
    if notice:
        st.success(notice)
    st.subheader(lobby.name)
    st.caption('Invite code')
    st.code(lobby.invite_code, language=None)
    with st.container(key='lobby_members', border=False):
        show_lobby_members(player_id, lobby.id)
    st.divider()
    if season:
        if st.button('View leaderboard', width='stretch'):
            dismiss_members()
            st.switch_page('pages/4_Standings.py')
    else:
        st.caption('The leaderboard will be available once lobby setup is complete.')
        retry_setup(player_id, lobby)
    leave_lobby_controls(player_id, lobby)
    delete_lobby_controls(player_id, lobby)
    close_members_button()


@st.fragment(run_every='60s')
def show_lobbies(player_id):
    css = (Path(__file__).parent / 'assets/lobbies.css').read_text()
    st.markdown(f'<style>{css}</style>', unsafe_allow_html=True)
    # Timed refreshes must not retain access after a membership is removed.
    try:
        memberships = db.list_memberships_for_player(player_id)
    except LOAD_ERRORS:
        st.button('Refresh lobbies')
        st.error('Your lobby access could not be checked. Use Refresh lobbies to try again.')
        return
    if st.session_state.get('_opened_lobby_id') not in {m.lobby_id for m in memberships}:
        st.session_state.pop('_opened_lobby_id', None)
    notice = st.session_state.pop('_left_lobby_notice', None)
    if notice:
        st.success(notice)
    show_overview_actions(player_id)
    st.button('Refresh lobbies')
    if not memberships:
        clear_selection()
        st.info('You have not joined any lobbies yet. Create one or join with a code above.')
        return
    try:
        lobbies = {l.id: l for l in db.list_lobbies()}
    except LOAD_ERRORS:
        st.error('Your lobbies could not be loaded. Use Refresh lobbies to try again.')
        return
    now = datetime.now(timezone.utc)
    groups = {key: [] for key in ('active', 'past', 'upcoming', 'setup')}
    def fetch_season(lobby_id):
        try:
            return latest_season(db.list_seasons_for_lobby(lobby_id))
        except LOAD_ERRORS as error:
            return error
    shown = [(membership, lobbies[membership.lobby_id]) for membership in memberships if membership.lobby_id in lobbies]
    # One request per lobby, all at the same time.
    for (membership, lobby), season in zip(shown, run_parallel(*[partial(fetch_season, lobby.id) for _, lobby in shown])):
        if isinstance(season, LOAD_ERRORS):
            st.warning(f'Dates for {lobby.name} are unavailable. Use Refresh lobbies to try again.')
            continue
        groups[lobby_status(season, now)].append((lobby, membership, season))
    for status in ('active', 'past', 'upcoming'):
        groups[status].sort(key=lambda row: (utc(row[2].ends_at if status == 'past' else row[2].starts_at), row[0].id), reverse=True)
    # Keep an explicitly opened lobby selected while refreshing its members.
    opened = next((row for rows in groups.values() for row in rows
                   if row[0].id == st.session_state.get('_opened_lobby_id')), None)
    selected = next((row for rows in groups.values() for row in rows
                     if row[0].id == st.session_state.get('current_lobby_id')
                     and lobby_status(row[2], now) != 'past'), None)
    if opened:
        st.session_state.pop('_lobby_choice_required', None)
        select_lobby(*opened)
        try:
            remember_choice(player_id, opened[0].id)
        except (PermissionError, *LOAD_ERRORS):
            st.warning('This lobby is selected for this visit, but your choice could not be saved. Reopen it to retry.')
    elif selected:
        select_lobby(*selected)
    elif groups['active'] and not st.session_state.get('_lobby_choice_required'):
        select_lobby(*groups['active'][0])
        st.caption(f'Automatically selected: {groups["active"][0][0].name}')
    else:
        clear_selection()
    for status, heading in (('active', 'Active Lobbies'), ('past', 'Past Lobbies'),
                            ('upcoming', 'Upcoming Lobbies'), ('setup', 'Incomplete setup')):
        rows = groups[status]
        if not rows and status not in ('active', 'past'):
            continue
        st.subheader(heading)
        if not rows:
            st.caption('No active lobbies.' if status == 'active' else 'No past lobbies yet.')
        for lobby, membership, season in rows:
            with st.container(key=f'lobby_card_{lobby.id}', gap=None):
                show_summary(player_id, lobby, season, status, now)
                if st.button('View lobby →', key=f'open_lobby_{lobby.id}',
                             help=f'Open {lobby.name}', width='stretch'):
                    dismiss_dialog()
                    st.session_state['_opened_lobby_id'] = lobby.id
                    st.session_state['_lobby_choice_pending'] = lobby.id
                    st.rerun()
                with st.container(key=f'trash_{lobby.id}'):   # top-right corner of the card
                    confirm_key = remove_lobby_button(player_id, lobby)
            remove_lobby_confirm(player_id, lobby, confirm_key)
    if opened and not st.session_state.get('_lobby_dialog'):
        lobby, membership, season = opened
        if lobby.game_mode == 'team':
            from team_ui import open_team_lobby
            open_team_lobby(player_id, lobby, season, finished=lobby_status(season, now) == 'past')
        else:
            show_lobby_details(player_id, *opened)
