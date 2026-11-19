"""The one file that talks to Supabase. Thin CRUD wrappers only -- no game
rules here. Pages call these functions and pass plain values; everything
else (validation, scoring, standings) lives in core/.

Server-only credentials come from .streamlit/secrets.toml (SUPABASE_URL /
SUPABASE_KEY), which is gitignored -- see .streamlit/secrets.toml.example.
"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from core.auth import new_token, token_hash
from core.checkin_photo import photo_expires_at
from core.photo_privacy import can_view_photo
from core.constants import UNLINKED_PHOTO_GRACE_HOURS

from supabase import Client, create_client
from postgrest.exceptions import APIError
from core.checkins import CheckinRejected

from core.models import Arena, DrinkEntry, Lobby, LobbyMembership, MinigameAttempt, Player, Season, Territory, Team

_client: Client | None = None
CHECKIN_PHOTO_BUCKET = "check-in-photos"


def get_client() -> Client:
    global _client
    if _client is not None:
        return _client

    url = None
    key = None
    try:
        import streamlit as st

        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
    except Exception:
        pass

    url = url or os.environ.get("SUPABASE_URL")
    key = key or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Supabase credentials missing. Set SUPABASE_URL and SUPABASE_KEY "
            "in .streamlit/secrets.toml (see secrets.toml.example)."
        )

    endpoint = urlsplit(url)
    local_http = endpoint.scheme == "http" and endpoint.hostname in ("localhost", "127.0.0.1", "::1")
    if not endpoint.hostname or (endpoint.scheme != "https" and not local_http):
        raise RuntimeError("Supabase requires HTTPS or an HTTP endpoint on localhost.")

    _client = create_client(url, key)
    return _client


# -- players -----------------------------------------------------------

def list_players() -> list[Player]:
    rows = get_client().table("players").select("*").execute().data
    return [
        Player(
            id=r["id"],
            display_name=r["display_name"],
            first_name=r["first_name"],
            last_name=r["last_name"],
            pin_hash=r["pin_hash"],
            email=r.get("email"),
        )
        for r in rows
    ]


def insert_player(player: Player) -> None:
    get_client().table("players").insert(
        {
            "id": player.id,
            "display_name": player.display_name,
            "first_name": player.first_name,
            "last_name": player.last_name,
            "pin_hash": player.pin_hash,
            "email": player.email,
        }
    ).execute()


# -- lobbies & memberships ------------------------------------------------

def list_lobbies() -> list[Lobby]:
    rows = get_client().table("lobbies").select("*").execute().data
    # Deleted lobbies are hidden for everyone (r.get: works before migration 017 too).
    return [Lobby(id=r["id"], name=r["name"], invite_code=r["invite_code"],
                  game_mode=r.get("game_mode", "individual"), team_count=r.get("team_count"),
                  team_capacity=r.get("team_capacity"), team_assignment=r.get("team_assignment"))
            for r in rows if not r.get("deleted_at")]


def insert_lobby(lobby: Lobby) -> None:
    row = {"id": lobby.id, "name": lobby.name, "invite_code": lobby.invite_code}
    if lobby.game_mode == "team":
        row.update(game_mode=lobby.game_mode, team_count=lobby.team_count,
                   team_capacity=lobby.team_capacity, team_assignment=lobby.team_assignment)
    get_client().table("lobbies").insert(row).execute()


def get_lobby_choice(player_id: str) -> str | None:
    rows = get_client().table("player_lobby_choices").select("lobby_id").eq("player_id", player_id).execute().data
    return rows[0]["lobby_id"] if rows else None


def save_lobby_choice(player_id: str, lobby_id: str) -> None:
    # Context is never authorization: validate before saving and on every use.
    if not any(m.lobby_id == lobby_id for m in list_memberships_for_player(player_id)):
        raise PermissionError("You are no longer a member of this lobby.")
    get_client().table("player_lobby_choices").upsert(
        {"player_id": player_id, "lobby_id": lobby_id}, on_conflict="player_id"
    ).execute()


def list_memberships_for_player(player_id: str, *, include_left: bool = False) -> list[LobbyMembership]:
    rows = get_client().table("lobby_memberships").select("*").eq("player_id", player_id).execute().data
    return [
        LobbyMembership(
            id=r["id"],
            player_id=r["player_id"],
            lobby_id=r["lobby_id"],
            joined_at=datetime.fromisoformat(r["joined_at"]),
            team_id=r.get("team_id"),
            left_at=datetime.fromisoformat(r["left_at"]) if r.get("left_at") else None,
        )
        for r in rows if include_left or not r.get("left_at")
    ]


def list_memberships_for_lobby(lobby_id: str, *, include_left: bool = False) -> list[LobbyMembership]:
    rows = get_client().table("lobby_memberships").select("*").eq("lobby_id", lobby_id).execute().data
    return [
        LobbyMembership(
            id=r["id"],
            player_id=r["player_id"],
            lobby_id=r["lobby_id"],
            joined_at=datetime.fromisoformat(r["joined_at"]),
            team_id=r.get("team_id"),
            left_at=datetime.fromisoformat(r["left_at"]) if r.get("left_at") else None,
        )
        for r in rows if include_left or not r.get("left_at")
    ]


def insert_membership(membership: LobbyMembership) -> None:
    get_client().table("lobby_memberships").insert(
        {
            "id": membership.id,
            "player_id": membership.player_id,
            "lobby_id": membership.lobby_id,
            "joined_at": membership.joined_at.isoformat(),
        }
    ).execute()


def leave_lobby(player_id: str, lobby_id: str) -> None:
    """Retain history; the database serializes departure with game actions."""
    _membership_rpc("leave_lobby", player_id, lobby_id)


def rejoin_lobby(player_id: str, lobby_id: str) -> None:
    _membership_rpc("rejoin_lobby", player_id, lobby_id)


def delete_lobby(player_id: str, lobby_id: str) -> None:
    """Hide the lobby for everyone; history stays. The database allows only its creator."""
    try:
        get_client().rpc("delete_lobby", {"actor_player": player_id, "target_lobby": lobby_id}).execute()
    except APIError as error:
        if getattr(error, "message", "") == "permission_denied":
            raise PermissionError("Only the person who created this lobby can delete it.") from None
        raise


def _membership_rpc(action: str, player_id: str, lobby_id: str) -> None:
    try:
        get_client().rpc(action, {"actor_player": player_id, "target_lobby": lobby_id}).execute()
    except APIError as error:
        reason = getattr(error, "message", "")
        if reason == "permission_denied":
            raise PermissionError("This account cannot change that lobby membership.") from None
        if reason in {"minigame_active", "time_busy"}:
            raise ValueError("Finish your active minigame before leaving, or wait for it to expire.") from None
        raise


def membership_display_name(membership_id: str, lobby_id: str) -> str:
    rows = get_client().table("lobby_memberships").select("players(display_name)").eq(
        "id", membership_id).eq("lobby_id", lobby_id).execute().data
    return rows[0]["players"]["display_name"] if rows else "Lobby member"


# -- seasons ----------------------------------------------------------

def list_seasons_for_lobby(lobby_id: str) -> list[Season]:
    rows = get_client().table("seasons").select("*").eq("lobby_id", lobby_id).execute().data
    return sorted([_row_to_season(r) for r in rows], key=lambda s: s.starts_at, reverse=True)


def membership_context(player_id: str, membership_id: str, lobby_id: str, season_id: str) -> tuple[LobbyMembership | None, Season | None]:
    """Fresh membership and its lobby's seasons in one scoped database read."""
    rows = (get_client().table("lobby_memberships")
        .select("*,lobbies!inner(seasons(*))")
        .eq("id", membership_id).eq("player_id", player_id).eq("lobby_id", lobby_id).execute().data)
    if not rows or rows[0].get("left_at"):
        return None, None
    row = rows[0]
    member = LobbyMembership(row["id"], row["player_id"], row["lobby_id"],
        datetime.fromisoformat(row["joined_at"]), row.get("team_id"))
    season = next((_row_to_season(s) for s in row["lobbies"]["seasons"]
                   if s["id"] == season_id and s["lobby_id"] == lobby_id), None)
    return member, season


