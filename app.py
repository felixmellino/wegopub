"""WeGoPub entry point: log in, then open on the Map -- no rules, no DB calls.

Actual login/account creation lives in account_ui.py, to keep this
file small and avoid everyone colliding on it as the team adds pages.
"""

import streamlit as st

from shared import require_login
from theme import apply_theme

st.set_page_config(page_title="WeGoPub", page_icon=":material/sports_bar:")
apply_theme()

require_login()  # shows the login screen (with the wordmark) until someone is logged in
st.switch_page("pages/5_Map.py")  # the start screen is the Map
