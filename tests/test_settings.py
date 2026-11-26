"""Settings regressions against disposable databases; no live credentials or network."""
from contextlib import closing
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import ast
import unittest
import zipfile
import pandas as pd
from PIL import Image
from streamlit.testing.v1 import AppTest
import sqlite_db
import owner_profile
import settings_store
import settings_ui
import local_auth


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / 'synthetic.sqlite3'
        self.identity = SimpleNamespace(session_state={'authenticated': True, 'local_owner_email': 'owner@example.test'}, secrets={'OWNER_EMAIL': 'owner@example.test'})
        for module, name, value in [(sqlite_db, 'DB_PATH', self.database),
                                    (owner_profile, 'DATABASE', self.database),
                                    (owner_profile, 'st', self.identity),
                                    (settings_ui, 'st', self.identity)]:
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        sqlite_db.initialize()

    def test_persistence_owner_isolation_and_guard(self):
        values = settings_store.load()
        values.update(category='Services', deadlines=False, prefix='BM')
        picture = BytesIO()
        Image.new('RGB', (10, 10), 'green').save(picture, 'PNG')
        settings_store.save(values, picture)
        self.assertEqual(settings_store.load(), values)
        self.assertTrue(settings_store.business_logo().startswith(b'\x89PNG'))
        self.identity.session_state['local_owner_email'] = 'other@example.test'
        self.assertEqual(settings_store.load()['prefix'], 'ORD')
        self.assertIsNone(settings_store.business_logo())
        self.identity.session_state['authenticated'] = False
        with self.assertRaises(PermissionError):
            settings_store.load()

    def test_validation_is_atomic(self):
        original = settings_store.load()
        with self.assertRaises(ValueError):
            settings_store.save({**original, 'prefix': 'invalid prefix'})
        with self.assertRaises(ValueError):
            settings_store.save(original, BytesIO(b'not an image'))
        with self.assertRaises(ValueError):
            settings_store.validate_phone('123abc')
        self.assertEqual(settings_store.load(), original)

    def test_new_defaults_preserve_history_and_block_cancellation(self):
        customer = sqlite_db.add('customers', {'name': 'Test', 'phone': '0123456789'})
        payload = {'customer_id': customer['id'], 'ordered_at': '2026-10-25', 'due_date': '2026-10-28'}
        old = sqlite_db.add('orders', payload)
        values = {**settings_store.DEFAULTS, 'prefix': 'BM', 'status': 'Confirmed', 'cancellation': False}
        settings_store.save(values)
        with patch.object(settings_store, 'runtime', return_value=values):
            new = sqlite_db.add('orders', payload)
            self.assertTrue(new['order_code'].startswith('BM'))
            self.assertEqual(new['status'], 'Confirmed')
            with self.assertRaises(ValueError):
                sqlite_db.edit('orders', new['id'], {'status': 'Cancelled'})
        historical = next(row for row in sqlite_db.all_rows('orders') if row['id'] == old['id'])
        self.assertEqual(historical['order_code'], old['order_code'])
        self.assertEqual(historical['status'], old['status'])

    def test_export_allowlist_and_identity(self):
        settings_store.save(settings_store.load())
        owner_profile.save_profile('Owner', 'Business', '')
        tables = settings_ui.export_tables()
        self.assertEqual(set(tables), {'products', 'customers', 'orders', 'order_items', 'payments'})
        with zipfile.ZipFile(BytesIO(settings_ui.csv_archive({'customers': pd.DataFrame([{'name': '=1+1'}])}))) as archive:
            self.assertIn("'=1+1", archive.read('customers.csv').decode('utf-8-sig'))
        self.identity.session_state['local_owner_email'] = 'other@example.test'
        with self.assertRaises(PermissionError):
            settings_ui.export_tables()

    def test_password_requires_current_password(self):
        with patch.object(local_auth, 'DATABASE', self.database):
            local_auth.provision('owner@example.test', 'original-password-123')
            with self.assertRaises(ValueError):
                local_auth.change_password('owner@example.test', 'wrong', 'replacement-password-123')
            self.assertTrue(local_auth.verify('owner@example.test', 'original-password-123'))
            local_auth.change_password('owner@example.test', 'original-password-123', 'replacement-password-123')
            self.assertFalse(local_auth.verify('owner@example.test', 'original-password-123'))
            self.assertTrue(local_auth.verify('owner@example.test', 'replacement-password-123'))

    def test_settings_ui_renders_and_saves(self):
        code = '''import streamlit as st
from settings_ui import render_settings
st.session_state.authenticated = True
st.session_state.local_owner_email = 'owner@example.test'
render_settings(lambda: None)
'''
        # Restore real Streamlit for the view; profile identity stays a test double.
        import streamlit
        with patch.object(settings_ui, 'st', streamlit):
            app = AppTest.from_string(code).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.tabs), 6)
            app.text_input[0].set_value('New Owner')
            next(button for button in app.button if button.label == 'Save account').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(owner_profile.get_profile()['display_name'], 'New Owner')

    def test_notification_toggles_hide_real_sections(self):
        app = AppTest.from_string('''import streamlit as st
import pandas as pd
from datetime import datetime
from settings_store import DEFAULTS
from production_alert_ui import render_production_alerts
st.session_state.bizmar_preferences = {**DEFAULTS, 'deadlines': False, 'pending_orders': False, 'overdue_payments': False}
render_production_alerts(pd.DataFrame(columns=['id', 'status', 'due_date']), pd.DataFrame(), pd.DataFrame(), lambda route: None, now=datetime.fromisoformat('2026-10-25T12:00:00+08:00'))
''').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.subheader), 3)

    def test_app_settings_branch_loads_data_tools_directly(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8-sig'))
        branch = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                      and isinstance(node.test, ast.Compare)
                      and isinstance(node.test.left, ast.Name) and node.test.left.id == 'page'
                      and any(isinstance(value, ast.Constant) and value.value == 'Settings' for value in node.test.comparators))
        code = '''import streamlit as st
st.session_state.authenticated = True
st.session_state.local_owner_email = 'owner@example.test'
sign_out_email = lambda: None
LOCAL_AUTH = False
render_alert_settings = lambda: None
''' + '\n'.join(ast.unparse(node) for node in branch.body)
        import streamlit
        with patch.object(settings_ui, 'st', streamlit):
            app = AppTest.from_string(code).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.tabs), 6)
        self.assertTrue(any('Upload one Excel' in upload.label for upload in app.get('file_uploader')))

    def test_new_order_always_pending_despite_legacy_default(self):
        # A legacy Confirmed preference must not introduce an intermediate status.
        import streamlit
        code = '''import streamlit as st
from settings_store import DEFAULTS
from quick_order import render_quick_order
st.session_state.bizmar_preferences = {**DEFAULTS, 'status': 'Confirmed'}
render_quick_order()
'''
        app = AppTest.from_string(code).run()
        self.assertFalse(app.exception)
        scope = 'om_add_' + app.session_state['qo_token']
        self.assertEqual(app.session_state[scope + '_status'], 'Pending')

    def test_appearance_persistence_and_validation(self):
        preferences = {**settings_store.load(), 'theme': 'Dark', 'language': 'Bahasa Melayu', 'date_format': 'YYYY-MM-DD'}
        settings_store.save(preferences)
        self.assertEqual(settings_store.load(), preferences)
        with self.assertRaises(ValueError):
            settings_store.save({**preferences, 'currency': 'USD'})
        with self.assertRaises(ValueError):
            settings_store.save({**preferences, 'date_format': 'invalid'})

    def test_display_helpers_preserve_values(self):
        from datetime import date
        import display_preferences as display
        import plotly.graph_objects as go
        preferences = {**settings_store.DEFAULTS, 'language': 'Bahasa Melayu', 'theme': 'Dark', 'date_format': 'MM/DD/YYYY'}
        with patch.object(display, 'runtime', return_value=preferences):
            self.assertEqual(display.tr('Settings'), 'Tetapan')
            self.assertEqual(display.format_date(date(2026, 10, 25)), '10/25/2026')
            self.assertEqual(display.date_input_format(), 'MM/DD/YYYY')
            fig = go.Figure(go.Bar(x=['A'], y=[123.45]))
            display.style_figure(fig)
            self.assertEqual(list(fig.data[0].y), [123.45])
            from forest_theme import tokens
            self.assertEqual(fig.layout.font.color, tokens()['text'])

    def test_malay_settings_and_navigation_render(self):
        settings_store.save({**settings_store.load(), 'language': 'Bahasa Melayu', 'theme': 'Dark'})
        code = '''import streamlit as st
from settings_ui import render_settings
from settings_store import load
from navigation import render_primary_navigation
st.session_state.authenticated = True
st.session_state.local_owner_email = 'owner@example.test'
st.session_state.bizmar_preferences = load()
render_primary_navigation()
render_settings(lambda: None)
'''
        import streamlit
        with patch.object(settings_ui, 'st', streamlit):
            app = AppTest.from_string(code).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.tabs[0].label, 'Tetapan Akaun')
        self.assertEqual(app.sidebar.button[0].label, 'Papan Pemuka')

    def test_appearance_form_saves_choices(self):
        import streamlit
        code = '''import streamlit as st
from settings_ui import render_settings
st.session_state.authenticated = True
st.session_state.local_owner_email = 'owner@example.test'
render_settings(lambda: None)
'''
        with patch.object(settings_ui, 'st', streamlit):
            app = AppTest.from_string(code).run()
            app.toggle(key='settings_dark_mode').set_value(True).run()
            app.selectbox(key='settings_language').set_value('Bahasa Melayu').run()
            app.selectbox(key='settings_date_format').set_value('YYYY-MM-DD').run()
        self.assertFalse(app.exception)
        saved = settings_store.load()
        self.assertEqual((saved['theme'], saved['language'], saved['date_format'], saved['currency']),
                         ('Dark', 'Bahasa Melayu', 'YYYY-MM-DD', 'MYR'))


if __name__ == '__main__':
    unittest.main()
