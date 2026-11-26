"""Build an isolated preview from the real dashboard code (synthetic records only)."""
from pathlib import Path
import ast
ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'app.py').read_text(encoding='utf-8')
tree = ast.parse(source)
functions = '\n\n'.join(ast.unparse(node) for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ('sales_date_filter', 'money', 'monthly_revenue_chart'))
start = source.index('shell_now = datetime.now')
end = source.index('render_section_navigation()', start)
header = source[start:end]
branch = next(node for node in ast.walk(tree) if isinstance(node, ast.If) and isinstance(node.test,ast.Compare) and isinstance(node.test.left,ast.Name) and node.test.left.id=='page' and any(isinstance(v,ast.Constant) and v.value=='Overview' for v in node.test.comparators) and any(isinstance(n,ast.Constant) and n.value=='nour_overview' for n in ast.walk(node)))
dashboard = '\n'.join(ast.unparse(node) for node in branch.body)
prefix = '''from typing import Literal, overload
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import base64,html
from datetime import datetime,date,timedelta
from zoneinfo import ZoneInfo
from navigation import ROUTE_LABELS, render_primary_navigation, go_back
import ui_theme
import importlib
importlib.reload(ui_theme)
from ui_theme import apply_theme, style_overview_chart
from customer_location_analytics import build_location_metrics, render_location_map
from settings_store import DEFAULTS, runtime as owner_preferences
from display_preferences import tr, format_date, date_pattern, date_input_format, style_figure
st.set_page_config(layout='wide')
mode = st.query_params.get('theme','Dark')
st.session_state.bizmar_preferences = {**DEFAULTS,'theme': mode}
apply_theme()
if mode=='Dark':
    st.markdown('<style>'+(ROOT/'styles/dark.css').read_text()+'</style>',unsafe_allow_html=True)
render_primary_navigation()
page='Overview'
PAGE_SUBTITLES={'Overview':''}
profile_label='Demo Owner'
avatar=None
if st.query_params.get('avatar') == '1':
    from PIL import Image
    from io import BytesIO
    sample = Image.new('RGB', (240, 120), '#F3B6BF')
    sample.paste('#173B2B', (80, 0, 160, 120))
    buffer = BytesIO()
    sample.save(buffer, format='PNG')
    avatar = buffer.getvalue()
google_authorized=False
profile={}
def navigate_to(route):
    st.session_state.preview_target=route
if st.session_state.get('preview_target'):
    st.info('Opened: '+st.session_state.preview_target)
today=datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date()
orders=pd.DataFrame([dict(id=i,customer_id=i,customer='Example Customer '+str(i),ordered_at=str(today-timedelta(days=i-1))+'T02:00:00Z',due_date=str(today+timedelta(days=2)),status='Pending',fulfilment_method='Delivery' if i==1 else 'Pickup',delivery_state='Selangor' if i==1 else '',customer_state_snapshot='Johor' if i==1 else 'Perak',revenue=12345678.12,profit=234567.12,paid=25.,balance=12345653.12) for i in range(1,4)])
customer_rows=[{'id':1,'name':'Example Customer 1','state':'Selangor'},{'id':2,'name':'Example Customer 2','state':'Johor'},{'id':3,'name':'Example Customer 3','state':'Perak'}]
customers=pd.DataFrame(customer_rows)
items=pd.DataFrame([dict(order_id=1,product_id=1,quantity=3)])
d={'products':[{'id':1,'name':'Demo product'}],'customers':customer_rows}
'''
(ROOT/'uat/dashboard_layout_preview.py').write_text((prefix+'\n'+functions+'\n'+header+'\n'+dashboard).replace("Path(__file__).parent / 'assets'", "ROOT / 'assets'"),encoding='utf-8')
print('Synthetic Streamlit dashboard fixture prepared')
