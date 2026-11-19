"""Legacy weekly window and existing minigame-window helper.

New drink scoring uses scoring_v1.window_bounds and a frozen lobby timezone.
The separate minigame-night definition remains a team decision.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from core.constants import WINDOW_END_TIME, WINDOW_END_WEEKDAY, WINDOW_START_TIME, WINDOW_START_WEEKDAY


def _week_monday(day: date) -> date:
    return day - timedelta(days=day.weekday())  # Monday == 0


def game_window_bounds(ts: datetime) -> tuple[datetime, datetime]:
    """Return (start, end) of the game window for ts's own week, whether or
    not ts itself falls inside it. Used by minigames to scope the shared
    play limit even on an off-day."""
    monday = _week_monday(ts.date())
    start = datetime.combine(monday + timedelta(days=WINDOW_START_WEEKDAY), WINDOW_START_TIME)
    end = datetime.combine(monday + timedelta(days=WINDOW_END_WEEKDAY), WINDOW_END_TIME)
    return start, end


def is_in_game_window(ts: datetime) -> bool:
    start, end = game_window_bounds(ts)
    return start <= ts <= end


def game_window_id(ts: datetime) -> str:
    """A stable id for ts's game window: the ISO date of that week's
    Thursday. Two timestamps in the same window share this id."""
    start, _end = game_window_bounds(ts)
    return start.date().isoformat()
