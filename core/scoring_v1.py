"""Frozen scoring rules and deterministic replay. No database or UI imports.

An owner-income quarter is exactly 0.25 season points. Focus awards can be
half-points, hence half a quarter (0.125 points). These binary-exact values
are also stored as exact PostgreSQL numeric values, never rounded income.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from math import ceil, isfinite
from zoneinfo import ZoneInfo

from core.checkins import CheckinRejected
from core.location import evaluate_location
from core.models import DrinkEntry, Season, Territory
from core.teams import competitor
from core.focus_challenge import new_focus_rules

VERSION = "v1"
DRINK_LABELS = {"beer": "Beer", "wine": "Wine", "shot": "Shot", "mixed": "Mixed drink"}
SIZE_LABELS = {"small": "Small", "medium": "Medium", "large": "Large"}
VOLUMES = {"beer": {"small": 250, "medium": 330, "large": 500},
           "wine": {"small": 100, "medium": 150, "large": 250}}
_RULES = {
    "version": VERSION,
    "points": {"beer": {"small": 1, "medium": 2, "large": 3},
               "wine": {"small": 1, "medium": 2, "large": 4},
               "mixed": {"small": 2, "medium": 3, "large": 5},
               "shot": {"standard": 4}},
    "cooldown_seconds": 120, "correction_seconds": 120,
    "start_weekday": 3, "start_hour": 18, "end_weekday": 6, "end_hour": 18,
    "owner_bonus_quarters_per_point": 1,
    "volumes": deepcopy(VOLUMES),
}


def current_time() -> datetime:
    """Server clock for UI previews; database RPCs independently recheck time."""
    return datetime.now(timezone.utc)


def new_rules(*, test_mode: bool = False) -> dict:
    """A new season gets its own snapshot, never the mutable module object."""
    rules = deepcopy(_RULES)
    rules['focus_challenge'] = new_focus_rules()
    if test_mode:
        rules.update(test_mode=True, start_weekday=2, start_hour=8)
    return rules


def rules_for(season: Season) -> dict:
    if season.scoring_version != VERSION or not season.scoring_rules:
        raise ValueError("This season does not have a v1 rule snapshot.")
    return season.scoring_rules


def utc(value: datetime) -> datetime:
    # Existing rows can contain naive timestamps; historical imports use UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def base_points(drink_type: str, size: str | None, rules: dict) -> int:
    key = "standard" if drink_type == "shot" and size is None else size
    try:
        points = rules["points"][drink_type][key]
    except (KeyError, TypeError):
        raise ValueError("Choose a supported drink and size.") from None
    if isinstance(points, bool) or not isinstance(points, int) or points <= 0:
        raise ValueError("Invalid season points configuration.")
    return points


def size_label(drink_type: str, size: str, rules: dict | None = None) -> str:
    label = SIZE_LABELS.get(size, "One serving")
    volume = (rules.get("volumes", VOLUMES) if rules else VOLUMES).get(drink_type, {}).get(size)
    return f"{label} · {volume} ml" if volume else label


def volume_for(drink_type: str, size: str | None, rules: dict | None = None) -> int | None:
    return (rules.get("volumes", VOLUMES) if rules else VOLUMES).get(drink_type, {}).get(size)


def window_bounds(now: datetime, season: Season) -> tuple[datetime, datetime]:
    rules = rules_for(season)
    zone = ZoneInfo(season.timezone_name)
    local = utc(now).astimezone(zone)
    monday = local.date() - timedelta(days=local.weekday())
    start = datetime.combine(monday + timedelta(days=rules["start_weekday"]), time(rules["start_hour"]), zone)
    end = datetime.combine(monday + timedelta(days=rules["end_weekday"]), time(rules["end_hour"]), zone)
    return start, end


def scoring_open(now: datetime, season: Season) -> bool:
    start, end = window_bounds(now, season)
    at = utc(now)
    return (utc(season.starts_at) <= at < utc(season.ends_at)
            and utc(start) <= at < utc(end))


def next_opening(now: datetime, season: Season) -> datetime | None:
    at = max(utc(now), utc(season.starts_at))
    start, end = window_bounds(at, season)
    if at >= utc(end):
        start, end = window_bounds(at + timedelta(days=7), season)
    candidate = max(at, utc(start))
    return candidate.astimezone(ZoneInfo(season.timezone_name)) if candidate < utc(season.ends_at) else None


def cooldown_remaining(membership_id: str, now: datetime, entries: list[DrinkEntry], seconds: int = 120) -> int:
    times = [utc(entry.submitted_at) for entry in entries if entry.membership_id == membership_id]
    return max(0, ceil((max(times) + timedelta(seconds=seconds) - utc(now)).total_seconds())) if times else 0


def can_correct(entry: DrinkEntry, season: Season, now: datetime) -> bool:
    if entry.rule_version != VERSION or entry.season_id != season.id or entry.duel_id:
        return False
    at = utc(now)
    return (utc(entry.submitted_at) <= at < utc(entry.submitted_at) + timedelta(seconds=rules_for(season)["correction_seconds"])
            and at < utc(season.ends_at))


def create_scored_entry(membership_id: str, season: Season, drink_type: str, size: str | None,
                        photo_ref: str, device_gps, accuracy_m: float | None, submitted_at: datetime,
                        territories: list[Territory], recent_entries: list[DrinkEntry], *, entry_id: str) -> DrinkEntry:
    if not photo_ref:
        raise CheckinRejected("missing_photo")
    rules = rules_for(season)
    try:
        points = base_points(drink_type, size, rules)
    except ValueError:
        raise CheckinRejected("invalid_selection") from None
    if not scoring_open(submitted_at, season):
        raise CheckinRejected("scoring_closed")
    if cooldown_remaining(membership_id, submitted_at, recent_entries, rules["cooldown_seconds"]):
        raise CheckinRejected("cooldown")
    # Only the phone's GPS reading counts (R-L01); its accuracy decides R-L02.
    if device_gps is not None:
        try:
            lat, lng = device_gps
            valid = isfinite(lat) and isfinite(lng) and abs(lat) <= 90 and abs(lng) <= 180
        except (TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            raise CheckinRejected("location_uncertain")
    if accuracy_m is not None:
        try:
            valid = isfinite(accuracy_m) and accuracy_m >= 0
        except TypeError:
            valid = False
        if not valid:
            raise CheckinRejected("location_uncertain")
    location, territory_id = evaluate_location(device_gps, accuracy_m, territories)
    if location in ("uncertain", "unavailable"):
        raise CheckinRejected(f"location_{location}")
    return DrinkEntry(entry_id, membership_id, season.id, drink_type, volume_for(drink_type, size, rules),
                      photo_ref, None, None, territory_id, location, points, utc(submitted_at),
                      size=size, rule_version=VERSION)


def corrected_entry(entry: DrinkEntry, season: Season, drink_type: str, size: str | None, now: datetime) -> DrinkEntry:
    if not can_correct(entry, season, now):
        raise CheckinRejected("correction_closed")
    try:
        points = base_points(drink_type, size, rules_for(season))
    except ValueError:
        raise CheckinRejected("invalid_selection") from None
    return replace(entry, drink_type=drink_type, size=size, amount=volume_for(drink_type, size, rules_for(season)),
                   points_awarded=points * (1.5 if entry.focus_attempt_id else 1),
                   time_bonus=points * 0.25 if entry.time_duel_id and not entry.focus_attempt_id else 0,
                   corrected_at=utc(now), revision=entry.revision + 1)


def entry_order(entry: DrinkEntry):
    # A v1 season is homogeneous. DB order resolves simultaneous submissions;
    # pure examples/imported legacy records fall back to time and stable ID.
    return (0, entry.event_order, entry.id) if entry.rule_version == VERSION and entry.event_order is not None else (1, utc(entry.submitted_at).timestamp(), entry.id)


@dataclass
class Replay:
    season_quarters: dict[str, int | float] = field(default_factory=dict)
    territory_totals: dict[str, dict[str, int | float]] = field(default_factory=dict)
    owners: dict[str, str] = field(default_factory=dict)
    awards: dict[str, tuple[str | None, int | float]] = field(default_factory=dict)
    reached: dict[str, tuple[int, int]] = field(default_factory=dict)
    territory_reached: dict[str, dict[str, int]] = field(default_factory=dict)

    def season_rows(self) -> list[tuple[str, Decimal]]:
        order = sorted(self.season_quarters, key=lambda m: (-self.season_quarters[m], self.reached[m], m))
        return [(m, Decimal(self.season_quarters[m]) / 4) for m in order]

    def territory_rows(self, territory_id: str) -> list[tuple[str, int | float]]:
        totals = self.territory_totals.get(territory_id, {})
        reached = self.territory_reached.get(territory_id, {})
        return [(m, totals[m]) for m in sorted(totals, key=lambda m: (-totals[m], reached[m], m))]


def replay_season(entries: list[DrinkEntry], transfers=()) -> Replay:
    """Rebuild from corrected source entries; never compound stored income.

    In a same-event season tie the previous higher-ranked recipient wins.
    With a 25% bonus, that recipient is necessarily the owner, whose prior
    total was higher; crediting income before the drinker implements this.
    """
    if len({entry.season_id for entry in entries} | {t.season_id for t in transfers}) > 1:
        raise ValueError("Replay one season at a time.")
    state = Replay()
    events = [(entry_order(entry), 0, entry) for entry in entries]
    events += [((0, entry.duel_transfer_order, entry.id), 1, entry) for entry in entries
               if entry.duel_transfer_to and entry.duel_transfer_order is not None]
    events += [((0, transfer.event_order, transfer.id), 2, transfer) for transfer in transfers]
    for index, (_, kind, entry) in enumerate(sorted(events, key=lambda event: (event[0], event[1]))):
        if kind == 2:
            if type(entry.points) is not int or not 3 <= entry.points <= 10 or entry.source_id == entry.target_id:
                raise ValueError('Invalid quiz stake transfer.')
            prior_order = {account: rank for rank, (account, _) in enumerate(state.season_rows())}
            for account, delta in ((entry.source_id, -entry.points * 4), (entry.target_id, entry.points * 4)):
                state.season_quarters[account] = state.season_quarters.get(account, 0) + delta
                state.reached[account] = (index, prior_order.get(account, len(prior_order)))
            continue
        if kind == 1:
            # Move only the loser's base award at the result's own event position.
            # Territory ownership and prior-owner income keep their original history.
            prior_order = {account: rank for rank, (account, _) in enumerate(state.season_rows())}
            for account, delta in ((competitor(entry), -entry.points_awarded * 4),
                                   (entry.duel_transfer_to, entry.points_awarded * 4)):
                state.season_quarters[account] = state.season_quarters.get(account, 0) + delta
                state.reached[account] = (index, prior_order.get(account, len(prior_order)))
            continue
        points = entry.points_awarded
        if points <= 0 or entry.location_check_result not in ("matched", "outside"):
            continue
        member = competitor(entry)
        territory = entry.territory_id if entry.location_check_result == "matched" else None
        owner = state.owners.get(territory) if territory else None
        bonus = (points if entry.rule_version == VERSION and owner and owner != member
                 and (entry.team_id is not None or owner not in entry.absent_member_ids) else 0)
        recipient = owner if bonus else None
        state.awards[entry.id] = (recipient, bonus)
        if recipient:
            state.season_quarters[recipient] = state.season_quarters.get(recipient, 0) + bonus
            state.reached[recipient] = (index, 0)
        state.season_quarters[member] = state.season_quarters.get(member, 0) + (points + entry.time_bonus) * 4
        state.reached[member] = (index, 1)
        if territory:
            totals = state.territory_totals.setdefault(territory, {})
            totals[member] = totals.get(member, 0) + points
            state.territory_reached.setdefault(territory, {})[member] = index
            if owner is None or totals[member] > totals[owner]:
                state.owners[territory] = member
    return state


def format_points(points) -> str:
    return format(Decimal(str(points)), ".3f").rstrip("0").rstrip(".")
