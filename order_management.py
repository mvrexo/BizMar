from display_preferences import option_labels
from display_preferences import tr
from display_preferences import localized_dialog
from display_preferences import style_table
"""Order management UI backed by the shared SQLite database."""
from display_preferences import date_input_format
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4
from pathlib import Path
from html import escape
import pandas as pd
import streamlit as st

import sqlite_db
import orders_store as store
from malaysian_states import STATES, CHOICES as STATE_CHOICES, display as state_label, destination
from ui_theme import order_section_title, order_status_style

STATUSES = list(store.STATUSES)
PAYMENT_STATUSES = ['Unpaid', 'Partial', 'Paid']
FULFILMENT_METHODS = ['Pickup', 'Delivery']


def _money(value):
    return f'RM {float(value or 0):,.2f}'


def _set_line_price(scope, index, products_by_id):
    product_id = st.session_state.get(f'{scope}_product_{index}')
    product = products_by_id.get(product_id)
    if product:
        st.session_state[f'{scope}_price_{index}'] = float(product['price'])
        # Selecting a replacement product creates a new cost snapshot on save.
        st.session_state[f'{scope}_source_item_{index}'] = None


def _init_order_line(scope, index, product_id=None, quantity=1, price=None):
    st.session_state.setdefault(f'{scope}_product_{index}', product_id)
    st.session_state.setdefault(f'{scope}_quantity_{index}', max(1, int(quantity)))
    if price is not None:
        st.session_state.setdefault(f'{scope}_price_{index}', float(price))


def _clear_order_form():
    st.session_state['om_form_mode'] = None
    st.session_state['om_edit_id'] = None
    st.session_state['om_form_token'] = None


def _remove_order_item(scope, index):
    """Shift the complete draft snapshot, retaining historical source item IDs."""
    count = st.session_state[f'{scope}_line_count']
    for position in range(index, count - 1):
        for suffix in ('product', 'quantity', 'price', 'source_item'):
            st.session_state[f'{scope}_{suffix}_{position}'] = st.session_state.get(f'{scope}_{suffix}_{position + 1}')
    for suffix in ('product', 'quantity', 'price', 'source_item'):
        st.session_state.pop(f'{scope}_{suffix}_{count - 1}', None)
    st.session_state[f'{scope}_line_count'] = count - 1


