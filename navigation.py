"""Five primary menus with legacy route compatibility. No database/auth imports."""
import re
from display_preferences import tr

PRIMARY_SECTIONS = {
    'Dashboard': [('Business overview', 'Overview')],
    'Orders': [('All Orders', 'Order Management'),
               ('Customers', 'Customers'), ('Deadline Calendar', 'Deadline Calendar'),
               ('Production Tracking', 'Production Board'), ('Payments', 'Payments'), ('Messages', 'Messages')],
    'Products': [('Product catalogue', 'Products')],
    'Analytics': [('Sales Analytics', 'Sales Analytics'), ('Profitability Analysis', 'Profitability Analysis'),
                  ('Customer Insights', 'Customer Insights'), ('Long-Term Trends', 'Long-Term Trends'), ('Reports', 'Reports')],
    'Settings': [('Settings', 'Settings'), ('Data Import', 'Data Import')],
}
PRIMARY_ICONS = dict(Dashboard=':material/home:', Orders=':material/receipt_long:',
                     Products=':material/inventory_2:', Analytics=':material/analytics:', Settings=':material/settings:')
ROUTE_LABELS = {route: label for entries in PRIMARY_SECTIONS.values() for label, route in entries}
ROUTE_LABELS.update(Overview='Dashboard', Notifications='Notifications & Alerts',
                    Profile='Business Profile', **{'Edit Profile': 'Business Profile'})
ROUTE_LABELS.update({'Account Settings': 'Account Settings', 'Data Import': 'Data Management'})
ALL_ROUTES = [*ROUTE_LABELS, 'Logout']
# Settings is both a legacy alert route and a new primary menu label. Legacy
# navigate_to('Settings') keeps its exact meaning; primary buttons use an explicit API.


def primary_for(route):
    if route in ('Profile', 'Edit Profile'):
        return None
    return next((primary for primary, entries in PRIMARY_SECTIONS.items()
                 if route in [target for _, target in entries]), None)


def initialize_navigation(state):
    if state.get('nour_current_page') == 'New Order':
        state['nour_current_page'] = 'Order Management'
    if state.get('nour_current_page') == 'Logout':
        state['nour_current_page'] = 'Account Settings'
    if state.get('nour_current_page') not in ROUTE_LABELS:
        state['nour_current_page'] = 'Overview'
    if not isinstance(state.get('nour_page_history'), list):
        state['nour_page_history'] = []
    if not isinstance(state.get('bizmar_last_sections'), dict):
        state['bizmar_last_sections'] = {}
    primary = primary_for(state['nour_current_page'])
    if primary:
        state['bizmar_last_sections'][primary] = state['nour_current_page']
        state['bizmar_last_primary'] = primary


def navigate(state, target):
    initialize_navigation(state)
    if target == 'New Order':
        target = 'Order Management'
    if target == 'Logout':
        target = 'Account Settings'
    if target == 'Dashboard':
        target = 'Overview'
    if target not in ROUTE_LABELS:
        raise ValueError('Unknown navigation route.')
    current = state['nour_current_page']
    if current != target:
        state['nour_page_history'].append(current)
        state['nour_current_page'] = target
    initialize_navigation(state)


def navigate_primary(state, primary):
    initialize_navigation(state)
    entries = PRIMARY_SECTIONS[primary]
    remembered = state['bizmar_last_sections'].get(primary)
    targets = [target for _, target in entries]
    navigate(state, remembered if remembered in targets else targets[0])


def go_back(state):
    initialize_navigation(state)
    history = state['nour_page_history']
    target = history.pop() if history else 'Overview'
    if target == 'New Order':
        target = 'Order Management'
    state['nour_current_page'] = target if target in ROUTE_LABELS else 'Overview'
    initialize_navigation(state)


def retain_widget_context(state):
    """Detach selected widget values from cleanup before rendering any widgets.

    No shadow copies of authentication tokens or credentials. Button events are
    never restored; existing save/cancel callbacks retain control of form state.
    """
    exact = {'om_form_mode', 'om_edit_id', 'om_form_token', 'om_selected_order', 'om_search',
             'om_status_filter', 'om_payment_filter', 'om_sort', 'om_date_from', 'om_date_to',
             'selected_customer_profile', 'customer_edit_id', 'customer_add_open', 'customer_search',
             'customer_category_filter', 'restore_customer_id', 'product_view', 'catalogue_selected_id',
             'bizmar_calendar_month', 'bizmar_calendar_date', 'long_term_profitability_aggregation'}
    fields = re.compile(r'^om_(?:add_[0-9a-f]+|edit_\d+_[0-9a-f]+)_(?:customer_id|customer_name|phone|address|order_date|fulfilment_date|fulfilment_method|status|notes|line_count|(?:product|quantity|price|source_item)_\d+)$')
    filters = re.compile(r'^(?:overview_sales|analytics_sales)_(?:mode|from|to|applied_from|applied_to|range_type|selected_date)$|^(?:analytics_repeat_insights|customer_repeat_insights)_(?:from|to|history_customer)$')
    for key in list(state):
        if key in exact or fields.fullmatch(key) or filters.fullmatch(key):
            state[key] = state[key]


def render_primary_navigation():
    import streamlit as st
    initialize_navigation(st.session_state)
    retain_widget_context(st.session_state)
    route = st.session_state['nour_current_page']
    active = None if route in ('Profile', 'Edit Profile') else (
        primary_for(route) or st.session_state.get('bizmar_last_primary', 'Dashboard')
    )
    with st.sidebar:
        for index, primary in enumerate(PRIMARY_SECTIONS):
            if st.button(tr(primary), key=f'nour_nav_PRIMARY_{index}', icon=PRIMARY_ICONS[primary],
                         type='primary' if active == primary else 'secondary', use_container_width=True):
                navigate_primary(st.session_state, primary)
                st.rerun()


def render_section_navigation():
    import streamlit as st
    route = st.session_state['nour_current_page']
    if route in ('Profile', 'Edit Profile'):
        return
    primary = primary_for(route)
    if not primary or len(PRIMARY_SECTIONS[primary]) == 1:
        return
    entries = PRIMARY_SECTIONS[primary]
    labels = dict((target, label) for label, target in entries)
    key = f'bizmar_section_widget_{primary}'
    st.session_state[key] = route
    def choose():
        navigate(st.session_state, st.session_state[key])
    with st.container(border=True, key='bizmar_section_navigation'):
        st.radio(tr(f'{primary} sections'), options=list(labels), format_func=lambda target: tr(labels[target]),
                 key=key, horizontal=True, on_change=choose)