def _row_to_season(row: dict) -> Season:
    return Season(row["id"], row["lobby_id"], datetime.fromisoformat(row["starts_at"]),
                  datetime.fromisoformat(row["ends_at"]), row["length_choice"],
                  row.get("timezone_name", "Europe/Lisbon"), row.get("scoring_version", "legacy"),
                  row.get("scoring_rules"))


def _scoring_rpc(name: str, parameters: dict):
    try:
        return get_client().rpc(name, parameters).execute().data
    except APIError as error:
        reason = getattr(error, "message", "")
        if reason == "quiz_reserved_points":
            from core.quiz_duel import ERRORS
            raise ValueError(ERRORS[reason]) from None
        if reason == "permission_denied":
            raise PermissionError("This account cannot change that lobby or entry.") from None
        if reason in {"invalid_selection", "scoring_closed", "cooldown", "correction_closed", "correction_conflict",
                      "team_required", "invalid_territory", "invalid_photo", "season_still_active", "lobby_already_started", "invalid_timezone", "invalid_rules"}:
            raise CheckinRejected(reason) from None
        if reason == "scoring_setup_required" or error.code in {"42703", "PGRST202", "PGRST204"}:
            raise RuntimeError("Scoring setup is required. Ask the Data owner to apply migration 005.") from None
        raise


def start_scoring_season(player_id: str, lobby_id: str, length_choice: str, timezone_name: str, *, test_mode: bool = False) -> Season:
    from core.scoring_v1 import new_rules
    # Friendly early rejection; migration 009 enforces this atomically too.
    if list_seasons_for_lobby(lobby_id):
        raise CheckinRejected("lobby_already_started")
    rows = _scoring_rpc("start_scoring_season", {"actor_player": player_id, "target_lobby": lobby_id,
        "length_choice": length_choice, "zone_name": timezone_name, "frozen_rules": new_rules(test_mode=test_mode)})
    return _row_to_season(rows[0])


def insert_season(season: Season) -> None:
    """Legacy import helper. v1 creation must use its transaction RPC."""
    if season.scoring_version != "legacy":
        raise RuntimeError("Start v1 seasons with start_scoring_season so membership and overlap checks run.")
    row = {
            "id": season.id,
            "lobby_id": season.lobby_id,
            "starts_at": season.starts_at.isoformat(),
            "ends_at": season.ends_at.isoformat(),
            "length_choice": season.length_choice,
        }
    get_client().table("seasons").insert(row).execute()


# -- territories & arenas -------------------------------------------------

def list_territories() -> list[Territory]:
    rows = get_client().table("territories").select("*").execute().data
    return [Territory(id=r["id"], name=r["name"], boundary=r["boundary"]) for r in rows]


def upsert_territories(territories: list[Territory]) -> None:
    """Copy territories into the table, inserting new ids and updating the
    name and outline of existing ones. Territories removed from the file are
    left in the table so older drink entries still point at a valid row."""
    if not territories:
        return
    get_client().table("territories").upsert(
        [{"id": t.id, "name": t.name, "boundary": t.boundary} for t in territories]
    ).execute()


def list_arenas() -> list[Arena]:
    rows = get_client().table("arenas").select("*").execute().data
    return [Arena(id=r["id"], name=r["name"], map_point=r["map_point"]) for r in rows]


# -- drink entries -------------------------------------------------------

def _all_rows(query) -> list[dict]:
    rows = []
    while True:
        batch = query.range(len(rows), len(rows) + 499).execute().data
        rows.extend(batch)
        if len(batch) < 500:
            return rows


def list_drink_entries(season_id: str) -> list[DrinkEntry]:
    rows = _all_rows(get_client().table("drink_entries").select("*").eq("season_id", season_id).order("submitted_at").order("id"))
    return [_row_to_drink_entry(r) for r in rows]


def list_drink_entries_for_membership(membership_id: str) -> list[DrinkEntry]:
    rows = _all_rows(get_client().table("drink_entries").select("*").eq("membership_id", membership_id).order("submitted_at").order("id"))
    return [_row_to_drink_entry(r) for r in rows]


