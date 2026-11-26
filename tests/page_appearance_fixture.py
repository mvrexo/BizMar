"""Actual page components against a disposable, network-free owner workspace."""
from pathlib import Path
from datetime import date,datetime,timedelta
from zoneinfo import ZoneInfo
import ast
import html
import sys
import tempfile
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from uat.isolated_test_support import install_database
@st.cache_resource
def directory():return tempfile.TemporaryDirectory(prefix='bizmar-page-theme-')
sqlite_db=install_database(Path(directory().name)/'isolated.sqlite3')
sqlite_db.initialize()
st.session_state.authenticated=True
st.session_state.local_owner_email='owner@example.test'
import orders_store
import products_store
orders_store.current_owner=lambda:'owner@example.test'
products_store.current_owner=lambda:'owner@example.test'
if not sqlite_db.all_rows('products'):
    product=sqlite_db.add('products',dict(name='Example Cake',category='Dessert',price=10.,unit_cost=3.,active=1))
    orders_store.save_order(dict(name='Example Customer',phone='0123456789',address='Example address',state='Kedah'),
                            dict(ordered_at=str(date.today()),fulfilment_date=str(date.today()+timedelta(days=1)),source='WhatsApp',fulfilment_method='Pickup'),
                            [dict(product_id=product['id'],quantity=2,unit_price=10)],token='fixture-page-theme-order')
from settings_store import load,save,DEFAULTS
if not st.session_state.get('fixture_initialized'):
    values=load()
    if st.query_params.get('theme'):values['theme']=st.query_params['theme']
    if st.query_params.get('language'):values['language']=st.query_params['language']
    save(values)
    st.session_state.fixture_initialized=True
st.session_state.bizmar_preferences=load()
from ui_theme import apply_theme,style_bi_chart,style_overview_chart,deadline_status_style
from display_preferences import tr,format_date,date_pattern,date_input_format,style_table,style_figure,localized_dialog
from navigation import render_primary_navigation,render_section_navigation,ROUTE_LABELS
from page_header import page_header
from deadline_calendar import shift_calendar_month,calendar_weeks,prepare_deadline_orders,deadline_day_orders,deadline_month_counts
st.set_page_config(layout='wide')
apply_theme()
if load()['theme']=='Dark':st.markdown('<style>'+(ROOT/'styles/dark.css').read_text()+'</style>',unsafe_allow_html=True)
route=st.query_params.get('route','Settings')
st.session_state.nour_current_page=route
with st.sidebar.container(key='bizmar_sidebar_logo'):st.image((ROOT/'assets/bizmar_logo.png').read_bytes(),width=190)
render_primary_navigation()
st.sidebar.markdown('<p class="nour-sidebar-brand">BizMar</p>',unsafe_allow_html=True)
st.sidebar.divider()
st.sidebar.button(tr('Sign Out'),key='sidebar_signout',icon=':material/logout:')
with page_header(tr(ROUTE_LABELS.get(route,route))):pass
render_section_navigation()
def fetch():return {table:sqlite_db.all_rows(table) for table in ('products','customers','orders','order_items','payments')}
def refresh():st.rerun()
def money(value):return f'RM {float(value):,.2f}'
add=sqlite_db.add
source=(ROOT/'app.py').read_text(encoding='utf-8')
functions=[node for node in ast.parse(source).body if isinstance(node,ast.FunctionDef) and node.name in ('load','render_payment_tracking','render_deadline_calendar')]
# Existing load() is the business-data assembler, not the Settings loader.
exec(compile(ast.Module(body=functions,type_ignores=[]),'actual_page_components','exec'),globals())
d,products,customers,orders,items,payments=load()
if route=='Settings':
    from settings_ui import render_settings
    render_settings(lambda:None)
elif route=='Customers':
    from customer_directory import render_customers
    render_customers(customers,store=sqlite_db,on_saved=refresh,normalize_phone=sqlite_db.normalize_customer_phone)
elif route=='Sales Analytics':
    from sales_analytics_ui import render_sales_analytics
    render_sales_analytics(d,owner_authorized=True)
elif route=='Order Management':
    from order_management import render_order_management
    render_order_management()
elif route=='Products':
    from products_ui import render_products
    render_products()
elif route=='Payments':render_payment_tracking()
elif route=='Deadline Calendar':render_deadline_calendar(orders)

with st.expander('QA shared controls'):
    value=st.selectbox(tr('Order status'),['Pending','Completed','Cancelled'],format_func=lambda item:{'Pending':tr('Pending'),'Completed':tr('Completed'),'Cancelled':tr('Cancelled')}[item],key='qa_status')
    st.caption('RAW='+value)
    st.dataframe(style_table(pd.DataFrame({'Status':['Pending','Paid'],'Customer Name':['Orders','BizMar']})),hide_index=True)
    figure=px.bar(pd.DataFrame({'Status':['Pending','Completed'],'Revenue':[10,20]}),x='Status',y='Revenue')
    st.plotly_chart(style_figure(figure),key='qa_chart')
    with st.popover('QA popup'):st.text_input(tr('Customer Name'),value='Example')
    @localized_dialog('Edit Customer')
    def dialog():
        st.text_input(tr('Customer Name'),value='Example')
        if st.button(tr('Cancel'),key='qa_dialog_cancel'):st.rerun()
    if st.button('QA dialog'):dialog()
