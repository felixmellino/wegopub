"""Minigames catalogue, lobby invitations and the Chug Duel board."""
from base64 import b64encode
from pathlib import Path
from uuid import uuid4

from html import escape
import streamlit as st
from httpx import RequestError
from postgrest.exceptions import APIError
from storage3.utils import StorageException

import data.db as db
from camera_capture import CameraCancelled, camera_photo
from chug_duel_component import duel_board
from core.chug_duel import allowances, component_action, night_id, unlimited_plays, validate_pair, ERRORS
from core.checkin_photo import InvalidCheckinPhoto
from core.checkins import CheckinRejected
from core.scoring_v1 import DRINK_LABELS, SIZE_LABELS, base_points, current_time, rules_for, scoring_open, size_label
from drink_entry_ui import page_header
from theme import button_icons, page_subtitle
from parallel import run_parallel
from phone_location import current_location, track_location
from core.focus_challenge import enabled as focus_enabled, test_mode as focus_test_mode
from focus_challenge_ui import render_focus
from quiz_duel_ui import render_quiz
from time_duel_ui import render_time

SERVICE_ERRORS = (APIError, RequestError, RuntimeError, OSError, StorageException)


def _error(error):
    if isinstance(error, CheckinRejected):
        st.error(ERRORS.get(error.reason, "The shared check-in could not be accepted. Please retry."))
    elif isinstance(error, (ValueError, PermissionError, RuntimeError)):
        st.error(str(error))
    else:
        st.error("The duel service is unavailable. Refresh to recover any saved action before retrying.")


def _act(player, duel, action, winner=None):
    try:
        db.chug_duel_action(player, duel["id"], action, winner)
        st.rerun()
    except (ValueError, PermissionError) + SERVICE_ERRORS as error:
        _error(error)


GAME_ART = Path(__file__).parent / "assets" / "games"


def _art(name):
    """An animated game illustration (assets/games/*.svg) as an image data URL."""
    return "data:image/svg+xml;base64," + b64encode((GAME_ART / f"{name}.svg").read_bytes()).decode()


def _game_tile(key, art, title, line, *, invites=0, alert=False, playable=True, real=True):
    """One colourful square tile: animated picture, name, one status line.
    A playable tile has its "Open …" button laid invisibly over it (CSS), so
    the whole tile is the tap target and keeps the button's accessible name.
    A real game that is closed right now keeps a disabled button; a
    coming-soon tile (real=False) has none."""
    tone = " game-tile-alert" if alert else ""
    off = "" if playable else " game-tile-off"
    badge = ""
    if invites:
        number = str(invites) if invites <= 99 else "99+"
        label = "invite" if invites == 1 else "invites"
        badge = (f'<span class="game-tile-invite-badge" role="img" '
                 f'aria-label="{invites} pending {escape(title)} {label}">{number} {label}</span>')
    with st.container(key=f"game_tile_{key}"):
        st.markdown(
            f'<div class="game-tile game-tile-{key}{off}"><img class="game-tile-art" src="{_art(art)}" alt="">'
            f'{badge}'
            f'<div class="game-tile-text"><strong>{escape(title)}</strong>'
            f'<small class="{tone.strip()}">{escape(line)}</small></div></div>',
            unsafe_allow_html=True)
        return real and st.button(f"Open {title}", key=f"open_game_{key}", width="stretch", disabled=not playable)


# Placeholder tiles after the playable games; each becomes a real game later.
COMING_SOON = [(f"soon_{n}", "coming-soon", "New game") for n in (1, 2)]