def _row_to_drink_entry(r: dict) -> DrinkEntry:
    device_gps = None
    if r.get("device_gps_lat") is not None and r.get("device_gps_lng") is not None:
        device_gps = (r["device_gps_lat"], r["device_gps_lng"])
    photo_gps = None
    if r.get("photo_gps_lat") is not None and r.get("photo_gps_lng") is not None:
        photo_gps = (r["photo_gps_lat"], r["photo_gps_lng"])
    return DrinkEntry(
        id=r["id"],
        membership_id=r["membership_id"],
        season_id=r["season_id"],
        drink_type=r["drink_type"],
        amount=r.get("amount"),
        photo_ref=r["photo_ref"],
        device_gps=device_gps,
        photo_gps=photo_gps,
        territory_id=r.get("territory_id"),
        location_check_result=r["location_check_result"],
        points_awarded=_score_number(r['points_awarded']),
        submitted_at=datetime.fromisoformat(r["submitted_at"]),
        photo_captured_at=datetime.fromisoformat(r["photo_captured_at"]) if r.get("photo_captured_at") else None,
        size=r.get("size"), rule_version=r.get("rule_version", "legacy"), event_order=r.get("event_order"),
        owner_membership_id=r.get("owner_membership_id"), owner_bonus_quarters=_score_number(r.get('owner_bonus_quarters', 0)),
        corrected_at=datetime.fromisoformat(r["corrected_at"]) if r.get("corrected_at") else None,
        revision=r.get("revision", 0), team_id=r.get("team_id"), owner_team_id=r.get("owner_team_id"),
        duel_id=r.get("duel_id"), duel_transfer_to=r.get("duel_transfer_to"),
        duel_transfer_order=r.get("duel_transfer_order"),
        focus_attempt_id=r.get('focus_attempt_id'),
        time_duel_id=r.get('time_duel_id'), time_bonus=_score_number(r.get('time_bonus', 0)),
        absent_member_ids=tuple(r.get('absent_member_ids') or ()),
    )


def _score_number(value) -> int | float:
    """DB numeric half-units are binary-exact; retain old integer presentation."""
    number = float(value)
    return int(number) if number.is_integer() else number


def _drink_entry_row(entry: DrinkEntry) -> dict:
    row = {
        "id": entry.id,
        "membership_id": entry.membership_id,
        "season_id": entry.season_id,
        "drink_type": entry.drink_type,
        "amount": entry.amount,
        "photo_ref": entry.photo_ref,
        # Verification is finished before persistence. Never keep exact GPS.
        "device_gps_lat": None,
        "device_gps_lng": None,
        "photo_gps_lat": None,
        "photo_gps_lng": None,
        "territory_id": entry.territory_id,
        "location_check_result": entry.location_check_result,
        "points_awarded": entry.points_awarded,
        "submitted_at": entry.submitted_at.isoformat(),
    }
    if entry.photo_captured_at is not None:
        row["photo_captured_at"] = entry.photo_captured_at.isoformat()
    if entry.rule_version != "legacy":
        row.update(size=entry.size, rule_version=entry.rule_version)
    if entry.focus_attempt_id:
        row['focus_attempt_id'] = entry.focus_attempt_id
    return row


def insert_drink_entry(entry: DrinkEntry) -> None:
    if entry.rule_version != "legacy":
        raise RuntimeError("Save v1 check-ins with save_drink_entry_photo so authoritative validation runs.")
    get_client().table("drink_entries").insert(_drink_entry_row(entry)).execute()


def _checkin_photo_path(lobby_id: str, entry_id: str) -> str:
    return f"{lobby_id}/{entry_id}.jpg"


def _private_photo_bucket():
    storage = get_client().storage
    if storage.get_bucket(CHECKIN_PHOTO_BUCKET).public is not False:
        raise RuntimeError("Check-in photos require a private storage bucket.")
    return storage.from_(CHECKIN_PHOTO_BUCKET)


def save_drink_entry_photo(player_id: str, lobby_id: str, entry: DrinkEntry, photo: bytes) -> DrinkEntry:
    """Save the photo first, then record points once for this camera capture."""
    selected_season = next((s for s in list_seasons_for_lobby(lobby_id) if s.id == entry.season_id), None)
    if not any(
        member.id == entry.membership_id and member.lobby_id == lobby_id
        for member in list_memberships_for_player(player_id)
    ) or selected_season is None:
        raise PermissionError("The player and season must belong to this lobby.")
    if entry.rule_version != getattr(selected_season, "scoring_version", "legacy"):
        raise RuntimeError("Scoring setup is required. Refresh and select the correct season.")

    table = get_client().table("drink_entries")
    saved = table.select("*").eq("id", entry.id).eq("membership_id", entry.membership_id).execute().data
    if saved:
        return _row_to_drink_entry(saved[0])

    if hasattr(selected_season, "starts_at") and hasattr(selected_season, "ends_at"):
        from core.scoring_v1 import utc
        if not utc(selected_season.starts_at) <= utc(entry.submitted_at) < utc(selected_season.ends_at):
            raise CheckinRejected("scoring_closed")

    photo_path = _checkin_photo_path(lobby_id, entry.id)
    _private_photo_bucket().upload(photo_path, photo, {"content-type": "image/jpeg", "upsert": "true"})
    if entry.rule_version == "v1":
        saved = _scoring_rpc("accept_scoring_checkin", {
            "actor_player": player_id, "capture_id": entry.id, "member_id": entry.membership_id,
            "target_season": entry.season_id, "selected_drink": entry.drink_type,
            "selected_size": entry.size, "verified_territory": entry.territory_id,
            "location_result": entry.location_check_result, "stored_photo": photo_path,
            "photo_received_at": entry.photo_captured_at.isoformat() if entry.photo_captured_at else entry.submitted_at.isoformat(),
        })
        return _row_to_drink_entry(saved[0])
    # Retrying the same capture uses the same object path and primary key.
    saved = table.upsert(
        _drink_entry_row(replace(entry, photo_ref=photo_path)),
        on_conflict="id",
        ignore_duplicates=True,
    ).execute().data
    if not saved:
        saved = table.select("*").eq("id", entry.id).eq("membership_id", entry.membership_id).execute().data
    if not saved:
        raise RuntimeError("Could not confirm the check-in was saved.")
    return _row_to_drink_entry(saved[0])


def _lobby_photo_query(player_id: str, lobby_id: str):
    if not any(member.lobby_id == lobby_id for member in list_memberships_for_player(player_id)):
        raise PermissionError("Only members of this lobby can view its check-in photos.")

    return (
        get_client().table("drink_entries")
        .select(
            "*,territories(name),seasons!inner(*),"
            "lobby_memberships!drink_entries_membership_id_fkey!inner(lobby_id,player_id,players(display_name))"
        )
        .eq("seasons.lobby_id", lobby_id)
        .eq("lobby_memberships.lobby_id", lobby_id)
    )


