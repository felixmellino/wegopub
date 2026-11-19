"""Read-only lobby lifecycle derived from the existing competition dates."""
from datetime import datetime
from math import ceil

from core.scoring_v1 import utc


def latest_season(seasons):
    """Keep historical multi-season lobbies readable; never create a renewal."""
    return max(seasons, key=lambda s: (utc(s.starts_at), s.id), default=None)


def lobby_status(season, now: datetime) -> str:
    if season is None:
        return "setup"
    if utc(now) >= utc(season.ends_at):
        return "past"
    if utc(now) < utc(season.starts_at):
        return "upcoming"
    return "active"


def time_left(ends_at: datetime, now: datetime) -> str:
    # Round up so a still-running lobby never reads as zero minutes left.
    minutes = max(0, ceil((utc(ends_at) - utc(now)).total_seconds() / 60))
    days, minutes = divmod(minutes, 1440)
    hours, minutes = divmod(minutes, 60)
    return f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m"