@localized_dialog('Order editor', width='large', on_dismiss=_clear_order_form)
def _render_order_form(edit_id=None):
    from display_preferences import style_table, tr, option_labels
    from display_preferences import date_input_format
    try:
        store.current_owner()
        details = store.details(edit_id) if edit_id is not None else None
    except PermissionError as exc:
        st.error(tr(str(exc)))
        return
    except Exception:
        st.error(tr('The order editor could not load its data. Please retry.'))
        return
    if edit_id is not None and details is None:
        st.error(tr('This order could not be found.'))
        st.session_state['om_form_mode'] = None
        return

    if details and details['order']['status'] != 'Pending':
        st.warning(tr('Only Pending orders can be edited.'))
        return
    form_token = st.session_state.get('om_form_token')
    if not form_token:
        form_token = uuid4().hex
        st.session_state['om_form_token'] = form_token
    scope = f'om_edit_{edit_id}_{form_token}' if edit_id is not None else f'om_add_{form_token}'
    order = details['order'] if details else {}
    existing_items = details['items'] if details else []
    st.session_state.setdefault(f'{scope}_version', order.get('version', 0))
    all_products = sqlite_db.all_rows('products')
    products = [product for product in all_products if product['active']]
    if details:
        editing_product_ids = {item.get('product_id') for item in existing_items}
        products.extend(
            product for product in all_products
            if not product['active'] and product['id'] in editing_product_ids
        )
    products_by_id = {int(product['id']): product for product in products}
    if details and any(item.get('product_id') not in products_by_id for item in existing_items):
        st.error(tr('A saved product is no longer in the catalogue. Editing is blocked to preserve the historical order lines.'))
        return
    if not products:
        st.warning(tr('Add or activate a product before creating an order.'))
        if st.button(tr('Cancel'), key=f'{scope}_cancel_empty'):
            _clear_order_form()
            st.rerun()
        return

    existing_count = len(existing_items)
    default_count = max(1, existing_count)
    line_count_key = f'{scope}_line_count'
    st.session_state.setdefault(line_count_key, default_count)
    line_count = int(st.session_state[line_count_key])
    for index in range(line_count):
        existing = existing_items[index] if index < existing_count else {}
        product_id = existing.get('product_id')
        if product_id not in products_by_id:
            product_id = int(products[0]['id'])
        product = products_by_id[product_id]
        st.session_state.setdefault(f'{scope}_source_item_{index}', existing.get('id'))
        _init_order_line(
            scope,
            index,
            product_id,
            existing.get('quantity', 1),
            existing.get('unit_price', product['price']),
        )

    with st.container(key='nour_order_form'):
        st.subheader(tr('Edit Order' if details else 'Add New Order'))
        st.caption(tr(f"Order ID: {order.get('order_code') or sqlite_db.next_order_code()}"))

        with st.container(border=True, key=f'{scope}_customer_card'):
            order_section_title('01', 'Customer information', 'The person behind this sweet order.')
            customers = [row for row in sqlite_db.all_rows('customers') if not row.get('archived')]
            st.selectbox(tr('Existing customer (optional)'), [None, *[row['id'] for row in customers]],
                         format_func=lambda identity: 'Enter customer details' if identity is None else next(f"{row['name']} · {row['phone']}" for row in customers if row['id']==identity),
                         key=f'{scope}_lookup', on_change=_customer_lookup, args=(scope, customers))
            customer_col, phone_col = st.columns(2)
            customer_name = customer_col.text_input(
                tr('Customer name *'),
                value=order.get('customer_name', ''),
                key=f'{scope}_customer_name',
            )
            phone = phone_col.text_input(
                tr('Phone number *'),
                value=order.get('phone_number', ''),
                key=f'{scope}_phone',
            )
            address = st.text_input(
                tr('Address (optional)'),
                value=order.get('customer_address', ''),
                key=f'{scope}_address',
            )
            customer_state = st.selectbox(tr('Customer residence state (optional)'), STATE_CHOICES,
                index=STATE_CHOICES.index(state_label(order.get('customer_state_snapshot'))),key=f'{scope}_customer_state',
                help=tr('Explicit customer residence. Used for Pickup orders; it does not set the delivery destination.'))
            order_date_default = datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date()
            try:
                order_date_default = datetime.fromisoformat(
                    str(order.get('ordered_at', ''))[:10]
                ).date()
            except ValueError:
                pass
            order_date = st.date_input(
                tr('Order date'),
                value=order_date_default,
                key=f'{scope}_order_date',
            format=date_input_format())

        with st.container(border=True, key=f'{scope}_products_card'):
            order_section_title('02', 'Order items', 'Choose products, quantities and selling prices.')
            line_totals = []
            for index in range(line_count):
                with st.container(key=f'{scope}_product_row_{index}'):
                    line_col, quantity_col, price_col, subtotal_col = st.columns([3.2, 1, 1.35, 1.5])
                    product = line_col.selectbox(
                        tr(f'Product {index + 1}'),
                        options=list(products_by_id),
                        format_func=lambda product_id: products_by_id[product_id]['name'],
                        key=f'{scope}_product_{index}',
                        on_change=_set_line_price,
                        args=(scope, index, products_by_id),
                    )
                    quantity = quantity_col.number_input(
                        tr('Quantity'),
                        min_value=1,
                        step=1,
                        key=f'{scope}_quantity_{index}',
                    )
                    price = price_col.number_input(
                        tr('Unit price (RM)'),
                        min_value=0.0,
                        step=0.5,
                        format='%.2f',
                        key=f'{scope}_price_{index}',
                    )
                    source_item_id = st.session_state.get(f'{scope}_source_item_{index}')
                    source_item = next(
                        (item for item in existing_items
                         if item['id'] == source_item_id and item['product_id'] == int(product)),
                        None,
                    )
                    unit_cost = (source_item['unit_cost'] if source_item is not None
                                 else products_by_id[int(product)]['unit_cost'])
                    subtotal = float(store.money(price) * int(quantity))
                    subtotal_col.metric(tr('Subtotal'), _money(subtotal))
                    line_totals.append({
                        'product_id': int(product),
                        'product_name': products_by_id[int(product)]['name'],
                        'quantity': int(quantity),
                        'unit_price': float(store.money(price)),
                        'unit_cost': float(unit_cost),
                        'subtotal': subtotal,
                    })
                    if source_item is not None:
                        # Transient identity: consumed by update_order, never a DB column.
                        line_totals[-1]['source_item_id'] = source_item['id']
                    if line_count > 1:
                        st.button(tr(f'Remove item {index + 1}'), key=f'{scope}_remove_item_{index}', icon=':material/delete:',
                                  on_click=_remove_order_item, args=(scope,index))
            add_col, remove_col, _ = st.columns([1.6, 1.8, 5])
            with add_col:
                if st.button(tr('＋ Add Another Product'), key=f'{scope}_add_line'):
                    st.session_state[f'{scope}_source_item_{line_count}'] = None
                    st.session_state[line_count_key] = line_count + 1
                    st.rerun()
            with remove_col:
                if line_count > 1 and st.button(tr('Remove Last Product'), key=f'{scope}_remove_line'):
                    for suffix in ('product', 'quantity', 'price', 'source_item'):
                        st.session_state.pop(f'{scope}_{suffix}_{line_count - 1}', None)
                    st.session_state[line_count_key] = line_count - 1
                    st.rerun()

        with st.container(border=True, key=f'{scope}_details_card'):
            order_section_title('03', 'Fulfillment details', 'Plan fulfilment and keep instructions together.')
            fulfillment_col, method_col, status_col = st.columns(3)
            current_due = order.get('fulfilment_date') or order.get('due_date')
            try:
                due_default = date.fromisoformat(str(current_due)[:10])
            except (TypeError, ValueError):
                due_default = datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date() + timedelta(days=3)
            fulfilment_date = fulfillment_col.date_input(
                tr('Pickup / delivery date'),
                value=due_default,
                key=f'{scope}_fulfilment_date',
            format=date_input_format())
            previous_method = order.get('fulfilment_method', 'Pickup')
            fulfilment_method = method_col.selectbox(
                tr('Fulfilment method'),
                FULFILMENT_METHODS,
                index=FULFILMENT_METHODS.index(previous_method)
                if previous_method in FULFILMENT_METHODS else 0,
                key=f'{scope}_fulfilment_method',
            )
            status_col.caption(tr('New orders start as Pending. Completion and cancellation are available in Order Details.'))
            source_col, time_col = st.columns(2)
            source = source_col.selectbox(tr('Order source'), store.SOURCES, index=store.SOURCES.index(order.get('source','Other')) if order.get('source','Other') in store.SOURCES else 4, key=f'{scope}_source')
            saved_time = None
            if order.get('fulfilment_time'):
                from datetime import time as clock_time
                saved_time = clock_time.fromisoformat(order['fulfilment_time'])
            fulfilment_time = time_col.time_input(tr('Fulfillment time (optional)'), value=saved_time, key=f'{scope}_fulfilment_time')
            delivery_address = st.text_area(tr('Delivery address (required for Delivery)'), value=order.get('delivery_address') or order.get('customer_address',''), key=f'{scope}_delivery_address') if fulfilment_method == 'Delivery' else ''
            delivery_state = st.selectbox(tr('Delivery destination state (optional)'),STATE_CHOICES,
                index=STATE_CHOICES.index(state_label(order.get('delivery_state'))),key=f'{scope}_delivery_state',
                help=tr('Destination for this order only. Kept separately from the customer residence.')) if fulfilment_method == 'Delivery' else ''
            notes = st.text_area(tr('Additional notes'), value=order.get('notes', ''), key=f'{scope}_notes')

        with st.container(border=True, key=f'{scope}_summary_card'):
            order_section_title('04', 'Order summary', 'Review your treats before saving.')
            st.dataframe(
                style_table(pd.DataFrame(line_totals)[['product_name', 'quantity', 'unit_price', 'subtotal']]),
                column_config={
                    'product_name': st.column_config.TextColumn(tr('Product')),
                    'quantity': st.column_config.NumberColumn(tr('Quantity')),
                    'unit_price': st.column_config.NumberColumn(tr('Unit price (RM)'), format='%.2f'),
                    'subtotal': st.column_config.NumberColumn(tr('Subtotal (RM)'), format='%.2f'),
                },
                hide_index=True,
                use_container_width=True,
            )
            discount_col, fee_col = st.columns(2)
            discount = discount_col.number_input(tr('Discount (RM)'), min_value=0., value=float(order.get('discount',0)), step=1., key=f'{scope}_discount')
            delivery_fee = fee_col.number_input(tr('Delivery fee (RM)'), min_value=0., value=float(order.get('delivery_fee',0)), step=1., key=f'{scope}_delivery_fee')
            product_subtotal = sum((store.money(line['subtotal']) for line in line_totals), store.money(0))
            is_google_delivery = bool(
                details
                and order.get('import_source') == 'Google Forms'
                and fulfilment_method == 'Delivery'
            )
            quote_pending = bool(details and order.get('quote_pending'))
            moving_below_free_delivery = bool(
                is_google_delivery
                and order.get('free_delivery_applied')
                and product_subtotal < store.money(100)
            )
            changing_method_to_delivery = bool(
                is_google_delivery
                and order.get('fulfilment_method') != 'Delivery'
                and product_subtotal < store.money(100)
            )
            fee_changed = bool(
                is_google_delivery
                and store.money(delivery_fee) != store.money(order.get('delivery_fee', 0))
            )
            needs_quote_confirmation = bool(
                is_google_delivery
                and product_subtotal < store.money(100)
                and (quote_pending or moving_below_free_delivery or changing_method_to_delivery or fee_changed)
            )
            confirm_rider_quote = False
            if needs_quote_confirmation:
                st.warning(tr('This order needs a rider quote. Enter the fee provided by the rider and confirm it before saving or recording payment.'))
                confirm_rider_quote = st.checkbox(
                    tr('I confirm this delivery fee was quoted by the rider.'),
                    key=f'{scope}_confirm_rider_quote',
                )
            quote_confirmation_missing = bool(
                needs_quote_confirmation and fee_changed and not confirm_rider_quote
            )
            effective_delivery_fee = delivery_fee
            if is_google_delivery and product_subtotal >= store.money(100):
                effective_delivery_fee = 0
                fee_col.caption(tr('Free delivery applies at RM 100 product subtotal.'))
            elif needs_quote_confirmation and not confirm_rider_quote:
                effective_delivery_fee = 0
                fee_col.caption(tr(f'Entered quote {_money(delivery_fee)} is not confirmed.'))
                st.caption(tr('The payable total remains pending until the rider quote is confirmed.'))
            total = product_subtotal - store.money(discount) + store.money(effective_delivery_fee)
            if not (is_google_delivery and product_subtotal < store.money(100) and (quote_pending or moving_below_free_delivery or changing_method_to_delivery) and not confirm_rider_quote):
                st.markdown(tr(f'### Grand total: {_money(total)}'))
            else:
                st.markdown(tr('### Grand total: Awaiting rider quote'))
            delivery_caption = (
                f'Delivery fee: Awaiting rider quote (entered {_money(delivery_fee)}; not confirmed)'
                if needs_quote_confirmation and not confirm_rider_quote
                else f'Delivery fee: {_money(effective_delivery_fee)}'
            )
            st.caption(tr(f"Subtotal: {_money(product_subtotal)} · Discount: {_money(discount)} · {delivery_caption}"))
            recorded_payments = sum((store.money(payment['amount']) for payment in details['payments']), store.money(0)) if details else store.money(0)
            if total >= 0:
                st.caption(tr(f'Payment status: {sqlite_db.payment_status_for_total(total, recorded_payments)} (ledger-based).'))
            st.caption(tr(f'Recorded payments: {_money(recorded_payments)} · Outstanding balance: {_money(total-recorded_payments)}'))
            acknowledge_overpayment = False
            if recorded_payments > total:
                st.warning(tr(f'This edit creates an overpayment of {_money(recorded_payments-total)}. Existing payments will be preserved; no refund will be issued.'))
                acknowledge_overpayment = st.checkbox(tr('I acknowledge the overpayment and will reconcile it separately.'), key=f'{scope}_overpayment')
            initial_payment = None
            if not details:
                amount_received = st.number_input(tr('Initial deposit / amount received (RM)'), min_value=0., value=None, step=1., key=f'{scope}_deposit', placeholder=tr('Leave blank if no money was received'))
                if amount_received is not None and amount_received > 0:
                    method = st.selectbox(tr('Payment method'), store.METHODS, key=f'{scope}_payment_method')
                    reference = st.text_input(tr('Payment reference (optional)'), key=f'{scope}_payment_reference')
                    payment_date = st.date_input(tr('Payment date'), value=datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date(),format=date_input_format(),key=f'{scope}_payment_date')
                    payment_notes = st.text_area(tr('Payment notes (optional)'),key=f'{scope}_payment_notes')
                    initial_payment = dict(amount=amount_received, method=method, reference=reference, notes=payment_notes,
                        paid_at=datetime.combine(payment_date,datetime.min.time(),ZoneInfo('Asia/Kuala_Lumpur')).isoformat())
                    st.caption(tr(f'Balance after this payment: {_money(total-store.money(amount_received))}'))

        with st.container(key=f'{scope}_save_actions'):
            save_col, cancel_col, _ = st.columns([1.5, 1, 5])
            with save_col:
                save = st.button(
                    tr('Save Changes' if details else 'Save Order'),
                    type='primary',
                    key=f'{scope}_save',
                    use_container_width=True,
                )
            with cancel_col:
                cancel = st.button(tr('Cancel'), key=f'{scope}_cancel', use_container_width=True)

        if cancel:
            _clear_order_form()
            st.rerun()
        if save:
            if not customer_name.strip() or not phone.strip():
                st.error(tr('Customer name and phone number are required.'))
                return
            if fulfilment_date < order_date:
                st.error(tr('Pickup / delivery date cannot be before the order date.'))
                return
            if quote_confirmation_missing:
                st.error(tr('Confirm the rider-provided delivery fee before saving this fee change.'))
                return
            order_values = {
                'ordered_at': datetime.combine(
                    order_date,
                    datetime.min.time(),
                    tzinfo=ZoneInfo('Asia/Kuala_Lumpur'),
                ).isoformat(timespec='seconds'),
                'due_date': fulfilment_date.isoformat(),
                'fulfilment_date': fulfilment_date.isoformat(),
                'fulfilment_method': fulfilment_method,
                'delivery_state': delivery_state,
                'source': source, 'discount': discount, 'delivery_fee': delivery_fee,
                'fulfilment_time': fulfilment_time.isoformat() if fulfilment_time else '',
                'delivery_address': delivery_address,
                'notes': notes.strip(),
            }
            if needs_quote_confirmation and confirm_rider_quote:
                order_values['confirmed_rider_quote'] = delivery_fee
            customer_values = {'name': customer_name, 'phone': phone, 'address': address, 'state':customer_state}
            try:
                if details:
                    store.save_order(customer_values, order_values, line_totals, token=form_token, order_id=edit_id, version=st.session_state[f'{scope}_version'], acknowledge_overpayment=acknowledge_overpayment)
                    st.session_state['om_flash_message'] = 'Order updated successfully.'
                else:
                    created = store.save_order(customer_values, order_values, line_totals, token=form_token, payment=initial_payment)
                    st.session_state['om_flash_message'] = f"Order {created['order_code']} saved successfully."
                st.cache_data.clear()
                _clear_order_form()
                st.rerun()
            except Exception as exc:
                st.error(tr(f'Unable to save order: {exc}'))


