"""Synthetic local app backed by the disposable PostgreSQL browser bridge."""
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import streamlit as st
import data.db as db
from tests.test_scoring_v1 import season
from focus_challenge_ui import render_focus

st.set_page_config(layout="centered")
root=Path(__file__).resolve().parents[2]
st.markdown('<style>'+ (root/'assets/theme.css').read_text(encoding='utf-8')
            +(root/'assets/minigames.css').read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)


def request(name, parameters=None):
    with urlopen(Request('http://127.0.0.1:8773',
            json.dumps(dict(name=name,parameters=parameters)).encode(),
            {'Content-Type':'application/json'}),timeout=15) as response:
        result=json.load(response)
    if 'error' in result:
        raise ValueError(result['error'])
    return result


db._focus_rpc=request
info=request('fixture')
game=season();game.id=info['sid'];game.lobby_id=info['lid'];game.scoring_rules['test_mode']=True
st.session_state['minigame_selected']='focus'
@st.fragment(run_every='1s')
def app():
    render_focus('00000000-0000-4000-8000-000000000001',game)
app()