def _photo_audience(player_id: str, lobby_id: str, rows: list[dict]):
    """Uncached current roster/consent, shared by listing and direct download."""
    members = list_memberships_for_lobby(lobby_id)
    owners = {row["lobby_memberships"]["player_id"] for row in rows}
    ids = owners | {m.player_id for m in members}
    preferences = (_all_rows(get_client().table("player_photo_preferences")
                   .select("player_id,share_checkin_photos").in_("player_id", sorted(ids))) if ids else [])
    sharing = {r["player_id"]: r["share_checkin_photos"] for r in preferences}
    return lambda row: can_view_photo(player_id, row["lobby_memberships"]["player_id"],
                                      row.get("team_id"), members, sharing)


def list_checkin_photos(player_id: str, lobby_id: str) -> list[dict]:
    rows = _all_rows(_lobby_photo_query(player_id, lobby_id).order("submitted_at", desc=True).order("id"))
    allowed = _photo_audience(player_id, lobby_id, rows) if rows else lambda row: False
    transfers = {row["duel_id"]: row for row in rows if row.get("duel_id") and row.get("duel_transfer_to")}
    names = {row.get("membership_id"): row["lobby_memberships"]["players"]["display_name"] for row in rows}
    team_names = ({team.id: team.name for team in list_lobby_teams(player_id, lobby_id)}
                  if any(row.get("team_id") for row in rows) else {})
    return [
        {
            "id": row["id"],
            "username": row["lobby_memberships"]["players"]["display_name"],
            "player_id": row["lobby_memberships"]["player_id"],
            "team_id": row.get("team_id"),
            "team_name": team_names.get(row.get("team_id")),
            "territory": row["territories"]["name"] if row["territories"] else None,
            "location": row["location_check_result"],
            "captured_at": row.get("photo_captured_at"),
            "submitted_at": row["submitted_at"],
            "is_owner": row["lobby_memberships"]["player_id"] == player_id,
            "has_photo": row["photo_ref"] == _checkin_photo_path(lobby_id, row["id"]),
            "season_id": row.get("season_id"), "membership_id": row.get("membership_id"),
            "timezone_name": row["seasons"].get("timezone_name", "UTC"),
            "season_ends_at": row["seasons"]["ends_at"],
            "drink_type": row.get("drink_type"), "size": row.get("size"),
            "rule_version": row.get("rule_version", "legacy"), "base_points": row.get("points_awarded", 0),
            "owner_bonus_quarters": row.get("owner_bonus_quarters", 0),
            "income_recipient": (team_names.get(row.get("owner_team_id"), "Team") if row.get("team_id")
                                 else names.get(row.get("owner_membership_id"), "Lobby member")),
            "corrected_at": row.get("corrected_at"), "revision": row.get("revision", 0),
            "entry": _row_to_drink_entry(row) if row.get("rule_version") == "v1" else None,
            "season": _row_to_season(row["seasons"]) if row.get("rule_version") == "v1" else None,
            "duel_id": row.get("duel_id"),
            "duel_season_points": (0 if row.get("duel_transfer_to") else row.get("points_awarded", 0)
                + (transfers[row["duel_id"]]["points_awarded"]
                   if row.get("duel_id") in transfers else 0)),
        }
        for row in rows
        if allowed(row) and datetime.now(timezone.utc) < photo_expires_at(datetime.fromisoformat(row["seasons"]["ends_at"]))
    ]


def correct_checkin(player_id: str, lobby_id: str, entry_id: str, drink_type: str,
                    size: str | None, expected_revision: int) -> DrinkEntry:
    rows = _lobby_photo_query(player_id, lobby_id).eq("id", entry_id).execute().data
    if not rows or rows[0]["lobby_memberships"]["player_id"] != player_id:
        raise PermissionError("Only the submitter can correct an entry.")
    saved = _scoring_rpc("correct_scoring_checkin", {"actor_player": player_id, "target_entry": entry_id,
        "selected_drink": drink_type, "selected_size": size, "expected_revision": expected_revision})
    return _row_to_drink_entry(saved[0])


def list_checkin_revisions(player_id: str, lobby_id: str, entry_id: str) -> list[dict]:
    if not _lobby_photo_query(player_id, lobby_id).eq("id", entry_id).execute().data:
        raise PermissionError("Entry is not in this lobby.")
    return get_client().table("drink_entry_revisions").select(
        "revision,old_drink_type,old_size,new_drink_type,new_size,corrected_at"
    ).eq("entry_id", entry_id).order("revision").execute().data


def download_checkin_photo(player_id: str, lobby_id: str, entry_id: str) -> bytes | None:
    rows = _lobby_photo_query(player_id, lobby_id).eq("id", entry_id).execute().data
    photo_path = _checkin_photo_path(lobby_id, entry_id)
    if not rows or rows[0]["photo_ref"] != photo_path:
        return None
    if datetime.now(timezone.utc) >= photo_expires_at(datetime.fromisoformat(rows[0]["seasons"]["ends_at"])):
        return None
    if not _photo_audience(player_id, lobby_id, rows)(rows[0]):
        raise PermissionError("This photo is private.")
    return _private_photo_bucket().download(photo_path)


def delete_checkin_photo(player_id: str, lobby_id: str, entry_id: str) -> None:
    """Remove the owner's image while preserving the entry and its score."""
    rows = _lobby_photo_query(player_id, lobby_id).eq("id", entry_id).execute().data
    if not rows or rows[0]["lobby_memberships"]["player_id"] != player_id:
        raise PermissionError("Only the photo's owner can delete it.")
    path = _checkin_photo_path(lobby_id, entry_id)
    if rows[0]["photo_ref"] != path:
        return
    _private_photo_bucket().remove([path])
    # Removing an already absent object is safe when a previous reply was lost.
    _mark_photo_removed(entry_id, path, "deleted")


def _mark_photo_removed(entry_id: str, path: str, reason: str) -> None:
    (get_client().table("drink_entries").update({"photo_ref": reason})
     .eq("id", entry_id).eq("photo_ref", path).execute())


def _list_photo_folder(bucket, path: str) -> list[dict]:
    """Read every page before deleting objects so offsets remain stable."""
    objects = []
    while True:
        batch = bucket.list(path, {"limit": 100, "offset": len(objects), "sortBy": {"column": "name", "order": "asc"}})
        objects.extend(batch)
        if len(batch) < 100:
            return objects


