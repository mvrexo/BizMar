from display_preferences import option_labels
"""Four-stage Quick Order Entry; existing SQLite save and payment handlers only."""
from display_preferences import tr
from display_preferences import date_input_format
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
import sqlite_db
from order_management import _money, _init_order_line, _set_line_price

STAGES = ['Customer', 'Products', 'Fulfilment', 'Review & Save']


def matching_customer(customers, phone):
    raw = str(phone).strip()
    normalized = sqlite_db.normalize_customer_phone(raw) or raw
    return next((row for row in sorted(customers, key=lambda row: row['id'])
                 if row.get('normalized_phone') == normalized or row.get('phone') == raw), None)


def save_order_once(state, token, customer, order, items):
    """Session-local replay guard, not a durable cross-process idempotency key."""
    results = state.setdefault('qo_saved_results', {})
    if token in results:
        return results[token]
    if state.get('qo_saving'):
        raise ValueError('An order save is already in progress.')
    state['qo_saving'] = True
    try:
        saved = sqlite_db.create_order(customer, order, items)
        results[token] = saved
        return saved
    finally:
        state['qo_saving'] = False


def reset_quick_order():
    token = st.session_state.get('qo_token')
    if token:
        for key in list(st.session_state):
            if key.startswith(f'om_add_{token}_'):
                del st.session_state[key]
    for key in ('qo_saved_order_id', 'qo_show_payment', 'quick_payment_saved_order'):
        st.session_state.pop(key, None)
    st.session_state['qo_token'] = uuid4().hex
    st.session_state['qo_stage'] = 'Customer'


