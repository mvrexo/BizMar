"""Preview deployment uses mock authentication and disposable synthetic records."""
from contextlib import closing
from pathlib import Path
import os
import importlib.util
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import sqlite_db
from uat_fixture import build

ROOT = Path(__file__).resolve().parents[1]


class PreviewModeTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('supabase'), 'Use the configured runtime with Supabase installed.')
    def test_owner_verification_rejects_unconfirmed_and_other_users(self):
        from types import SimpleNamespace
        import auth
        state={'supabase_access_token':'synthetic-token'}
        with patch('streamlit.session_state',state), patch('streamlit.secrets',{'OWNER_EMAIL':'synthetic-owner@example.test'}), patch.object(auth,'get_auth_client') as client:
            for email,confirmed,expected in (('synthetic-owner@example.test',True,True),('other@example.test',True,False),('synthetic-owner@example.test',False,False)):
                client.return_value.auth.get_user.return_value=SimpleNamespace(user=SimpleNamespace(email=email,email_confirmed_at=confirmed))
                self.assertEqual(auth.is_authorized_supabase_user(),expected)

    @unittest.skipUnless(importlib.util.find_spec('supabase'), 'Use the configured runtime with Supabase installed.')
    def test_actual_pages_with_mocked_owner_and_readonly_database(self):
        with tempfile.TemporaryDirectory(prefix='bizmar-preview-check-') as temp:
            database = Path(temp)/'preview.sqlite3'
            build(database)
            with closing(sqlite3.connect(database)) as connection:
                connection.execute('CREATE TABLE owner_profiles (email TEXT PRIMARY KEY, display_name TEXT, business_name TEXT, phone TEXT, avatar BLOB)')
                connection.execute('CREATE TABLE owner_settings (email TEXT PRIMARY KEY, preferences TEXT, logo BLOB)')
                connection.commit()
            original = sqlite3.connect
            def readonly(*args, **kwargs):
                connection = original(*args, **kwargs)
                connection.execute('PRAGMA query_only=ON')
                return connection
            secrets = dict(OWNER_EMAIL='synthetic-owner@example.test', ADMIN_PASSWORD='synthetic-password-only', auth={})
            with patch.object(sqlite_db,'DB_PATH',database), patch('owner_profile.DATABASE',database), \
                 patch.dict(os.environ,{'BIZMAR_PREVIEW_ONLY':'1','BIZMAR_AUTH_MODE':'supabase'}), \
                 patch('sqlite3.connect',side_effect=readonly), patch('streamlit.secrets',secrets), \
                 patch('auth.is_authorized_supabase_user',return_value=True):
                for route in ('Overview','Order Management','Products','Customers','Payments','Notifications','Data Import','Messages'):
                    with self.subTest(route=route):
                        app = AppTest.from_file(str(ROOT/'app.py'))
                        app.session_state['nour_current_page'] = route
                        app.run(timeout=40)
                        self.assertFalse(app.exception, [e.message for e in app.exception])
                        if route == 'Overview':
                            self.assertGreaterEqual(len(app.metric),3)
                            self.assertTrue(all(m.value for m in app.metric))
                        self.assertFalse(any(b.label in ('Sync Now','Confirm Import and Enable Auto Sync') for b in app.button))
                with closing(sqlite_db._connect()) as connection:
                    with self.assertRaises(sqlite3.OperationalError):
                        connection.execute("UPDATE products SET name='forbidden'")
                    self.assertEqual(connection.execute('SELECT count(*) FROM orders').fetchone()[0],6)
                    self.assertEqual(connection.execute('SELECT count(*) FROM google_sheets_sync_state').fetchone()[0],0)
                with patch('auth.is_authorized_supabase_user',return_value=False):
                    login = AppTest.from_file(str(ROOT/'app.py')).run(timeout=40)
                    self.assertFalse(login.exception)
                    self.assertTrue(any('Log In' in b.label for b in login.button))
                    self.assertFalse(any(b.key=='nour_header_nav_profile' for b in login.button))

    def test_sync_migration_is_additive_and_idempotent(self):
        from orders_schema import migrate_google_sheets
        with closing(sqlite3.connect(':memory:')) as connection:
            connection.row_factory=sqlite3.Row
            connection.execute('CREATE TABLE orders(id INTEGER PRIMARY KEY, notes TEXT)')
            connection.execute("INSERT INTO orders VALUES (1,'preserve')")
            connection.execute('CREATE TABLE app_metadata(key TEXT PRIMARY KEY,value TEXT)')
            migrate_google_sheets(connection)
            migrate_google_sheets(connection)
            self.assertEqual(tuple(connection.execute('SELECT * FROM orders').fetchone()),(1,'preserve'))
            self.assertEqual(connection.execute('SELECT count(*) FROM google_sheets_sync_state').fetchone()[0],0)


if __name__=='__main__':
    unittest.main()
