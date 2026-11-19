"""The shared-phone board; the server validates host, participants and countdown."""
from pathlib import Path
from streamlit.components.v1 import declare_component
from core.scoring_v1 import current_time

_board = declare_component("chug_duel", path=str(Path(__file__).parent / "components" / "chug_duel"))


def duel_board(duel: dict, challenger: str, opponent: str):
    # Reuse the app's design tokens inside the component's isolated iframe.
    css = (Path(__file__).parent / "assets" / "theme.css").read_text(encoding="utf-8")
    tokens = css[css.index(":root {"):css.index("/* Base */")]
    return _board(duel_id=duel["id"], challenger=challenger, opponent=opponent,
                  state=duel["status"], winner=("challenger" if duel.get("winner_id") == duel["challenger_id"]
                    else "opponent" if duel.get("winner_id") == duel["opponent_id"] else None),
                  play_at=duel.get("play_at"), server_now=current_time().isoformat(), tokens=tokens,
                  key=f"chug_board_{duel['id']}", default=None)