def _customer_lookup(scope, customers):
    identity = st.session_state.get(f'{scope}_lookup')
    customer = next((row for row in customers if row['id'] == identity), None)
    if customer:
        st.session_state[f'{scope}_customer_name'] = customer['name']
        st.session_state[f'{scope}_phone'] = customer['phone']
        st.session_state[f'{scope}_address'] = customer.get('address','')
        st.session_state[f'{scope}_customer_state'] = state_label(customer.get('state'))



def _dismiss_cancel():
    st.session_state.pop('om_cancel_target', None)


def _dismiss_details():
    st.session_state.pop('om_detail_open_id', None)


@localized_dialog('Cancel Order', on_dismiss=_dismiss_cancel)
def _confirm_cancel(order_id, reference, customer):
    st.write(f'{reference} · {customer}')
    st.warning(tr('Cancel this order? It will leave active schedules. Items and payment history will be retained. No refund will be issued automatically.'))
    reason = st.text_area(tr('Cancellation reason (optional)'), max_chars=2000, key=f'om_cancel_reason_{order_id}')
    keep, confirm = st.columns(2)
    if keep.button(tr('Keep Order'), key=f'om_keep_{order_id}', width='stretch'):
        _dismiss_cancel()
        st.rerun()
    if confirm.button(tr('Yes, Cancel Order'), type='primary', key=f'om_cancel_confirm_{order_id}', width='stretch'):
        try:
            store.transition(order_id,'Cancelled',reason)
            _dismiss_cancel()
            _changed(f'{reference} was cancelled. Payment history was preserved.')
        except (ValueError,PermissionError) as exc:
            st.error(tr(str(exc)))
        except Exception:
            st.error(tr('The cancellation could not be saved. Please retry; no partial change was committed.'))


