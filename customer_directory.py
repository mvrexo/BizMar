"""Minimal customer directory using the existing customer CRUD service."""
import math
import re
from pathlib import Path
import pandas as pd
import streamlit as st
from display_preferences import localized_dialog, tr
from malaysian_states import (
    STATES, canonical as canonical_state, display as state_label,
    normalize as normalize_state,
)


def text(value):
    return '' if value is None or (isinstance(value,float) and math.isnan(value)) else str(value).strip()


def directory_rows(records,query='',normalize=None):
    source=records.to_dict('records') if isinstance(records,pd.DataFrame) else records
    rows=[]
    term=query.strip().casefold()
    digits=re.sub(r'\D','',query) if re.fullmatch(r'[+\d\s().-]+',query) else ''
    canonical=normalize(query) if normalize and digits else ''
    for original in source:
        row=dict(original)
        if text(row.get('archived')) not in ('','0','0.0','False'):continue
        row['customer_name']=text(row.get('full_name')) or text(row.get('name'))
        row['phone_number']=text(row.get('phone_number')) or text(row.get('phone'))
        phone_digits=re.sub(r'\D','',row['phone_number'])
        normalized=normalize(row['phone_number']) if normalize else ''
        if term and not (term in row['customer_name'].casefold() or term in row['phone_number'].casefold()
                         or (digits and (digits in phone_digits or digits in re.sub(r'\D','',normalized))) or (canonical and canonical==normalized)):
            continue
        rows.append(row)
    return sorted(rows,key=lambda row:(row['customer_name'].casefold(),str(row['id'])))


def save_customer(store,values,identity=None):
    """Only customer fields are updated. Order snapshots and IDs are untouched."""
    name,phone,address=(text(values.get(field)) for field in ('name','phone','address'))
    state=normalize_state(values.get('state'))
    if not name:raise ValueError('Customer name is required.')
    normalized=store.normalize_customer_phone(phone)
    if not re.fullmatch(r'[+\d\s().-]+',phone) or not normalized or not re.fullmatch(r'\+60\d{9,10}',normalized):
        raise ValueError('Enter a valid Malaysian phone number.')
    if not address:raise ValueError('Address is required.')
    if not state:raise ValueError('Select a Malaysian state.')
    existing=store.all_rows('customers')
    if identity is not None and not any(row['id']==identity for row in existing):
        raise ValueError('Customer no longer exists. Refresh and try again.')
    for row in existing:
        if row['id']==identity:continue
        phones=[row.get(field) for field in ('normalized_phone','phone_number','phone')]
        if any(store.normalize_customer_phone(text(value))==normalized for value in phones if text(value)):
            raise ValueError('This phone number is already registered to another customer.')
    payload=dict(name=name,full_name=name,phone=phone,phone_number=phone,
                 normalized_phone=normalized,address=address,state=state)
    if identity is None:return store.add('customers',payload)
    return store.edit('customers',identity,payload)


def _dismiss_remove():
    st.session_state.pop('directory_remove_id',None)


@localized_dialog('Remove Customer', on_dismiss=_dismiss_remove)
def _confirm_remove(identity, name, store, on_removed):
    st.text(f'{tr("Remove")} {name}?')
    st.caption(tr(
        'Customers with orders or other linked records will be archived to preserve their history; '
        'only customers with no linked records are permanently deleted.'
    ))
    cancel, confirm = st.columns(2)
    if cancel.button(tr('Cancel'), key='directory_remove_cancel'):
        _dismiss_remove()
        st.rerun()
    if confirm.button(tr('Confirm Remove'), type='primary', key='directory_remove_confirm'):
        try:
            outcome = store.remove_customer(identity)
        except ValueError as error:
            st.error(tr(str(error)))
            return
        _dismiss_remove()
        st.session_state['directory_removed'] = (
            'Customer archived to preserve linked records.'
            if outcome == 'archived' else 'Customer removed successfully.'
        )
        if on_removed:
            on_removed()
        st.rerun()


