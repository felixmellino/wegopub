"""Season-wide standings. Reuses the R-R01 replay algorithm from
territories.py instead of reimplementing tie-breaking here."""

from __future__ import annotations

from decimal import Decimal

from core.models import DrinkEntry
from core.territories import replay_leader


def _season_events(entries: list[DrinkEntry]) -> list[tuple]:
    return [
        (entry.submitted_at, entry.membership_id, entry.points_awarded)
        for entry in entries
        if entry.points_awarded > 0
    ]


def season_leader(entries: list[DrinkEntry], transfers=()) -> str | None:
    if transfers or any(entry.rule_version == "v1" for entry in entries):
        rows = season_leaderboard(entries, transfers)
        return rows[0][0] if rows else None
    return replay_leader(_season_events(entries))


def season_leaderboard(entries: list[DrinkEntry], transfers=()) -> list[tuple[str, int | Decimal]]:
    if transfers or any(entry.rule_version == "v1" for entry in entries):
        from core.scoring_v1 import replay_season
        return replay_season(entries, transfers).season_rows()
    totals: dict[str, int] = {}
    for _ts, membership_id, points in _season_events(entries):
        totals[membership_id] = totals.get(membership_id, 0) + points
    return sorted(totals.items(), key=lambda item: item[1], reverse=True)
