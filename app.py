from typing import Literal, overload
import importlib
from display_preferences import style_table, tr
from display_preferences import style_figure
from uat_hardening import image as uat_image
import streamlit as st
from pathlib import Path
import base64
import html
import re
LOGO_PATH = Path(__file__).parent / "assets" / "bizmar_logo.png"
import hmac
import os

LOCAL_AUTH = os.environ.get("BIZMAR_AUTH_MODE", "supabase") == "sqlite"
from datetime import date, timedelta
from receipt_storage import upload_payment_receipt, signed_receipt_url
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from copy import deepcopy
_nour_plotly_template = deepcopy(pio.templates['plotly_white'])
_nour_plotly_template.layout.font.family = 'Inter, Arial, sans-serif'
_nour_plotly_template.layout.font.color = '#40313A'
_nour_plotly_template.layout.title.font.family = 'Plus Jakarta Sans, Arial, sans-serif'
pio.templates['nour_sans'] = _nour_plotly_template
pio.templates.default = 'nour_sans'

import streamlit as st
import sqlite_db
from sqlite_db import configured, all_rows, add, edit, remove

st.set_page_config(page_title='BizMar', layout='wide', initial_sidebar_state='expanded')
if os.environ.get('BIZMAR_PREVIEW_ONLY') == '1':
    st.info(tr('Preview mode: business records are read-only. Google Sheets live sync is OFF.'))
from ui_theme import apply_theme, style_overview_chart, style_bi_chart, deadline_status_style
from bi_analytics import daily_order_volume, product_profitability
from deadline_calendar import (
    shift_calendar_month, calendar_weeks, prepare_deadline_orders,
    deadline_day_orders, deadline_month_counts,
)
from production_alert_ui import render_alert_settings, render_production_alerts
from advanced_bi_ui import render_long_term_profitability, render_repeat_customer_insights
apply_theme()
# ==========================================
# 1. CHECK CONFIGURATION
# ==========================================

supabase_ready = LOCAL_AUTH or all(
    isinstance(st.secrets.get(key), str) and st.secrets.get(key).strip()
    for key in ('SUPABASE_URL', 'SUPABASE_ANON_KEY', 'OWNER_EMAIL')
)
if not configured() or not supabase_ready:
    st.title(tr('Welcome to BizMar'))
    st.info(
        tr('First-time setup: configure the Supabase URL, publishable/anon key, '
        'and authorized owner email in `.streamlit/secrets.toml`. Follow README.md.')
    )
    st.stop()



import auth as auth_module
auth_module = importlib.reload(auth_module)
from auth import (
    sign_in_with_email,
    is_authorized_supabase_user,
    sign_out_email,
    google_oauth_configured,
    is_authorized_google_user,
)

# =====================================
# BIZMAR - AUTHENTICATION
# =====================================

google_login_enabled = (
    not LOCAL_AUTH
    and google_oauth_configured(st.secrets.get("auth", {}))
)
google_logged_in = False
google_authorized = False
if google_login_enabled:
    google_user = st.user
    google_logged_in = google_user.is_logged_in
    google_authorized = is_authorized_google_user(
        google_user, st.secrets["OWNER_EMAIL"]
    )

supabase_authorized = False if LOCAL_AUTH else is_authorized_supabase_user()

if LOCAL_AUTH:
    from local_auth import verify

    def sign_in_with_email(email, password):
        if verify(email, password):
            st.session_state.local_owner_email = email
            return True, "Login successful."
        return False, "Invalid email or password."

    def sign_out_email():
        st.session_state.pop("local_owner_email", None)
        st.session_state.authenticated = False

authorized = bool(st.session_state.get("local_owner_email")) if LOCAL_AUTH else (google_authorized or supabase_authorized)


# =====================================
# LOGIN / REGISTER PAGE
# =====================================

if not authorized:

    st.session_state.authenticated = False

    import login_ui as login_ui_module
    login_ui_module = importlib.reload(login_ui_module)
    render_login = login_ui_module.render_login

    render_login(
        sign_in_with_email,
        google_enabled=google_login_enabled,
        google_unauthorized=google_logged_in and not google_authorized,
    )
    st.stop()


# =====================================
# AUTHORIZED OWNER
# =====================================

st.session_state.authenticated = True
from settings_store import load as load_owner_settings, runtime as owner_preferences
from display_preferences import tr, format_date, date_pattern, date_input_format
st.session_state.bizmar_preferences = load_owner_settings()
if owner_preferences()["theme"] == "Dark":
    st.markdown(tr("<style>" + (Path(__file__).parent / "styles/dark.css").read_text(encoding="utf-8") + "</style>"), unsafe_allow_html=True)


# The authorization check above accepts either verified Google owner or
# verified Supabase owner. Do not check st.user again here: email/password
# sign-in does not populate Streamlit's Google identity.


# =====================================
# ORIGINAL BUSINESS LOGO - UNCHANGED
# =====================================

if LOGO_PATH.exists():
    with st.sidebar.container(key='bizmar_sidebar_logo'):
        uat_image(st, LOGO_PATH, width=176)


# =====================================
# BUSINESS TAGLINE
# =====================================



# =====================================
# NAVIGATION WITH ICONS
# =====================================

from navigation import (
    ALL_ROUTES, ROUTE_LABELS, primary_for, navigate, go_back,
    render_primary_navigation, render_section_navigation,
)
PAGES = ALL_ROUTES

def navigate_to(target):
    navigate(st.session_state, target)


def _open_notified_order(order_id):
    from order_management import _reset_order_filters
    _reset_order_filters()
    st.session_state['om_detail_open_id'] = int(order_id)
    st.session_state['om_detail_selected'] = int(order_id)
    navigate_to('Order Management')
    st.rerun()


def _render_order_notification(notification, key_prefix):
    from notifications_ui import render_notification
    render_notification(notification,key_prefix,_open_notified_order)


render_primary_navigation()
page = st.session_state['nour_current_page']

# =====================================
# DATABASE STATUS
# =====================================

st.sidebar.markdown(
    tr('<div class="nour-workspace-label">BizMar</div>'),
    unsafe_allow_html=True,
)

st.sidebar.divider()

# =====================================
# NAVIGATION SHELL: sidebar + top header
# =====================================

# Ensure the sidebar nav items are rendered in the layout requested in the design spec.
# The app already preserves the selected page state; keep the same workflow while adding
# the missing navigation entries that were previously omitted.

# =====================================
# SIGN OUT
# =====================================

