import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]

LOGIN_SOURCE = '''
import streamlit as st
from login_ui import render_login

def sign_in(email, password):
    st.session_state.login_probe = (email, password)
    return False, "Email or password is incorrect."

render_login(sign_in, google_enabled=True)
'''


class LoginUiTests(unittest.TestCase):
    def test_app_starts_with_supabase_secrets_but_without_google_oauth(self):
        secrets = {
            'SUPABASE_URL': 'https://synthetic-project.supabase.co',
            'SUPABASE_ANON_KEY': 'synthetic-anon-key',
            'OWNER_EMAIL': 'owner@example.test',
        }
        with patch('streamlit.secrets', secrets):
            app = AppTest.from_file(str(ROOT / 'app.py')).run(timeout=60)

        self.assertFalse(app.exception, [str(error.value) for error in app.exception])
        self.assertIn('Log In →', [button.label for button in app.button])
        self.assertNotIn('Continue with Google', [button.label for button in app.button])

    def test_login_has_no_prefilled_email_and_submits_through_form(self):
        app = AppTest.from_string(LOGIN_SOURCE).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_input(key='login_email').value, '')
        self.assertEqual(app.text_input(key='login_password').value, '')
        self.assertIn('Continue with Google', [button.label for button in app.button])
        self.assertNotIn('Forgot your password?', [item.value for item in app.markdown])
        self.assertNotIn('Resend confirmation email', [item.value for item in app.markdown])
        self.assertIn('Log In →', [button.label for button in app.button])
        self.assertTrue(any('data:image/svg+xml;base64,' in item.value for item in app.markdown))

        with patch('streamlit.login') as login:
            next(button for button in app.button if button.key == 'bizmar_google_login').click().run()
        self.assertFalse(app.exception)
        login.assert_called_once_with()

        app.text_input(key='login_email').set_value('owner@example.test')
        app.text_input(key='login_password').set_value('synthetic-password')
        next(button for button in app.button if button.key == 'login_submit').click().run()

        self.assertFalse(app.exception)
        self.assertEqual(
            app.session_state['login_probe'],
            ('owner@example.test', 'synthetic-password'),
        )
        self.assertEqual(app.error[-1].value, 'Email or password is incorrect.')

    def test_google_button_is_hidden_when_oauth_is_not_configured(self):
        source = LOGIN_SOURCE.replace(
            'google_enabled=True',
            'google_enabled=False',
        )
        app = AppTest.from_string(source).run()
        self.assertFalse(app.exception)
        self.assertNotIn('Continue with Google', [button.label for button in app.button])


if __name__ == '__main__':
    unittest.main()
