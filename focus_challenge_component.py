"""Browser timing and touch UI; PostgreSQL owns progress, deadlines and rewards."""
from pathlib import Path
from streamlit.components.v1 import declare_component

_board = declare_component('focus_challenge', path=str(Path(__file__).parent / 'components' / 'focus_challenge'))


def focus_board(attempt):
    css = (Path(__file__).parent / 'assets' / 'theme.css').read_text(encoding='utf-8')
    tokens = css[css.index(':root {'):css.index('/* Base */')]
    return _board(attempt=attempt, tokens=tokens, key=f"focus_board_{attempt['id']}", default=None)