def _changed(message):
    st.cache_data.clear()
    st.session_state['om_flash_message'] = message
    st.rerun()


def _complete_order(order_id, order_code):
    try:
        store.transition(order_id, 'Completed')
        st.session_state['om_completion_toast'] = f'{order_code} marked Completed.'
    except (ValueError, PermissionError) as exc:
        st.session_state['om_flash_error'] = str(exc)
    except Exception:
        st.session_state['om_flash_error'] = 'Completion could not be saved. Please reload and retry.'


def _payment_form(order):
    identity = order['id']
    token_key = f'om_payment_token_{identity}'
    st.session_state.setdefault(token_key,uuid4().hex)
    with st.form(f'om_payment_{identity}',clear_on_submit=False):
        st.subheader(tr('Record Payment'))
        st.caption(tr('Record money actually received. Saving does not complete the order.'))
        amount = st.number_input(tr('Amount received (RM)'),min_value=0.,value=None,key=f'om_payment_amount_{identity}')
        left,right = st.columns(2)
        paid_date = left.date_input(tr('Payment date'),value=datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date(),format=date_input_format(),key=f'om_payment_date_{identity}')
        method = right.selectbox(tr('Payment method'),store.METHODS,key=f'om_payment_method_{identity}')
        reference = st.text_input(tr('Payment reference (optional)'),key=f'om_payment_ref_{identity}')
        notes = st.text_area(tr('Payment notes (optional)'),key=f'om_payment_notes_{identity}')
        save = st.form_submit_button(tr('Save Payment'),type='primary')
    if save:
        try:
            store.record_payment(identity,dict(amount=amount,method=method,reference=reference,notes=notes,
                paid_at=datetime.combine(paid_date,datetime.min.time(),ZoneInfo('Asia/Kuala_Lumpur')).isoformat()),token=st.session_state[token_key])
            st.session_state[f'om_payment_saved_{identity}'] = True
            st.session_state[f'om_payment_open_{identity}'] = False
            _changed('Payment recorded. Balance updated.')
        except (ValueError,PermissionError) as exc:
            st.error(tr(str(exc)))
        except Exception:
            st.error(tr('Payment could not be saved. Retry this submission; duplicate payments are prevented.'))


