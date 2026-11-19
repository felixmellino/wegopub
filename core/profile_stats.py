"""Personal lifetime totals, with each season's ownership replay kept separate."""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from core.scoring_v1 import replay_season, utc
from core.leaderboard import season_leader


@dataclass(frozen=True)
class ProfileStats:
    points: Decimal
    drinks: int
    lobbies: int
    wins: int


def season_finished(season, now):
    """Only completed seasons can award a lifetime win."""
    return utc(season.ends_at) <= utc(now)


def all_time_stats(memberships, entries, *, finished_season_ids=(), transfers=()):
    """Count personal drinks plus individual owner income, never teammates' scores.

    Full season entries are needed: somebody else's drink can pay the player
    owner income. Replay also keeps corrections consistent with standings.
    Points and drinks count immediately; wins require a completed season.
    """
    member_lobbies = {member.id: member.lobby_id for member in memberships}
    identities = {getattr(member, "team_id", None) or member.id for member in memberships}
    seasons = defaultdict(list)
    for entry in {entry.id: entry for entry in entries}.values():
        if entry.points_awarded > 0 and entry.location_check_result in ("matched", "outside"):
            seasons[entry.season_id].append(entry)
    points = Decimal(0)
    drinks = 0
    wins = 0
    played = set()
    unique_transfers = {t.id: t for t in transfers}.values()
    for transfer in unique_transfers:
        seasons.setdefault(transfer.season_id, [])
        if transfer.source_id == transfer.source_membership_id and transfer.source_id in member_lobbies:
            points -= transfer.points
        if transfer.target_id == transfer.target_membership_id and transfer.target_id in member_lobbies:
            points += transfer.points
    for season_id, season_entries in seasons.items():
        season_transfers = [t for t in unique_transfers if t.season_id == season_id]
        if season_id in finished_season_ids and season_leader(season_entries, season_transfers) in identities:
            wins += 1
        for entry in season_entries:
            if (entry.membership_id in member_lobbies and entry.points_awarded > 0
                    and entry.location_check_result in ("matched", "outside")):
                points += Decimal(str(entry.points_awarded))
                drinks += 1
                played.add(member_lobbies[entry.membership_id])
        if any(entry.rule_version == "v1" for entry in season_entries):
            for recipient, quarters in replay_season(season_entries).awards.values():
                if recipient in member_lobbies:
                    points += Decimal(quarters) / 4
    return ProfileStats(points, drinks, len(played), wins)
