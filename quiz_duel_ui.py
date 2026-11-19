"""Quiz lobby and invitations. Only sanitized state crosses the component bridge."""
from html import escape
from uuid import uuid4
import streamlit as st
from httpx import RequestError
from postgrest.exceptions import APIError
import data.db as db
from core.quiz_duel import ACTIVE, FINAL, component_action, validate_pair
from core.scoring_v1 import format_points
from quiz_duel_component import quiz_board

SERVICE_ERRORS = (APIError, RequestError, RuntimeError, OSError, ValueError, PermissionError)


def _action(player, duel, action, round_no=None, choice=None):
    try:
        db.quiz_action(player, duel["id"], action, round_no, choice)
        st.rerun(scope="fragment")
    except SERVICE_ERRORS as error:
        st.error(str(error) if isinstance(error, (ValueError, PermissionError, RuntimeError))
                 else "The quiz service is unavailable. Refresh to recover your saved game.")


def _stage(player, member, duel, labels):
    with st.container(key="quiz_stage"):
        ack_key = "quiz_ack_" + duel["id"]
        value = quiz_board(duel, member, labels, st.session_state.get(ack_key))
        parsed = component_action(value, duel)
        if not parsed or value["event_id"] == st.session_state.get(ack_key):
            return
        action, round_no, choice = parsed
        if action == "back":
            if duel["status"] not in FINAL:
                return
            st.session_state[ack_key] = value["event_id"]
            st.session_state.pop("quiz_focused_id", None)
            st.session_state["quiz_dismissed"] = duel["id"]
            st.rerun(scope="fragment")
        try:
            db.quiz_action(player, duel["id"], action, round_no, choice)
            st.session_state[ack_key] = value["event_id"]
            st.rerun(scope="fragment")
        except SERVICE_ERRORS as error:
            st.error(str(error) if isinstance(error, (ValueError, PermissionError, RuntimeError))
                     else "Connection interrupted. Your first answer will retry automatically.")


def render_quiz(player, member, lobby, season, members, labels):
    try:
        state = db.quiz_status(player, season.id)
    except SERVICE_ERRORS as error:
        st.error(str(error) if isinstance(error, (ValueError, RuntimeError, PermissionError))
                 else "Quiz Duel is temporarily unavailable. Refresh to retry.")
        if st.button("All games", key="quiz_error_back"):
            st.session_state.pop("minigame_selected", None)
            st.rerun()
        return
    duels = state["duels"]
    running = next((d for d in duels if d["status"] in ACTIVE), None)
    focused = running or next((d for d in duels if d["id"] == st.session_state.get("quiz_focused_id")), None)
    if focused:
        st.session_state["quiz_focused_id"] = focused["id"]
        _stage(player, member, focused, labels)
        return
    from minigames_ui import game_header, game_note
    game_header("Quiz Duel", "", "quiz_back")
    points = format_points(state["available_points"])
    game_note(f"{points} points")
    pending = [d for d in duels if d["status"] == "invited"]
    for duel in pending:
        with st.container(border=True):
            st.markdown(f'<p class="duel-vs">{escape(labels.get(duel["challenger_id"], "Player"))} <span>vs</span> '
                        f'{escape(labels.get(duel["opponent_id"], "Player"))}</p>'
                        f'<p class="duel-what">Stake {duel["stake"]} each</p>', unsafe_allow_html=True)
            if member == duel["opponent_id"]:
                accept, decline = st.columns(2)
                with accept:
                    if st.button("Accept", key="quiz_accept_" + duel["id"], type="primary", width="stretch"):
                        _action(player, duel, "accept")
                with decline:
                    if st.button("Decline", key="quiz_decline_" + duel["id"], width="stretch"):
                        _action(player, duel, "decline")
            else:
                game_note("Waiting for an answer.")
                if st.button("Cancel", key="quiz_cancel_" + duel["id"], width="stretch"):
                    _action(player, duel, "cancel")
    own = next(m for m in members if m.id == member)
    opponents = []
    for other in members:
        try:
            validate_pair(own, other, lobby)
            opponents.append(other.id)
        except ValueError:
            continue
    if not state["open"]:
        game_note("Opens with the scoring window.")
    elif opponents:
        if not state["outgoing"]:
            game_note("You already challenged tonight.")
        elif not any(d["challenger_id"] == member for d in pending):
            opponent = st.radio("Who", opponents, index=0 if len(opponents) == 1 else None,
                                format_func=lambda m: labels.get(m, "Lobby member"), horizontal=True,
                                key="pill_radio_quiz_opponent")
            stake = st.radio("Stake", list(range(3, 11)), horizontal=True, key="pill_radio_quiz_stake")
            if st.button("Challenge", type="primary", key="quiz_challenge", width="stretch",
                         disabled=opponent is None or state["available_points"] < stake):
                request = st.session_state.setdefault("quiz_invitation_id", str(uuid4()))
                try:
                    db.invite_quiz_duel(player, season.id, request, opponent, stake)
                    st.session_state.pop("quiz_invitation_id", None)
                    st.rerun(scope="fragment")
                except SERVICE_ERRORS as error:
                    st.error(str(error) if isinstance(error, (ValueError, RuntimeError, PermissionError))
                             else "Could not send. Try again.")
    else:
        game_note("Needs another player." if lobby.game_mode != "team" else "Needs a rival team.")
    recent = [d for d in duels if d["status"] in FINAL]
    if recent:
        with st.expander("Recent"):
            for duel in recent[:10]:
                result = labels.get(duel.get("winner_id"), "Draw") if duel.get("winner_id") else duel["status"].title()
                st.write(f"{duel['challenger_score']} : {duel['opponent_score']} · {result} · Stake {duel['stake']}")
                if st.button("View result", key="quiz_result_" + duel["id"]):
                    st.session_state["quiz_focused_id"] = duel["id"]
                    st.rerun(scope="fragment")