@localized_dialog('Order Details', width='large', on_dismiss=_dismiss_details)
def _details(identity):
    try:
        details = store.details(identity)
    except PermissionError as exc:
        st.error(tr(str(exc))); return
    except Exception:
        st.error(tr('Order details could not be loaded. Please retry.')); return
    if not details:
        st.info(tr('This order is no longer available.'))
        return
    order = details['order']
    st.subheader(tr(f"Order Details · {order['order_code']}"))
    if st.button(tr('Message Customer'),key=f'om_message_customer_{identity}',icon=':material/chat_bubble:'):
        from customer_messages_ui import open_messages
        from navigation import navigate
        open_messages(lambda page:navigate(st.session_state,page),order['customer_id'],identity)
    st.markdown(tr(f'''<div class="orders-detail-hero"><div><div class="orders-customer">{escape(str(order['customer_name']))}</div>
        <div class="orders-secondary">{escape(str(order['phone_number']))}</div></div><div class="orders-badges">
        <span class="orders-badge orders-{order['status'].lower()}">{order['status']}</span>
        <span class="orders-badge orders-{order['payment_status'].lower()}">{order['payment_status']}</span></div></div>
        <div class="orders-fulfilment"><div><span>{escape(order['fulfilment_method'])}</span><strong>{escape(str(order['fulfilment_date']))} {escape(str(order.get('fulfilment_time') or ''))}</strong></div>
        <div><span>Order source</span><strong>{escape(order['source'])}</strong></div></div>'''), unsafe_allow_html=True)
    if order['legacy_status'] != order['status']:
        st.caption(tr(f"Legacy status '{order['legacy_status']}' is displayed as Pending. The stored record has not been rewritten."))
    if order['fulfilment_method'] == 'Delivery': st.write('Delivery address: '+order['delivery_address'])
    st.caption(tr('Customer residence: '+state_label(order.get('customer_state_snapshot'))))
    if order['fulfilment_method'] == 'Delivery':
        st.caption(tr('Delivery destination state: '+state_label(order.get('delivery_state'))))
    st.markdown(tr('#### Order items'))
    items = pd.DataFrame(details['items'])
    if not items.empty:
        st.dataframe(style_table(items[['product_name','quantity','unit_price','subtotal']].rename(columns={
            'product_name':'Product','quantity':'Quantity','unit_price':'Unit Price (RM)','subtotal':'Subtotal (RM)'})),hide_index=True,width='stretch',
            column_config={label:st.column_config.NumberColumn(format='%.2f') for label in ('Unit Price (RM)','Subtotal (RM)')})
    subtotal = sum((store.money(line['subtotal']) for line in details['items']),store.money(0))
    st.caption(tr(f"Subtotal: {_money(subtotal)} · Discount: {_money(order['discount'])} · Delivery fee: {_money(order['delivery_fee'])}"))
    if order.get('quote_pending'):
        st.warning(tr('Delivery fee is awaiting a rider quote. Edit this order, enter the quoted fee, and confirm it before recording payment.'))
    with st.container(key='nour_orders_payment_summary'):
        total,paid,balance = st.columns(3)
        total.metric(tr('Grand Total'),_money(order['total_amount']))
        paid.metric(tr('Amount Paid'),_money(order['amount_paid']))
        balance.metric(tr('Outstanding Balance'),_money(order['balance']))
    if order['balance'] < 0: st.warning(tr(f"Overpayment: {_money(-order['balance'])}. Reconcile separately; payment history is unchanged."))
    if order.get('notes'): st.write('Instructions: '+order['notes'])
    st.caption(tr(f"Created: {order['created_at']} · Last modified: {order['updated_at']}"))
    if order['status'] == 'Completed': st.caption(tr('Completed: '+str(order.get('completed_at') or order['status_updated_at'])))
    if order['status'] == 'Cancelled':
        st.caption(tr('Cancelled: '+str(order.get('cancelled_at') or order['status_updated_at'])))
        st.write('Reason: '+(order.get('cancellation_reason') or 'Not provided'))
    with st.container(key='nour_orders_detail_actions'):
        st.caption(tr('Manage this order'))
        action_row = st.container(horizontal=True, gap='small')
        actions = [action_row] * 4
        if order['status'] == 'Pending':
            if actions[0].button(tr('Edit Order'),key=f'om_edit_{identity}',icon=':material/edit:'):
                _dismiss_details()
                st.session_state.update(om_form_mode='edit',om_edit_id=identity,om_form_token=uuid4().hex)
                st.rerun()
            actions[1].button(
                tr('Mark Completed'),
                key=f'om_complete_{identity}',
                type='primary',
                icon=':material/check_circle:',
                on_click=_complete_order,
                args=(identity, order['order_code']),
            )
            if actions[2].button(tr('Cancel Order'),key=f'om_cancel_{identity}',icon=':material/block:'):
                st.session_state['om_cancel_target'] = identity
                _dismiss_details()
                st.rerun()
        if order['status'] != 'Cancelled' and order['balance'] > 0 and not order.get('quote_pending'):
            if actions[3].button(tr('Record Payment'),key=f'om_record_payment_{identity}',icon=':material/payments:'):
                if st.session_state.pop(f'om_payment_saved_{identity}',False):
                    st.session_state[f'om_payment_token_{identity}'] = uuid4().hex
                    st.session_state[f'om_payment_amount_{identity}'] = None
                    st.session_state[f'om_payment_ref_{identity}'] = ''
                    st.session_state[f'om_payment_notes_{identity}'] = ''
                    st.session_state[f'om_payment_date_{identity}'] = datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date()
                st.session_state[f'om_payment_open_{identity}'] = True
                st.rerun()
    if st.session_state.get(f'om_payment_open_{identity}') and order['status'] != 'Cancelled':
        _payment_form(order)
    phone = sqlite_db.normalize_customer_phone(order['phone_number'])
    if phone and order['status'] != 'Cancelled':
        from urllib.parse import quote
        from orders_view import whatsapp_message
        st.link_button('WhatsApp Customer',f'https://wa.me/{phone.lstrip("+")}?text={quote(whatsapp_message(order,details["items"]))}')
    with st.expander(tr('Payment transactions'),expanded=False):
        if details['payments']:
            payments = pd.DataFrame(details['payments'])
            payments['id'] = payments['id'].map(lambda value:f'PAY-{value:05d}')
            st.dataframe(style_table(payments[['id','paid_at','amount','method','reference','notes']].rename(columns={'id':'Payment ID','paid_at':'Payment Date','amount':'Amount (RM)','method':'Method','reference':'Reference','notes':'Notes'})),hide_index=True,width='stretch')
        else: st.info(tr('No payments recorded. This order is Unpaid.'))
    with st.expander(tr('Order activity history')):
        if details['activity']: st.dataframe(style_table(pd.DataFrame(details['activity']).rename(columns={'action':'Activity','occurred_at':'Date & Time','actor':'Owner','summary':'Change Summary'})),hide_index=True,width='stretch')
        else: st.caption(tr('Historical activity before this update is not reconstructed.'))
