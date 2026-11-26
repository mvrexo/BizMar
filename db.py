"""Server-side Supabase PostgREST adapter. Never expose service key to a browser."""
import requests
import streamlit as st


def configured():
    return bool(st.secrets.get('SUPABASE_URL') and st.secrets.get('SUPABASE_SERVICE_ROLE_KEY'))


def request(table, method='GET', *, params=None, payload=None, prefer=None):
    from uat_hardening import blocked
    blocked()
    base = st.secrets['SUPABASE_URL'].rstrip('/')
    key = st.secrets['SUPABASE_SERVICE_ROLE_KEY']
    headers = {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    if prefer:
        headers['Prefer'] = prefer
    resp = requests.request(method, f'{base}/rest/v1/{table}', params=params,
                            json=payload, headers=headers, timeout=25)
    if not resp.ok:
        raise RuntimeError(f'Database request failed ({resp.status_code}): {resp.text[:350]}')
    return resp.json() if resp.content else []


def all_rows(table, select='*', **filters):
    return request(table, params={'select':select, **filters})


def add(table, payload):
    data = request(table,'POST',payload=payload,prefer='return=representation')
    return data[0] if isinstance(data,list) else data


def edit(table, row_id, payload):
    return request(table,'PATCH',params={'id':f'eq.{row_id}'},payload=payload,prefer='return=representation')


def remove(table, row_id):
    return request(table,'DELETE',params={'id':f'eq.{row_id}'})
