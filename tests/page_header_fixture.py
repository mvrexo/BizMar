"""Isolated visual fixture, using the actual shared component and route catalogue."""
from pathlib import Path
import sys
import tempfile
import streamlit as st
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from uat.isolated_test_support import install_database

@st.cache_resource
def fixture_directory():return tempfile.TemporaryDirectory(prefix='bizmar-header-visual-')

install_database(Path(fixture_directory().name)/'isolated.sqlite3')
from navigation import ROUTE_LABELS
import importlib
import ui_theme
importlib.reload(ui_theme)
from ui_theme import apply_theme
from page_header import page_header,header_title

st.set_page_config(layout='wide')
apply_theme()
theme=st.query_params.get('theme','Light')
if theme=='Dark':st.markdown('<style>'+(ROOT/'styles/dark.css').read_text()+'</style>',unsafe_allow_html=True)
routes=[*ROUTE_LABELS,'Customer Location Analytics','Long title test']
selected=st.selectbox('Route',routes,key='header_test_route')
title='Long-Term Profitability Analysis and Customer Location Performance Across Multiple Reporting Periods' if selected=='Long title test' else header_title(selected,ROUTE_LABELS)
with page_header(title,greeting='Good Morning, Owner!' if selected=='Overview' else None,with_actions=selected=='Overview') as actions:
    if actions:
        with actions,st.container(key='nour_shell_actions'):
            for column,icon in zip(st.columns(3),['notifications','chat_bubble','account_circle']):
                with column:st.button('',icon=f':material/{icon}:',key='header_test_'+icon)
st.title(title)  # Existing page renderer title must not produce a second visible H1.
