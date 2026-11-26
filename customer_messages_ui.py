from display_preferences import option_labels
"""Customer communication workbench; never sends through an external API."""
from display_preferences import tr
from datetime import datetime, timedelta
from uuid import uuid4
import pandas as pd
import streamlit as st
import customer_messages_store as store
from customer_message_templates import DEFAULTS,FIELDS
from sync_monitor_ui import malaysia_time


def open_messages(navigate_to,customer_id=None,order_id=None):
    store._guard()
    if customer_id is not None:st.session_state['messages_customer_id']=int(customer_id)
    st.session_state['messages_order_id']=int(order_id) if order_id else None
    st.session_state.pop('messages_editor_id',None)
    navigate_to('Messages')
    st.rerun()


def render_summary(navigate_to):
    try:counts=store.reminder_counts()
    except PermissionError:
        st.info(tr('Sign in again to view message reminders.'));return
    with st.container(border=True,key='messages_overview_summary'):
        st.markdown(tr('**Customer Messages & Follow-ups**'))
        columns=st.columns(3)
        for column,label,value in zip(columns,['Follow-ups due today','Overdue follow-ups','Pending drafts'],[counts['due_today'],counts['overdue'],counts['drafts']]):column.metric(tr(label),value)
        if st.button(tr('Open Messages'),key='messages_open_from_overview',icon=':material/chat_bubble:'):
            open_messages(navigate_to)


def _composer(customer_id,order_id):
    editor_id=st.session_state.get('messages_editor_id')
    message=store.get_message(editor_id) if editor_id else None
    if message and (message['customer_id']!=customer_id or message['order_id']!=order_id):
        st.session_state.pop('messages_editor_id',None);message=None
    if message and message['status']!='Draft':
        st.caption(tr('Start a new draft to change an opened or sent message.'))
        st.text(message['content'])
        return message
    context=f"{customer_id}_{order_id or 0}_{message['id'] if message else 'new'}"
    choices=list(DEFAULTS)
    template=st.selectbox(tr('Quick message template'),choices,index=choices.index(message['template_type']) if message else 0,key=f'message_template_{context}')
    with st.expander(tr('Edit reusable template')):
        raw=st.text_area(tr('Template text'),value=store.templates()[template],key=f'message_raw_template_{context}_{template}',max_chars=4000)
        st.caption(tr('Supported placeholders: '+', '.join('{'+name+'}' for name in sorted(FIELDS))))
        if st.button(tr('Save reusable template'),key=f'message_save_template_{context}_{template}'):
            try:store.save_template(template,raw);st.success(tr('Template saved. Apply it below to update your draft.'))
            except (ValueError,PermissionError) as error:st.error(tr(str(error)))
    body_key=f'message_body_{context}'
    try:initial=message['content'] if message else store.template_message(customer_id,order_id,template)
    except ValueError as error:initial='';st.warning(tr(str(error)))
    if st.button(tr('Apply template'),key=f'message_apply_{context}'):
        try:st.session_state[body_key]=store.template_message(customer_id,order_id,template,raw)
        except ValueError as error:st.error(tr(str(error)))
    body=st.text_area(tr('Message composer'),value=initial,key=body_key,height=180,max_chars=4000)
    st.caption(tr('Save your draft, then review and send it yourself in WhatsApp.'))
    token_key=f'message_token_{context}'
    if token_key not in st.session_state:st.session_state[token_key]=uuid4().hex
    if st.button(tr('Save Draft'),key='messages_save_draft',icon=':material/save:',type='primary'):
        try:
            saved=store.save_draft(customer_id,order_id,template,body,token=st.session_state[token_key],message_id=message['id'] if message else None,version=message['version'] if message else None)
            st.session_state['messages_editor_id']=saved['id'];st.session_state['messages_notice']='Draft saved.';st.rerun()
        except (ValueError,PermissionError) as error:st.error(tr(str(error)))
    if message and (body!=message['content'] or template!=message['template_type']):
        st.warning(tr('Save your changes before opening WhatsApp.'))
        return None
    return message


