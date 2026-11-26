"""Isolated browser fixture for the actual Sales Analytics renderer."""
from pathlib import Path
import sys
import tempfile
from datetime import date
import streamlit as st
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from uat.isolated_test_support import install_database
@st.cache_resource
def directory():return tempfile.TemporaryDirectory(prefix='bizmar-sales-visual-')
install_database(Path(directory().name)/'analytics.sqlite3')
import ui_theme
from settings_store import DEFAULTS
from page_header import page_header
from sales_analytics_ui import render_sales_analytics
from test_sales_analytics import snapshot
st.set_page_config(layout='wide')
theme=st.query_params.get('theme','Light')
st.session_state.bizmar_preferences={**DEFAULTS,'theme':theme}
ui_theme.apply_theme()
if theme=='Dark':st.markdown('<style>'+(ROOT/'styles/dark.css').read_text()+'</style>',unsafe_allow_html=True)
with page_header('Sales Analytics'):pass
st.session_state.setdefault('sales_report_period','Custom')
st.session_state.setdefault('sales_report_start',date(2026,1,1))
st.session_state.setdefault('sales_report_end',date(2026,1,7))
render_sales_analytics({} if st.query_params.get('empty')=='1' else snapshot(),owner_authorized=True)