def _reset_order_filters():
    defaults={'om_search':'','om_state_filter':'All States','om_status_filter':'All','om_payment_filter':'All',
              'om_date_from':None,'om_date_to':None,'om_fulfillment_filter':'All','om_source_filter':'All','om_sort':'Newest date','om_page':1}
    st.session_state.update(defaults)


def _clear_order_filter(key):
    defaults={'om_search':'','om_state_filter':'All States','om_status_filter':'All','om_payment_filter':'All',
              'om_date_from':None,'om_date_to':None,'om_fulfillment_filter':'All','om_source_filter':'All'}
    st.session_state[key]=defaults[key]
    st.session_state['om_page']=1


def _step_order_page(direction):
    st.session_state['om_page']=max(1,st.session_state.get('om_page',1)+direction)


def _row_action(action, identity):
    _choose_order(identity)
    try:
        detail=store.details(identity)
        if not detail:
            raise ValueError('Order no longer exists.')
        order=detail['order']
        if action=='details':
            st.session_state['om_detail_open_id'] = identity
            return
        if action in ('edit','complete','cancel') and order['status']!='Pending':
            raise ValueError('Only Pending orders support this action. Reload the order.')
        if action=='edit':
            _dismiss_details()
            st.session_state.update(om_form_mode='edit',om_edit_id=identity,om_form_token=uuid4().hex)
        elif action=='complete':
            store.transition(identity,'Completed')
            st.cache_data.clear()
            st.session_state['om_flash_message']=f"{order['order_code']} marked Completed. Payment status is unchanged."
        elif action=='cancel':
            _dismiss_details()
            st.session_state['om_cancel_target']=identity
        elif action=='payment':
            if order.get('quote_pending'):
                raise ValueError('Confirm the rider quote before recording a payment.')
            if order['status']=='Cancelled' or order['balance']<=0:
                raise ValueError('This order has no payable balance.')
            st.session_state['om_detail_open_id'] = identity
            if st.session_state.pop(f'om_payment_saved_{identity}',False):
                st.session_state[f'om_payment_token_{identity}']=uuid4().hex
                st.session_state[f'om_payment_amount_{identity}']=None
                st.session_state[f'om_payment_ref_{identity}']=''
                st.session_state[f'om_payment_notes_{identity}']=''
                st.session_state[f'om_payment_date_{identity}']=datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date()
            st.session_state[f'om_payment_open_{identity}']=True
    except (ValueError,PermissionError) as error:
        st.session_state['om_flash_error']=str(error)
    except Exception:
        st.session_state['om_flash_error']='This action could not be saved. Reload the order and retry.'