def _actions(message):
    if not message:
        st.button(tr('Send via WhatsApp'),key='messages_send_disabled',disabled=True,help=tr('Save your draft and any changes first.'))
        return
    st.caption(tr(f"Message #{message['id']} · {message['status']}"))
    if message['status']!='Sent':
        try:
            url=store.launch_url(message['id'])
            from whatsapp_launch import launch_button
            event=launch_button(url,message)
            if isinstance(event,dict) and event.get('action')=='opened' and event.get('message_id')==message['id']:
                updated=store.record_opened(message['id'],event.get('event_id'),event.get('version'))
                if updated['version']!=message['version']:st.rerun()
        except (ValueError,PermissionError) as error:st.warning(tr(str(error)))
        st.caption(tr('Opened does not mean sent. Send manually in WhatsApp, then mark it here.'))
        if message['whatsapp_opened_at']:
            confirmed=st.checkbox(tr('I manually sent this message in WhatsApp'),key=f'messages_sent_confirm_{message["id"]}')
            if st.button(tr('Mark as Sent'),key=f'messages_mark_sent_{message["id"]}',disabled=not confirmed):
                try:store.mark_sent(message['id'],confirmed=confirmed);st.rerun()
                except (ValueError,PermissionError) as error:st.error(tr(str(error)))
    with st.expander(tr('Schedule or reschedule follow-up')):
        when=datetime.fromisoformat(message['followup_at']) if message['followup_at'] else datetime.now(store.MYT)+timedelta(days=1)
        with st.form(f'message_followup_{message["id"]}'):
            day=st.date_input(tr('Follow-up date'),value=when.date())
            clock=st.time_input(tr('Follow-up time (MYT)'),value=when.time().replace(tzinfo=None))
            notes=st.text_area(tr('Follow-up notes'),value=message['notes'],max_chars=2000)
            if st.form_submit_button(tr('Save Follow-up')):
                try:store.schedule_followup(message['id'],datetime.combine(day,clock,tzinfo=store.MYT),notes);st.rerun()
                except (ValueError,PermissionError) as error:st.error(tr(str(error)))
    if message['followup_at']:
        st.caption(tr('Follow-up: '+malaysia_time(message['followup_at'])+(' · Completed' if message['followup_completed_at'] else ' · Pending')))
        if not message['followup_completed_at'] and st.button(tr('Complete Follow-up'),key=f'messages_complete_{message["id"]}'):
            store.complete_followup(message['id']);st.rerun()