if st.sidebar.button(
    tr("Sign Out"),
    key="sidebar_signout",
    icon=":material/logout:",
    use_container_width=True
):

    sign_out_email()

    if google_logged_in:
        st.logout()
    else:
        st.rerun()



@st.cache_data(ttl=10,show_spinner=False)
def fetch():
    return {t:all_rows(t) for t in ['products','customers','orders','order_items','payments']}

def refresh():
    fetch.clear()
    st.rerun()

@overload
def sales_date_filter(frame: pd.DataFrame, key: str, *, return_period: Literal[True]) -> tuple[pd.DataFrame, str, date, date]: ...

@overload
def sales_date_filter(frame: pd.DataFrame, key: str, *, return_period: Literal[False] = False) -> tuple[pd.DataFrame, str]: ...

@overload
def sales_date_filter(frame: pd.DataFrame, key: str, *, return_period: bool) -> tuple[pd.DataFrame, str, date, date] | tuple[pd.DataFrame, str]: ...

def sales_date_filter(frame, key, *, return_period=False):
    from sales_period import sales_date_filter as render_period_filter
    return render_period_filter(frame, key, return_period=return_period)


def render_deadline_calendar(order_frame):
    """Native monthly calendar over saved deadlines; never writes business data."""
    from display_preferences import style_table
    from display_preferences import date_input_format, format_date, tr
    today = datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date()
    prepared = prepare_deadline_orders(order_frame, today)
    month_key, date_key = 'bizmar_calendar_month', 'bizmar_calendar_date'
    st.session_state.setdefault(month_key, today.replace(day=1))
    st.session_state.setdefault(date_key, today)

    def move_month(offset):
        month = shift_calendar_month(st.session_state[month_key], offset)
        st.session_state[month_key] = month
        st.session_state[date_key] = month

    def choose_day(day):
        st.session_state[date_key] = day

    def choose_from_input():
        st.session_state[month_key] = st.session_state[date_key].replace(day=1)

    def display_rows(rows):
        display = pd.DataFrame({
            'Order reference': rows['calendar_reference'],
            'Customer': rows['calendar_customer'],
            'Deadline (Malaysia)': rows['calendar_date'].map(
                lambda value: format_date(value) if value is not None else 'Unassigned'
            ),
            'Order status': rows['status'],
            'Deadline state': rows['deadline_state'],
        })
        st.dataframe(
            style_table(display.style.map(deadline_status_style, subset=['Deadline state'])),
            hide_index=True, use_container_width=True,
        )

    with st.container(border=True, key='bizmar_deadline_calendar'):
        st.subheader(tr('Deadline Calendar'))
        st.caption(tr('Saved fulfilment date first; saved due date is used only when fulfilment is blank. Counts include all order statuses. Completed and Cancelled orders are never active overdue work.'))
        controls = st.columns([1, 3, 1], vertical_alignment='center')
        controls[0].button(tr('Previous'), key='bizmar_calendar_previous',
                           on_click=move_month, args=(-1,), use_container_width=True)
        month = st.session_state[month_key]
        controls[1].markdown(tr(f'<div class="bizmar-calendar-month">{month:%B %Y}</div>'),
                             unsafe_allow_html=True)
        controls[2].button(tr('Next'), key='bizmar_calendar_next',
                           on_click=move_month, args=(1,), use_container_width=True)
        st.date_input(tr('Selected date'), key=date_key, on_change=choose_from_input, format=date_input_format())
        st.caption(tr('Deadline states: Overdue | Due today | Upcoming | Completed | Cancelled'))
        counts = deadline_month_counts(prepared, month)
        if prepared.empty:
            st.info(tr('No orders yet. Saved orders will appear here after normal data refresh.'))
        elif not any(counts.values()):
            st.info(tr('No orders are scheduled in this month.'))
        with st.container(key='bizmar_calendar_grid'):
            headings = st.columns(7)
            for column, label in zip(headings, ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')):
                column.markdown(tr(f'<div class="bizmar-calendar-weekday">{label}</div>'),
                                unsafe_allow_html=True)
            for week in calendar_weeks(month):
                columns = st.columns(7)
                for column, day in zip(columns, week):
                    with column:
                        if day.month != month.month:
                            st.markdown(tr('<div class="bizmar-calendar-blank" aria-hidden="true"></div>'),
                                        unsafe_allow_html=True)
                            continue
                        count = counts[day]
                        day_states = deadline_day_orders(prepared, day)['deadline_state']
                        priority = ('Overdue', 'Due today', 'Upcoming', 'Completed', 'Cancelled')
                        dominant = next((state for state in priority if state in day_states.values), '')
                        tones = {'Overdue': 'overdue', 'Due today': 'today', 'Upcoming': 'upcoming',
                                 'Completed': 'completed', 'Cancelled': 'cancelled'}
                        tone = 'scheduled_' + tones.get(dominant, 'upcoming') if count else 'empty'
                        state_summary = ', '.join(f'{state}: {number}' for state, number in day_states.value_counts().items())
                        with st.container(key=f'bizmar_calendar_{tone}_{day:%Y%m%d}'):
                            st.button(
                                tr(f"{day.day} | {count}"),
                                key=f'bizmar_calendar_day_{day:%Y%m%d}',
                                type='primary' if day == st.session_state[date_key] else 'secondary',
                                help=f"{day:%d %B %Y}: {count} order(s). {state_summary}",
                                on_click=choose_day, args=(day,), use_container_width=True,
                            )
        st.caption(tr('Each button shows day | order count. Pink: overdue; lavender: due today; matcha: upcoming; pale green: completed; gray: cancelled. Mixed days prioritize active work. Select a day for every order; the outlined date is selected.'))
        selected = deadline_day_orders(prepared, st.session_state[date_key])
        st.markdown(tr(f"#### Orders for {st.session_state[date_key]:%d %B %Y}"))
        if selected.empty:
            st.info(tr('No orders are scheduled on this date.'))
        else:
            display_rows(selected)
        unscheduled = prepared.loc[prepared['calendar_date'].isna()]
        if not unscheduled.empty:
            with st.expander(tr(f'Unassigned or invalid deadlines ({len(unscheduled)})'), expanded=True):
                st.caption(tr('No deadline has been invented. Review these orders in Order Management.'))
                display_rows(unscheduled)
        if not prepared.empty:
            if st.button(tr('Manage orders'), key='bizmar_calendar_manage_orders',
                         icon=':material/receipt_long:'):
                navigate_to('Order Management')
                st.rerun()
    return prepared


def render_bi_requirements(order_frame, item_frame, start, end, view='all'):
    """Show FR05/FR08 from real loaded data without changing existing KPI rules."""
    from display_preferences import style_table
    from display_preferences import style_figure, tr
    if view in ('all', 'volume'):
        with st.container(border=True, key='bizmar_daily_volume'):
            st.subheader(tr('Daily Order Volume'))
            st.caption(tr('Counts unique orders by Malaysia order date. Includes Pending, Confirmed, Preparing, Ready and Completed; excludes Cancelled. Zero-order dates are shown.'))
            volume = daily_order_volume(order_frame, start, end)
            if volume.empty:
                st.info(tr('Choose a valid date range to view daily order counts.'))
            else:
                if not volume['order_count'].any():
                    st.info(tr('No non-cancelled orders in this period. Every selected day has zero orders.'))
                volume_chart = px.bar(volume, x='date', y='order_count',
                                      color_discrete_sequence=['#9BB89A'])
                volume_chart.update_traces(
                    marker_line_color='#526F5A', marker_line_width=1,
                    hovertemplate='%{x|%d %b %Y}<br>Orders: %{y:.0f}<extra></extra>',
                )
                style_bi_chart(volume_chart)
                volume_chart.update_layout(height=280, xaxis_title='Order date (Malaysia)', yaxis_title='Number of orders')
                volume_chart.update_xaxes(type='date')
                volume_chart.update_yaxes(rangemode='tozero', tickformat=',d',
                                          dtick=1 if volume['order_count'].max() <= 10 else None)
                st.plotly_chart(style_figure(volume_chart), use_container_width=True)

    if view in ('all', 'profitability'):
        with st.container(border=True, key='bizmar_product_profitability'):
            st.subheader(tr('Product Profitability Ranking'))
            st.caption(tr('Gross profit = quantity x (saved unit selling price - saved unit cost). Uses the selected Malaysia order-date range and all non-cancelled orders, including pending/unpaid orders. This is not net profit or collected cash.'))
            ranking = product_profitability(order_frame, item_frame, start, end)
            if ranking.empty:
                st.info(tr('No product lines from non-cancelled orders in this period.'))
            else:
                ranking['Product'] = [
                    f"{row.product_name} (ID {int(row.product_id)})"
                    if pd.notna(row.product_id)
                    else (f"{row.product_name} ({row.product_key})"
                          if row.product_key.startswith('historical-line:')
                          else f"{row.product_name} (historical)")
                    for row in ranking.itertuples()
                ]
                chart_rows = ranking.head(10)
                profit_chart = px.bar(
                    chart_rows, x='gross_profit', y='Product', orientation='h',
                    color='gross_profit', color_continuous_scale=['#F4B6C2', '#9BB89A'],
                    custom_data=['units_sold', 'revenue', 'recorded_cost'],
                )
                profit_chart.update_traces(
                    hovertemplate='%{y}<br>Gross profit: RM %{x:,.2f}<br>Units: %{customdata[0]}<br>Revenue: RM %{customdata[1]:,.2f}<br>Recorded cost: RM %{customdata[2]:,.2f}<extra></extra>'
                )
                style_bi_chart(profit_chart)
                profit_chart.update_layout(
                    height=max(260, len(chart_rows) * 34), coloraxis_showscale=False,
                    xaxis_title='Total gross profit (RM)', yaxis_title='',
                    yaxis=dict(categoryorder='array', categoryarray=list(chart_rows['Product']), autorange='reversed'),
                )
                profit_chart.update_xaxes(zeroline=True, zerolinecolor='#655e6c')
                st.plotly_chart(style_figure(profit_chart), use_container_width=True)
                st.caption(tr('Chart: ten highest gross-profit products. Table: every ranked product, including losses and zero profit. Historical rows with missing product IDs are grouped by saved name.'))
                st.dataframe(
                    style_table(ranking[['Product', 'units_sold', 'revenue', 'recorded_cost', 'gross_profit']]),
                    column_config={
                        'Product': st.column_config.TextColumn(tr('Product')),
                        'units_sold': st.column_config.NumberColumn(tr('Units sold')),
                        'revenue': st.column_config.NumberColumn(tr('Revenue (RM)'), format='RM %.2f'),
                        'recorded_cost': st.column_config.NumberColumn(tr('Recorded cost (RM)'), format='RM %.2f'),
                        'gross_profit': st.column_config.NumberColumn(tr('Gross profit (RM)'), format='RM %.2f'),
                    },
                    hide_index=True, use_container_width=True,
                )



def sales_trend_chart(frame, mode, height=320, *, dashboard_style=False):
    from display_preferences import style_figure
    if frame.empty:
        st.info(tr('No sales for this period.'))
        return
    timestamps = pd.to_datetime(frame['ordered_at'], errors='coerce', utc=True).dt.tz_convert('Asia/Kuala_Lumpur')
    trend = frame.copy()
    local_dates = timestamps.dt.tz_localize(None)
    if mode in ('Daily', 'Weekly', 'Monthly', 'Custom Range', 'Today', 'Yesterday', '7D'):
        trend['Period'] = local_dates.dt.strftime('%Y-%m-%d')
    elif mode == 'Yearly':
        trend['Period'] = local_dates.dt.strftime('%Y-%m')
    else:
        trend['Period'] = local_dates.dt.strftime('%Y-%m')
    trend = trend.dropna(subset=['Period']).groupby('Period', as_index=False)[['revenue', 'profit']].sum()
    if trend.empty:
        st.info(tr('No dated sales available.'))
        return
    melted = trend.melt(id_vars='Period', var_name='Metric', value_name='RM')
    fig = px.line(melted, x='Period', y='RM', color='Metric', markers=True,
                  color_discrete_map={'revenue': '#C57B8F', 'profit': '#819A78'})
    fig.update_traces(line_width=3)
    fig.update_layout(height=height, paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(0,0,0,0)', xaxis_title='', yaxis_title='RM')
    if dashboard_style:
        style_overview_chart(fig)
    st.plotly_chart(style_figure(fig), use_container_width=True)


def monthly_revenue_chart(frame, height=320):
    from dashboard_revenue import render_monthly_revenue
    render_monthly_revenue(frame, height=height)


def money(n): return f'RM {float(n):,.2f}'

def load():
    d=fetch()
    products=pd.DataFrame(d['products']); customers=pd.DataFrame(d['customers'])
    orders=pd.DataFrame(d['orders']); items=pd.DataFrame(d['order_items']); payments=pd.DataFrame(d['payments'])
    if orders.empty:
        orders=pd.DataFrame(columns=['id','customer_id','ordered_at','due_date','status','notes'])
    # Preserve legacy rows while presenting the same three statuses as Orders.
    orders['status']=orders['status'].where(orders['status'].isin(['Pending','Completed','Cancelled']),'Pending')
    if items.empty:
        items=pd.DataFrame(columns=['id','order_id','product_id','quantity','unit_price','unit_cost'])
    if payments.empty:
        payments=pd.DataFrame(columns=['id','order_id','amount','paid_at','method','reference'])
    for col in ['quantity','unit_price','unit_cost']:
        items[col]=pd.to_numeric(items[col],errors='coerce').fillna(0)
    payments['amount']=pd.to_numeric(payments['amount'],errors='coerce').fillna(0)
    items['revenue']=items.quantity*items.unit_price
    items['cost']=items.quantity*items.unit_cost
    totals=items.groupby('order_id',as_index=False)[['revenue','cost']].sum()
    paid=payments.groupby('order_id',as_index=False)['amount'].sum().rename(columns={'amount':'paid'})
    orders=orders.merge(totals,left_on='id',right_on='order_id',how='left').drop(columns='order_id',errors='ignore')
    orders=orders.merge(paid,left_on='id',right_on='order_id',how='left').drop(columns='order_id',errors='ignore')
    for c in ['revenue','cost','paid']:orders[c]=orders[c].fillna(0)
    if 'total_amount' in orders:
        orders['revenue'] = pd.to_numeric(orders['total_amount'], errors='coerce').fillna(orders['revenue'])
    orders['balance']=(orders.revenue-orders.paid).clip(lower=0)
    orders['profit']=orders.revenue-orders.cost
    names={int(c['id']):c['name'] for c in d['customers']}
    orders['customer']=orders.customer_id.map(names).fillna('Unknown')
    if 'customer_name_snapshot' in orders:
        orders['customer']=orders['customer_name_snapshot'].fillna('').where(orders['customer_name_snapshot'].fillna('').ne(''),orders['customer'])
    return d,products,customers,orders,items,payments

try: d,products,customers,orders,items,payments=load()
except Exception as e:
    st.error(tr(f'Unable to load the local SQLite database. Details: {e}'))
    st.stop()


def normalize_customer_phone(phone):
    digits = re.sub(r'\D', '', str(phone or ''))
    if not digits:
        return ''
    if digits.startswith('60'):
        normalized = digits
    elif digits.startswith('0'):
        normalized = '60' + digits[1:]
    elif digits.startswith('1') and len(digits) == 9:
        normalized = '60' + digits
    else:
        normalized = digits if digits.startswith('6') and len(digits) in (10, 11) else digits
    if not re.fullmatch(r'60\d{9,10}', normalized):
        return ''
    return f'+{normalized}'


def validate_customer_phone(phone):
    return bool(normalize_customer_phone(phone))


def customer_category_for_completed(completed_orders):
    if completed_orders == 0:
        return 'No Purchase'
    if completed_orders == 1:
        return 'New Customer'
    if 2 <= completed_orders <= 4:
        return 'Returning Customer'
    if 5 <= completed_orders <= 9:
        return 'Loyal Customer'
    return 'VIP Customer'


def customer_summary_frame(frame):
    customer_frame = frame.copy()
    if customer_frame.empty:
        # The page filters archived customers even when the input has no columns.
        customer_frame['archived'] = pd.Series(index=customer_frame.index, dtype='int64')
        return customer_frame
    customer_frame['customer_id'] = customer_frame.get('customer_id', pd.Series([None] * len(customer_frame)))
    customer_frame['customer_id'] = customer_frame['customer_id'].fillna(customer_frame['id'].astype(str))
    empty_text = pd.Series('', index=customer_frame.index, dtype='object')
    legacy_names = customer_frame.get('name', empty_text).fillna('')
    legacy_names = legacy_names.mask(legacy_names.astype('string').str.strip().eq(''), '')
    full_names = customer_frame.get('full_name', empty_text)
    missing_full_name = full_names.astype('string').str.strip().eq('').fillna(True)
    customer_frame['full_name'] = full_names.mask(missing_full_name, legacy_names).fillna('')
    customer_frame['customer_name'] = customer_frame['full_name']
    legacy_phones = customer_frame.get('phone', empty_text).fillna('')
    phone_numbers = customer_frame.get('phone_number', empty_text).fillna(legacy_phones)
    customer_frame['phone_number'] = phone_numbers.mask(phone_numbers.eq(''), legacy_phones)
    customer_frame['archived'] = customer_frame.get('archived', 0).fillna(0).astype(int)
    customer_frame['created_at'] = pd.to_datetime(customer_frame.get('created_at', pd.Timestamp.now()), errors='coerce')
    customer_frame['registration_date'] = customer_frame['created_at'].dt.strftime('%Y-%m-%d')
    customer_frame['customer_key'] = customer_frame['id'].astype(str)
    order_counts = orders[orders['status'] != 'Cancelled'].groupby('customer_id').size().rename('total_orders')
    completed_counts = orders[(orders['status'] == 'Completed') & (orders['status'] != 'Cancelled')].groupby('customer_id').size().rename('completed_orders')
    customer_frame = customer_frame.merge(order_counts.rename('total_orders'), left_on='id', right_index=True, how='left')
    customer_frame = customer_frame.merge(completed_counts.rename('completed_orders'), left_on='id', right_index=True, how='left')
    customer_frame['total_orders'] = customer_frame['total_orders'].fillna(0).astype(int)
    customer_frame['completed_orders'] = customer_frame['completed_orders'].fillna(0).astype(int)
    customer_frame['total_spent'] = customer_frame['id'].map(
        orders[orders['status'] != 'Cancelled'].groupby('customer_id')['revenue'].sum().to_dict()
    ).fillna(0)
    customer_frame['last_purchase'] = customer_frame['id'].map(
        orders[orders['status'] != 'Cancelled'].groupby('customer_id')['ordered_at'].max().to_dict()
    )
    customer_frame['category'] = customer_frame['completed_orders'].map(customer_category_for_completed)
    customer_frame['address'] = customer_frame.get('address', '').fillna('')
    return customer_frame


def render_customer_management():
    from customer_directory import render_customers
    render_customers(customers, store=sqlite_db, on_saved=lambda: refresh(), normalize_phone=normalize_customer_phone)

def render_payment_tracking(order_id=None):
    from display_preferences import style_table
    from display_preferences import date_pattern, tr
    embedded_order_id = order_id
    payment_orders = orders if embedded_order_id is None else orders.loc[orders['id'].eq(embedded_order_id)]
    with st.container(key='nour_payment_page'):
        if payment_orders.empty:
            st.info(tr('Create an order first.'))
        else:
            active=payment_orders[payment_orders.status!='Cancelled']
            options={f"#{int(r.id)} · {r.customer} · Balance {money(r.balance)}":int(r.id) for _,r in active.iterrows()}
            with st.container(key='nour_payment_kpis'):
                value_col, paid_col, balance_col = st.columns(3)
                value_col.metric(tr('Order value'), money(active['revenue'].sum()))
                paid_col.metric(tr('Payments recorded'), money(active['paid'].sum()))
                balance_col.metric(tr('Outstanding balance'), money(active['balance'].sum()))
            if options:
                with st.container(key='nour_payment_split'):
                    record_col, summary_col = st.columns([1.15, 1], gap='medium')
                with record_col, st.container(border=True, key='nour_payment_record'):
                    st.subheader(tr('Record Payment'))
                    quick_complete = embedded_order_id is not None and st.session_state.get('quick_payment_saved_order') == embedded_order_id
                    if quick_complete:
                        st.success(tr('Payment recorded. Start another payment only if more money was received.'))
                        if st.button(tr('Record another payment'), key='quick_another_payment'):
                            st.session_state.pop('quick_payment_saved_order', None)
                            st.rerun()
                    with st.form('payment'):
                        order_label=st.selectbox(tr('Order'),list(options))
                        amount=st.number_input(tr('Payment received (RM)'),min_value=0.01,value=1.,step=1.)
                        methods = ['Transfer', 'Cash', 'E-wallet', 'Other']
                        from settings_store import runtime
                        method=st.selectbox(tr('Payment method'), methods, index=methods.index(runtime()['payment']))
                        ref=st.text_input(tr('Reference / notes'))
                        if st.form_submit_button(tr('Record payment'),type='primary',disabled=quick_complete) and not quick_complete:
                            order_id=options[order_label]
                            balance=float(active[active.id==order_id].iloc[0].balance)
                            if amount>balance+0.001:st.error(tr(f'Payment exceeds outstanding balance ({money(balance)}).'))
                            else:
                                try:
                                    add('payments',{'order_id':order_id,'amount':amount,'method':method,'reference':ref})
                                    if embedded_order_id is not None:
                                        st.session_state['quick_payment_saved_order'] = embedded_order_id
                                    refresh()
                                except Exception as ex:st.error(tr(str(ex)))

                with summary_col, st.container(border=True, key='nour_payment_selected'):
                    st.subheader(tr('Selected Order'))
                    selected_payment_order = active[active.id == options[order_label]].iloc[0]
                    st.markdown(tr('**' + html.escape(str(order_label)) + '**'))
                    st.caption(tr('Summary reflects the last submitted order selection.'))
                    summary_total, summary_paid = st.columns(2)
                    summary_total.metric(tr('Order total'), money(selected_payment_order['revenue']))
                    summary_paid.metric(tr('Already paid'), money(selected_payment_order['paid']))
                    st.metric(tr('Outstanding'), money(selected_payment_order['balance']))
                    st.caption(tr('Order status: ' + str(selected_payment_order['status'])))
            with st.container(border=True, key='nour_payment_history'):
                st.subheader(tr('Payment History'))
                scoped_payments = payments if embedded_order_id is None else payments.loc[payments['order_id'].eq(embedded_order_id)]
                if not scoped_payments.empty:
                    payment_history = scoped_payments[['id','order_id','paid_at','amount','method','reference']].copy()
                    payment_history['paid_at'] = pd.to_datetime(payment_history['paid_at'], errors='coerce', utc=True).dt.tz_convert('Asia/Kuala_Lumpur').dt.strftime(date_pattern() + ' %H:%M').fillna('Date unavailable')
                    payment_history['amount'] = payment_history['amount'].map(money)
                    payment_history = payment_history.rename(columns={
                        'id': 'Payment reference', 'order_id': 'Order ID',
                        'paid_at': 'Payment date (MYT)', 'amount': 'Amount (RM)',
                        'method': 'Payment method', 'reference': 'Reference / notes',
                    })
                    st.dataframe(style_table(payment_history), hide_index=True, use_container_width=True)
                else:
                    st.info(tr('No payments recorded yet.'))


# Replace the simple customers page block below.
from owner_profile import get_profile, save_profile, upload_avatar, remove_avatar, avatar_url

profile = get_profile()
profile_label = profile.get('display_name') or 'Owner'
avatar = avatar_url(profile)


PAGE_SUBTITLES = {}

shell_now = datetime.now(ZoneInfo('Asia/Kuala_Lumpur'))
header_greeting = 'Good Morning' if shell_now.hour < 12 else 'Good Afternoon' if shell_now.hour < 17 else 'Good Evening'
header_name = (st.user.get('given_name') or st.user.get('name')) if google_authorized else None
if not header_name:
    header_name = profile_label if profile_label != 'UAT Owner' else (
        st.session_state.get('local_owner_email', '').split('@')[0] or 'Owner'
    )
if page != 'Overview':
    if st.button(tr('← Back'), key='nour_page_back'):
        go_back(st.session_state)
        st.rerun()

profile_button_label = ''
if avatar:
    profile_avatar_data = base64.b64encode(avatar).decode('ascii')
    profile_button_label = f'![Edit Profile](data:image/png;base64,{profile_avatar_data})'

from page_header import page_header, header_title
with page_header(tr(header_title(page,ROUTE_LABELS)),when=shell_now,date_text=format_date(shell_now),
                 greeting=f'{tr(header_greeting)}, {header_name}!' if page=='Overview' else None,
                 with_actions=page=='Overview') as shortcuts_col:
    if page=='Overview':
        with shortcuts_col:
            with st.container(key='nour_shell_actions'):
                notification_col, messages_col, profile_col = st.columns(3)
                with notification_col:
                    from display_preferences import tr
                    import orders_store
                    try:
                        unread_count = orders_store.order_notification_counts()['unread']
                        with st.popover(
                            tr(str(unread_count) if unread_count else ''),
                            key='nour_header_nav_notifications',
                            help=tr('Notifications'),
                            icon=':material/notifications:',
                        ):
                            from notifications_ui import render_notifications
                            render_notifications(_open_notified_order,compact=True,key_prefix='nour_header_notification')
                            if st.button(
                                tr('View all notifications'),
                                key='nour_header_view_notifications',
                            ):
                                navigate_to('Notifications')
                                st.rerun()
                    except Exception as error:
                        st.error(tr(f'Notifications are unavailable: {error}'))
                with messages_col:
                    if st.button(tr(''),key='nour_header_nav_messages',help=tr('Messages'),icon=':material/chat_bubble:'):
                        navigate_to('Messages');st.rerun()
                with profile_col:
                    if st.button(tr(profile_button_label), key='nour_header_nav_profile', help=tr('Edit Profile'), icon=None if avatar else ':material/account_circle:'):
                        navigate_to('Edit Profile')
                        st.rerun()
render_section_navigation()


from google_sheets_sync_ui import render_google_sheets_sync, render_sync_background
render_sync_background(page,navigate_to)


# ── Overview: reference-inspired bakery dashboard ───────────────────────────
if page == 'Overview':
    with st.container(key='nour_overview'):
        now = datetime.now(ZoneInfo('Asia/Kuala_Lumpur'))
        if not st.session_state.get('nour_topbar_ready'):
            st.session_state['nour_topbar_ready'] = True
        # Overview uses records from the shared SQLite database.
        if orders.empty:
            st.info(tr('No orders yet. Create your first order to get started.'))
        import html
        with st.container(key='nour_overview_filters'):
            period_orders, overview_mode, overview_start, overview_end = sales_date_filter(
                orders, 'overview_sales', return_period=True,
            )
        valid = period_orders[period_orders['status'] != 'Cancelled'].copy()
        total_orders = len(valid)
        completed_count = int((valid['status'] == 'Completed').sum())
        revenue = float(valid['revenue'].sum())
        gross_profit = float(valid['profit'].sum())
        total_customers = len(customers)
        active_customers = int(valid['customer_id'].nunique()) if not valid.empty else 0
        completed_pct = 100 * completed_count / total_orders if total_orders else 0
        paid_pct = 100 * min(float(valid['paid'].sum()) / revenue, 1) if revenue > 0 else 0

        with st.container(key='nour_overview_kpis'):
            c1,c2,c3,c4 = st.columns(4, gap='medium')
        from kpi_sparklines import daily_kpi_trends, sparkline_html
        kpi_trends = daily_kpi_trends(valid, pd.DataFrame(d.get('order_items', [])), overview_start, overview_end)
        def overview_stat(container, title, value, foot, tone):
            icon_name = {'lavender': 'orders', 'pink': 'revenue', 'mint': 'profit', 'peach': 'balance'}[tone]
            icon_path = Path(__file__).parent / 'assets' / 'icons' / f'kpi-{icon_name}.svg'
            icon_data = base64.b64encode(icon_path.read_bytes()).decode('ascii')
            icon = f'<img src="data:image/svg+xml;base64,{icon_data}" width="24" height="24" alt="" />'
            trend_key = {'lavender':'orders','pink':'revenue','mint':'profit','peach':'balance'}[tone]
            trend = sparkline_html(kpi_trends[trend_key], tone, title, unavailable=trend_key == 'balance' or (trend_key == 'profit' and not valid.empty and overview_start != overview_end))
            with container:
                st.markdown(tr(f'<div class="nour-stat nour-stat-{tone}"><div class="nour-stat-top"><div class="nour-stat-label">{html.escape(tr(title))}</div><span class="nour-stat-icon" aria-hidden="true">{icon}</span></div><div class="nour-stat-value">{html.escape(str(value))}</div><div class="nour-stat-foot">{html.escape(foot)}</div>{trend}</div>'), unsafe_allow_html=True)
        overview_stat(c1,'Total Orders',f'{total_orders:,}',f'{completed_pct:.0f}% completed','lavender')
        overview_stat(c2,'Total Revenue',money(revenue),f'{paid_pct:.0f}% collected','pink')
        overview_stat(c3,'Total Profits',money(gross_profit),'Before overheads','mint')
        overview_stat(c4,'Outstanding Balance',money(valid['balance'].sum()),'Selected orders; after recorded payments','peach')

        sold = items[items['order_id'].isin(valid['id'])].copy()
        if not sold.empty:
            product_names = {int(product['id']): product['name'] for product in d['products']}
            sold['Product'] = sold['product_id'].map(product_names)
            if 'product_name' in sold:
                sold['Product'] = sold['Product'].fillna(sold['product_name'])
            sold['Product'] = sold['Product'].fillna('Unknown')
            product_ranking = sold.groupby('Product', as_index=False)['quantity'].sum().sort_values(
                ['quantity', 'Product'], ascending=[False, True],
            )
        else:
            product_ranking = pd.DataFrame(columns=['Product', 'quantity'])
        from malaysian_states import destination
        state_sales = valid.copy()
        state_sales['State'] = [destination(order) for order in state_sales.to_dict('records')]
        state_ranking = state_sales.groupby('State', as_index=False)['revenue'].sum().sort_values(
            ['revenue', 'State'], ascending=[False, True],
        )
        with st.container(border=True, key='nour_overview_insights'):
            st.markdown(tr('#### Key Insights'))
            insight_product, insight_state, insight_average, insight_completion = st.columns(4)
            if product_ranking.empty:
                insight_product.metric(tr('Top-Selling Product'), '—')
                insight_product.caption(tr('No sales yet'))
            else:
                top_product = product_ranking.iloc[0]
                insight_product.metric(tr('Top-Selling Product'), str(top_product['Product']))
                insight_product.caption(tr(f"{int(top_product['quantity']):,} {tr('units sold')}"))
            if state_ranking.empty:
                insight_state.metric(tr('Top Sales State'), '—')
                insight_state.caption(tr('No sales yet'))
            else:
                top_state = state_ranking.iloc[0]
                insight_state.metric(tr('Top Sales State'), str(top_state['State']))
                insight_state.caption(tr(money(top_state['revenue'])))
            insight_average.metric(
                tr('Average Order Value'),
                money(revenue / total_orders) if total_orders else '—',
            )
            insight_average.caption(tr('per order in selected period'))
            insight_completion.metric(
                tr('Completion Rate'),
                f'{completed_pct:.0f}%' if total_orders else '—',
            )
            insight_completion.caption(
                tr(f'{completed_count:,} {tr("of")} {total_orders:,} {tr("orders completed")}'
                if total_orders else tr('No orders in selected period'))
            )

        with st.container(key='nour_overview_activity'):
            activity_col, tasks_col = st.columns([1.55, 1], gap='medium')
        with activity_col:
            with st.container(border=True, key='nour_overview_sales'):
                st.markdown(tr('#### Revenue Over Time (Monthly)'))
                monthly_revenue_chart(valid, height=320)
            with st.container(border=True, key='nour_overview_products'):
                st.markdown(tr('#### Best Selling Product'))
                if sold.empty:
                    st.info(tr('Product rankings appear after sales are recorded.'))
                else:
                    ranking = product_ranking.head(5).sort_values('quantity')
                    fig = px.bar(ranking,x='quantity',y='Product',orientation='h',text='quantity',color_discrete_sequence=['#9BB89A'])
                    fig.update_layout(height=280,title_text='',margin=dict(l=0,r=8,t=8,b=0),paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',xaxis_title='Units sold',yaxis_title='',yaxis={'categoryorder':'total ascending'},showlegend=False)
                    style_overview_chart(fig, product_ranking=True)
                    st.plotly_chart(style_figure(fig),use_container_width=True,config={'displayModeBar':False})
        with tasks_col:
            with st.container(border=True, key='nour_overview_orders'):
                st.markdown(tr('#### Upcoming Orders'))
                active = period_orders[~period_orders['status'].isin(['Completed','Cancelled'])].copy()
                active['due_parsed'] = pd.to_datetime(active['due_date'], errors='coerce')
                active = active.sort_values('due_parsed', na_position='last').head(3)
                if active.empty:
                    st.info(tr('No upcoming orders. You are all caught up!'))
                else:
                    for _,r in active.iterrows():
                        due_label = format_date(r['due_date']) if pd.notna(r['due_date']) else 'No deadline'
                        overdue = pd.notna(r['due_parsed']) and r['due_parsed'].date() < now.date()
                        row_class = 'nour-task nour-task-overdue' if overdue else 'nour-task'
                        status_tone = {'Pending': 'pending', 'Confirmed': 'confirmed', 'Preparing': 'preparing', 'Ready': 'ready'}.get(str(r['status']), 'pending')
                        overdue_label = ' - Overdue' if overdue else ''
                        st.markdown(tr(f'<div class="{row_class}"><div><strong>Order #{int(r["id"])} · {html.escape(str(r["customer"]))}</strong><small>Due {html.escape(due_label)}{overdue_label}</small></div><span class="nour-status-{status_tone}">{html.escape(str(r["status"]))}</span></div>'), unsafe_allow_html=True)
                if st.button(tr('View all orders'), key='overview_manage_orders', use_container_width=True):
                    navigate_to('Order Management')
                    st.rerun()

            with st.container(border=True, key='nour_overview_customers'):
                st.markdown(tr('#### Top Customer'))
                if valid.empty:
                    st.info(tr('Your top customers will appear here.'))
                else:
                    top = valid.groupby(['customer_id','customer'],as_index=False).agg(Orders=('id','count'),Spent=('revenue','sum'))
                    top = top.sort_values(['Spent','Orders'],ascending=False).head(4).reset_index(drop=True)
                    for i,r in top.iterrows():
                        st.markdown(tr(f'<div class="nour-customer"><span><span class="nour-customer-rank" aria-hidden="true">{i+1:02d}</span> {html.escape(str(r["customer"]))}</span><strong>{html.escape(money(r["Spent"]))}</strong></div>'),unsafe_allow_html=True)
                if st.button(tr('View customers'), key='overview_customers', use_container_width=True):
                    navigate_to('Customers')
                    st.rerun()

        from customer_location_analytics import build_location_metrics, render_location_map
        location_metrics = build_location_metrics(
            customers, orders, overview_start, overview_end,
        )
        with st.container(border=True, key='nour_customer_location_analytics'):
            st.markdown(tr('#### Customer Location Analytics'))
            location_mode = st.segmented_control(
                tr('Measure'),
                ['customers', 'orders'],
                format_func=lambda value: tr(
                    'By Customers' if value == 'customers' else 'By Orders'
                ),
                default='customers',
                key='customer_location_measure',
                selection_mode='single',
            ) or 'customers'
            customer_measure = location_mode == 'customers'
            count_column = 'customer_count' if customer_measure else 'order_count'
            percent_column = 'customer_percent' if customer_measure else 'order_percent'
            count_label = tr('Customers') if customer_measure else tr('Orders')
            known_total = location_metrics['known_customers'] if customer_measure else location_metrics['known_orders']
            top_states = location_metrics['states'].sort_values(
                [count_column, 'state'], ascending=[False, True],
            )
            top_state = top_states.iloc[0] if known_total else None
            map_column, details_column = st.columns([1.45, 1], gap='large')
            with map_column:
                render_location_map(
                    location_metrics,
                    metric=count_column,
                )
                st.caption(
                    tr('Boundaries: geoBoundaries gbOpen Malaysia ADM1 (2017), '
                    'OpenStreetMap/Wambacher, ODbL 1.0.')
                )
            with details_column:
                st.markdown(
                    tr(tr('#### Top 5 Customer States')
                    if customer_measure else tr('#### Top 5 States by Orders'))
                )
                if not known_total:
                    st.info(tr('No known customer locations in this period.'))
                else:
                    for _, state_row in top_states.head(5).iterrows():
                        st.markdown(
                            tr(f"**{html.escape(str(state_row['state']))}**"
                            f"<span style='float:right'>{state_row[percent_column]:.1f}% "
                            f"· {int(state_row[count_column]):,} {html.escape(count_label)}</span>"),
                            unsafe_allow_html=True,
                        )
                        st.progress(float(state_row[percent_column]) / 100)
        st.caption(tr('Revenue excludes cancelled orders. Gross profit = revenue minus recorded product costs; excludes other expenses.'))

elif page=='Products':
    from products_ui import render_products
    render_products(on_change=refresh)

elif page=='Customers':
    render_customer_management()
    with st.expander(tr('Repeat Customer Insights'), expanded=False):
        render_repeat_customer_insights(orders, items, customers, 'customer_repeat_insights')

elif page=='Order Management':
    from order_management import render_order_management
    render_order_management()

elif page=='Payments':
    render_payment_tracking()

elif page=='Deadline Calendar':
    render_deadline_calendar(orders)

elif page=='Production Board':
    st.title(tr('Production Tracking'))
    st.caption(tr('Move an order to its next production stage using Order Management.'))
    calendar_orders = prepare_deadline_orders(orders, datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date())
    st.subheader(tr('Production stages'))
    cols=st.columns(5)
    stages=['Pending','Confirmed','Preparing','Ready','Completed']
    for col,stage in zip(cols,stages):
        with col:
            st.markdown(tr(f'#### {stage}'))
            for _,r in calendar_orders[calendar_orders.status==stage].iterrows():
                with st.container(border=True):
                    st.markdown(tr(f"**Order #{int(r.id)}**"))
                    st.caption(tr(r.customer))
                    st.write(f"Due: {r['calendar_date'] if r['calendar_date'] is not None else 'Unassigned'}")
                    st.write(money(r.revenue))
    overdue=calendar_orders[calendar_orders['deadline_state']=='Overdue']
    if not overdue.empty:st.error(tr(f'{len(overdue)} orders are past their deadline.'))

elif page in ('Sales Analytics', 'Profitability Analysis', 'Customer Insights', 'Long-Term Trends'):
    if page != 'Sales Analytics':
        filtered_orders, analytics_mode, analytics_start, analytics_end = sales_date_filter(orders, 'analytics_sales', return_period=True)
    if page == 'Sales Analytics':
        from sales_analytics_ui import render_sales_analytics
        render_sales_analytics(d, owner_authorized=authorized)
    elif page == 'Profitability Analysis':
        render_bi_requirements(orders, items, analytics_start, analytics_end, view='profitability')
    elif page == 'Long-Term Trends':
        render_long_term_profitability(orders, items, analytics_start, analytics_end)
    else:
        st.metric(tr('Total Customers'), len(customers))
        render_repeat_customer_insights(orders, items, customers, 'analytics_repeat_insights', analytics_start, analytics_end)

elif page == 'Messages':
    from customer_messages_ui import render_messages
    render_messages(navigate_to)

elif page == 'Data Import':
    from data_import import render_data_import, render_import_cleanup
    st.title(tr('Data Import'))
    tab_sheets, tab_import, tab_cleanup, tab_legacy = st.tabs([tr('Google Sheets Sync'), tr('Import One Master File'), tr('Remove Old Imported Data'), tr('Supabase import / refresh')])
    with tab_sheets:
        render_google_sheets_sync()
    with tab_import:
        render_data_import()
    with tab_cleanup:
        render_import_cleanup()

    with tab_legacy:
        if st.button(tr('Refresh data'), key='settings_refresh_data', type='primary'):
            refresh()
        st.divider()
        st.subheader(tr('Move existing records from Supabase'))
        st.caption(
            tr('Imports your existing products, customers, orders, order items and payments '
            'into this local database once. This does not delete the Supabase records.')
        )
        import_confirmed = st.checkbox(
            tr('I understand this will copy Supabase business records into this computer’s SQLite database.'),
            key='sqlite_supabase_migration_confirm',
        )
        if st.button(
            tr('Import Supabase records into SQLite'),
            key='sqlite_supabase_migration',
            disabled=not import_confirmed,
        ):
            try:
                from sqlite_db import import_supabase_records
                migrated = import_supabase_records()
                st.cache_data.clear()
                st.success(
                    tr('Import completed: ' + ', '.join(
                        f'{count} {table}' for table, count in migrated.items()
                    ))
                )
                st.rerun()
            except Exception as exc:
                st.error(tr(f'Could not import Supabase records: {exc}'))

elif page=='Reports':
    st.title(tr('Reports & Export'))
    if orders.empty:st.info(tr('No data to export.'))
    else:
        start=st.date_input(tr('From'),value=date.today()-timedelta(days=90), format=date_input_format())
        end=st.date_input(tr('To'),value=date.today(), format=date_input_format())
        dates=pd.to_datetime(orders.ordered_at).dt.date
        report=orders[(dates>=start)&(dates<=end)]
        st.metric(tr('Orders in period'),len(report))
        st.dataframe(style_table(report[['id','customer','ordered_at','due_date','status','revenue','cost','profit','paid','balance']]),hide_index=True,use_container_width=True)
        st.download_button(tr('Download CSV'),report.to_csv(index=False).encode('utf-8-sig'),file_name='bizmar_orders.csv',mime='text/csv')

elif page == 'Settings':
    from settings_ui import render_settings
    from data_import import render_data_import, render_import_cleanup
    with st.container(key='bizmar_settings'):
        render_settings(sign_out_email, local_auth=LOCAL_AUTH, alert_renderer=render_alert_settings,
                        import_renderer=lambda: (render_data_import(), render_import_cleanup()))

elif page == 'Account Settings':
    st.title(tr('Account Settings'))

elif page == 'Notifications':
    from notifications_ui import render_notifications
    render_notifications(_open_notified_order)
    with st.expander(tr('Business alerts and reminders'),expanded=False):
        render_production_alerts(orders, items, products, navigate_to)

elif page in ('Profile', 'Edit Profile'):
    if st.session_state.pop('profile_saved', False):
        st.success(tr('Profile saved!'))
    if avatar:
        st.image(avatar, width=85)
    else:
        st.caption(tr('Owner profile'))
    st.markdown(tr(f'**{profile_label}**'))
    st.caption(tr('Business Owner · ' + profile['email']))
    with st.form('owner_profile_form'):
        display_name = st.text_input(tr('Display name'), value=profile.get('display_name') or '')
        business_name = st.text_input(tr('Business name'), value=profile.get('business_name') or '')
        phone = st.text_input(tr('Phone'), value=profile.get('phone') or '')
        photo = st.file_uploader(tr('Profile picture (max 3 MB)'), type=['jpg', 'jpeg', 'png', 'webp'])
        saved = st.form_submit_button(tr('Save Profile'), type='primary', use_container_width=True)
    if saved:
        if not display_name.strip() or not business_name.strip():
            st.warning(tr('Display name and business name are required.'))
        else:
            try:
                save_profile(display_name, business_name, phone, photo=photo)
                st.session_state.profile_saved = True
                st.rerun()
            except Exception as exc:
                st.error(tr(f'Unable to save profile: {exc}'))
    if profile.get('avatar_path') and st.button(tr('Remove profile photo'), key='remove_profile_photo'):
        try:
            remove_avatar()
            st.rerun()
        except Exception as exc:
            st.error(tr(f'Unable to remove photo: {exc}'))