def cleanup_checkin_photos(*, apply: bool = False) -> dict[str, int]:
    """Server maintenance: expired images and abandoned uploads, never scores.

    Dry run by default. Only inspect the lobby/entry.jpg layout generated here.
    Unlinked uploads get 24 hours for a failed check-in save to be retried.
    """
    bucket = _private_photo_bucket()
    now = datetime.now(timezone.utc)
    counts = {"expired": 0, "unlinked": 0}
    for folder in _list_photo_folder(bucket, ""):
        lobby_id = folder["name"]
        if folder.get("id") is not None or not lobby_id or "/" in lobby_id or lobby_id in (".", ".."):
            continue
        for obj in _list_photo_folder(bucket, lobby_id):
            name = obj["name"]
            if not obj.get("id") or not name.endswith(".jpg") or "/" in name:
                continue
            entry_id = name[:-4]
            path = _checkin_photo_path(lobby_id, entry_id)
            rows = (get_client().table("drink_entries").select("id,photo_ref,seasons!inner(ends_at)")
                    .eq("id", entry_id).eq("photo_ref", path).execute().data)
            if rows:
                if now < photo_expires_at(datetime.fromisoformat(rows[0]["seasons"]["ends_at"])):
                    continue
                reason = "expired"
            else:
                # Missing timestamps fail closed: do not guess an upload's age.
                modified = obj.get("updated_at") or obj.get("created_at")
                if not modified:
                    continue
                modified_at = datetime.fromisoformat(modified.replace("Z", "+00:00"))
                if modified_at.tzinfo is None:
                    modified_at = modified_at.replace(tzinfo=timezone.utc)
                if now < modified_at + timedelta(hours=UNLINKED_PHOTO_GRACE_HOURS):
                    continue
                reason = "unlinked"
            if apply:
                bucket.remove([path])
                if rows:
                    _mark_photo_removed(entry_id, path, "expired")
            counts[reason] += 1
    return counts


# -- minigame attempts ------------------------------------------------

def _focus_rpc(name: str, parameters: dict) -> dict:
    from core.focus_challenge import ERRORS
    from core.quiz_duel import ERRORS as QUIZ_ERRORS
    try:
        return get_client().rpc(name, parameters).execute().data
    except APIError as error:
        reason = error.message.strip()
        if reason == "time_busy":
            from core.time_duel import ERRORS as TIME_ERRORS
            raise ValueError(TIME_ERRORS[reason]) from None
        if reason == "quiz_busy":
            raise ValueError(QUIZ_ERRORS[reason]) from None
        if reason == 'permission_denied':
            raise PermissionError(ERRORS[reason]) from None
        if reason in ERRORS:
            raise ValueError(ERRORS[reason]) from None
        if error.code in {'42P01', '42703', 'PGRST202', 'PGRST204'}:
            raise RuntimeError('Focus Challenge setup is required: apply migrations 014 and 015.') from None
        raise


def focus_status(player_id: str, season_id: str) -> dict:
    return _focus_rpc('focus_status', {'actor_player': player_id, 'target_season': season_id})


def start_focus_attempt(player_id: str, season_id: str, request_id: str) -> dict:
    return _focus_rpc('start_focus_attempt', {'actor_player': player_id,
        'target_season': season_id, 'request_id': request_id})


def focus_attempt_action(player_id: str, attempt_id: str, revision: int, action: str, evidence: dict) -> dict:
    return _focus_rpc('focus_attempt_action', {'actor_player': player_id, 'target_attempt': attempt_id,
        'expected_revision': revision, 'selected_action': action, 'evidence': evidence})

def _duel_rpc(name: str, parameters: dict) -> list[dict]:
    from core.chug_duel import ERRORS
    from core.quiz_duel import ERRORS as QUIZ_ERRORS
    try:
        return get_client().rpc(name, parameters).execute().data
    except APIError as error:
        reason = error.message.strip()
        if reason == 'time_busy':
            from core.time_duel import ERRORS as TIME_ERRORS
            raise ValueError(TIME_ERRORS[reason]) from None
        if reason in {"quiz_busy", "quiz_reserved_points"}:
            raise ValueError(QUIZ_ERRORS[reason]) from None
        if reason == "permission_denied":
            raise PermissionError(ERRORS[reason]) from None
        if reason in ERRORS:
            raise ValueError(ERRORS[reason]) from None
        if error.code in {"42P01", "42703", "PGRST202", "PGRST204"} or reason == "scoring_setup_required":
            raise RuntimeError("Chug Duel setup is not complete. Please contact the app organizer.") from None
        raise


def list_chug_duels(player_id: str, season_id: str) -> list[dict]:
    return _duel_rpc("list_chug_duels", {"actor_player": player_id, "target_season": season_id})


def pending_minigame_invite_count(player_id: str, season_id: str) -> int:
    return get_client().rpc("pending_minigame_invite_count", {
        "actor_player": player_id, "target_season": season_id,
    }).execute().data


def pending_minigame_invites(player_id: str, season_id: str) -> dict[str, int]:
    return get_client().rpc("pending_minigame_invites", {
        "actor_player": player_id, "target_season": season_id,
    }).execute().data[0]


def invite_chug_duel(player_id: str, season_id: str, invitation_id: str,
                     opponent_id: str, drink: str, size: str | None) -> dict:
    return _duel_rpc("invite_chug_duel", {"actor_player": player_id, "target_season": season_id,
        "invitation_id": invitation_id, "opponent_member": opponent_id,
        "selected_drink": drink, "selected_size": size})[0]


def chug_duel_action(player_id: str, duel_id: str, action: str, winner_id: str | None = None) -> dict:
    return _duel_rpc("chug_duel_action", {"actor_player": player_id, "target_duel": duel_id,
        "selected_action": action, "winning_member": winner_id})[0]


