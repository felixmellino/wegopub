"""Legacy one-play-per-lobby-per-game-window minigame placeholder.

Chug Duel uses core.chug_duel and migration 011's separate outgoing/incoming
nightly allowances. No playable screen calls this older weekly helper.

membership_id already identifies a player WITHIN one specific lobby, so
scoping by membership_id automatically makes this limit per-lobby, not
global across a player's lobbies -- no separate lobby_id parameter needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from core.constants import MAX_MINIGAME_PLAYS_PER_WINDOW
from core.models import MinigameAttempt


def can_play(membership_id: str, game_window_id: str, attempts: list[MinigameAttempt]) -> bool:
    plays = sum(
        1
        for attempt in attempts
        if attempt.membership_id == membership_id and attempt.game_window_id == game_window_id
    )
    return plays < MAX_MINIGAME_PLAYS_PER_WINDOW


def record_attempt(
    membership_id: str,
    season_id: str,
    arena_id: str,
    game_type: str,
    game_window_id: str,
    started_at: datetime,
    attempts: list[MinigameAttempt],
) -> MinigameAttempt:
    if not can_play(membership_id, game_window_id, attempts):
        raise ValueError("minigame play limit reached for this game window")

    return MinigameAttempt(
        id=str(uuid.uuid4()),
        membership_id=membership_id,
        season_id=season_id,
        arena_id=arena_id,
        game_type=game_type,
        game_window_id=game_window_id,
        started_at=started_at,
        status="started",
        result=None,
    )
