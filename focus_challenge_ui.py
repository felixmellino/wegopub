"""Focus Challenge (shown to players as "Reaction Test"): availability and saved full-screen attempts."""
from datetime import datetime
from zoneinfo import ZoneInfo
from uuid import uuid4

import streamlit as st
import data.db as db
from core.focus_challenge import component_action, test_mode
from core.scoring_v1 import current_time, scoring_open, utc
from focus_challenge_component import focus_board


def render_focus(player, season):
    # Import at call time to keep the shared service error policy in one place.
    from minigames_ui import SERVICE_ERRORS, _error
    try:
        info = db.focus_status(player, season.id)
    except (ValueError, PermissionError) + SERVICE_ERRORS as error:
        _error(error)
        return
    attempt = info.get('attempt')
    if test_mode(season) and info.get('unlimited') is not True:
        st.error('Test-mode Focus setup is required: apply migration 015 after 014.')
        return
    # The RPC reads the current frozen season on every poll. A fragment can
    # still hold an older page snapshot across a deployment or reconnect.
    qa = info.get('unlimited') is True
    if attempt and (attempt['status'] == 'running'
                    or st.session_state.get('focus_start_request') == attempt['id']):
        # Recover a committed start whose reply was lost before the UI cleared it.
        st.session_state.pop('focus_start_request', None)
    if attempt and (attempt['status'] == 'running'
                    or st.session_state.get('focus_focused_id') == attempt['id']):
        st.session_state['focus_focused_id'] = attempt['id']
        with st.container(key='focus_stage'):
            value = focus_board(attempt)
            with st.container(key='focus_exit'):
                if st.button('Back to games', icon=':material/close:', key='focus_back',
                             help='Leave the screen. A running attempt keeps its deadline.'):
                    st.session_state.pop('focus_focused_id', None)
                    st.session_state.pop('minigame_selected', None)
                    st.rerun()
            action = component_action(value, attempt)
            if action and attempt['status'] == 'running':
                try:
                    db.focus_attempt_action(player, attempt['id'], attempt['revision'], *action)
                    # The fragment poll recovers the next phase without remounting the board.
                except (ValueError, PermissionError) + SERVICE_ERRORS as error:
                    _error(error)
        return
    from minigames_ui import game_header, game_note
    game_header('Reaction Test', '×1.5 points for 1 hour', 'focus_home')
    count, threshold = info['count'], info['threshold']
    if not qa:
        if type(threshold) is not int or threshold <= 0:
            st.error('Could not load. Reload the page.')
            return
        if count < threshold and not info['won'] and not info.get('boost_ends_at'):
            st.progress(min(1.0, count / threshold), text=f'{count} / {threshold} check-ins to unlock')
    if info.get('boost_ends_at'):
        end = datetime.fromisoformat(info['boost_ends_at']).astimezone(ZoneInfo(season.timezone_name))
        st.success(f'×1.5 active until {end:%H:%M}')
    elif info['won'] and not qa:
        game_note('Done for tonight. Resets at 06:00.')
    elif attempt and attempt['status'] == 'failed' and not qa:
        game_note(f'Missed. Next try after {threshold} check-ins.')
    now = current_time()
    open_now = (utc(season.starts_at) <= utc(now) < utc(season.ends_at)
                if qa else scoring_open(now, season))
    if not open_now:
        game_note('Opens with the scoring window.')
    allowed = open_now and (qa or (count >= threshold and not info['won'] and not info.get('boost_ends_at')))
    if st.button('Start', type='primary', width='stretch', disabled=not allowed, key='focus_start'):
        request = st.session_state.setdefault('focus_start_request', str(uuid4()))
        try:
            saved = db.start_focus_attempt(player, season.id, request)
            st.session_state['focus_focused_id'] = saved['id']
            st.session_state.pop('focus_start_request', None)
            st.rerun()
        except (ValueError, PermissionError) + SERVICE_ERRORS as error:
            _error(error)