def start_chug_duel(player_id: str, lobby_id: str, season_id: str, duel_id: str,
                    photo: bytes, photo_received_at: datetime, device_gps, accuracy_m) -> dict:
    """One shared capture, two private copies with existing owner/retention rules.

    Both scored entries and the started state commit in one database transaction.
    Exact coordinates never leave this Python process.
    """
    from core.checkin_photo import prepare_checkin_photo
    from core.scoring_v1 import create_scored_entry, current_time, utc
    from core.chug_duel import ERRORS
    duel = next((d for d in list_chug_duels(player_id, season_id) if d["id"] == duel_id), None)
    if not duel:
        raise PermissionError(ERRORS["permission_denied"])
    members = list_memberships_for_player(player_id)
    if not any(m.id == duel["challenger_id"] and m.lobby_id == lobby_id for m in members):
        raise PermissionError(ERRORS["permission_denied"])
    season = next((s for s in list_seasons_for_lobby(lobby_id) if s.id == season_id), None)
    if season is None:
        raise PermissionError(ERRORS["permission_denied"])
    if duel["status"] in {"started", "completed", "aborted"}:
        return duel  # recover a committed start without replacing its images
    if duel["status"] != "accepted":
        raise ValueError(ERRORS["duel_unavailable"])
    now = current_time()
    if not utc(datetime.fromisoformat(duel["accepted_at"])) <= utc(photo_received_at) <= now:
        raise ValueError(ERRORS["invalid_photo"])
    _, cleaned = prepare_checkin_photo(photo)
    from data.territory_file import load_territories
    territories = load_territories()
    entries = []
    for role in ("challenger", "opponent"):
        mid, eid = duel[f"{role}_id"], duel[f"{role}_entry_id"]
        entries.append(create_scored_entry(mid, season, duel["drink_type"], duel.get("size"),
            _checkin_photo_path(lobby_id, eid), device_gps, accuracy_m, now, territories,
            list_drink_entries_for_membership(mid), entry_id=eid))
    upsert_territories(territories)
    bucket = _private_photo_bucket()
    for entry in entries:
        bucket.upload(entry.photo_ref, cleaned, {"content-type": "image/jpeg", "upsert": "true"})
    return _duel_rpc("start_chug_duel", {"actor_player": player_id, "target_duel": duel_id,
        "verified_territory": entries[0].territory_id, "location_result": entries[0].location_check_result,
        "photo_received_at": utc(photo_received_at).isoformat()})[0]

def list_minigame_attempts_for_membership(membership_id: str) -> list[MinigameAttempt]:
    rows = (
        get_client()
        .table("minigame_attempts")
        .select("*")
        .eq("membership_id", membership_id)
        .execute()
        .data
    )
    return [
        MinigameAttempt(
            id=r["id"],
            membership_id=r["membership_id"],
            season_id=r["season_id"],
            arena_id=r["arena_id"],
            game_type=r["game_type"],
            game_window_id=r["game_window_id"],
            started_at=datetime.fromisoformat(r["started_at"]),
            status=r["status"],
            result=r.get("result"),
        )
        for r in rows
    ]


def insert_minigame_attempt(attempt: MinigameAttempt) -> None:
    get_client().table("minigame_attempts").insert(
        {
            "id": attempt.id,
            "membership_id": attempt.membership_id,
            "season_id": attempt.season_id,
            "arena_id": attempt.arena_id,
            "game_type": attempt.game_type,
            "game_window_id": attempt.game_window_id,
            "started_at": attempt.started_at.isoformat(),
            "status": attempt.status,
            "result": attempt.result,
        }
    ).execute()


def get_player(player_id: str) -> Player | None:
    rows = get_client().table("players").select("*").eq("id", player_id).execute().data
    return Player(**rows[0]) if rows else None


def allow_login_attempt(player_id: str) -> bool:
    return bool(get_client().rpc("allow_login_attempt", {"target_player": player_id}).execute().data)


def _player_by_email(email: str) -> Player | None:
    rows = get_client().table("players").select("*").eq("email", email).limit(1).execute().data
    return Player(**rows[0]) if rows else None


def request_password_reset(email: str) -> None:
    from core.auth import normalize_email
    from core.password_recovery import new_reset_code, reset_code_hash
    from password_email import email_settings, send_reset_email

    email = normalize_email(email)
    settings = email_settings()  # Configuration failures must not reveal account existence.
    player = _player_by_email(email)
    if not player or not allow_login_attempt(player.id):
        return
    code = new_reset_code()
    stored_hash = reset_code_hash(code, player.pin_hash)
    issued = get_client().rpc("issue_password_reset", {
        "target_player": player.id, "new_code_hash": stored_hash,
    }).execute().data
    if issued:
        try:
            send_reset_email(email, code, settings)
        except RuntimeError:
            # Same public response for unknown accounts and delivery failures.
            # Remove only this failed code; do not remove a concurrent replacement.
            (get_client().table("password_resets").delete().eq("player_id", player.id)
             .eq("code_hash", stored_hash).execute())


def reset_password(email: str, code: str, password: str, confirmation: str) -> None:
    from core.auth import hash_password, normalize_email, validate_password, verify_password
    from core.password_recovery import RESET_ERROR, reset_code_hash

    email = normalize_email(email)
    validate_password(password, confirmation)
    player = _player_by_email(email)
    if not player or not allow_login_attempt(player.id):
        raise ValueError(RESET_ERROR)
    stored_hash = reset_code_hash(code, player.pin_hash)
    # Do not reveal whether a proposed password matches an account's current one.
    if verify_password(password, player.pin_hash):
        raise ValueError(RESET_ERROR)
    consumed = get_client().rpc("consume_password_reset", {
        "target_email": email, "supplied_code_hash": stored_hash,
        "new_password_hash": hash_password(password),
    }).execute().data
    if not consumed:
        raise ValueError(RESET_ERROR)


def _profile_actor(player_id: str, credential_version: str) -> Player:
    player = get_player(player_id)
    if not player or player.pin_hash != credential_version:
        raise ValueError("Your sign-in changed. Please log in again.")
    return player


def _save_account_fields(player: Player, credential_version: str, fields: dict) -> Player:
    # A concurrent password change must also block a stale session's write.
    rows = (get_client().table("players").update(fields).eq("id", player.id)
            .eq("pin_hash", credential_version).execute().data)
    if not rows:
        raise ValueError("Your sign-in changed. Please log in again.")
    return Player(**rows[0])


def update_profile(player_id: str, credential_version: str, first_name: str,
                   last_name: str, username: str) -> Player:
    from core.profile import edit_profile

    player = edit_profile(_profile_actor(player_id, credential_version), first_name,
                          last_name, username, list_public_usernames())
    # Existing unique indexes also reject concurrent duplicate usernames.
    return _save_account_fields(player, credential_version, {
        "first_name": player.first_name, "last_name": player.last_name,
        "display_name": player.display_name,
    })


def update_password(player_id: str, credential_version: str, current: str,
                    password: str, confirmation: str) -> Player:
    from core.profile import change_password

    player = _profile_actor(player_id, credential_version)
    if not allow_login_attempt(player_id):
        raise ValueError("Too many login attempts. Wait 15 minutes and try again.")
    player = change_password(player, current, password, confirmation)
    return _save_account_fields(player, credential_version, {"pin_hash": player.pin_hash})


def get_photo_sharing(player_id: str, credential_version: str) -> bool:
    _profile_actor(player_id, credential_version)
    rows = (get_client().table("player_photo_preferences").select("share_checkin_photos")
            .eq("player_id", player_id).execute().data)
    return bool(rows and rows[0]["share_checkin_photos"] is True)