def _game_cards(player, season, member, duels, *, service_available=True):
    """Six colourful tiles (3 rows of 2): the playable games first, then what is coming.
    Frozen season rules decide whether the Reaction Test (Focus Challenge) is open;
    test seasons allow unlimited Reaction Test plays (focus_qa)."""
    try:
        invites = db.pending_minigame_invites(player, season.id)
    except SERVICE_ERRORS:
        invites = {}  # The next refresh retries. Players can still open each game.
    active = any(d['status'] in {'accepted', 'started'}
                 or (d['status'] == 'invited' and d['challenger_id'] == member) for d in duels)
    focus_available, focus_qa = focus_enabled(season), focus_test_mode(season)
    if not service_available:
        chug_line = 'Unavailable'
    elif active:
        chug_line = 'Duel open'
    else:
        chug_line = '1 vs 1 · Race on one phone'
    with st.container(key='games_grid'):
        if _game_tile('chug', 'chug-duel', 'Chug Duel', chug_line,
                      invites=invites.get('chug', 0), alert=active, playable=service_available):
            st.session_state['minigame_selected'] = 'chug_duel'
            st.rerun()
        if _game_tile('focus', 'reaction-test', 'Reaction Test',
                      'Test mode · Unlimited plays' if focus_qa
                      else 'Solo · Win ×1.5 for an hour' if focus_available else 'Not in this season',
                      playable=focus_available):
            st.session_state['minigame_selected'] = 'focus'
            st.rerun()
        if _game_tile('quiz', 'quiz', 'Quiz Duel', '1 vs 1 · Stake 3–10 points',
                      invites=invites.get('quiz', 0)):
            st.session_state['minigame_selected'] = 'quiz'
            st.rerun()
        if _game_tile('time', 'time-duel', 'Time Duel', '1 vs 1 · Win ×1.25 for an hour',
                      invites=invites.get('time', 0)):
            st.session_state['minigame_selected'] = 'time'
            st.rerun()
        for key, art, title in COMING_SOON:
            _game_tile(key, art, title, 'Coming soon', playable=False, real=False)


def _focused_duel(player, duel, labels):
    """Keep one keyed board in the same screen position through all play phases."""
    with st.container(key="chug_duel_stage"):
        value = duel_board(duel, labels.get(duel["challenger_id"], "Challenger"),
                           labels.get(duel["opponent_id"], "Opponent"))
        with st.container(key="chug_duel_controls"):
            if duel["status"] == "started":
                # A compact exit is separate from both large finish targets.
                if st.button("End without winner", icon=":material/close:",
                             key=f"abort_{duel['id']}", help="End the duel. Both keep their normal drink points."):
                    _act(player, duel, "abort")
            elif st.button("Back to Minigames", key=f"chug_done_{duel['id']}"):
                st.session_state.pop("chug_focused_duel", None)
                st.rerun()
        if duel["status"] == "started":
            action = component_action(value, duel)
            if action:
                _act(player, duel, *action)


def game_header(title, line, back_key):
    """Every game screen starts the same way: a quiet way back, the name, one short line."""
    button_icons({back_key: 'caret-left'})
    if st.button('All games', key=back_key, type='tertiary'):
        st.session_state.pop('minigame_selected', None)
        st.rerun()
    line = f'<p class="game-line">{escape(line)}</p>' if line else ''
    st.markdown(f'<h2 class="game-title">{escape(title)}</h2>{line}', unsafe_allow_html=True)


def game_note(text):
    """One small grey line; the only kind of explanation game screens show."""
    st.markdown(f'<p class="game-note">{escape(text)}</p>', unsafe_allow_html=True)


def _capture_and_start(player, lobby, season, duel):
    key = f"chug_photo_{duel['id']}"
    capture = st.session_state.get(key)
    if not capture:
        game_note("Photo of both drinks")
        stage = st.empty()
        try:
            with stage.container(key="chug_camera_stage"):
                photo = camera_photo(key=f"{key}_{st.session_state.get(key + '_number', 0)}")
        except CameraCancelled:
            stage.empty()
            if st.button("Open camera", key=key + "_reopen", type="primary", width="stretch"):
                st.session_state[key + "_number"] = st.session_state.get(key + "_number", 0) + 1
                st.rerun()
            return
        except InvalidCheckinPhoto as error:
            stage.empty()
            st.error(str(error))
            if st.button("Retake photo", key=key + "_invalid", width="stretch"):
                st.session_state[key + "_number"] = st.session_state.get(key + "_number", 0) + 1
                st.rerun()
            return
        if photo:
            capture = (photo.getvalue(), current_time())
            st.session_state[key] = capture
            st.rerun()
        return
    encoded = b64encode(capture[0]).decode("ascii")
    st.html(f'<img class="chug-photo" src="data:image/jpeg;base64,{encoded}" alt="Shared duel photo">')
    gps, accuracy, problem = current_location()
    if problem:
        st.warning("Waiting for your location. Allow it and keep this page open.")
    start, retake = st.columns(2)
    with start:
        go = st.button("Start duel", type="primary", key=key + "_start", disabled=bool(problem), width="stretch")
    with retake:
        if st.button("Retake photo", key=key + "_retake", width="stretch"):
            st.session_state.pop(key, None)
            st.session_state[key + "_number"] = st.session_state.get(key + "_number", 0) + 1
            st.rerun()
    if go:
        try:
            # Read the newest reading again at submission; do not use a preview.
            gps, accuracy, problem = current_location()
            if problem:
                raise ValueError(ERRORS["location_unavailable"])
            saved = db.start_chug_duel(player, lobby.id, season.id, duel["id"], capture[0], capture[1], gps, accuracy)
            if saved["status"] in {"started", "completed", "aborted"}:
                st.session_state.pop(key, None)
                st.rerun()
            st.warning("This duel is no longer available.")
        except (ValueError, PermissionError, CheckinRejected) + SERVICE_ERRORS as error:
            _error(error)


