"""Chug Duel eligibility and presentation rules; persistence uses atomic RPCs."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.scoring_v1 import base_points, rules_for, scoring_open, utc

RESET_HOUR = 6
RESERVED_STATUSES = {"accepted", "started", "completed", "aborted"}


def night_id(now: datetime, timezone_name: str) -> str:
    local = utc(now).astimezone(ZoneInfo(timezone_name))
    day = local.date() - timedelta(days=local.hour < RESET_HOUR)
    return day.isoformat()


def next_reset(now: datetime, timezone_name: str) -> datetime:
    zone = ZoneInfo(timezone_name)
    local = utc(now).astimezone(zone)
    day = local.date() + timedelta(days=local.hour >= RESET_HOUR)
    return datetime(day.year, day.month, day.day, RESET_HOUR, tzinfo=zone)


def unlimited_plays(season) -> bool:
    """Only the frozen QA flag enables unlimited replays, never a lobby name."""
    return rules_for(season).get("test_mode") is True


def allowances(member_id: str, night: str, duels: list[dict], *, season=None) -> tuple[bool, bool]:
    """Normal nightly role limits; QA seasons can repeat after a game ends."""
    if season is not None and unlimited_plays(season):
        return True, True
    used = [d for d in duels if d["game_night"] == night and d["status"] in RESERVED_STATUSES]
    return (not any(d["challenger_id"] == member_id for d in used),
            not any(d["opponent_id"] == member_id for d in used))


def validate_pair(challenger, opponent, lobby) -> None:
    if (challenger.id == opponent.id or challenger.player_id == opponent.player_id
            or challenger.lobby_id != lobby.id or opponent.lobby_id != lobby.id):
        raise ValueError("Choose another member of this lobby.")
    if lobby.game_mode == "team":
        if not challenger.team_id or not opponent.team_id:
            raise ValueError("Both players must join a team first.")
        if challenger.team_id == opponent.team_id:
            raise ValueError("Choose a player from another team.")


def validate_invitation(challenger, opponent, lobby, season, drink, size, now, duels):
    validate_pair(challenger, opponent, lobby)
    if season.lobby_id != lobby.id or not scoring_open(now, season):
        raise ValueError("Duels are available only while this season's scoring is open.")
    points = base_points(drink, size, rules_for(season))
    outgoing, _ = allowances(challenger.id, night_id(now, season.timezone_name), duels, season=season)
    _, incoming = allowances(opponent.id, night_id(now, season.timezone_name), duels, season=season)
    if not outgoing:
        raise ValueError("You have already used your challenge for this evening.")
    if not incoming:
        raise ValueError("This player has already accepted a duel this evening.")
    return points


def component_action(value, duel: dict) -> tuple[str, str | None] | None:
    """Only a ready event or a participant's first-tap result crosses the bridge."""
    if not isinstance(value, dict) or value.get("duel_id") != duel["id"]:
        return None
    if value.get("phase") == "ready" and not duel.get("play_at"):
        return "arm", None
    if value.get("phase") == "result" and duel.get("play_at"):
        side = value.get("winner")
        if side in ("challenger", "opponent"):
            return "finish", duel[f"{side}_id"]
    return None


ERRORS = {
    'focus_busy': 'Finish the running Focus Challenge before starting a duel.',
    "permission_denied": "You cannot perform this duel action.",
    "duel_limit": "An evening allowance is already used or reserved. Refresh the list.",
    "duel_pending": "You already have an open invitation. Cancel it before sending another.",
    "duel_unavailable": "This invitation or game has expired or changed. Refresh the list.",
    "duel_busy": "A player is already in an accepted or running duel.",
    "duel_team": "Choose a player from another team. Both players need a team.",
    "duel_early": "Wait for the countdown to finish before submitting a result.",
    "duel_entry_locked": "Duel drinks are agreed by both players and cannot be corrected separately.",
    "scoring_closed": "Duels are closed outside the season's scoring window.",
    "cooldown": "One of you has a recent check-in. Wait two minutes after both players' last posts.",
    "invalid_selection": "Choose a supported drink and size.",
    "invalid_photo": "Take a fresh shared photo before starting.",
    "location_unavailable": "A current, accurate phone location is required.",
    "invalid_territory": "The verified territory could not be accepted. Refresh and retry.",
}