def save_photo_sharing(player_id: str, credential_version: str, enabled: bool) -> None:
    _profile_actor(player_id, credential_version)
    if type(enabled) is not bool:
        raise ValueError("Choose on or off for photo sharing.")
    get_client().table("player_photo_preferences").upsert(
        {"player_id": player_id, "share_checkin_photos": enabled}, on_conflict="player_id"
    ).execute()


# The browser stores only the random token; Supabase stores only its hash.
def create_remembered_session(player: Player) -> str:
    token, stored_hash = new_token()
    get_client().table("remembered_sessions").insert({
        "token_hash": stored_hash, "player_id": player.id,
        "credential_version": token_hash(player.pin_hash),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    }).execute()
    return token


def get_remembered_player(token: str) -> Player | None:
    if not 40 <= len(token) <= 100:
        return None
    rows = (get_client().table("remembered_sessions").select("*")
            .eq("token_hash", token_hash(token)).execute().data)
    if not rows:
        return None
    session = rows[0]
    player = get_player(session["player_id"])
    if (datetime.fromisoformat(session["expires_at"]) <= datetime.now(timezone.utc)
            or not player or not player.email
            or session["credential_version"] != token_hash(player.pin_hash)):
        revoke_remembered_session(token)
        return None
    return player


def revoke_remembered_session(token: str) -> None:
    get_client().table("remembered_sessions").delete().eq("token_hash", token_hash(token)).execute()


# -- private friendships (call only after require_login) -----------------

def list_public_usernames() -> list[dict]:
    """Fetch no names, emails or credential hashes for friend search."""
    # Page through the directory so search includes users beyond Supabase's
    # default 1,000-row response limit.
    users = []
    offset = 0
    while True:
        rows = get_client().table("players").select("id,display_name").order("id").range(offset, offset + 999).execute().data
        users.extend(rows)
        if len(rows) < 1000:
            return users
        offset += 1000


def list_friendships(player_id: str) -> list[dict]:
    """Only this authenticated player's relationships; never another list."""
    rows = []
    offset = 0
    while True:
        page = (get_client().table("friendships").select("*")
                .or_(f"sender_id.eq.{player_id},recipient_id.eq.{player_id}")
                .order("pair_low").order("pair_high").range(offset, offset + 999).execute().data)
        rows.extend(page)
        if len(page) < 1000:
            return rows
        offset += 1000


def change_friendship(player_id: str, other_id: str, action: str) -> None:
    from core.friends import transition

    low, high = sorted((player_id, other_id))
    rows = (get_client().table("friendships").select("*")
            .eq("pair_low", low).eq("pair_high", high).execute().data)
    current = rows[0] if rows else None
    next_row = transition(player_id, other_id, action, current, datetime.now(timezone.utc))
    get_client().rpc("save_friendship", {
        "sender": next_row["sender_id"], "recipient": next_row["recipient_id"],
        "next_status": next_row["status"],
        "expected_version": current["version"] if current else None,
    }).execute()


# -- profile pictures: owner, accepted friends and pending requests only --
PROFILE_PICTURE_BUCKET = "profile-pictures"


def _profile_picture_bucket():
    storage = get_client().storage
    if storage.get_bucket(PROFILE_PICTURE_BUCKET).public is not False:
        raise RuntimeError("Profile pictures require a private storage bucket.")
    return storage.from_(PROFILE_PICTURE_BUCKET)


def _profile_picture_row(player_id: str):
    rows = (get_client().table("profile_pictures").select("photo_ref")
            .eq("player_id", player_id).execute().data)
    return rows[0]["photo_ref"] if rows else None


def _validate_profile_picture_path(player_id: str, path: str) -> None:
    import uuid

    try:
        folder, filename = path.split("/")
        valid = folder == player_id and filename == f"{uuid.UUID(filename.removesuffix('.jpg'))}.jpg"
    except (ValueError, AttributeError):
        valid = False
    if not valid:
        raise PermissionError("Invalid profile picture reference.")


def download_profile_picture(viewer_id: str, credential_version: str, owner_id: str) -> bytes | None:
    from core.profile_photo import can_view_profile_photo

    _profile_actor(viewer_id, credential_version)
    relationships = [] if viewer_id == owner_id else list_friendships(viewer_id)
    if not can_view_profile_photo(viewer_id, owner_id, relationships):
        return None
    path = _profile_picture_row(owner_id)
    if not path:
        return None
    _validate_profile_picture_path(owner_id, path)
    return _profile_picture_bucket().download(path)


