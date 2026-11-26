"""Streamlit approval/notification workflows use mock Sheets and temporary SQLite."""
from pathlib import Path
import ast
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import test_google_sheets_sync as fixtures
import google_sheets_sync_ui as ui
import orders_store as store
import sqlite_db


class GoogleSyncUITests(unittest.TestCase):
    setUp=fixtures.GoogleSheetsSyncTests.setUp
    tearDown=fixtures.GoogleSheetsSyncTests.tearDown
    headers=fixtures.GoogleSheetsSyncTests.headers
    make_snapshot=fixtures.GoogleSheetsSyncTests.make_snapshot
    row=fixtures.GoogleSheetsSyncTests.row
    prepare=fixtures.GoogleSheetsSyncTests.prepare

    def test_deployment_preview_has_no_live_actions_and_never_imports(self):
        import os
        code="""import streamlit as st
st.session_state.authenticated=True
st.session_state.local_owner_email='synthetic-owner@example.test'
from google_sheets_sync_ui import render_google_sheets_sync
render_google_sheets_sync()
"""
        with patch.dict(os.environ,{'BIZMAR_PREVIEW_ONLY':'1'}), patch.object(ui.google_sheets_connection,'load_config',return_value=self.config), patch.object(ui.google_sheets_connection,'read_snapshot',return_value=self.make_snapshot([self.row()])) as reader, patch.object(ui.st,'secrets',{}):
            app=AppTest.from_string(code).run()
            reader.assert_not_called()
            app.button(key='google_sheets_readonly_preview').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(sqlite_db.all_rows('orders'),[])
            self.assertIsNone(store.google_sheets_sync_state(self.config.spreadsheet_id))
            self.assertFalse(any(b.label in ('Sync Now','Confirm Import and Enable Auto Sync') for b in app.button))
            with self.assertRaises(PermissionError):
                ui.google_sheets_sync.synchronize(self.config,force=True)

    def test_preview_is_readonly_and_live_sync_requires_both_approvals(self):
        script='''import streamlit as st
st.session_state.authenticated=True
st.session_state.local_owner_email='synthetic-owner@example.test'
from google_sheets_sync_ui import render_google_sheets_sync
render_google_sheets_sync()
'''
        snapshot=self.make_snapshot([self.row()])
        with patch.object(ui.google_sheets_connection,'load_config',return_value=self.config),patch.object(ui.google_sheets_connection,'read_snapshot',return_value=snapshot),patch.object(ui.st,'secrets',{}):
            app=AppTest.from_string(script).run()
            self.assertFalse(app.exception)
            self.assertIsNone(store.google_sheets_sync_state(self.config.spreadsheet_id))
            app.button(key='google_sheets_preview').click().run()
            self.assertEqual(sqlite_db.all_rows('orders'),[])
            self.assertTrue(app.button(key='google_sheets_confirm_import').disabled)
            signature=app.session_state['google_sheets_sync_preview'].signature[:12]
            app.checkbox(key='google_sheets_reviewed_'+signature).set_value(True).run()
            self.assertTrue(app.button(key='google_sheets_confirm_import').disabled)
            app.checkbox(key='google_sheets_live_approval_'+signature).set_value(True).run()
            self.assertFalse(app.button(key='google_sheets_confirm_import').disabled)
            app.button(key='google_sheets_confirm_import').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(sqlite_db.all_rows('orders')),1)
            self.assertEqual(store.order_notification_counts()['unread'],1)
            app.button(key='google_sheets_pause').click().run()
            self.assertIsNone(store.google_sheets_sync_state(self.config.spreadsheet_id)['confirmed_at'])
            self.assertFalse(app.exception)

    def test_actual_header_notification_actions_and_link(self):
        prepared=self.prepare(self.make_snapshot([self.row()]))
        store.activate_google_sheets_preview(self.config.spreadsheet_id,prepared.sheet_id,prepared.preview.records)
        notice=store.list_order_notifications()[0]
        root=Path(__file__).resolve().parents[1]
        tree=ast.parse((root/'app.py').read_text(encoding='utf-8'))
        functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('_open_notified_order','_render_order_notification')]
        notification_with=next(n for n in ast.walk(tree) if isinstance(n,ast.With) and any(isinstance(i.context_expr,ast.Name) and i.context_expr.id=='notification_col' for i in n.items))
        code='''import streamlit as st
st.session_state.authenticated=True
st.session_state.local_owner_email='synthetic-owner@example.test'
def navigate_to(target):st.session_state['test_target']=target
'''+ast.unparse(ast.Module(body=functions+notification_with.body,type_ignores=[]))
        with patch.object(ui.st,'secrets',{}):
            app=AppTest.from_string(code).run()
            self.assertFalse(app.exception)
            app.button(key=f'nour_header_notification_order_{notice["id"]}').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['test_target'],'Order Management')
            self.assertEqual(app.session_state['om_detail_open_id'],notice['order_id'])
            self.assertEqual(store.order_notification_counts()['unread'],0)

    def test_expired_owner_fragment_does_not_read_google(self):
        with patch.object(store,'current_owner',side_effect=PermissionError('Expired')),patch.object(ui.google_sheets_connection,'read_snapshot') as reader:
            app=AppTest.from_string('from google_sheets_sync_ui import render_google_sheets_sync\nrender_google_sheets_sync()').run()
            self.assertFalse(app.exception)
            reader.assert_not_called()
