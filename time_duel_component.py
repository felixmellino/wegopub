"""Persistent phone timer; local monotonic intervals avoid network-speed scoring."""
from pathlib import Path
from streamlit.components.v1 import declare_component

_board = declare_component('time_duel', path=str(Path(__file__).parent / 'components' / 'time_duel'))


def time_board(duel, member, labels, acknowledgement=None):
    return _board(duel=duel, member=member,
        challenger=labels.get(duel['challenger_id'], 'Challenger'),
        opponent=labels.get(duel['opponent_id'], 'Opponent'),
        acknowledgement=acknowledgement, key=f"time_board_{duel['id']}", default=None)
