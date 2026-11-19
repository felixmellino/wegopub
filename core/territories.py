"""Territory ownership, computed live from confirmed drink entries.

Rule R-R01: when two players tie on points, whoever reached that score
first ranks higher / keeps ownership. replay_leader() implements this with
no extra bookkeeping: it replays scoring events in time order and only lets
the leader change on a STRICT improvement, so a later entry that merely
ties the leader's total never displaces them.
"""

from __future__ import annotations

import re
from datetime import datetime

from core.models import DrinkEntry, Territory

# (timestamp, membership_id, points) in the order they happened.
ScoreEvent = tuple[datetime, str, int]

# A territory id is a short, readable, permanent key such as "rua-da-rosa":
# lowercase letters and digits, words joined by single hyphens.
TERRITORY_ID_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def parse_territories(collection: dict) -> list[Territory]:
    """Turn the GeoJSON from data/territories.geojson into Territory records,
    enforcing R-T01: every territory has a permanent short `id` (like
    "rua-da-rosa"), a non-empty `name`, and a closed Polygon outline; ids
    and names are unique. Raises
    ValueError naming the broken territory. Extra properties (like the
    geojson.io colours) are ignored. R-T02 (no overlap) is checked by
    tests/test_territory_data.py, because it needs a slow geometric scan."""
    if collection.get("type") != "FeatureCollection":
        raise ValueError("territory file must be a GeoJSON FeatureCollection")

    territories: list[Territory] = []
    for position, feature in enumerate(collection.get("features", []), start=1):
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        name = str(properties.get("name", "")).strip()
        label = name or f"territory #{position}"

        if not name:
            raise ValueError(f"{label} has no name")
        territory_id = properties.get("id")
        if not isinstance(territory_id, str) or not TERRITORY_ID_PATTERN.fullmatch(territory_id):
            raise ValueError(f"{label} needs a short id like 'rua-da-rosa' (lowercase letters, digits, hyphens)")
        if geometry.get("type") != "Polygon":
            raise ValueError(f"{label} must be a Polygon")
        ring = (geometry.get("coordinates") or [[]])[0]
        if len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError(f"{label} needs a closed outline with at least 3 corners")

        territories.append(
            Territory(id=territory_id, name=name, boundary={"type": "Polygon", "coordinates": geometry["coordinates"]})
        )

    ids = [t.id for t in territories]
    names = [t.name for t in territories]
    if len(set(ids)) != len(ids):
        raise ValueError("two territories share the same id")
    if len(set(names)) != len(names):
        raise ValueError("two territories share the same name")
    return territories


def replay_leader(events: list[ScoreEvent]) -> str | None:
    ordered = sorted(events, key=lambda event: event[0])
    totals: dict[str, int] = {}
    leader: str | None = None
    for _ts, membership_id, points in ordered:
        totals[membership_id] = totals.get(membership_id, 0) + points
        if leader is None or totals[membership_id] > totals[leader]:
            leader = membership_id
    return leader


def _territory_events(entries: list[DrinkEntry], territory_id: str) -> list[ScoreEvent]:
    return [
        (entry.submitted_at, entry.membership_id, entry.points_awarded)
        for entry in entries
        if entry.territory_id == territory_id and entry.location_check_result == "matched"
    ]


def territory_owner(entries: list[DrinkEntry], territory_id: str) -> str | None:
    if any(entry.rule_version == "v1" for entry in entries):
        from core.scoring_v1 import replay_season
        return replay_season(entries).owners.get(territory_id)
    return replay_leader(_territory_events(entries, territory_id))


def territory_standings(entries: list[DrinkEntry], territory_id: str) -> list[tuple[str, int]]:
    """Summed totals per membership for display, sorted descending. Only
    the top slot is guaranteed to match territory_owner()'s tie-break --
    ordering among non-leading ties is a simplification."""
    if any(entry.rule_version == "v1" for entry in entries):
        from core.scoring_v1 import replay_season
        return replay_season(entries).territory_rows(territory_id)
    totals: dict[str, int] = {}
    for _ts, membership_id, points in _territory_events(entries, territory_id):
        totals[membership_id] = totals.get(membership_id, 0) + points
    return sorted(totals.items(), key=lambda item: item[1], reverse=True)


def capture_status(rows: list[tuple[str, int]], owner: str | None, me: str, *, point_step=1):
    """What a territory means for one player on the map.

    `rows` are the territory standings (membership_id, points) and `owner`
    the current owner, both from the functions above. Returns one of:
    - ("free", 0): nobody owns it yet; the next accepted drink there claims it.
    - ("yours", lead): you own it; lead = how far ahead of the runner-up you are.
    - ("theirs", needed): someone else owns it; needed = points you must add
      to take it. A tie keeps the owner (R-R01), so add one scoring quantum
      above the gap (half a point when Focus awards are present).
    Only base points from drinks in the territory count; owner income never
    claims or defends a territory."""
    points = dict(rows)
    if owner is None:
        return "free", 0
    if owner == me:
        others = [p for member, p in rows if member != me]
        return "yours", points.get(me, 0) - (max(others) if others else 0)
    return "theirs", points.get(owner, 0) - points.get(me, 0) + point_step
