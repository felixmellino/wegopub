"""Local synthetic two-player app; the HTTP bridge owns disposable PostgreSQL."""
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import streamlit as st
import data.db as db
from core.models import Lobby, LobbyMembership
from tests.test_scoring_v1 import START, season
from quiz_duel_ui import render_quiz

st.set_page_config(page_title="Quiz Duel browser fixture", layout="centered")
root = Path(__file__).resolve().parents[2]
st.markdown('<style>' + (root/'assets/theme.css').read_text(encoding='utf-8')
            + (root/'assets/minigames.css').read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)


def request(payload):
    with urlopen(Request('http://127.0.0.1:8771', json.dumps(payload).encode(),
                         {'Content-Type': 'application/json'}), timeout=15) as response:
        result = json.load(response)
    if 'error' in result:
        from core.quiz_duel import ERRORS
        raise ValueError(ERRORS.get(result['error'], result['error']))
    return result


db._quiz_rpc = lambda name, parameters: request(dict(name=name, parameters=parameters))
info = request(dict(name='fixture'))
p = int(st.query_params.get('player', '1'))
uid = lambda n: f'00000000-0000-4000-8000-{n:012d}'
members = [LobbyMembership(uid(1010+n), uid(n), info['lid'], START) for n in range(1, 7)]
labels = {m.id: 'Player '+str(i+1) for i, m in enumerate(members)}
game = season(); game.id=info['sid']; game.lobby_id=info['lid']
lobby = Lobby(info['lid'], 'Synthetic quiz lobby', 'LOCAL')


@st.fragment(run_every='1s')
def app():
    render_quiz(uid(p), uid(1010+p), lobby, game, members, labels)


app()
