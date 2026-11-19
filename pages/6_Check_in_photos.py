"""Show check-in photos to the members of the lobby where they were taken."""

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import streamlit as st
from httpx import RequestError
from postgrest.exceptions import APIError
from storage3.utils import StorageException

import data.db as db
from core.constants import PHOTO_RETENTION_DAYS
from core.checkins import CheckinRejected
from core.scoring_v1 import (DRINK_LABELS, SIZE_LABELS, base_points, can_correct, current_time, format_points, size_label, utc)
from drink_entry_ui import context_line, page_header, section_heading
from photo_history_ui import game_night_bounds, game_night_label, memory_tile, photo_metadata, framed_photo
from shared import require_active_membership, require_login, show_logged_in_as


def entry_label(entry: dict) -> str:
    timestamp = entry["captured_at"] or entry["submitted_at"]
    time = show_time(timestamp, entry.get("timezone_name", "UTC"))
    return f"{entry['username']} · {time}"


def show_time(timestamp: str, zone_name: str) -> str:
    time = utc(datetime.fromisoformat(timestamp)).astimezone(ZoneInfo(zone_name))
    return f"{time:%d %b %Y at %H:%M:%S %Z (%z)} · {zone_name}"


player_id = require_login()
show_logged_in_as()
_, lobby_id, _ = require_active_membership()

page_header("Photo history", "Every moment, with the player, place, drink and points together.")
st.caption("Your photos and photos shared with you in this lobby. Manage sharing in Profile → Account & security → Photo privacy.")
st.caption(f"Photos are available until {PHOTO_RETENTION_DAYS} days after their season ends. Deleting your photo keeps your score.")
if st.session_state.pop("photo_deleted", False):
    st.success("Photo deleted. Your score is unchanged.")
if st.session_state.pop("checkin_corrected", False):
    st.success("Correction saved. Ownership and all affected owner income have been recalculated.")

try:
    entries = db.list_checkin_photos(player_id, lobby_id)
    if not entries:
        st.info("No photo history is available to you in this lobby yet. Other players' photos depend on their privacy settings.")
        st.stop()

except PermissionError:
    st.error("Choose a lobby you belong to to view its photos.")
    st.stop()
except (APIError, RequestError, RuntimeError, StorageException):
    st.error("We couldn't load the photo. Try again.")
    st.stop()

entries_by_id = {item["id"]: item for item in entries}
detail_id = st.session_state.get("history_detail_id")
if detail_id not in entries_by_id:
    st.session_state.pop("history_detail_id", None)
    detail_id = None

NIGHTS_PER_PAGE = 2

if len(entries) > 1 and detail_id is None:
    nights = []  # [[start, end, [entries...]], ...], newest night first
    for item in entries:  # already newest-first
        start, end = game_night_bounds(item)
        if nights and nights[-1][0] == start:
            nights[-1][2].append(item)
        else:
            nights.append([start, end, [item]])

    last_page = (len(nights) - 1) // NIGHTS_PER_PAGE
    page_number = min(max(st.session_state.get("history_page", 0), 0), last_page)
    first = page_number * NIGHTS_PER_PAGE
    visible_nights = nights[first:first + NIGHTS_PER_PAGE]

    for start, end, night_entries in visible_nights:
        count = f"{len(night_entries)} check-in{'s' if len(night_entries) != 1 else ''}"
        st.markdown(f'<div class="memory-night-label"><strong>{game_night_label(start, end)}</strong>'
                    f'<span>{count}</span></div>', unsafe_allow_html=True)
        with st.container(key=f"memory_row_{start.date().isoformat()}"):
            for column, item in zip(st.columns(len(night_entries)), night_entries):
                with column, st.container(key=f"memory_tile_{item['id']}"):
                    try:
                        photo = db.download_checkin_photo(player_id, lobby_id, item["id"])
                    except PermissionError:
                        st.warning("Photo access changed. Refresh to load the current photo history.")
                        st.stop()
                    except (APIError, RequestError, RuntimeError, StorageException):
                        st.warning("This photo could not be loaded. Its details are still available.")
                        photo = None
                    if memory_tile(item, photo, key=f"memory_tile_{item['id']}"):
                        st.session_state["history_detail_id"] = item["id"]
                        st.rerun()

    if last_page > 0:
        newer, _, older = st.columns(3)
        with newer:
            if st.button("Newer nights", disabled=page_number == 0):
                st.session_state["history_page"] = page_number - 1
                st.rerun()
        with older:
            if st.button("Older nights", disabled=page_number == last_page):
                st.session_state["history_page"] = page_number + 1
                st.rerun()
    st.stop()

if len(entries) > 1 and st.button("Back to photos"):
    st.session_state.pop("history_detail_id", None)
    st.rerun()
entry = entries_by_id[detail_id] if detail_id in entries_by_id else entries_by_id[next(iter(entries_by_id))]

try:
    photo = db.download_checkin_photo(player_id, lobby_id, entry["id"])
except PermissionError:
    st.warning("Photo access changed. Refresh to load the current photo history.")
    st.stop()
except (APIError, RequestError, RuntimeError, StorageException):
    st.error("We couldn't load the photo. Try again.")
    photo = None

