"""Visual QA only: actual dashboard card function, isolated historical samples."""
import ast
import base64
from datetime import date
import html
from pathlib import Path
import sys
import streamlit as st
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import importlib
import ui_theme
importlib.reload(ui_theme)
from kpi_sparklines import daily_kpi_trends,sparkline_html
st.set_page_config(layout='wide')
ui_theme.apply_theme()
if st.query_params.get('theme')=='Dark':
    st.markdown('<style>'+(ROOT/'styles/dark.css').read_text()+'</style>',unsafe_allow_html=True)
from test_kpi_sparklines import KpiSparklineTests
sample=KpiSparklineTests();sample.setUp()
valid=sample.orders.loc[sample.orders.status.ne('Cancelled')].copy()
overview_start,overview_end=date(2026,1,1),date(2026,1,4)
scenario=st.query_params.get('scenario','history')
if scenario=='empty':valid=valid.iloc[:0]
if scenario=='single':overview_start=overview_end=date(2026,1,2)
if scenario=='short':overview_start=date(2026,1,3)
valid=valid.loc[pd.to_datetime(valid.ordered_at,utc=True).dt.tz_convert('Asia/Kuala_Lumpur').dt.date.between(overview_start,overview_end)]
kpi_trends=daily_kpi_trends(valid,sample.items,overview_start,overview_end)
tr=lambda text:text
source=(ROOT/'app.py').read_text(encoding='utf-8')
function=next(node for node in ast.walk(ast.parse(source)) if isinstance(node,ast.FunctionDef) and node.name=='overview_stat')
# Preserve production icon paths when executing the production renderer.
__file__=str(ROOT/'app.py')
exec(compile(ast.Module(body=[function],type_ignores=[]),'actual_dashboard_card','exec'))
with st.container(key='nour_overview'), st.container(key='nour_overview_kpis'):
    cols=st.columns(4,gap='medium')
    for col,label,field,tone,foot in zip(cols,['Total Orders','Total Revenue','Total Profits','Outstanding Balance'],['orders','revenue','profit','balance'],['lavender','pink','mint','peach'],['50% completed','33% collected','Before overheads','Selected orders; after recorded payments']):
        value=str(len(valid)) if field=='orders' else f'RM {valid[field].sum():,.2f}'
        overview_stat(col,label,value,foot,tone)
