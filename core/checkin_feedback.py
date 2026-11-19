"""Ownership feedback for an accepted check-in, using existing replay rules."""
from core.models import DrinkEntry
from core.teams import competitor
from core.scoring_v1 import entry_order, replay_season


def captured_territory(entry_id: str, entries: list[DrinkEntry]) -> str | None:
    """Return the territory this saved entry claimed or took from another player.

    Replay only through this entry: subsequent submissions must not change
    what its success message says. A preview or an unsaved entry is insufficient.
    """
    saved = next((entry for entry in entries if entry.id == entry_id), None)
    if saved is None or saved.points_awarded <= 0 or saved.location_check_result != "matched" or not saved.territory_id:
        return None
    preceding = [entry for entry in entries if entry.season_id == saved.season_id
                 and entry_order(entry) < entry_order(saved)]
    before = replay_season(preceding).owners.get(saved.territory_id)
    after = replay_season(preceding + [saved]).owners.get(saved.territory_id)
    return saved.territory_id if before != competitor(saved) and after == competitor(saved) else None
