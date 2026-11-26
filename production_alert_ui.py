from display_preferences import tr
from display_preferences import style_table
"""Native Streamlit presentation for FR13; no database or authentication imports."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from bi_analytics import MALAYSIA_TIMEZONE
from deadline_calendar import prepare_deadline_orders
from production_alerts import (
    load_settings, save_settings, aging_alerts, demand_alerts, margin_alerts,
)


def render_alert_settings():
    values, warning = load_settings()
    from settings_store import runtime
    owner_values = runtime()
    if st.session_state.get('bizmar_preferences'):
        values.update({key: owner_values[key] for key in values})
    st.subheader(tr('Production alert settings'))
    st.caption(tr('Production thresholds are saved for the authenticated owner in the existing business database.'))
    if warning:
        st.warning(tr(warning))
    with st.form('production_alert_settings_form'):
        left, right = st.columns(2)
        with left:
            hours = st.number_input(tr('Order aging threshold (hours)'), min_value=1.0, max_value=8760.0,
                                    value=float(values['aging_hours']), key='production_alert_aging_hours')
            units = st.number_input(tr('High demand threshold (units)'), min_value=1, max_value=1000000,
                                    value=int(values['demand_units']), key='production_alert_demand_units')
        with right:
            days = st.number_input(tr('High demand window (calendar days)'), min_value=1, max_value=366,
                                   value=int(values['demand_days']), key='production_alert_demand_days')
            margin = st.number_input(tr('Low gross margin threshold (%)'), min_value=0.0, max_value=100.0,
                                     value=float(values['margin_percent']), key='production_alert_margin_percent')
        st.caption(tr('Alerts use strictly older than, above demand, and below margin thresholds. Demand includes today and the preceding window days.'))
        saved = st.form_submit_button(tr('Save alert settings'), type='primary')
    if saved:
        try:
            thresholds = dict(aging_hours=hours, demand_units=units, demand_days=days, margin_percent=margin)
            if st.session_state.get('authenticated'):
                from settings_store import load, save
                updated = {**load(), **thresholds}
                save(updated)
                st.session_state.bizmar_preferences = updated
            else:
                # Retain the standalone threshold editor's existing local workflow.
                save_settings(thresholds)
        except (OSError, ValueError):
            st.error(tr('Alert settings could not be saved. Check the values and local folder permissions; existing configuration was not replaced unless the save completed.'))
        else:
            st.success(tr('Alert settings saved for future reruns and restarts.'))


def deadline_notifications(orders, today, reminder_days=2):
    """Preserve Notifications' existing saved due_date and inclusive two-day window.

    The calendar's date/status normalization is reused, without changing the
    Production Board's separate fulfilment-date preference.
    """
    source = orders.copy()
    source['fulfilment_date'] = source.get('due_date', pd.Series(index=source.index, dtype=object))
    prepared = prepare_deadline_orders(source, today)
    overdue = prepared.loc[prepared['deadline_state'].eq('Overdue')]
    soon = prepared.loc[prepared['deadline_state'].isin(['Due today', 'Upcoming'])].copy()
    soon = soon.loc[soon['calendar_date'].map(lambda value: value <= today + timedelta(days=reminder_days))]
    return overdue, soon


def _table(frame, columns, money=()):
    from display_preferences import style_table
    shown = frame.reindex(columns=list(columns)).copy()
    for name in money:
        shown[name] = shown[name].map(lambda value: f'RM {value:,.2f}')
    st.dataframe(style_table(shown.rename(columns=columns)), hide_index=True, use_container_width=True)


def render_production_alerts(orders, items, products, navigate, now=None):
    st.title(tr('Notifications & Alerts'))
    settings, warning = load_settings()
    from settings_store import runtime
    owner_values = runtime()
    if st.session_state.get('bizmar_preferences'):
        settings.update({key: owner_values[key] for key in settings})
    if warning:
        st.warning(tr(warning))
    now = now if now is not None else datetime.now(ZoneInfo(MALAYSIA_TIMEZONE))
    today = now.astimezone(ZoneInfo(MALAYSIA_TIMEZONE)).date()
    aged, unknown_age = aging_alerts(orders, now, settings['aging_hours'])
    demand = demand_alerts(orders, items, today, settings['demand_days'], settings['demand_units'])
    margins, undefined = margin_alerts(products, settings['margin_percent'])
    from settings_store import runtime
    preferences = runtime()
    overdue, soon = deadline_notifications(orders, today, preferences['reminder_days'])
    st.caption(tr('Live, read-only business alerts. No notification records or messages are created. Business data uses the existing refresh/cache policy.'))
    st.subheader(tr(f'Order Aging ({len(aged)})'))
    st.caption(tr(f"Active orders strictly older than {settings['aging_hours']:g} elapsed hours. Saved creation times are displayed in Malaysia time."))
    if aged.empty:
        st.success(tr('No active orders exceed the aging threshold.'))
    else:
        aged = aged.copy()
        aged['created_local'] = aged['created_local'].map(lambda value: value.strftime('%d %b %Y, %H:%M %Z'))
        aged['age_hours'] = aged['age_hours'].round(2)
        _table(aged, {'id': 'Order ID', 'order_code': 'Reference', 'customer': 'Customer',
                     'created_local': 'Created (Malaysia)', 'age_hours': 'Age (hours)',
                     'status': 'Status', 'due_date': 'Saved deadline'})
    if not unknown_age.empty:
        st.warning(tr(f'{len(unknown_age)} active order(s) cannot be assessed: creation timestamp is missing, invalid or date-only. No creation time was inferred.'))
        with st.expander(tr('Orders with unassessable creation times')):
            _table(unknown_age, {'id': 'Order ID', 'order_code': 'Reference', 'customer': 'Customer', 'status': 'Status'})
    st.subheader(tr(f'High Demand ({len(demand)})'))
    start = today - timedelta(days=settings['demand_days'] - 1)
    st.caption(tr(f"Order demand, not inventory shortage: strictly more than {settings['demand_units']} units, {start:%d %b %Y} to {today:%d %b %Y}, inclusive Malaysia dates. All non-cancelled orders, including pending and completed."))
    if demand.empty:
        st.success(tr('No products exceed the demand threshold in this window.'))
    else:
        _table(demand, {'product_key': 'Product reference', 'product_name': 'Product', 'ordered_units': 'Ordered units'})
    st.subheader(tr(f'Low Profit Margin ({len(margins)})'))
    st.caption(tr(f"Current active catalogue gross margin strictly below {settings['margin_percent']:g}%. This is not historical realized margin or net profit."))
    if margins.empty:
        st.success(tr('No assessable active products fall below the gross margin threshold.'))
    else:
        margins = margins.copy()
        margins['gross_margin_percent'] = margins['gross_margin_percent'].map(lambda value: f'{value:.2f}%')
        _table(margins, {'id': 'Product ID', 'name': 'Product', 'price': 'Selling price',
                        'unit_cost': 'Unit cost', 'gross_margin_percent': 'Gross margin'}, money=('price', 'unit_cost'))
    if not undefined.empty:
        st.warning(tr(f'{len(undefined)} active product(s) have undefined margins: zero/invalid selling price or missing/invalid cost.'))
        with st.expander(tr('Products with undefined margins')):
            _table(undefined, {'id': 'Product ID', 'name': 'Product', 'price': 'Selling price', 'unit_cost': 'Unit cost'})
    if preferences['deadlines']:
        st.subheader(tr(f'Deadline Alerts ({len(overdue) + len(soon)})'))
        st.caption(tr(f"Active saved due dates, overdue or within {preferences['reminder_days']} days."))
        if overdue.empty and soon.empty:
            st.success(tr('No urgent production deadlines.'))
        for frame, label in ((overdue, 'Overdue'), (soon, f"Due within {preferences['reminder_days']} days")):
            if not frame.empty:
                st.warning(tr(f'{label}: {len(frame)} order(s)'))
                _table(frame, {'calendar_reference': 'Reference', 'calendar_customer': 'Customer',
                               'calendar_date': 'Deadline', 'status': 'Status'})
    if preferences['pending_orders']:
        pending = orders.loc[orders['status'].eq('Pending')]
        st.subheader(tr(f'Pending Orders ({len(pending)})'))
        if pending.empty:
            st.success(tr('No pending orders.'))
        else:
            _table(pending, {'id': 'Order ID', 'customer': 'Customer', 'due_date': 'Deadline', 'status': 'Status'})
    if preferences['overdue_payments']:
        due = pd.to_datetime(orders['due_date'], errors='coerce').dt.date
        balance = pd.to_numeric(orders.get('balance', pd.Series(0, index=orders.index)), errors='coerce').fillna(0)
        unpaid = orders.loc[due.map(lambda value: pd.notna(value) and value < today) & balance.gt(0) & orders['status'].ne('Cancelled')]
        st.subheader(tr(f'Overdue Payments ({len(unpaid)})'))
        st.caption(tr('Outstanding balance on non-cancelled orders past their saved due date; no separate payment due date exists.'))
        if unpaid.empty:
            st.success(tr('No overdue balances on dated orders.'))
        else:
            _table(unpaid, {'id': 'Order ID', 'customer': 'Customer', 'due_date': 'Deadline', 'balance': 'Outstanding'}, money=('balance',))
    for column, label, target, key in zip(st.columns(3),
            ('Open Order Management', 'Open Products', 'Configure alerts'),
            ('Order Management', 'Products', 'Settings'),
            ('alerts_open_orders', 'alerts_open_products', 'alerts_open_settings')):
        with column:
            if st.button(tr(label), key=key, use_container_width=True):
                navigate(target)
                st.rerun()