def render_quick_order(payment_renderer=None):
    from display_preferences import date_input_format
    st.subheader(tr('Quick Order Entry'))
    state = st.session_state
    state.setdefault('qo_token', uuid4().hex)
    state.setdefault('qo_stage', 'Customer')
    scope = 'om_add_' + state['qo_token']
    # Keep keyed drafts alive while a different stage or primary page is shown.
    for key in list(state):
        if key.startswith(scope + '_') and not key.endswith(('_next', '_save', '_add_line', '_remove_line')):
            state[key] = state[key]
    if state.get('qo_saved_order_id') is not None:
        saved_id = state['qo_saved_order_id']
        details = sqlite_db.order_details(saved_id)
        if details is None:
            st.warning(tr('The saved order is no longer available.'))
        else:
            st.success(tr(f"Order {details['order']['order_code']} saved successfully. Total: {_money(details['order']['total_amount'])}"))
            if st.button(tr('Record Payment'), key='qo_record_payment'):
                state['qo_show_payment'] = True
            if state.get('qo_show_payment'):
                if payment_renderer is not None:
                    payment_renderer(order_id=saved_id)
                else:
                    st.info(tr('Payment Tracking is available from Orders > Payments.'))
        if st.button(tr('Start New Order'), key='qo_start_new'):
            reset_quick_order(); st.rerun()
        return
    customers = sqlite_db.all_rows('customers')
    products = [row for row in sqlite_db.all_rows('products') if row['active']]
    by_id = {int(row['id']): row for row in products}
    today = datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date()
    state.setdefault(scope + '_customer_id', None)
    state.setdefault(scope + '_line_count', 1)
    state.setdefault(scope + '_order_date', today)
    state.setdefault(scope + '_fulfilment_date', today + timedelta(days=3))
    state.setdefault(scope + '_fulfilment_method', 'Pickup')
    from settings_store import runtime
    state[scope + '_status'] = 'Pending'
    state.setdefault(scope + '_notes', '')
    state.setdefault(scope + '_address', '')
    for index in range(state[scope + '_line_count']):
        product_id = state.get(f'{scope}_product_{index}')
        if product_id is None and products:
            product_id = int(products[0]['id'])
        product = by_id.get(product_id)
        _init_order_line(scope, index, product_id, 1, product['price'] if product else 0)
    state['qo_stage_widget'] = state['qo_stage']
    def choose_stage():
        state['qo_stage'] = state['qo_stage_widget']
    st.radio(tr('Order entry stage'), STAGES, horizontal=True, key='qo_stage_widget', on_change=choose_stage)
    stage = state['qo_stage']
    selected_id = state.get(scope + '_customer_id')
    selected = next((row for row in customers if row['id'] == selected_id), None)
    if stage == 'Customer':
        labels = {row['id']: f"{row.get('name') or row.get('full_name') or 'Unnamed'} - {row.get('phone') or row.get('phone_number') or 'No phone'} (ID {row['id']})" for row in customers}
        if selected_id is not None and selected_id not in labels:
            state[scope + '_customer_id'] = None
        st.selectbox(tr('Customer'), options=[None, *labels], format_func=lambda identity: 'Add new customer' if identity is None else labels[identity], key=scope + '_customer_id')
        selected_id = state[scope + '_customer_id']
        selected = next((row for row in customers if row['id'] == selected_id), None)
        if selected:
            st.caption(tr('Saved customer details will be reused using the existing phone-matching rule.'))
            st.write(selected.get('name') or selected.get('full_name'))
            st.caption(tr(selected.get('phone') or selected.get('phone_number') or 'Phone unavailable'))
        else:
            st.text_input(tr('Customer name *'), key=scope + '_customer_name')
            st.text_input(tr('Phone number *'), key=scope + '_phone')
            match = matching_customer(customers, state.get(scope + '_phone', '')) if state.get(scope + '_phone', '').strip() else None
            if match:
                st.warning(tr(f"This phone matches existing customer ID {match['id']}. Select that customer above to reuse the record."))
    elif stage == 'Products':
        if not products:
            st.warning(tr('Add or activate a product in Products before saving an order.'))
        for index in range(state[scope + '_line_count']):
            with st.container(border=True):
                left, middle, right = st.columns([3, 1, 1.5])
                left.selectbox(tr(f'Product {index+1}'), list(by_id), format_func=lambda identity: by_id[identity]['name'],
                               key=f'{scope}_product_{index}', on_change=_set_line_price, args=(scope,index,by_id), disabled=not products)
                middle.number_input(tr('Quantity'), min_value=1, step=1, key=f'{scope}_quantity_{index}')
                right.number_input(tr('Unit price (RM)'), min_value=0.0, step=0.5, format='%.2f', key=f'{scope}_price_{index}')
                st.caption(tr('Subtotal: ' + _money(state[f'{scope}_quantity_{index}'] * state[f'{scope}_price_{index}'])))
        add, remove = st.columns(2)
        if add.button(tr('Add product'), key=scope + '_add_line'):
            state[scope + '_line_count'] += 1; st.rerun()
        if state[scope + '_line_count'] > 1 and remove.button(tr('Remove last product'), key=scope + '_remove_line'):
            index = state[scope + '_line_count'] - 1
            for suffix in ('product','quantity','price','source_item'):
                state.pop(f'{scope}_{suffix}_{index}',None)
            state[scope + '_line_count'] -= 1; st.rerun()
    elif stage == 'Fulfilment':
        st.date_input(tr('Pickup / delivery date *'), key=scope + '_fulfilment_date', format=date_input_format())
        with st.expander(tr('Advanced Details')):
            st.selectbox(tr('Fulfilment method'), ['Pickup','Delivery'], key=scope + '_fulfilment_method', format_func=option_labels(['Pickup','Delivery']))
            st.date_input(tr('Order date'), key=scope + '_order_date', format=date_input_format())
            st.caption(tr('New orders start as Pending. Manage completion and cancellation in Order Details.'))
            if selected is None:
                st.text_input(tr('Address (optional)'), key=scope + '_address')
            st.text_area(tr('Additional notes'), key=scope + '_notes')
    if selected:
        customer = dict(name=selected.get('name') or selected.get('full_name') or '',
                        phone=selected.get('phone') or selected.get('phone_number') or '', address=selected.get('address') or '')
    else:
        customer = dict(name=state.get(scope + '_customer_name',''), phone=state.get(scope + '_phone',''), address=state.get(scope + '_address',''))
    lines=[]
    for index in range(state[scope + '_line_count']):
        product = by_id.get(state.get(f'{scope}_product_{index}'))
        if product:
            quantity=int(state[f'{scope}_quantity_{index}']); price=float(state[f'{scope}_price_{index}'])
            lines.append(dict(product_id=int(product['id']),product_name=product['name'],quantity=quantity,
                              unit_price=price,unit_cost=float(product['unit_cost']),subtotal=quantity*price))
    order_date=state[scope + '_order_date'];due=state[scope + '_fulfilment_date']
    def errors(through):
        problems=[]
        if not customer['name'].strip() or not customer['phone'].strip():
            problems.append('Enter a customer name and phone number, or select an existing customer.')
        match=matching_customer(customers,customer['phone']) if customer['phone'].strip() else None
        if selected_id is not None and (selected is None or match is None or match['id'] != selected_id):
            problems.append('The selected customer cannot be resolved by the existing phone rule. Review their details in Customers.')
        elif selected_id is None and match is not None:
            problems.append('This phone already belongs to an existing customer. Select that customer to avoid duplicate entry.')
        if through>=1:
            if len(lines)!=state[scope + '_line_count'] or not lines:
                problems.append('Select an available product for every line.')
            if any(line['unit_price']<=0 or line['quantity']<1 for line in lines):
                problems.append('Every product needs quantity at least 1 and a selling price greater than RM 0.00.')
        if through>=2 and (due is None or order_date is None or due<order_date):
            problems.append('Choose a fulfilment date on or after the order date.')
        return problems
    if stage in ('Products','Review & Save'):
        st.markdown(tr('**Order total: ' + _money(sum(line['subtotal'] for line in lines)) + '**'))
    if stage == 'Review & Save':
        st.write('Customer: ' + customer['name'])
        st.caption(tr(customer['phone']))
        st.write('Fulfilment: ' + (due.isoformat() if due else 'Required'))
        st.dataframe(pd.DataFrame(lines).reindex(columns=['product_name','quantity','unit_price','subtotal']).rename(
            columns={'product_name':'Product','quantity':'Quantity','unit_price':'Unit price (RM)','subtotal':'Subtotal (RM)'}),hide_index=True,use_container_width=True)
        st.caption(tr('Use the stage selector to correct details. Payments are recorded separately after saving; no payment status is set manually.'))
        problems=errors(3)
        for problem in problems:st.warning(tr(problem))
        if st.button(tr('Save Order'), type='primary', key=scope + '_save', disabled=bool(problems)):
            values=dict(ordered_at=datetime.combine(order_date,datetime.min.time(),tzinfo=ZoneInfo('Asia/Kuala_Lumpur')).isoformat(timespec='seconds'),
                        due_date=due.isoformat(),fulfilment_date=due.isoformat(),fulfilment_method=state[scope + '_fulfilment_method'],
                        status=state[scope + '_status'],notes=state[scope + '_notes'].strip())
            try:
                saved=save_order_once(state,state['qo_token'],customer,values,lines)
                state['qo_saved_order_id']=saved['id']
                st.cache_data.clear();st.rerun()
            except Exception as exc:
                st.error(tr(f'Unable to save order: {exc}'))
    else:
        if st.button(tr('Continue'), type='primary', key=scope + '_next'):
            problems=errors(STAGES.index(stage))
            if problems:
                for problem in problems:st.error(tr(problem))
            else:
                state['qo_stage']=STAGES[STAGES.index(stage)+1];st.rerun()
    if st.button(tr('Cancel / Start New Order'), key='qo_cancel'):
        reset_quick_order();st.rerun()
