"""Photo audience rules. Missing consent always means sharing is off."""
from core.models import LobbyMembership


def can_view_photo(viewer_id: str, owner_id: str, team_id: str | None,
                   members: list[LobbyMembership], sharing: dict[str, bool]) -> bool:
    viewer = next((m for m in members if m.player_id == viewer_id), None)
    if viewer is None:
        return False
    if viewer_id == owner_id:
        return True
    if team_id is None:
        return sharing.get(owner_id) is True
    if viewer.team_id == team_id:
        return True
    roster = [m for m in members if m.team_id == team_id]
    return (bool(roster) and sharing.get(owner_id) is True
            and all(sharing.get(m.player_id) is True for m in roster))
