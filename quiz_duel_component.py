"""One stable, mobile board. Answers and winners are verified in PostgreSQL."""
from pathlib import Path
from streamlit.components.v1 import declare_component

_board = declare_component("quiz_duel", path=str(Path(__file__).parent / "components" / "quiz_duel"))


def quiz_board(duel, member, labels, acknowledgement=None):
    css = (Path(__file__).parent / "assets" / "theme.css").read_text(encoding="utf-8")
    tokens = css[css.index(":root {"):css.index("/* Base */")]
    return _board(duel=duel, member=member,
        challenger=labels.get(duel["challenger_id"], "Challenger"),
        opponent=labels.get(duel["opponent_id"], "Opponent"), tokens=tokens,
        acknowledgement=acknowledgement, key=f"quiz_board_{duel['id']}", default=None)
