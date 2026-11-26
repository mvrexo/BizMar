"""Theme-preserving operational monitor; no import or polling implementation here."""
from display_preferences import tr
from datetime import datetime, timedelta
import math
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from sync_monitor_store import monitor_data

MYT=ZoneInfo('Asia/Kuala_Lumpur')


def malaysia_time(value):
    if not value:
        return 'Never'
    try:
        parsed=datetime.fromisoformat(value)
        if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=MYT)
        return parsed.astimezone(MYT).strftime('%d %b %Y, %H:%M:%S MYT')
    except (TypeError,ValueError):
        return 'Unavailable'


def status_model(data,interval,now=None):
    state=data['state']
    latest=next((r for r in data['history'] if r['result']!='Running'),{})
    kind=latest.get('error_kind','') if latest.get('result') in ('Failed','Partial') or state.get('last_error') else ''
    connection='Error' if kind=='Connection' else ('Connected' if state.get('last_synced_at') or kind=='Validation' else 'Disconnected')
    if state.get('last_error') and not kind:connection='Error'
    auto='Paused' if not state.get('confirmed_at') else (
        'Review' if kind=='Partial' else ('Error' if state.get('last_error') or kind else 'Enabled')
    )
    current=now or datetime.now(MYT)
    remaining=None
    if auto!='Paused' and state.get('last_attempt_at'):
        attempted=datetime.fromisoformat(state['last_attempt_at'])
        if attempted.tzinfo is None:attempted=attempted.replace(tzinfo=MYT)
        remaining=max(0,math.ceil((attempted+timedelta(seconds=interval)-current).total_seconds()))
    next_poll='Paused' if auto=='Paused' else (f'Approximately {remaining}s' if remaining else f'Next active-session tick (up to {interval}s)')
    return dict(connection=connection,auto=auto,next_poll=next_poll,last_success=malaysia_time(state.get('last_synced_at')),error_kind=kind,
                latest_imported=data['latest_success'].get('imported',state.get('last_new_orders',0)))


def render_monitor_cards(config):
    data=monitor_data(config.spreadsheet_id)
    model=status_model(data,config.sync_interval_seconds)
    with st.container(key='google_sheets_monitor'):
        st.markdown(tr('''<style>
        .st-key-google_sheets_monitor [data-testid="stMetric"] {
            border:1px solid var(--nour-line,#e7d8db);border-radius:20px;
            background:var(--forest-card,var(--nour-surface,#fffcf8));padding:18px;min-height:125px;
            box-shadow:var(--nour-shadow,0 4px 14px rgba(0,0,0,.08));
        }
        .st-key-google_sheets_monitor [data-testid="stColumn"]:nth-child(odd) [data-testid="stMetric"] {border-top:3px solid var(--forest-primary,var(--nour-matcha,#dce9cb));}
        .st-key-google_sheets_monitor [data-testid="stColumn"]:nth-child(even) [data-testid="stMetric"] {border-top:3px solid var(--forest-pink,var(--nour-strawberry,#f8dce2));}
        .st-key-google_sheets_monitor [data-testid="stMetricValue"] {white-space:normal;overflow-wrap:anywhere;}
        </style>'''),unsafe_allow_html=True)
        columns=st.columns(4)
        for column,label,value in zip(columns,['↔ Connection Status','◷ Last Successful Sync','↓ Total Imported Orders','! Failed Imports'],
                                      [model['connection'],model['last_success'],data['total_imported'],data['failed_imports']]):
            column.metric(tr(label),value)
        st.caption(tr(f"Auto Sync: {model['auto']} · Worksheet: {config.worksheet_name} · Polling interval: {config.sync_interval_seconds} seconds"))
        st.caption(tr(f"Next poll: {model['next_poll']} · Last checked: {malaysia_time(data['state'].get('last_attempt_at'))}"))
        st.caption(tr(f"Already-linked responses: {data['linked_responses']} · Existing-order associations: {data['existing_associations']} · Recorded skipped responses: {data['skipped_total']} · Failed attempts: {data['failed_attempts']}"))
        with st.expander(tr('Metric details')):
            st.caption(tr('Failed Imports counts rejected response attempts, including retries. Connection failures increment Failed attempts. Imported totals include earlier source links; attempt history starts when the monitor was installed.'))
        if model['error_kind']=='Connection':
            st.warning(tr('Google Sheets is unavailable. Previous successful sync time is retained. Retry with Sync Now.'))
        elif data['state'].get('last_error'):
            st.warning(tr('Sync requires review. Check the validation results below before retrying.'))
    return data,model


def render_history(data):
    st.markdown(tr('#### Recent sync activity'))
    if not data['history']:
        st.info(tr('No sync attempts recorded yet.'))
        return
    rows=[{'Date and time (MYT)':malaysia_time(r['finished_at'] or r['started_at']),'Trigger':r['trigger'],
           'Result':r['result'],'New orders':r['imported'],'Associated':r['associated'],'Skipped':r['skipped'],
           'Failed responses':r['failed_rows'],'Error type':r['error_kind'],'Error summary':r['error_summary']} for r in data['history']]
    st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')


def render_overview_widget(config,navigate_to):
    data=monitor_data(config.spreadsheet_id)
    model=status_model(data,config.sync_interval_seconds)
    with st.container(border=True,key='google_sheets_overview_status'):
        st.markdown(tr('**Google Sheets Sync Status**'))
        st.caption(tr(f"{model['connection']} · Auto Sync: {model['auto']} · Last successful sync: {model['last_success']} · Latest successful attempt: {model['latest_imported']} new orders"))
        if st.button(tr('Open Sync Monitor'),key='google_sheets_open_monitor',icon=':material/sync:'):
            st.session_state['bizmar_data_import_tab']='Google Sheets Sync'
            navigate_to('Data Import')
            st.rerun()
