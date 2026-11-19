"""Private friend controls for the authenticated Profile page."""
from pathlib import Path

import streamlit as st
from httpx import RequestError
from postgrest.exceptions import APIError

import data.db as db
from core.friends import search_usernames
from profile_picture_ui import picture_identity, show_picture_identity


def friendship_action(player_id, label, other, operation, *, key_prefix="friend", refresh_label="Refresh friends", success_message=None):
    if st.button(label, key=f"{key_prefix}_{operation}_{other}"):
        try:
            db.change_friendship(player_id, other, operation)
        except ValueError as exc:
            st.error(str(exc))
        except APIError as exc:
            if exc.code == "40001":
                st.error(f"This request changed. {refresh_label} and try again.")
            else:
                st.error("Could not update friends. Please try again later.")
        except (RuntimeError, OSError, RequestError):
            st.error("Could not update friends. Please try again later.")
        else:
            if success_message:
                st.session_state["_friends_notice"] = success_message
                st.session_state.pop("_friend_remove", None)
            st.rerun()



SECTIONS = {
    "search": ("Find players", ":material/person_search:"),
    "accepted": ("Current Friends", ":material/group:"),
    "incoming": ("Incoming requests", ":material/person_add:"),
    "outgoing": ("Outgoing requests", ":material/send:"),
}
LOAD_ERRORS = (APIError, RuntimeError, OSError, RequestError)


def dismiss_friends():
    for key in ("_friends_dialog", "_friend_remove", "_friends_notice", "_friends_focus"):
        st.session_state.pop(key, None)


def load_friends(player_id):
    users = db.list_public_usernames()
    relationships = db.list_friendships(player_id)
    names = {p["id"]: p["display_name"] for p in users}
    by_other = {
        r["recipient_id"] if r["sender_id"] == player_id else r["sender_id"]: r
        for r in relationships
    }
    return users, names, by_other


def section_players(section, player_id, names, by_other):
    def belongs(row):
        if section == "accepted":
            return row["status"] == "accepted"
        return row["status"] == "pending" and row[
            "recipient_id" if section == "incoming" else "sender_id"
        ] == player_id

    return sorted((other for other, row in by_other.items() if belongs(row)),
                  key=lambda other: (names.get(other, "").casefold(), other))


def friend_identity(player_id, other, names, by_other):
    name = names.get(other, "Unknown player")
    if by_other.get(other, {}).get("status") in ("accepted", "pending"):
        show_picture_identity(player_id, other, name, size=40)
    else:
        picture_identity(name, size=40)


def profile_action(player_id, label, other, operation, message):
    friendship_action(player_id, label, other, operation,
                      key_prefix="profile_friend", success_message=message)


def focus_search():
    # Fixed code only: no usernames or other user input are inserted into JS.
    # Wait briefly for the native dialog input to mount, then focus it once.
    st.html("""<script>
    (() => {
      let tries = 0;
      const timer = setInterval(() => {
        const input = document.querySelector('[role="dialog"] .st-key-friends_search input');
        if (input) { input.focus(); clearInterval(timer); }
        else if (++tries > 40) clearInterval(timer);
      }, 50);
    })();
    </script>""", unsafe_allow_javascript=True)


def show_search(player_id, users, names, by_other):
    query = st.text_input("Search usernames", max_chars=80, key="friends_search",
                          placeholder="Enter a player's username")
    if st.session_state.pop("_friends_focus", False):
        focus_search()
    results = search_usernames(query, users, player_id)
    if not query.strip():
        st.caption("Search for a username to send a friend request.")
    elif not results:
        st.info("No matching usernames found.")
    for user in results:
        other = user["id"]
        with st.container(border=True):
            friend_identity(player_id, other, names, by_other)
            row = by_other.get(other, {})
            status = row.get("status")
            if status == "accepted":
                st.caption("Already friends")
            elif status == "pending":
                st.caption("Incoming request — open Incoming requests." if row["recipient_id"] == player_id
                           else "Request sent — open Outgoing requests to cancel.")
            else:
                if status == "declined":
                    st.caption("After a decline, wait 10 minutes before sending another request.")
                profile_action(player_id, "Send friend request", other, "request", "Friend request sent.")


def show_friend_list(section, player_id, names, by_other):
    players = section_players(section, player_id, names, by_other)
    if not players:
        st.caption({"accepted": "No friends yet. Open Find players to search for a username.",
                    "incoming": "No incoming requests.", "outgoing": "No outgoing requests."}[section])
    for other in players:
        with st.container(border=True):
            friend_identity(player_id, other, names, by_other)
            if section == "incoming":
                left, right = st.columns(2)
                with left:
                    profile_action(player_id, "Accept", other, "accept", "Friend request accepted.")
                with right:
                    profile_action(player_id, "Decline", other, "decline", "Friend request declined.")
            elif section == "outgoing":
                profile_action(player_id, "Cancel request", other, "cancel", "Friend request cancelled.")
            elif st.session_state.get("_friend_remove") == other:
                st.warning(f"Remove {names.get(other, 'this player')} from your friends? This removes the friendship for both of you.")
                left, right = st.columns(2)
                with left:
                    profile_action(player_id, "Confirm removal", other, "remove", "Friend removed.")
                with right:
                    if st.button("Keep friend", key=f"keep_friend_{other}"):
                        st.session_state.pop("_friend_remove", None)
                        st.rerun()
            elif st.button("Remove friend", key=f"remove_friend_{other}"):
                st.session_state["_friend_remove"] = other
                st.rerun()


@st.dialog("Friends", dismissible=True, on_dismiss=dismiss_friends)
def friends_dialog(player_id, section):
    st.subheader(SECTIONS[section][0])
    notice = st.session_state.pop("_friends_notice", None)
    if notice:
        st.success(notice)
    if st.button("Refresh friends", key="friends_dialog_refresh"):
        st.rerun()
    try:
        users, names, by_other = load_friends(player_id)
    except LOAD_ERRORS:
        st.error("Friends are unavailable. Please try again later.")
    else:
        if section == "search":
            show_search(player_id, users, names, by_other)
        else:
            show_friend_list(section, player_id, names, by_other)
    if st.button("Close", key="close_friends_dialog", width="stretch"):
        dismiss_friends()
        st.rerun()


def show_friends(player_id: str):
    st.header("Friends")
    st.caption("Your friends list is private. Find players across the app.")
    st.html(Path(__file__).parent / "assets" / "friends.css")
    if st.button("Refresh friends", key="friends_overview_refresh"):
        st.rerun()
    try:
        _, names, by_other = load_friends(player_id)
    except LOAD_ERRORS:
        st.error("Friends are unavailable. Please try again later.")
        # Keep the sections usable so a dialog can retry independently.
        names, by_other = {}, None
    for sections in (("search", "accepted"), ("incoming", "outgoing")):
        for column, section in zip(st.columns(2), sections):
            title, icon = SECTIONS[section]
            count = "" if section == "search" else (
                f" · {len(section_players(section, player_id, names, by_other))}"
                if by_other is not None else " · Unavailable")
            with column, st.container(key=f"friends_card_{section}"):
                if st.button(title + count, icon=icon, width="stretch", key=f"open_friends_{section}"):
                    dismiss_friends()
                    st.session_state["_friends_dialog"] = section
                    st.session_state["_friends_focus"] = section == "search"
                    st.rerun()
    section = st.session_state.get("_friends_dialog")
    if section in SECTIONS:
        friends_dialog(player_id, section)
