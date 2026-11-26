"""Reference-style order rows using native, accessible three-dot popovers."""
from display_preferences import tr
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from malaysian_states import destination

WIDTHS = [1.1,1.9,1.2,1.8,1.2,1.25,1.1,1.1,.5]
HEADINGS = ('Order number','Customer','State','Products','Total price','Fulfillment','Payment','Status','')


def actions_for(order):
    actions = [('details','View Details',':material/info:')]
    if order['status']=='Pending':
        actions += [('edit','Edit Order',':material/edit:'),('complete','Mark Completed',':material/check_circle:')]
    if order['status']!='Cancelled' and order['balance']>0 and not order.get('quote_pending'):
        actions += [('payment','Record Payment',':material/payments:')]
    if order['status']=='Pending':
        actions += [('cancel','Cancel Order',':material/block:')]
    return actions


def product_summary(order):
    first = order.get('first_product')
    if first and pd.notna(first):
        count = int(order.get('item_count') or 1)
        return str(first) + (f' +{count-1} more' if count>1 else '')
    return str(order.get('products') or '—')


def _badge(value, overdue=False):
    late=' · '+tr('Overdue fulfilment') if overdue else ''
    return f'<span class="orders-badge orders-{value.lower()}">{escape(tr(value))}{late}</span>'


def _dispatch(callback, action, identity, popover_key):
    # Close the native overlay before opening an editor/confirmation dialog.
    st.session_state[popover_key]=False
    st.session_state['om_menu_epoch']=st.session_state.get('om_menu_epoch',0)+1
    callback(action,identity)


def _menu(order, callback, surface):
    if st.session_state.get('om_form_mode') or st.session_state.get('om_cancel_target'):
        return  # Unmount portals while a native editor/confirmation dialog is open.
    popover_key=f'om_menu_open_{surface}_{order["id"]}_{st.session_state.get("om_menu_epoch",0)}'
    with st.popover(tr(''), icon=':material/more_horiz:',help=f"Actions for {order['order_code']}",use_container_width=False,
                    key=popover_key,on_change='rerun'):
        st.caption(tr(order['order_code']))
        for action,label,icon in actions_for(order):
            st.button(tr(label),key=f'om_menu_{surface}_{action}_{order["id"]}',icon=icon,width='stretch',
                on_click=_dispatch,args=(callback,action,int(order['id']),popover_key))


def render_order_rows(frame, callback):
    today=datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date()
    with st.container(key='nour_orders_table'):
        with st.container(key='orders_desktop_rows'):
            with st.container(key='orders_table_heading'):
                for column, heading in zip(st.columns(WIDTHS,gap='small'),HEADINGS):
                    column.markdown(tr(f'<div class="orders-th">{heading}</div>'),unsafe_allow_html=True)
            for order in frame.to_dict('records'):
                with st.container(key=f'orders_table_row_{order["id"]}'):
                    columns=st.columns(WIDTHS,gap='small',vertical_alignment='center')
                    due=pd.to_datetime(order['fulfilment_date'],errors='coerce')
                    overdue=order['status']=='Pending' and pd.notna(due) and due.date()<today
                    summary=product_summary(order)
                    cells=(f'<strong>{escape(order["order_code"])}</strong>',
                           f'<strong>{escape(order["customer_name"])}</strong><small>{escape(order["phone_number"])}</small>',
                           escape(destination(order)),
                           f'<span title="{escape(str(order["products"]),quote=True)}">{escape(summary)}</span>',
                           f'<strong class="orders-tabular">RM {order["total_amount"]:,.2f}</strong>',
                           escape(str(order['fulfilment_date'])),
                           _badge(order['payment_status']),_badge(order['status'],overdue))
                    columns[0].markdown(tr(f'<div class="orders-cell">{cells[0]}</div>'),unsafe_allow_html=True)
                    with columns[1]:
                        st.button(
                            tr(str(order['customer_name'])),
                            key=f'om_customer_details_row_{order["id"]}',
                            on_click=callback,
                            args=('details',int(order['id'])),
                            width='stretch',
                        )
                        st.markdown(
                            tr(f'<div class="orders-cell orders-customer-phone">{escape(order["phone_number"])}</div>'),
                            unsafe_allow_html=True,
                        )
                    for column,cell in zip(columns[2:],cells[2:]):
                        column.markdown(tr(f'<div class="orders-cell">{cell}</div>'),unsafe_allow_html=True)
                    with columns[-1]:
                        _menu(order,callback,'row')
    with st.container(key='nour_orders_mobile_list'):
        for order in frame.to_dict('records'):
            with st.container(border=True,key=f'om_mobile_card_{order["id"]}'):
                title,menu=st.columns([4,1],vertical_alignment='center')
                title.markdown(tr(f'<strong>{escape(order["order_code"])}</strong>'),unsafe_allow_html=True)
                with menu:
                    _menu(order,callback,'mobile')
                st.button(
                    tr(str(order['customer_name'])),
                    key=f'om_customer_details_mobile_{order["id"]}',
                    on_click=callback,
                    args=('details',int(order['id'])),
                    width='stretch',
                )
                st.markdown(tr(f'''<div class="orders-secondary">{escape(order['phone_number'])} · {escape(destination(order))}</div>
                    <p>{escape(product_summary(order))}</p><div class="orders-secondary">{escape(order['fulfilment_method'])} · {escape(str(order['fulfilment_date']))}</div>
                    <div class="orders-mobile-amount"><strong>RM {order['total_amount']:,.2f}</strong><span>Balance RM {order['balance']:,.2f}</span></div>
                    <div class="orders-badges">{_badge(order['payment_status'])}{_badge(order['status'])}</div>'''),unsafe_allow_html=True)