def save_profile_picture(player_id: str, credential_version: str, raw: bytes) -> None:
    import uuid
    from core.profile_photo import prepare_profile_photo

    _profile_actor(player_id, credential_version)
    photo = prepare_profile_photo(raw)
    previous = _profile_picture_row(player_id)
    if previous:
        _validate_profile_picture_path(player_id, previous)
    path = f"{player_id}/{uuid.uuid4()}.jpg"
    bucket = _profile_picture_bucket()
    bucket.upload(path, photo, {"content-type": "image/jpeg"})
    # Recheck after upload before publishing the new reference. On an uncertain
    # write failure, leave the private upload for cleanup rather than risking
    # deletion of a picture whose reference may have committed.
    _profile_actor(player_id, credential_version)
    get_client().table("profile_pictures").upsert({
        "player_id": player_id, "photo_ref": path,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    if previous:
        try:
            bucket.remove([previous])
        except Exception:
            # The new picture is saved; cleanup can remove an unlinked object.
            pass


def remove_profile_picture(player_id: str, credential_version: str) -> None:
    _profile_actor(player_id, credential_version)
    path = _profile_picture_row(player_id)
    if not path:
        return
    _validate_profile_picture_path(player_id, path)
    _profile_picture_bucket().remove([path])
    (get_client().table("profile_pictures").delete().eq("player_id", player_id)
     .eq("photo_ref", path).execute())


def cleanup_profile_pictures(*, apply: bool = False) -> int:
    """Remove only unlinked uploads older than 24h; keep current pictures."""
    bucket = _profile_picture_bucket()
    now = datetime.now(timezone.utc)
    count = 0
    for folder in _list_photo_folder(bucket, ""):
        owner = folder["name"]
        if folder.get("id") is not None or not owner or "/" in owner or owner in (".", ".."):
            continue
        for obj in _list_photo_folder(bucket, owner):
            if not obj.get("id"):
                continue
            path = f"{owner}/{obj['name']}"
            try:
                _validate_profile_picture_path(owner, path)
            except PermissionError:
                continue
            modified = obj.get("updated_at") or obj.get("created_at")
            if not modified:
                continue
            timestamp = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            if now < timestamp + timedelta(hours=UNLINKED_PHOTO_GRACE_HOURS):
                continue
            # Recheck the live reference immediately before deletion.
            if _profile_picture_row(owner) == path:
                continue
            if apply:
                bucket.remove([path])
            count += 1
    return count


# -- lobby teams (private to joined lobby members) -----------------------
def list_lobby_teams(player_id: str, lobby_id: str) -> list[Team]:
    if not any(m.lobby_id == lobby_id for m in list_memberships_for_player(player_id)):
        raise PermissionError("Only lobby members can view teams.")
    rows = get_client().table("lobby_teams").select("*").eq("lobby_id", lobby_id).order("number").execute().data
    return [Team(r["id"], r["lobby_id"], r["number"], r["name"], r.get("photo_base64")) for r in rows]


def _team_rpc(name: str, parameters: dict):
    from core.quiz_duel import ERRORS as QUIZ_ERRORS
    messages = {
        "team_full": "That team is full. Choose another team.",
        "lobby_full": "This lobby is full.",
        "team_locked": "Your team is locked after your first scored check-in.",
        "random_team_locked": "Teams are assigned at random in this lobby.",
        "lobby_finished": "This lobby has finished. Teams are frozen.",
        "invalid_team": "Choose a team in this lobby.",
        "invalid_team_name": "Use a team name of 1–40 characters.",
        "permission_denied": "Only members of this team can edit it.",
    }
    try:
        return get_client().rpc(name, parameters).execute().data
    except APIError as error:
        reason = getattr(error, "message", "")
        if reason == 'time_busy':
            from core.time_duel import ERRORS as TIME_ERRORS
            raise ValueError(TIME_ERRORS[reason]) from None
        if reason in {"quiz_busy", "quiz_reserved_points"}:
            raise ValueError(QUIZ_ERRORS[reason]) from None
        if reason in messages:
            raise ValueError(messages[reason]) from None
        if error.code == "23505":
            raise ValueError("Another team in this lobby already uses that name.") from None
        raise


def choose_lobby_team(player_id: str, lobby_id: str, team_id: str) -> None:
    _team_rpc("choose_lobby_team", {"actor_player": player_id, "target_lobby": lobby_id, "target_team": team_id})


def edit_lobby_team(player_id: str, team_id: str, name: str, raw_photo: bytes | None = None, *, remove_photo=False) -> None:
    import base64
    from core.teams import team_name
    from core.profile_photo import prepare_profile_photo
    photo = base64.b64encode(prepare_profile_photo(raw_photo)).decode("ascii") if raw_photo is not None else None
    if photo and len(photo) > 524288:
        raise ValueError("Choose a simpler picture.")
    _team_rpc("edit_lobby_team", {"actor_player": player_id, "target_team": team_id,
        "new_name": team_name(name), "new_photo": photo, "change_photo": raw_photo is not None or remove_photo})


# -- Quiz Duel: private question packs and transactional server decisions --
def _quiz_rpc(name, parameters):
    from core.quiz_duel import ERRORS
    try:
        return get_client().rpc(name, parameters).execute().data
    except APIError as error:
        if error.message == 'time_busy':
            from core.time_duel import ERRORS as TIME_ERRORS
            raise ValueError(TIME_ERRORS['time_busy']) from None
        if error.message in ERRORS:
            raise ValueError(ERRORS[error.message]) from None
        if error.code in {"PGRST202", "42P01", "PGRST205"}:
            raise RuntimeError("Quiz Duel needs database migration 016 before it can open.") from None
        raise


def quiz_status(player_id, season_id):
    return _quiz_rpc("quiz_status", {"actor_player": player_id, "target_season": season_id})


def invite_quiz_duel(player_id, season_id, invitation_id, opponent_id, stake):
    from core.quiz_duel import validate_stake
    from data.quiz_questions import prepare_duel_deck
    return _quiz_rpc("invite_quiz_duel", dict(actor_player=player_id, target_season=season_id,
        invitation_id=invitation_id, opponent_member=opponent_id, selected_stake=validate_stake(stake),
        private_questions=prepare_duel_deck(invitation_id)))


def quiz_action(player_id, duel_id, action, round_no=None, choice=None):
    return _quiz_rpc("quiz_action", dict(actor_player=player_id, target_duel=duel_id,
        selected_action=action, expected_round=round_no, selected_choice=choice))


def list_season_transfers(season_id):
    from core.models import SeasonTransfer
    try:
        rows = (get_client().table("quiz_transfers").select("*").eq("season_id", season_id)
                .order("event_order").execute().data)
    except APIError as error:
        # Additive deployment: ordinary standings still work before migration 016.
        if error.code in {"42P01", "PGRST205"}:
            return []
        raise
    return [SeasonTransfer(**dict(row, created_at=datetime.fromisoformat(row["created_at"]))) for row in rows]


# -- Time Duel: server-owned rounds, first-result locks and automatic rewards --
def _time_rpc(name, parameters):
    from core.time_duel import ERRORS
    try:
        return get_client().rpc(name, parameters).execute().data
    except APIError as error:
        reason = error.message.strip()
        if reason == 'permission_denied':
            raise PermissionError(ERRORS[reason]) from None
        if reason in ERRORS:
            raise ValueError(ERRORS[reason]) from None
        if reason in {'quiz_busy', 'focus_busy'}:
            raise ValueError(ERRORS['time_busy']) from None
        if error.code in {'PGRST202', '42P01', 'PGRST205', '42703', 'PGRST204'}:
            raise RuntimeError('Time Duel needs database migration 017 before it can open.') from None
        raise


def time_status(player_id, season_id):
    return _time_rpc('time_status', dict(actor_player=player_id, target_season=season_id))


def invite_time_duel(player_id, season_id, invitation_id, opponent_id):
    return _time_rpc('invite_time_duel', dict(actor_player=player_id, target_season=season_id,
        invitation_id=invitation_id, opponent_member=opponent_id))


def time_action(player_id, duel_id, action, round_no=None, elapsed_ms=None):
    return _time_rpc('time_action', dict(actor_player=player_id, target_duel=duel_id,
        selected_action=action, expected_round=round_no, elapsed=elapsed_ms))