def render_messages(navigate_to):
    try:store._guard()
    except PermissionError:
        st.error(tr('Sign in as the owner to access customer messages.'));return
    st.title(tr('Customer Messages'))
    notice=st.session_state.pop('messages_notice',None)
    if notice:st.success(tr(notice))
    counts=store.reminder_counts()
    cols=st.columns(4)
    for col,label,value in zip(cols,['Due today','Overdue','Upcoming','Drafts'],[counts['due_today'],counts['overdue'],counts['upcoming'],counts['drafts']]):col.metric(tr(label),value)
    st.caption(tr('MYT · In-app reminders only. Overdue reminders are counted separately.'))
    with st.expander(tr('Follow-up reminders — all customers')):
        reminder_view=st.radio(tr('Reminder view'),['Upcoming','Overdue','Completed'],horizontal=True,key='messages_reminder_view', format_func=option_labels(['Upcoming','Overdue','Completed']))
        reminders=store.followups(reminder_view)
        if not reminders:st.info(tr('No reminders in this view.'))
        else:
            st.dataframe(pd.DataFrame([{'Message':r['id'],'Customer':r['customer_name'],'Order':r['order_code'] or '—','Follow-up (MYT)':malaysia_time(r['followup_at']),'Notes':r['notes']} for r in reminders]),hide_index=True,width='stretch')
            lookup={r['id']:r for r in reminders}
            reminder_id=st.selectbox(tr('Select reminder'),list(lookup),format_func=lambda identity:f"#{identity} · {lookup[identity]['customer_name']}",key='messages_reminder_selection')
            if st.button(tr('Open reminder'),key='messages_open_reminder'):
                reminder=lookup[reminder_id]
                st.session_state['messages_customer_id']=reminder['customer_id'];st.session_state['messages_order_id']=reminder['order_id'];st.session_state['messages_editor_id']=reminder_id;st.session_state['messages_filter']='All';st.rerun()
    search=st.text_input(tr('Search customer name, phone or Order ID'),key='messages_search',icon=':material/search:')
    filter_name=st.segmented_control(tr('Inbox filter'),['All','Follow-up Needed','Drafts','WhatsApp Opened','Completed'],default='All',key='messages_filter', format_func=option_labels(['All','Follow-up Needed','Drafts','WhatsApp Opened','Completed'])) or 'All'
    customers=store.inbox(search,filter_name)
    with st.container(key='messages_workbench'):
        directory,panel=st.columns([1,2],gap='large')
    with directory,st.container(border=True,key='messages_customer_inbox'):
        st.subheader(tr('Customer inbox'))
        if not customers:st.info(tr('No customers match this filter.'));return
        ids=[c['id'] for c in customers]
        current=st.session_state.get('messages_customer_id')
        by_id={c['id']:c for c in customers}
        if current in ids and st.session_state.get('messages_customer_picker')!=current:
            st.session_state['messages_customer_picker']=current
        def customer_changed():
            st.session_state['messages_customer_id']=st.session_state['messages_customer_picker']
            st.session_state.pop('messages_editor_id',None)
        selected=st.selectbox(tr('Select customer'),ids,index=ids.index(current) if current in ids else 0,format_func=lambda identity:by_id[identity]['display_name'],key='messages_customer_picker',on_change=customer_changed)
        if current!=selected:
            st.session_state['messages_customer_id']=selected;st.session_state.pop('messages_editor_id',None)
        customer=by_id[selected]
        for entry in customers:
            latest=entry['latest_order']
            with st.container(border=True):
                st.text(entry['display_name']);st.caption(tr(entry['whatsapp'] or 'No phone provided'))
                st.caption(tr(f"{latest.get('order_code','No orders')} · {latest.get('status','—')} · {latest.get('payment_status','—')}"))
                st.caption(tr('Latest activity: '+malaysia_time(entry['last_activity'])+' · Follow-up: '+entry['followup_status']))
                if st.button(tr('Open conversation'),key=f'messages_select_{entry["id"]}'):
                    st.session_state['messages_customer_id']=entry['id'];st.session_state.pop('messages_editor_id',None);st.rerun()
    with panel,st.container(border=True,key='messages_selected_customer'):
        st.subheader(tr('Customer details'))
        st.text(customer['display_name'])
        st.text('WhatsApp: '+(customer['whatsapp'] or 'Not provided'))
        st.text('Address: '+(customer.get('address') or 'Not provided'))
        orders=store.customer_orders(selected)
        options=[None]+[o['id'] for o in orders];order_by_id={o['id']:o for o in orders}
        requested=st.session_state.get('messages_order_id')
        draft=store.get_message(st.session_state['messages_editor_id']) if st.session_state.get('messages_editor_id') else None
        preferred=draft['order_id'] if draft and draft['customer_id']==selected else requested
        default_index=options.index(preferred) if preferred in options and (preferred is not None or draft is not None) else (1 if orders else 0)
        order_id=st.selectbox(tr('Related order'),options,index=default_index,format_func=lambda identity:'No related order' if identity is None else f"{order_by_id[identity]['order_code']} · {order_by_id[identity]['status']} · {order_by_id[identity]['payment_status']}",key=f"messages_order_{selected}_{preferred}_{draft['id'] if draft else 'new'}")
        if orders:
            with st.expander(tr('All related orders')):
                st.dataframe(pd.DataFrame([{'Order':o['order_code'],'Status':o['status'],'Payment':o['payment_status'],'Total (RM)':o['total_amount'],'Fulfilment':o['fulfilment_date']} for o in orders]),hide_index=True,width='stretch')
        if order_id and st.button(tr('View Order'),key='messages_view_order',icon=':material/receipt_long:'):
            from order_management import _reset_order_filters
            _reset_order_filters();st.session_state['om_detail_open_id']=order_id;st.session_state['om_detail_selected']=order_id;navigate_to('Order Management');st.rerun()
        if st.button(tr('New message'),key='messages_new_message',icon=':material/edit:'):
            st.session_state.pop('messages_editor_id',None)
            prefix=f'message_token_{selected}_{order_id or 0}_new'
            st.session_state.pop(prefix,None);st.session_state.pop(f'message_body_{selected}_{order_id or 0}_new',None);st.rerun()
        message=_composer(selected,order_id)
        _actions(message)
        st.divider();st.markdown(tr('#### Message history'))
        history=store.messages(selected)
        if not history:st.info(tr('No saved messages for this customer yet.'))
        for old in history:
            with st.expander(tr(f"Message #{old['id']} · {old['template_type']} · {old['status']} · {malaysia_time(old['created_at'])}")):
                st.text(old['content'])
                st.caption(tr(f"WhatsApp opened: {malaysia_time(old['whatsapp_opened_at'])} · Owner marked sent: {malaysia_time(old['sent_at'])}"))
                if old['followup_at']:st.caption(tr('Follow-up: '+malaysia_time(old['followup_at'])+(' · Completed' if old['followup_completed_at'] else ' · Pending')))
                if st.button(tr('Select message'),key=f'messages_history_select_{old["id"]}'):
                    st.session_state['messages_editor_id']=old['id'];st.session_state['messages_order_id']=old['order_id'];st.rerun()
        events=store.activity_history(selected)
        if events:
            with st.expander(tr('Message activity history')):
                st.dataframe(pd.DataFrame([{'Message':e['message_id'],'Activity':e['action'],'Date (MYT)':malaysia_time(e['occurred_at'])} for e in events]),hide_index=True,width='stretch')
        with st.expander(tr('Upcoming and overdue follow-ups')):
            for reminder in history:
                if reminder['followup_at'] and not reminder['followup_completed_at']:
                    overdue=datetime.fromisoformat(reminder['followup_at'])<datetime.now(store.MYT)
                    st.write(('Overdue' if overdue else 'Upcoming')+f" · Message #{reminder['id']} · "+malaysia_time(reminder['followup_at']))
                    if reminder['notes']:st.text(reminder['notes'])
