import unittest
import socket
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import auth
from supabase_auth.errors import AuthApiError
from uat_hardening import UATBlocked


class SessionState(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key, value):
        self[key] = value


def verified_user(email='owner@example.test'):
    return SimpleNamespace(email=email, email_confirmed_at='2026-01-01T00:00:00Z')


def auth_response(*, user=None, with_session=True):
    session = SimpleNamespace(access_token='synthetic-access', refresh_token='synthetic-refresh') if with_session else None
    return SimpleNamespace(user=user, session=session)


class SupabaseAuthTests(unittest.TestCase):
    def setUp(self):
        self.state = SessionState()
        self.state_patch = patch.object(auth.st, 'session_state', self.state)
        self.state_patch.start()
        self.owner_patch = patch.object(auth, 'owner_email', return_value='owner@example.test')
        self.owner_patch.start()

    def tearDown(self):
        self.owner_patch.stop()
        self.state_patch.stop()

    def test_sign_in_persists_tokens_only_for_verified_owner(self):
        api = Mock()
        api.sign_in_with_password.return_value = auth_response(user=verified_user())
        with patch.object(auth, 'get_auth_client', return_value=SimpleNamespace(auth=api)):
            self.assertEqual(auth.sign_in_with_email(' OWNER@example.test ', 'secret'), (True, 'Login successful.'))
        self.assertEqual(self.state['supabase_access_token'], 'synthetic-access')
        self.assertEqual(self.state['supabase_refresh_token'], 'synthetic-refresh')
        api.sign_in_with_password.assert_called_once_with({
            'email': 'owner@example.test',
            'password': 'secret',
        })

    def test_invalid_password_and_unverified_email_have_distinct_safe_messages(self):
        api = Mock()
        api.sign_in_with_password.side_effect = AuthApiError('Invalid login credentials', 400, 'invalid_credentials')
        with patch.object(auth, 'get_auth_client', return_value=SimpleNamespace(auth=api)):
            success, message = auth.sign_in_with_email('owner@example.test', 'wrong')
        self.assertFalse(success)
        self.assertEqual(message, 'Email or password is incorrect.')

        api.sign_in_with_password.side_effect = AuthApiError('Email not confirmed', 400, 'email_not_confirmed')
        with patch.object(auth, 'get_auth_client', return_value=SimpleNamespace(auth=api)):
            success, message = auth.sign_in_with_email('owner@example.test', 'secret')
        self.assertFalse(success)
        self.assertIn('verify your email', message)
        self.assertNotIn('wrong', message)

    def test_endpoint_policy_failure_is_not_reported_as_bad_credentials(self):
        with patch.object(auth, 'get_auth_client', side_effect=UATBlocked('blocked endpoint')):
            success, message = auth.sign_in_with_email('owner@example.test', 'secret')
        self.assertFalse(success)
        self.assertIn('not enabled for this deployment', message)
        self.assertNotIn('incorrect', message)

    def test_endpoint_policy_failure_clears_supabase_session(self):
        self.state.supabase_access_token = 'synthetic-access'
        self.state.supabase_refresh_token = 'synthetic-refresh'
        self.state.authenticated = True
        with patch.object(auth, 'get_auth_client', side_effect=UATBlocked('blocked endpoint')):
            self.assertFalse(auth.is_authorized_supabase_user())
        self.assertNotIn('supabase_access_token', self.state)
        self.assertNotIn('supabase_refresh_token', self.state)
        self.assertFalse(self.state['authenticated'])

    def test_google_oauth_requires_the_local_callback_and_complete_credentials(self):
        settings = {
            'redirect_uri': auth.GOOGLE_OIDC_REDIRECT_URI,
            'cookie_secret': 'c' * 40,
            'client_id': '123456789012-test.apps.googleusercontent.com',
            'client_secret': 'synthetic-client-secret',
            'server_metadata_url': auth.GOOGLE_OIDC_METADATA_URL,
        }
        self.assertTrue(auth.google_oauth_configured(settings))
        for key, value in (
            ('redirect_uri', 'http://localhost:8502/oauth2callback'),
            ('server_metadata_url', 'https://unapproved.invalid/openid'),
            ('cookie_secret', 'short'),
            ('client_id', 'not-a-google-client-id'),
            ('client_secret', ''),
        ):
            invalid_settings = {**settings, key: value}
            with self.subTest(key=key):
                self.assertFalse(auth.google_oauth_configured(invalid_settings))
        self.assertFalse(auth.google_oauth_configured(None))

    def test_google_session_requires_verified_configured_owner(self):
        def google_user(email, *, verified=True, logged_in=True):
            claims = {'email': email, 'email_verified': verified}
            return SimpleNamespace(is_logged_in=logged_in, get=claims.get)

        self.assertTrue(
            auth.is_authorized_google_user(
                google_user('OWNER@example.test'),
                'owner@example.test',
            )
        )
        self.assertFalse(
            auth.is_authorized_google_user(
                google_user('other@example.test'),
                'owner@example.test',
            )
        )
        self.assertFalse(
            auth.is_authorized_google_user(
                google_user('owner@example.test', verified=False),
                'owner@example.test',
            )
        )
        self.assertFalse(
            auth.is_authorized_google_user(
                google_user('owner@example.test', logged_in=False),
                'owner@example.test',
            )
        )
        self.assertFalse(
            auth.is_authorized_google_user(None, 'owner@example.test')
        )

    def test_dns_failure_has_safe_diagnostic_and_actionable_message(self):
        api = Mock()
        transport_error = httpx.ConnectError(
            'connection failed',
            request=httpx.Request('POST', 'https://synthetic.invalid/auth/v1/token'),
        )
        transport_error.__cause__ = socket.gaierror(11001, 'getaddrinfo failed')
        api.sign_in_with_password.side_effect = transport_error
        with patch.object(auth, 'get_auth_client', return_value=SimpleNamespace(auth=api)):
            with patch.object(auth.logger, 'warning') as warning:
                success, message = auth.sign_in_with_email('owner@example.test', 'secret')
        self.assertFalse(success)
        self.assertIn('network DNS', message)
        self.assertNotIn('synthetic.invalid', message)
        warning.assert_called_once()
        self.assertIn('DNS resolution', warning.call_args.args)
        self.assertEqual(warning.call_args.args[-1], 11001)

    def test_unrecognized_email_is_rejected_without_supabase_request(self):
        with patch.object(auth, 'get_auth_client') as get_client:
            result = auth.sign_in_with_email('other@example.test', 'secret')
        self.assertEqual(result, (False, 'Email or password is incorrect.'))
        get_client.assert_not_called()

    def test_unconfirmed_or_non_owner_supabase_users_are_denied(self):
        api = Mock()
        api.sign_in_with_password.return_value = auth_response(
            user=SimpleNamespace(email='owner@example.test', email_confirmed_at=None)
        )
        with patch.object(auth, 'get_auth_client', return_value=SimpleNamespace(auth=api)):
            success, message = auth.sign_in_with_email('owner@example.test', 'secret')
        self.assertFalse(success)
        self.assertIn('verify your email', message)
        self.assertNotIn('supabase_access_token', self.state)

        self.state.supabase_access_token = 'valid-token'
        self.state.supabase_refresh_token = 'refresh-token'
        self.state.authenticated = True
        api.get_user.return_value = SimpleNamespace(user=verified_user('other@example.test'))
        with patch.object(auth, 'get_auth_client', return_value=SimpleNamespace(auth=api)):
            self.assertFalse(auth.is_authorized_supabase_user())
        self.assertNotIn('supabase_access_token', self.state)
        self.assertFalse(self.state['authenticated'])

    def test_expired_access_token_uses_refresh_token_and_updates_session(self):
        api = Mock()
        api.get_user.side_effect = AuthApiError('JWT expired', 401, 'bad_jwt')
        api.refresh_session.return_value = auth_response(user=verified_user())
        self.state.supabase_access_token = 'old-access'
        self.state.supabase_refresh_token = 'old-refresh'
        with patch.object(auth, 'get_auth_client', return_value=SimpleNamespace(auth=api)):
            self.assertTrue(auth.is_authorized_supabase_user())
        api.refresh_session.assert_called_once_with('old-refresh')
        self.assertEqual(self.state['supabase_access_token'], 'synthetic-access')
        self.assertEqual(self.state['supabase_refresh_token'], 'synthetic-refresh')

    def test_failed_network_refresh_clears_unverified_session(self):
        api = Mock()
        api.get_user.side_effect = AuthApiError('JWT expired', 401, 'bad_jwt')
        api.refresh_session.side_effect = httpx.ConnectError('offline')
        self.state.supabase_access_token = 'old-access'
        self.state.supabase_refresh_token = 'old-refresh'
        with patch.object(auth, 'get_auth_client', return_value=SimpleNamespace(auth=api)):
            self.assertFalse(auth.is_authorized_supabase_user())
        self.assertNotIn('supabase_access_token', self.state)
        self.assertNotIn('supabase_refresh_token', self.state)
        self.assertFalse(self.state['authenticated'])

    def test_logout_revokes_local_supabase_session_and_clears_tokens(self):
        api = Mock()
        self.state.supabase_access_token = 'synthetic-access'
        self.state.supabase_refresh_token = 'synthetic-refresh'
        self.state.authenticated = True
        with patch.object(auth, 'get_auth_client', return_value=SimpleNamespace(auth=api)):
            auth.sign_out_email()
        api.set_session.assert_called_once_with('synthetic-access', 'synthetic-refresh')
        api.sign_out.assert_called_once_with({'scope': 'local'})
        self.assertNotIn('supabase_access_token', self.state)
        self.assertNotIn('supabase_refresh_token', self.state)
        self.assertFalse(self.state['authenticated'])


if __name__ == '__main__':
    unittest.main()
