import logging
import re
import socket
from collections.abc import Mapping

import httpx
import streamlit as st
from supabase import create_client
from supabase_auth.errors import AuthApiError

from uat_hardening import UATBlocked

logger = logging.getLogger(__name__)

GOOGLE_OIDC_REDIRECT_URI = "http://localhost:8501/oauth2callback"
GOOGLE_OIDC_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"


def google_oauth_configured(settings):
    if not isinstance(settings, Mapping):
        return False
    required = ("cookie_secret", "client_id", "client_secret")
    if not all(
        isinstance(settings.get(key), str) and settings[key].strip()
        for key in required
    ):
        return False
    return (
        len(settings["cookie_secret"]) >= 32
        and re.fullmatch(
            r"[0-9]+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com",
            settings["client_id"],
        ) is not None
        and settings.get("redirect_uri") == GOOGLE_OIDC_REDIRECT_URI
        and settings.get("server_metadata_url") == GOOGLE_OIDC_METADATA_URL
    )


def is_authorized_google_user(user, configured_owner_email):
    if user is None or not user.is_logged_in:
        return False
    email = str(user.get("email", "")).strip().lower()
    return (
        user.get("email_verified") is True
        and email == configured_owner_email.strip().lower()
    )


def _transport_failure_details(error):
    pending = [error]
    visited = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        if isinstance(current, socket.gaierror):
            return "DNS resolution", current.errno
        pending.extend(
            cause
            for cause in (current.__cause__, current.__context__)
            if cause is not None
        )
    return type(error).__name__, getattr(error, "errno", None)


def _log_transport_failure(operation, error):
    failure, error_number = _transport_failure_details(error)
    logger.warning(
        "Supabase %s transport failure (%s; errno=%s).",
        operation,
        failure,
        error_number,
    )


def get_auth_client():
    from uat_hardening import check_endpoint

    check_endpoint(st.secrets["SUPABASE_URL"])
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_ANON_KEY"],
    )


def owner_email():
    return st.secrets["OWNER_EMAIL"].strip().lower()


def _clear_session():
    st.session_state.pop("supabase_access_token", None)
    st.session_state.pop("supabase_refresh_token", None)
    st.session_state.authenticated = False


def _save_session(session):
    st.session_state.supabase_access_token = session.access_token
    st.session_state.supabase_refresh_token = session.refresh_token


def _verified_owner(user):
    if user is None:
        return False
    email = (user.email or "").strip().lower()
    return email == owner_email() and bool(user.email_confirmed_at)


def is_authorized_supabase_user():
    token = st.session_state.get("supabase_access_token")
    if not token:
        return False

    try:
        client = get_auth_client()
    except UATBlocked:
        logger.warning("Supabase session verification blocked by the deployment endpoint policy.")
        _clear_session()
        return False
    try:
        response = client.auth.get_user(token)
    except AuthApiError as error:
        refresh_token = st.session_state.get("supabase_refresh_token")
        if not refresh_token:
            _clear_session()
            return False
        try:
            response = client.auth.refresh_session(refresh_token)
        except (AuthApiError, httpx.HTTPError) as refresh_error:
            if isinstance(refresh_error, httpx.HTTPError):
                _log_transport_failure("session refresh", refresh_error)
            else:
                logger.warning(
                    "Supabase session refresh rejected (%s).",
                    str(getattr(refresh_error, "code", "") or "provider_error"),
                )
            _clear_session()
            return False
        if not response.session:
            _clear_session()
            return False
        _save_session(response.session)
    except httpx.HTTPError as error:
        _log_transport_failure("session verification", error)
        return False

    if not _verified_owner(response.user):
        _clear_session()
        return False
    return True


def _login_error(error):
    if isinstance(error, AuthApiError):
        code = str(getattr(error, "code", "") or "").lower()
        status = getattr(error, "status", None)
        if code == "email_not_confirmed" or "email not confirmed" in str(error).lower():
            return "Please verify your email before signing in."
        if code in {"invalid_credentials", "invalid_grant"}:
            return "Email or password is incorrect."
        if status == 429:
            return "Too many login attempts. Please wait and try again."
        logger.warning("Supabase sign-in rejected (%s).", code or "provider_error")
        return "Unable to sign in. Please check the account and try again."
    if isinstance(error, httpx.HTTPError):
        failure, error_number = _transport_failure_details(error)
        logger.warning(
            "Supabase sign-in transport failure (%s; errno=%s).",
            failure,
            error_number,
        )
        if failure == "DNS resolution":
            return (
                "The authentication server could not be found. Check the "
                "configured Supabase project and your network DNS, then try again."
            )
        return "Authentication service is temporarily unavailable. Please try again."
    if isinstance(error, UATBlocked):
        logger.warning("Supabase sign-in blocked by the deployment endpoint policy.")
        return "Authentication is not enabled for this deployment. Contact the administrator."
    if isinstance(error, (KeyError, ValueError)):
        logger.error("Supabase sign-in configuration is incomplete (%s).", type(error).__name__)
        return "Authentication is not configured correctly. Contact the administrator."
    raise TypeError("Unexpected Supabase sign-in error type.")


def sign_in_with_email(email, password):
    email = email.strip().lower()
    if email != owner_email():
        return False, "Email or password is incorrect."

    try:
        response = get_auth_client().auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
    except (AuthApiError, httpx.HTTPError, UATBlocked, KeyError, ValueError) as error:
        return False, _login_error(error)

    if not response.session:
        return False, "Email or password is incorrect."
    if not _verified_owner(response.user):
        return False, "Please verify your email before signing in."
    _save_session(response.session)
    return True, "Login successful."


def create_owner_account(name, email, password):
    from uat_hardening import blocked

    blocked()


def sign_out_email():
    access_token = st.session_state.get("supabase_access_token")
    refresh_token = st.session_state.get("supabase_refresh_token")
    if access_token:
        try:
            client = get_auth_client()
            client.auth.set_session(access_token, refresh_token or "")
            client.auth.sign_out({"scope": "local"})
        except (AuthApiError, httpx.HTTPError, UATBlocked, KeyError, ValueError) as error:
            logger.warning(
                "Supabase sign-out could not revoke the current session (%s).",
                type(error).__name__,
            )
    _clear_session()
