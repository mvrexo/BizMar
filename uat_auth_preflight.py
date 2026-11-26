"""Offline, explicit UAT authentication validation. No Streamlit or network imports."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import tomllib
from urllib.parse import urlsplit

CALLBACK = 'http://localhost:8501/oauth2callback'
METADATA = 'https://accounts.google.com/.well-known/openid-configuration'

class PreflightError(ValueError):
    pass


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and not any(
        word in value.upper() for word in ('REPLACE_', 'PLACEHOLDER', 'YOUR_TEST_', 'EXAMPLE.COM'))


def validate_configuration(secrets, approval):
    """Return no credentials, tokens, IDs or email addresses, even on failure."""
    def fail(message):
        raise PreflightError(message)
    if not isinstance(secrets, dict) or not isinstance(approval, dict):
        fail('Private configuration must contain TOML tables.')
    if approval.get('environment') != 'dedicated-uat' or approval.get('owner_attests_no_production_data_access') is not True:
        fail('Owner test-service approval is missing.')
    approved_url=approval.get('approved_supabase_url')
    approved_client=approval.get('approved_google_client_id')
    if not _text(approved_url) or not _text(approved_client):
        fail('Explicit test endpoint and Google client approval are required.')
    if set(approval) != {'environment','owner_attests_no_production_data_access','approved_supabase_url','approved_google_client_id',
                         'google_client_mode','owner_approves_existing_google_client','owner_attests_separate_development_cookie_secret'}:
        fail('Approval configuration has unexpected or missing keys.')
    mode=approval['google_client_mode']
    if mode not in ('dedicated-test','owner-approved-existing'):
        fail('Choose Dedicated Test Client or Owner-Approved Existing Client explicitly.')
    shared=mode=='owner-approved-existing'
    if approval['owner_approves_existing_google_client'] is not shared:
        fail('Shared Google client use requires explicit approval; dedicated mode must not declare shared-client approval.')
    if approval['owner_attests_separate_development_cookie_secret'] is not True:
        fail('An independent development cookie secret must be explicitly confirmed for either client mode.')

    required={'SUPABASE_URL','SUPABASE_ANON_KEY','OWNER_EMAIL','ADMIN_PASSWORD','auth'}
    if not required.issubset(secrets) or set(secrets)-(required|{'google_sheets'}):
        fail('Use exactly the required top-level UAT secrets; privileged keys and alternate providers are not allowed.')
    if 'google_sheets' in secrets:
        sheets=secrets['google_sheets']
        if not isinstance(sheets,dict) or set(sheets)-{'spreadsheet_id','worksheet_name','service_account_file','sync_interval_seconds'} or not {'spreadsheet_id','worksheet_name','service_account_file'}.issubset(sheets):
            fail('Google Sheets must use only the dedicated read-only connection settings.')
        if any(not _text(sheets.get(k)) for k in ('spreadsheet_id','worksheet_name','service_account_file')):
            fail('Google Sheets read-only configuration is incomplete.')
        key_path=Path(sheets['service_account_file'])
        if not key_path.is_absolute() or key_path.resolve().is_relative_to(Path(__file__).resolve().parent):
            fail('Keep the Google service-account JSON outside the project.')
        interval=sheets.get('sync_interval_seconds',30)
        if isinstance(interval,bool) or not isinstance(interval,int) or not 30<=interval<=3600:
            fail('Google Sheets poll interval must be an integer from 30 to 3600 seconds.')
    for key in required-{'auth'}:
        if not _text(secrets.get(key)):
            fail('Required top-level UAT configuration is missing or still a placeholder.')
    if secrets['SUPABASE_URL']!=approved_url:
        fail('Supabase endpoint is not the explicitly approved test endpoint.')
    parts=urlsplit(approved_url)
    if parts.scheme!='https' or not re.fullmatch(r'[a-z0-9]{20}\.supabase\.co',parts.netloc) or parts.path not in ('','/') or parts.query or parts.fragment or approved_url.endswith('/'):
        fail('Use a canonical dedicated Supabase cloud HTTPS project URL, without a trailing slash.')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',secrets['OWNER_EMAIL']):
        fail('OWNER_EMAIL must identify the dedicated verified test Owner.')
    if len(secrets['ADMIN_PASSWORD'])<24:
        fail('Use a separate development ADMIN_PASSWORD of at least 24 characters.')
    key=secrets['SUPABASE_ANON_KEY']
    if key.startswith('sb_publishable_'):
        if len(key)<30:fail('The test publishable key is malformed.')
    else:
        try:
            pieces=key.split('.')
            if len(pieces)!=3:raise ValueError()
            payload=json.loads(base64.urlsafe_b64decode(pieces[1]+'='*(-len(pieces[1])%4)))
            if payload.get('role')!='anon' or payload.get('ref')!=parts.hostname.split('.')[0]:raise ValueError()
        except Exception:
            fail('Use a test publishable key or test anon JWT bound to the approved project; privileged keys are forbidden.')
    auth=secrets.get('auth')
    if not isinstance(auth,dict) or set(auth)!={'redirect_uri','cookie_secret','client_id','client_secret','server_metadata_url'}:
        fail('The default Google [auth] table must contain exactly the required OIDC keys.')
    if any(not _text(auth.get(key)) for key in auth):fail('Google OIDC configuration is missing or still a placeholder.')
    if auth['redirect_uri']!=CALLBACK:fail('Google callback must match the guarded localhost:8501 application callback exactly.')
    if auth['server_metadata_url']!=METADATA:fail('Google discovery must use the approved Google OpenID metadata URL.')
    if auth['client_id']!=approved_client or not re.fullmatch(r'[0-9]+-[a-zA-Z0-9_-]+\.apps\.googleusercontent\.com',approved_client):
        fail('Google client does not match the explicitly approved test client.')
    if len(auth['cookie_secret'])<32:fail('Use a separate development cookie_secret of at least 32 characters.')
    return {'status':'passed', 'configuration':'dedicated Supabase test project',
            'google_client_mode':mode, 'reduced_authentication_isolation':shared,
            'warning':'Google OAuth client is shared with production; authentication isolation is reduced.' if shared else None,
            'callback':CALLBACK,'live_authentication_tested':False}


def preflight(root=None):
    root=Path(root if root is not None else Path(__file__).parent).resolve()
    if root!=Path(__file__).resolve().parent:
        raise PreflightError('Preflight must use its own isolated development source directory.')
    # Paths only: never inspect global/production secret values or merge settings.
    private=root/'.streamlit'
    secret_path=private/'secrets.toml'
    approval_path=private/'uat-approval.toml'
    if private.is_symlink() or private.is_junction() or any(p.is_symlink() for p in (secret_path,approval_path)):
        raise PreflightError('Private UAT configuration must not use symbolic links.')
    for path in (secret_path,approval_path):
        if not path.is_file() or path.resolve().parent!=root/'.streamlit' or path.stat().st_nlink!=1:
            raise PreflightError('Private development secrets.toml and uat-approval.toml must be supplied manually before launch.')
    isolation_path=root.parent/'isolation.json'
    try:
        isolation=json.loads(isolation_path.read_text(encoding='utf-8'))
        expected=root/'uat'/'synthetic.sqlite3'
        original=Path(isolation['production_database']).absolute()
        if Path(isolation['workspace']).resolve()!=root or Path(isolation['database']).absolute()!=expected:
            raise PreflightError('Development SQLite path isolation failed.')
        import runpy
        guard=runpy.run_path(str(root.parent/'launch_dev.py'),run_name='uat_guard_validation')
        try:
            guard['validate_database_configuration'](isolation)
        except RuntimeError:
            raise PreflightError('Development SQLite path isolation failed.') from None
        settings=Path(isolation['development_localappdata']).resolve()
        if not settings.is_relative_to(root.parent) or settings==root.parent:
            raise PreflightError('Development alert settings path isolation failed.')
        # Parse only the explicitly supplied development files, never fall back.
        secret_bytes=secret_path.read_bytes()
        approval_bytes=approval_path.read_bytes()
        from uat_hardening import check_endpoint
        parsed=tomllib.loads(secret_bytes.decode('utf-8'))
        check_endpoint(parsed.get('SUPABASE_URL'))
        synthetic=root/'uat'/'synthetic.sqlite3'
        if not synthetic.is_file() or synthetic.is_symlink() or synthetic.stat().st_nlink != 1 or synthetic.resolve().parent != root/'uat':
            raise PreflightError('Synthetic UAT database isolation failed.')
        result=validate_configuration(tomllib.loads(secret_bytes.decode('utf-8')),tomllib.loads(approval_bytes.decode('utf-8')))
        return result
    except PreflightError:
        raise
    except Exception:
        raise PreflightError('Private UAT configuration is invalid or cannot be read; values are redacted.') from None


def main():
    parser=argparse.ArgumentParser(description='Offline UAT configuration check; never starts a server.')
    parser.parse_args()
    try:result=preflight()
    except PreflightError as error:
        print('UAT preflight blocked: '+str(error))
        return 1
    print(json.dumps(result))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