def render_minigames(player, member, lobby, season):
    rules = rules_for(season)
    unlimited = unlimited_plays(season)
    css = (Path(__file__).parent / "assets" / "minigames.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    if not st.session_state.get('minigame_selected'):   # a game screen has its own header
        page_header("Minigames", compact=True)
        page_subtitle(lobby.name, "Test season · Unlimited plays" if unlimited else "Evening resets at 06:00")
    context = (member, lobby.id, season.id)
    if st.session_state.get('minigames_context', context) != context:
        st.session_state.pop('minigame_selected', None)
        st.session_state.pop('chug_focused_duel', None)
        st.session_state.pop('focus_focused_id', None)
        st.session_state.pop('focus_start_request', None)
        st.session_state.pop('quiz_focused_id', None)
        st.session_state.pop('quiz_invitation_id', None)
        st.session_state.pop('time_focused_id', None)
        st.session_state.pop('time_invitation_id', None)
        st.session_state.pop('time_invitation_target', None)
        st.session_state.pop('time_accept_confirmation', None)
    st.session_state['minigames_context'] = context
    try:
        members, usernames = run_parallel(lambda: db.list_memberships_for_lobby(lobby.id), db.list_public_usernames)
        own = next((m for m in members if m.id == member and m.player_id == player), None)
        if own is None:
            raise PermissionError("Your membership is no longer available.")
        names = {p["id"]: p["display_name"] for p in usernames}
    except (ValueError, PermissionError) + SERVICE_ERRORS as error:
        _error(error)
        return
    labels = {m.id: names.get(m.player_id, "Lobby member") for m in members}

    @st.fragment(run_every="1s" if st.session_state.get('minigame_selected') in {'quiz', 'time', 'focus'} else "3s")
    def live_duels():
        now = current_time()
        if st.session_state.get('minigame_selected') == 'time':
            render_time(player, member, lobby, season, members, labels)
            return
        if st.session_state.get('minigame_selected') == 'quiz':
            render_quiz(player, member, lobby, season, members, labels)
            return
        if st.session_state.get('minigame_selected') == 'focus' and focus_enabled(season):
            render_focus(player, season)
            return
        try:
            duels = db.list_chug_duels(player, season.id)
        except (ValueError, PermissionError) + SERVICE_ERRORS as error:
            _game_cards(player, season, member, [], service_available=False)
            _error(error)
            return
        running = next((d for d in duels if d["status"] == "started" and d["challenger_id"] == member), None)
        if running:
            st.session_state["chug_focused_duel"] = running["id"]
        focused = running or next((d for d in duels if d["id"] == st.session_state.get("chug_focused_duel")
            and d["challenger_id"] == member and d["status"] in {"completed", "aborted"}), None)
        if focused:
            track_location()
            _focused_duel(player, focused, labels)
            return
        st.session_state.pop("chug_focused_duel", None)
        if st.session_state.get('minigame_selected') != 'chug_duel':
            # The game list; an opened game replaces it, like a page on a phone.
            _game_cards(player, season, member, duels)
            return
        game_header('Chug Duel', '', 'minigames_home')
        track_location()
        outgoing, incoming = allowances(member, night_id(now, season.timezone_name), duels, season=season)

        def who(member_id):
            return labels.get(member_id, 'Lobby member')

        active = [d for d in duels if d["status"] in {"invited", "accepted", "started"}]
        for duel in active:
            cid, oid = duel["challenger_id"], duel["opponent_id"]
            host = cid == member
            with st.container(border=True, key=f"chug_card_{duel['id']}"):
                points = base_points(duel["drink_type"], duel.get("size"), rules)
                selection = DRINK_LABELS[duel["drink_type"]]
                if duel.get("size"):
                    selection += " · " + size_label(duel["drink_type"], duel["size"], rules)
                st.markdown(f'<p class="duel-vs">{escape(who(cid))} <span>vs</span> {escape(who(oid))}</p>'
                            f'<p class="duel-what">{escape(selection)} · winner +{points * 2}</p>', unsafe_allow_html=True)
                status = duel["status"]
                if status == "invited":
                    if host:
                        game_note(f"Waiting for {who(oid)}")
                        if st.button("Cancel", key=f"cancel_{duel['id']}", width="stretch"):
                            _act(player, duel, "cancel")
                    else:
                        a, b = st.columns(2)
                        if a.button("Accept", key=f"accept_{duel['id']}", type="primary", disabled=not incoming, width="stretch"):
                            _act(player, duel, "accept")
                        if b.button("Decline", key=f"decline_{duel['id']}", width="stretch"):
                            _act(player, duel, "decline")
                        if not incoming:
                            game_note("You already accepted a duel tonight.")
                elif status == "accepted":
                    if host:
                        _capture_and_start(player, lobby, season, duel)
                    else:
                        game_note(f"Go to {who(cid)}'s phone.")
                    if st.button("Cancel", key=f"abort_{duel['id']}", width="stretch"):
                        _act(player, duel, "cancel" if host else "abort")
                else:
                    game_note(f"Playing on {who(cid)}'s phone.")
                    if st.button("End without winner", key=f"abort_{duel['id']}", width="stretch"):
                        _act(player, duel, "abort")

        if not scoring_open(now, season):
            game_note("Duels open with the scoring window.")
        elif outgoing and not active:   # one thing at a time: answer or finish the open duel first
            opponents = []
            for candidate in members:
                try:
                    validate_pair(own, candidate, lobby)
                    opponents.append(candidate.id)
                except ValueError:
                    pass
            if not opponents:
                game_note("Needs another player." if lobby.game_mode != "team" else "Needs a rival team.")
            else:
                opponent = st.radio("Who", opponents, index=0 if len(opponents) == 1 else None,
                                    format_func=lambda mid: labels[mid], horizontal=True, key="pill_radio_chug_opponent")
                drink = st.radio("Drink", list(DRINK_LABELS), format_func=DRINK_LABELS.get, horizontal=True, key="chug_drink")
                size = None if drink == "shot" else st.radio("Size", list(SIZE_LABELS),
                    format_func=lambda s: size_label(drink, s, rules), horizontal=True, key=f"chug_drink_size_{drink}")
                game_note(f"Winner +{base_points(drink, size, rules) * 2}")
                request = (player, season.id, opponent, drink, size)
                if st.session_state.get("chug_request") != request:
                    st.session_state["chug_request"] = request
                    st.session_state["chug_invitation_id"] = str(uuid4())
                if st.button("Challenge", type="primary", key="chug_invite", disabled=opponent is None, width="stretch"):
                    try:
                        db.invite_chug_duel(player, season.id, st.session_state["chug_invitation_id"], opponent, drink, size)
                        st.session_state.pop("chug_request", None)
                        st.rerun()
                    except (ValueError, PermissionError) + SERVICE_ERRORS as error:
                        _error(error)
        elif not outgoing and not active:
            game_note("You already challenged tonight.")

        history = [d for d in duels if d["status"] not in {"invited", "accepted", "started"}]
        for duel in history[:3]:
            if duel["status"] == "completed":
                points = base_points(duel["drink_type"], duel.get("size"), rules)
                st.success(f"{who(duel['winner_id'])} won · +{points * 2}")
            else:
                game_note(f"{who(duel['challenger_id'])} vs {who(duel['opponent_id'])} · {duel['status'].capitalize()}")
    live_duels()
