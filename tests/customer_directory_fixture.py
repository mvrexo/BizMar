"""Isolated visual fixture: never connects to the live business database."""
from pathlib import Path
import sys
import tempfile
import streamlit as st
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from uat.isolated_test_support import install_database
@st.cache_resource
def directory():return tempfile.TemporaryDirectory(prefix='bizmar-directory-visual-')
store=install_database(Path(directory().name)/'customers.sqlite3')
store.initialize()
if not store.all_rows('customers'):
    for i in range(17):store.add('customers',dict(name=f'Example Customer {i:02d}',phone=f'011{10000000+i}',address='Example address',state='Kedah'))
from settings_store import DEFAULTS
from display_preferences import tr
from ui_theme import apply_theme
from page_header import page_header
from customer_directory import render_customers
st.set_page_config(layout='wide')
theme=st.query_params.get('theme','Light')
language=st.query_params.get('language','English')
st.session_state.bizmar_preferences={**DEFAULTS,'theme':theme,'language':language}
apply_theme()
if theme=='Dark':st.markdown('<style>'+(ROOT/'styles/dark.css').read_text()+'</style>',unsafe_allow_html=True)
with page_header(tr('Customers')):pass
records=[] if st.query_params.get('empty')=='1' else store.all_rows('customers')
render_customers(records,store=store,on_saved=lambda:None,normalize_phone=store.normalize_customer_phone)