def render_customers(records,*,store,on_saved,normalize_phone):
    with st.container(key='bizmar_customer_directory'):
        st.markdown(tr('<style>'+(Path(__file__).parent/'styles/customer_directory.css').read_text(encoding='utf-8')+'</style>'),unsafe_allow_html=True)
        if st.session_state.pop('directory_saved',False):st.success(tr('Customer saved successfully.'))
        removed=st.session_state.pop('directory_removed',None)
        if removed:st.success(tr(removed))
        rows=directory_rows(records)
        for row in rows:
            row['state']=state_label(row.get('state'))
        count,space=st.columns([1,3])
        with count:st.metric(tr('Total Customers'),len(rows))
        search,add=st.columns([4,1],vertical_alignment='bottom')
        query=search.text_input(tr('Search Customer'),placeholder=tr('Search by name or phone number'),key='directory_search')
        if add.button(tr('Add Customer'),icon=':material/person_add:',type='primary',width='stretch',key='directory_add'):
            st.session_state['directory_edit']='new'
        editing=st.session_state.get('directory_edit')
        if editing is not None:
            current=next((row for row in rows if row['id']==editing),{})
            if editing!='new' and not current:
                st.warning(tr('Customer no longer exists. Refresh and try again.'))
                st.session_state.pop('directory_edit',None)
            else:
                _editor(current,editing,store,on_saved)
        filtered=directory_rows(records,query,normalize_phone)
        st.subheader(tr('Customer List'))
        if not rows:
            st.info(tr('No customers yet. Add your first customer to get started.'));return
        if not filtered:
            st.info(tr('No customers match your search.'));return
        page_size=15
        pages=max(1,(len(filtered)+page_size-1)//page_size)
        if st.session_state.get('directory_last_search')!=query:
            st.session_state['directory_page']=1
            st.session_state['directory_last_search']=query
        if st.session_state.get('directory_page',1)>pages:st.session_state['directory_page']=pages
        if pages>1:
            page=int(st.number_input(tr('Page'),min_value=1,max_value=pages,step=1,key='directory_page'))
        else:page=1
        with st.container(key='bizmar_directory_table'):
            with st.container(key='bizmar_directory_headers'):
                headers=st.columns([3,2,2,1.8])
                for col,label in zip(headers,('Customer Name','Phone Number','State','Actions')):col.markdown(tr('**'+tr(label)+'**'))
            for row in filtered[(page-1)*page_size:page*page_size]:
                with st.container(key=f'bizmar_customer_row_{row["id"]}'):
                    name,phone,state,action=st.columns([3,2,2,1.8],vertical_alignment='center')
                    name.write(row['customer_name']);phone.write(row['phone_number'])
                    state.write(row['state'])
                    edit,remove=action.columns(2)
                    if edit.button('',icon=':material/edit:',help=tr('Edit Customer'),key=f'directory_edit_{row["id"]}',width='stretch'):
                        st.session_state['directory_edit']=row['id'];st.rerun()
                    if remove.button('',icon=':material/delete:',help=tr('Remove Customer'),key=f'directory_remove_{row["id"]}',width='stretch'):
                        st.session_state['directory_remove_id']=row['id']
        identity=st.session_state.get('directory_remove_id')
        if identity is not None:
            customer=next((row for row in store.all_rows('customers',id=identity) if not row.get('archived')),None)
            if customer is None:
                _dismiss_remove()
                st.warning(tr('Customer no longer exists. Refresh and try again.'))
            else:
                _confirm_remove(identity,customer.get('full_name') or customer.get('name') or '',store,on_saved)


def _editor(current,identity,store,on_saved):
    with st.container(border=True,key='bizmar_customer_editor'):
        st.subheader(tr('Add Customer' if identity=='new' else 'Edit Customer'))
        with st.form(f'directory_form_{identity}'):
            name=st.text_input(tr('Customer Name'),value=current.get('customer_name',''))
            phone=st.text_input(tr('Phone Number'),value=current.get('phone_number',''))
            address=st.text_area(tr('Address'),value=text(current.get('address')))
            current_state=canonical_state(current.get('state'))
            state=st.selectbox(tr('State'),['',*STATES],index=STATES.index(current_state)+1 if current_state in STATES else 0,format_func=lambda value:value or tr('Select a state'))
            save,cancel=st.columns(2)
            submitted=save.form_submit_button(tr('Save Customer'),type='primary',width='stretch')
            cancelled=cancel.form_submit_button(tr('Cancel'),width='stretch')
        if cancelled:
            st.session_state.pop('directory_edit',None);st.rerun()
        if submitted:
            try:save_customer(store,dict(name=name,phone=phone,address=address,state=state),None if identity=='new' else identity)
            except ValueError as error:st.error(tr(str(error)))
            except Exception:st.error(tr('Could not save customer. Please try again.'))
            else:
                st.session_state.pop('directory_edit',None)
                st.session_state['directory_saved']=True
                on_saved()
                st.rerun()