def _choose_order(identity):
    st.session_state['om_detail_selected'] = identity


def _render_order_dialog(records):
    if st.session_state.get('om_form_mode') or st.session_state.get('google_forms_import_open'):
        return
    cancel_target = st.session_state.get('om_cancel_target')
    if cancel_target is not None:
        order = next((row for row in records if int(row['id']) == int(cancel_target)), None)
        if order:
            _confirm_cancel(cancel_target, order['order_code'], order['customer_name'])
        else:
            _dismiss_cancel()
        return
    identity = st.session_state.get('om_detail_open_id')
    if identity is not None:
        _details(identity)


def render_order_management():
    from orders_view import order_frame,date_scope,filter_orders,export_frame,excel_bytes,order_summary
    st.markdown(tr('<style>'+(Path(__file__).parent/'styles/orders.css').read_text(encoding='utf-8-sig')+'</style>'),unsafe_allow_html=True)
    try:
        records = store.list_orders()
    except PermissionError as exc:
        st.error(tr(str(exc))); return
    except Exception:
        st.error(tr('Orders could not be loaded. Please retry.')); return
    frame = order_frame(records)
    _render_order_dialog(records)
    with st.container(key='nour_orders_page'):
        if st.session_state.get('nour_current_page') != 'Order Management':
            st.title(tr('Order List'))
            st.caption(tr('Manage and monitor customer orders.'))
        message = st.session_state.pop('om_flash_message',None)
        if message: st.success(tr(message))
        completion_toast = st.session_state.pop('om_completion_toast', None)
        if completion_toast: st.toast(completion_toast, icon=':material/check_circle:')
        error=st.session_state.pop('om_flash_error',None)
        if error: st.error(tr(error))
        # Read persisted date widgets before rendering KPIs above the filter panel.
        dated = date_scope(frame,st.session_state.get('om_date_from'),st.session_state.get('om_date_to'))
        with st.container(key='nour_orders_toolbar',horizontal=True,horizontal_alignment='right',gap='small'):
            header_export=st.container(key='orders_export_slot')
            header_import=st.container(key='orders_import_slot')
            header_add=st.container(key='orders_add_slot')
        if header_import.button(tr('Import Orders'),key='om_import_orders',icon=':material/upload_file:'):
            st.session_state['google_forms_import_open'] = True
        if st.session_state.get('google_forms_import_open'):
            from google_forms_importer import render_google_forms_import
            render_google_forms_import()
        if header_add.button(tr('Add Order'),key='om_add_new',type='primary',icon=':material/add:'):
            st.session_state.update(om_form_mode='add',om_edit_id=None,om_form_token=uuid4().hex)
            st.rerun()
        if st.session_state.get('om_form_mode') in ('add','edit'):
            _render_order_form(st.session_state.get('om_edit_id') if st.session_state['om_form_mode']=='edit' else None)
        with st.container(key='nour_orders_kpis'):
            summary = order_summary(dated)
            for column,label,value in zip(st.columns(4),('Total Orders','Pending Orders','Completed Orders','Cancelled Orders'),
                                          (f'{summary["total"]:,}',f'{summary["pending"]:,}',f'{summary["completed"]:,}',f'{summary["cancelled"]:,}')):
                column.metric(tr(label),value)
        deadlines = order_summary(frame)
        st.caption(tr('KPIs follow the order-date range. Deadlines below include all Pending orders (MYT).'))
        st.markdown(tr(f'''<div class="orders-deadlines"><span>Due today <strong>{deadlines['today']}</strong></span>
            <span>Due tomorrow <strong>{deadlines['tomorrow']}</strong></span><span class="orders-overdue">Overdue pending <strong>{deadlines['overdue']}</strong></span></div>'''),unsafe_allow_html=True)
        with st.container(border=True,key='nour_orders_filters'):
            search_col,state_col,payment_col,sort_col = st.columns([2.4,2.1,1.1,1.3])
            search = search_col.text_input(tr('Search'),placeholder=tr('Find an order, customer or product…'),key='om_search',icon=':material/search:')
            state=state_col.selectbox(tr('State'),['All States',*STATES,'Not Specified'],key='om_state_filter')
            payment = payment_col.selectbox(tr('Payment status'),['All',*PAYMENT_STATUSES],key='om_payment_filter')
            sort = sort_col.selectbox(tr('Sort by'),['Newest date','Oldest date','Fulfillment deadline','Highest amount','Lowest amount'],key='om_sort', format_func=option_labels(['Newest date','Oldest date','Fulfillment deadline','Highest amount','Lowest amount']))
            status = st.segmented_control(tr('Order status'),['All',*STATUSES],default='All',key='om_status_filter',selection_mode='single') or 'All'
            with st.expander(tr('More filters'), icon=':material/tune:'):
                start_col,end_col,method_col,source_col = st.columns(4)
                start = start_col.date_input(tr('Order date from'),value=None,key='om_date_from',format=date_input_format())
                end = end_col.date_input(tr('Order date to'),value=None,key='om_date_to',format=date_input_format())
                fulfillment = method_col.selectbox(tr('Fulfillment'),['All',*FULFILMENT_METHODS],key='om_fulfillment_filter')
                source = source_col.selectbox(tr('Source'),['All',*store.SOURCES],key='om_source_filter')
                st.button(tr('Clear Filters'), key='om_reset_filters', icon=':material/restart_alt:', on_click=_reset_order_filters)
        if start and end and start > end: st.warning(tr('End date must be on or after the start date.'))
        signature=(search,state,status,payment,start,end,fulfillment,source,sort)
        if signature != st.session_state.get('om_filter_signature'):
            st.session_state['om_page']=1
            st.session_state['om_filter_signature']=signature
        with st.container(key='orders_filter_chips',horizontal=True,gap='small'):
            chips=[('State',state,'All States','om_state_filter'),('Status',status,'All','om_status_filter'),
                   ('Payment',payment,'All','om_payment_filter'),('Source',source,'All','om_source_filter'),
                   ('Fulfillment',fulfillment,'All','om_fulfillment_filter'),('Search',search,'','om_search'),
                   ('From',start,None,'om_date_from'),('To',end,None,'om_date_to')]
            active=[chip for chip in chips if chip[1]!=chip[2]]
            for label,value,default,key in active:
                st.button(tr(f'{label}: {str(value)[:40]} ×'),key=f'om_chip_{key}',on_click=_clear_order_filter,args=(key,))
            if active:
                st.button(tr('Clear All'),key='om_clear_all',on_click=_reset_order_filters)
        filtered = filter_orders(date_scope(frame,start,end),search=search,status=status,payment=payment,fulfillment=fulfillment,source=source,state=state,sort=sort)
        with header_export.popover(tr('Export'),icon=':material/download:'):
            st.caption(tr(f'Export all {len(filtered)} matching orders, across all table pages.'))
            st.download_button(tr('CSV'),export_frame(filtered).to_csv(index=False).encode('utf-8-sig'),'bizmar-orders.csv','text/csv',key='om_export_csv')
            import importlib.util
            if importlib.util.find_spec('openpyxl'):
                st.download_button(tr('Excel (.xlsx)'),excel_bytes(filtered),'bizmar-orders.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='om_export_excel')
        st.caption(tr(f'{len(filtered)} orders · Select a customer name to view order details; use the three-dot menu for actions.'))
        if filtered.empty:
            st.info(tr('No orders yet. Create your first order to get started.' if frame.empty else 'No orders found for the selected state.' if state!='All States' else 'No orders match these filters. Add an order or adjust the filters.'))
            if active:
                st.button(tr('Clear Filters'),key='om_empty_clear',on_click=_reset_order_filters)
            return
        pages = max(1,(len(filtered)+19)//20)
        if st.session_state.get('om_page',1)>pages: st.session_state['om_page']=1
        page = 1
        if pages > 1:
            with st.container(key='nour_orders_pagination'):
                previous,jump,label,next_page = st.columns([1,2,3,1],vertical_alignment='bottom')
                previous.button(tr(''),icon=':material/chevron_left:',help=tr('Previous page'),key='om_prev',disabled=st.session_state.get('om_page',1)<=1,on_click=_step_order_page,args=(-1,))
                page = jump.number_input(tr('Page'),min_value=1,max_value=pages,value=1,step=1,key='om_page')
                label.caption(tr(f'of {pages} ? 20 orders per page'))
                next_page.button(tr(''),icon=':material/chevron_right:',help=tr('Next page'),key='om_next',disabled=page>=pages,on_click=_step_order_page,args=(1,))
        visible = filtered.iloc[(page-1)*20:page*20].copy()
        from orders_list_ui import render_order_rows
        render_order_rows(visible,_row_action)
        identities = filtered.id.astype(int).tolist()
        selected = st.session_state.get('om_detail_selected')
        if selected not in identities: selected = identities[0]
        st.session_state['om_detail_selected'] = selected


def render_new_order(payment_renderer=None):
    from quick_order import render_quick_order
    render_quick_order(payment_renderer=payment_renderer)
