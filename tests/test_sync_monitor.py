"""Sync monitor uses only synthetic Sheet responses and temporary SQLite."""
from contextlib import closing
from datetime import datetime
from zoneinfo import ZoneInfo
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import test_google_sheets_sync as fixtures
import google_sheets_sync as sync
import google_sheets_sync_ui as ui
import orders_store as store
import sqlite_db
from sync_monitor_store import monitor_data
from sync_monitor_ui import status_model, malaysia_time


class SyncMonitorTests(unittest.TestCase):
    setUp=fixtures.GoogleSheetsSyncTests.setUp
    tearDown=fixtures.GoogleSheetsSyncTests.tearDown
    headers=fixtures.GoogleSheetsSyncTests.headers
    make_snapshot=fixtures.GoogleSheetsSyncTests.make_snapshot
    row=fixtures.GoogleSheetsSyncTests.row
    prepare=fixtures.GoogleSheetsSyncTests.prepare

    def enable(self):
        store.confirm_google_sheets_sync(self.config.spreadsheet_id,1234)

    def poll(self,rows=None,force=True):
        with patch.object(sync.google_sheets_connection,'read_snapshot',return_value=self.make_snapshot(rows or [self.row()])):
            return sync.synchronize(self.config,force=force)

    def test_manual_sync_history_persistence_counts_and_no_duplicates(self):
        self.enable()
        result=self.poll()
        self.assertEqual(result['imported'],1)
        self.assertEqual(self.poll()['skipped'],1)
        data=monitor_data(self.config.spreadsheet_id)
        self.assertEqual((data['total_imported'],data['linked_responses'],data['failed_imports']),(1,1,0))
        self.assertEqual([r['imported'] for r in data['history']],[0,1])
        self.assertTrue(all(r['trigger']=='Manual' and r['result']=='Success' for r in data['history']))
        with closing(sqlite_db._connect()) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM google_sheets_sync_history').fetchone()[0],2)
        self.assertEqual(store.order_notification_counts()['total'],1)
        self.assertEqual(len(sqlite_db.all_rows('orders')),1)

    def test_timer_throttling_and_concurrent_lease_create_no_extra_attempts(self):
        self.enable()
        self.poll(force=False)
        self.assertTrue(self.poll(force=False)['waiting'])
        token=store.acquire_google_sheets_lease(self.config.spreadsheet_id,1234,trigger='Manual')
        with patch.object(sync.google_sheets_connection,'read_snapshot') as read:
            self.assertTrue(sync.synchronize(self.config,force=True)['syncing'])
            read.assert_not_called()
        data=monitor_data(self.config.spreadsheet_id)
        self.assertEqual(len(data['history']),2)
        self.assertEqual(data['history'][1]['trigger'],'Automatic')
        self.assertEqual(data['history'][0]['result'],'Running')
        store.finish_google_sheets_sync(self.config.spreadsheet_id,token)

    def test_connection_failure_preserves_success_and_safe_history(self):
        self.enable();self.poll()
        previous=monitor_data(self.config.spreadsheet_id)['state']['last_synced_at']
        with patch.object(sync.google_sheets_connection,'read_snapshot',side_effect=sync.google_sheets_connection.GoogleSheetsConnectionError('Connection timed out')):
            with self.assertRaises(sync.google_sheets_connection.GoogleSheetsConnectionError):sync.synchronize(self.config,force=True)
        data=monitor_data(self.config.spreadsheet_id)
        self.assertEqual(data['state']['last_synced_at'],previous)
        self.assertEqual((data['failed_imports'],data['failed_attempts']),(0,1))
        self.assertEqual(data['history'][0]['error_kind'],'Connection')
        self.assertEqual(status_model(data,30)['connection'],'Error')
        self.poll()
        self.assertEqual(status_model(monitor_data(self.config.spreadsheet_id),30)['connection'],'Connected')

    def test_partial_sync_is_connected_and_marked_for_review(self):
        data={
            'state':{
                'confirmed_at':'2026-10-29T10:00:00+08:00',
                'last_synced_at':'2026-10-29T10:01:00+08:00',
                'last_attempt_at':'2026-10-29T10:01:00+08:00',
                'last_error':'Valid new orders were imported; some source rows still require owner review.',
            },
            'history':[{'result':'Partial','error_kind':'Partial'}],
            'latest_success':{'imported':1},
        }
        model=status_model(data,30)
        self.assertEqual(model['connection'],'Connected')
        self.assertEqual(model['auto'],'Review')

    def test_validation_error_counts_responses_without_corrupting_order(self):
        self.enable();self.poll()
        before=sqlite_db.all_rows('orders')
        changed=self.row(quantity='5')
        with self.assertRaises(sync.SyncReviewRequired):self.poll([changed])
        data=monitor_data(self.config.spreadsheet_id)
        self.assertEqual((data['failed_imports'],data['history'][0]['error_kind']),(1,'Validation'))
        self.assertEqual(status_model(data,30)['connection'],'Connected')
        self.assertEqual(status_model(data,30)['auto'],'Error')
        self.assertEqual(sqlite_db.all_rows('orders'),before)

    def test_history_never_contains_internal_exception_or_customer_details(self):
        self.enable()
        with patch.object(sync.google_sheets_connection,'read_snapshot',side_effect=RuntimeError('private-token customer@example.test')):
            with self.assertRaises(RuntimeError):sync.synchronize(self.config,force=True)
        data=monitor_data(self.config.spreadsheet_id)
        self.assertNotIn('private-token',str(data))
        self.assertNotIn('customer@example.test',str(data))
        self.assertEqual(data['history'][0]['error_kind'],'Internal')

    def test_latest_twenty_attempts_and_stale_running_attempt_accounting(self):
        self.enable()
        for _ in range(22):self.poll()
        data=monitor_data(self.config.spreadsheet_id)
        self.assertEqual(len(data['history']),20)
        self.assertGreater(data['history'][0]['id'],data['history'][-1]['id'])
        token=store.acquire_google_sheets_lease(self.config.spreadsheet_id,1234)
        with sqlite_db.transaction() as connection:
            connection.execute("UPDATE google_sheets_sync_state SET lease_until='2000-01-01'")
            connection.execute("UPDATE google_sheets_sync_history SET lease_expires_at='2000-01-01' WHERE lease_token=?",(token,))
        self.poll()
        data=monitor_data(self.config.spreadsheet_id)
        self.assertEqual(data['history'][1]['error_kind'],'Interrupted')

    def test_historical_linked_file_import_is_not_counted_as_new_sync_import(self):
        record=dict(self.prepare(self.make_snapshot([self.row()])).preview.records[0])
        record['import_response_key']=record['forms_response_key']
        store.import_google_forms_orders([record])
        prepared=self.prepare(self.make_snapshot([self.row()]))
        store.activate_google_sheets_preview(self.config.spreadsheet_id,prepared.sheet_id,prepared.preview.records)
        data=monitor_data(self.config.spreadsheet_id)
        self.assertEqual((data['total_imported'],data['existing_associations'],data['linked_responses']),(0,1,1))

    def test_owner_only_access_to_monitor_and_background_poll(self):
        with patch.object(store,'current_owner',side_effect=PermissionError('Expired')),patch.object(sync.google_sheets_connection,'read_snapshot') as read:
            with self.assertRaises(PermissionError):monitor_data(self.config.spreadsheet_id)
            app=AppTest.from_string("from google_sheets_sync_ui import render_sync_background,render_google_sheets_sync\nrender_sync_background('Overview',lambda page:None)\nrender_google_sheets_sync()").run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.button),0)
            read.assert_not_called()

    def test_status_countdown_timezone_and_paused_state(self):
        self.enable();self.poll()
        data=monitor_data(self.config.spreadsheet_id)
        data['state']['last_attempt_at']='2026-10-29T01:00:00+00:00'
        model=status_model(data,30,datetime(2026,10,29,9,0,10,tzinfo=ZoneInfo('Asia/Kuala_Lumpur')))
        self.assertEqual(model['next_poll'],'Approximately 20s')
        self.assertIn('09:00:00 MYT',malaysia_time(data['state']['last_attempt_at']))
        data['state']['confirmed_at']=None
        self.assertEqual(status_model(data,30)['auto'],'Paused')

    def test_sync_now_ui_uses_service_updates_kpis_and_history(self):
        self.enable()
        with sqlite_db.transaction() as connection:
            connection.execute('UPDATE google_sheets_sync_state SET last_attempt_at=?',(store.now(),))
        script="""import streamlit as st
st.session_state.authenticated=True
st.session_state.local_owner_email='synthetic-owner@example.test'
from google_sheets_sync_ui import render_google_sheets_sync
render_google_sheets_sync()
"""
        with patch.object(sync.google_sheets_connection,'load_config',return_value=self.config),patch.object(sync.google_sheets_connection,'read_snapshot',return_value=self.make_snapshot([self.row()])),patch.object(ui.st,'secrets',{}):
            app=AppTest.from_string(script).run()
            self.assertFalse(app.exception)
            app.button(key='google_sheets_sync_now').click().run()
            self.assertFalse(app.exception)
            metrics={m.label:m.value for m in app.metric}
            self.assertEqual(metrics['↓ Total Imported Orders'],'1')
            self.assertTrue(any('imported' in message.value for message in app.success))
            self.assertEqual(monitor_data(self.config.spreadsheet_id)['history'][0]['trigger'],'Manual')
            self.assertEqual(store.order_notification_counts()['unread'],1)

    def test_overview_widget_navigates_to_monitor(self):
        self.enable()
        script="""import streamlit as st
from sync_monitor_ui import render_overview_widget
from google_sheets_connection import GoogleSheetsConfig
from pathlib import Path
def navigate(page):st.session_state['target']=page
render_overview_widget(GoogleSheetsConfig('synthetic-sheet-0123456789','Form Responses 1',Path('unused.json')),navigate)
"""
        app=AppTest.from_string(script).run()
        self.assertFalse(app.exception)
        app.button(key='google_sheets_open_monitor').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['target'],'Data Import')

    def test_manual_connection_failure_is_visible_immediately(self):
        self.enable()
        with sqlite_db.transaction() as connection:
            connection.execute('UPDATE google_sheets_sync_state SET last_attempt_at=?',(store.now(),))
        script='from google_sheets_sync_ui import render_google_sheets_sync\nrender_google_sheets_sync()'
        with patch.object(sync.google_sheets_connection,'load_config',return_value=self.config),patch.object(sync.google_sheets_connection,'read_snapshot',side_effect=sync.google_sheets_connection.GoogleSheetsConnectionError('Connection timed out')),patch.object(ui.st,'secrets',{}):
            app=AppTest.from_string(script).run()
            app.button(key='google_sheets_sync_now').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('unavailable' in warning.value for warning in app.warning))
            self.assertEqual(monitor_data(self.config.spreadsheet_id)['history'][0]['result'],'Failed')

    def test_background_owner_poll_remains_active_without_overview_widget(self):
        self.enable()
        script="""import streamlit as st
from google_sheets_sync_ui import render_sync_background
def navigate(page):st.session_state['target']=page
render_sync_background('Overview',navigate)
"""
        with patch.object(sync.google_sheets_connection,'load_config',return_value=self.config),patch.object(sync.google_sheets_connection,'read_snapshot',return_value=self.make_snapshot([self.row()])),patch.object(ui.st,'secrets',{}):
            app=AppTest.from_string(script).run()
            self.assertFalse(app.exception)
            self.assertFalse(any('Google Sheets Sync Status' in item.value for item in app.markdown))
            self.assertFalse(any(button.key=='google_sheets_open_monitor' for button in app.button))
            self.assertEqual(monitor_data(self.config.spreadsheet_id)['history'][0]['trigger'],'Automatic')
            self.assertEqual(store.order_notification_counts()['unread'],1)


if __name__=='__main__':unittest.main()