with st.container(key="drink_ui_panel_photo"):
    location = "Outside game territories" if entry["location"] == "outside" else entry["territory"]
    context_line(entry["username"], location or "No territory assigned")
    if photo is None:
        framed_photo(entry, None, detail=True)
        st.info("This check-in's photo is unavailable.")
        st.caption("Removing a photo keeps the check-in and its score.")
    else:
        framed_photo(entry, photo, detail=True)
    time_label = "Photo received" if entry["captured_at"] else "Check-in submitted"
    st.text(f"{time_label} · {entry_label(entry)}")

# Scores and revision history remain visible after photo deletion.
if entry.get("rule_version") == "v1":
    model, season = entry["entry"], entry["season"]
    zone = season.timezone_name
    with st.container(key="drink_ui_panel_details"):
        section_heading("02", "Points & details", "The current award for this check-in.")
        selection = DRINK_LABELS.get(model.drink_type, model.drink_type)
        if model.size:
            selection += f" · {size_label(model.drink_type, model.size, season.scoring_rules)}"
        st.text(selection)
        territory_points = model.points_awarded if model.location_check_result == "matched" else 0
        st.text(f"Drinker: +{format_points(model.points_awarded + model.time_bonus)} season points · +{format_points(territory_points)} territory points")
        if model.focus_attempt_id:
            st.caption('Focus boost ×1.5 · This check-in keeps its earned multiplier after the boost ends.')
        if model.owner_bonus_quarters:
            income = format_points(Decimal(model.owner_bonus_quarters) / 4)
            st.text(f"Additional owner income: +{income} season points to {entry['income_recipient']}")
        else:
            st.text("No owner income for this check-in.")
        st.caption("Awards reflect the current corrected history. Corrections elsewhere can change the owner-income recipient.")
    with st.expander("Exact timestamps"):
        st.text(f"Submitted · {show_time(entry['submitted_at'], zone)}")
        if entry["captured_at"]:
            st.text(f"Photo received · {show_time(entry['captured_at'], zone)}")
    if model.revision:
        st.text(f"Corrected · {show_time(entry['corrected_at'], zone)} · revision {model.revision}")
        try:
            revisions = db.list_checkin_revisions(player_id, lobby_id, model.id)
        except (APIError, RequestError, RuntimeError, PermissionError):
            st.warning("The correction history could not be loaded. Refresh to try again.")
        else:
            with st.expander("Correction history"):
                st.table([{"Revision": r["revision"],
                    "Before": f"{r['old_drink_type']} / {r['old_size'] or 'one serving'}",
                    "After": f"{r['new_drink_type']} / {r['new_size'] or 'one serving'}",
                    "Changed": show_time(r["corrected_at"], zone)} for r in revisions])
    if entry["is_owner"] and can_correct(model, season, current_time()):
        with st.expander("Correct drink or size"):
            st.caption("Available for two minutes after the original submission, before season end. A correction can change later owner income and territory ownership.")
            key = f"correct_{model.id}_{model.revision}"
            with st.container(key="drink_ui_drinks"):
                chosen_drink = st.radio("Correct drink", list(DRINK_LABELS),
                    index=list(DRINK_LABELS).index(model.drink_type), format_func=DRINK_LABELS.get,
                    horizontal=True, width="stretch", key=f"{key}_drink")
            chosen_size = None
            if chosen_drink != "shot":
                with st.container(key="drink_ui_sizes"):
                    chosen_size = st.radio("Correct size", list(SIZE_LABELS),
                        index=list(SIZE_LABELS).index(model.size) if model.size in SIZE_LABELS else 0,
                        format_func=lambda value: size_label(chosen_drink, value, season.scoring_rules),
                        horizontal=True, width="stretch", key=f"{key}_size")
            st.info(f"Corrected base award: {base_points(chosen_drink, chosen_size, season.scoring_rules)} points")
            unchanged = chosen_drink == model.drink_type and chosen_size == model.size
            if st.button("Save correction", key=f"{key}_save", type="primary", width="stretch", disabled=unchanged):
                try:
                    db.correct_checkin(player_id, lobby_id, model.id, chosen_drink, chosen_size, model.revision)
                except PermissionError:
                    st.error("Only the submitter can correct this entry.")
                except CheckinRejected as error:
                    if error.reason == "correction_conflict":
                        st.error("This entry changed in another session. Refresh and review it before retrying.")
                    else:
                        st.error("The correction window has closed or this selection is invalid. Refresh to see the saved result.")
                except (APIError, RequestError, RuntimeError):
                    st.error("The correction result is uncertain. Refresh and check the saved entry before retrying.")
                else:
                    st.session_state["checkin_corrected"] = True
                    st.rerun()

else:
    with st.container(key="drink_ui_panel_details"):
        section_heading("02", "Drink & points", "Original details for this historical check-in.")
        photo_metadata(entry)

# Keep deletion available even when the download failed, so partial deletions
# can still be retried. This action never changes the scored entry.
if entry["is_owner"] and entry["has_photo"]:
    with st.expander("Manage your photo"):
        st.caption("Permanently remove the image. Your check-in, points and owner income stay.")
        confirmed = st.checkbox("Permanently delete this photo", key=f"confirm_delete_{entry['id']}")
        if st.button("Delete my photo", disabled=not confirmed):
            try:
                db.delete_checkin_photo(player_id, lobby_id, entry["id"])
            except PermissionError:
                st.error("Only the photo's owner can delete it.")
            except (APIError, RequestError, RuntimeError, StorageException):
                st.error("We couldn't finish deleting the photo. Try again.")
            else:
                st.session_state["photo_deleted"] = True
                st.rerun()
