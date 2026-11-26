"""Owner preferences in the existing database. No authentication or business export tables."""
from contextlib import closing
import json
import re
import sqlite_db
from owner_profile import _email, _image_bytes

DEFAULTS = dict(category='Bakery & Desserts', address='', contact='', description='', hours='',
                status='Pending', prefix='ORD', payment='Transfer', cancellation=True,
                deadlines=True, overdue_payments=True, pending_orders=True, reminder_days=2,
                aging_hours=48.0, demand_units=30, demand_days=7, margin_percent=20.0,
                theme='Light', language='English', currency='MYR', date_format='DD/MM/YYYY')


def _connect():
    connection = sqlite_db._connect()
    connection.execute('''CREATE TABLE IF NOT EXISTS owner_settings (
        email TEXT PRIMARY KEY, preferences TEXT NOT NULL, logo BLOB)''')
    connection.commit()
    return connection


def load():
    email = _email()
    with closing(_connect()) as connection:
        row = connection.execute('SELECT preferences FROM owner_settings WHERE email = ?', (email,)).fetchone()
    return {**DEFAULTS, **(json.loads(row['preferences']) if row else {})}


def save(values, logo=None):
    email = _email()
    if set(values) != set(DEFAULTS):
        raise ValueError('Invalid settings fields.')
    for key, allowed in dict(theme=('Light', 'Dark'), language=('English', 'Bahasa Melayu'),
                             currency=('MYR',), date_format=('DD/MM/YYYY', 'MM/DD/YYYY', 'YYYY-MM-DD')).items():
        if values[key] not in allowed:
            raise ValueError(f'Invalid {key} preference.')
    if values['status'] not in ('Pending', 'Confirmed') or values['payment'] not in ('Transfer', 'Cash', 'E-wallet', 'Other'):
        raise ValueError('Invalid order defaults.')
    if not re.fullmatch(r'[A-Z][A-Z0-9]{0,9}', values['prefix']):
        raise ValueError('Order prefix must be 1–10 uppercase letters or digits, starting with a letter.')
    if values['category'] not in ('Bakery & Desserts', 'Food & Beverages', 'Retail', 'Services', 'Other'):
        raise ValueError('Invalid business category.')
    if not isinstance(values['reminder_days'], int) or not 0 <= values['reminder_days'] <= 30:
        raise ValueError('Reminder days must be between 0 and 30.')
    for key in ('cancellation', 'deadlines', 'overdue_payments', 'pending_orders'):
        if not isinstance(values[key], bool):
            raise ValueError('Invalid notification or cancellation setting.')
    for key in ('address', 'contact', 'description', 'hours'):
        if not isinstance(values[key], str) or len(values[key]) > 2000:
            raise ValueError('Business fields must be at most 2000 characters.')
    validate_phone(values['contact'])
    from production_alerts import validate_settings
    validate_settings({key: values[key] for key in ('aging_hours', 'demand_units', 'demand_days', 'margin_percent')})
    image = _image_bytes(logo) if logo is not None else None
    with closing(_connect()) as connection, connection:
        connection.execute('''INSERT INTO owner_settings (email, preferences) VALUES (?, ?)
            ON CONFLICT(email) DO UPDATE SET preferences=excluded.preferences''', (email, json.dumps(values)))
        if image is not None:
            connection.execute('UPDATE owner_settings SET logo = ? WHERE email = ?', (image, email))


def business_logo():
    email = _email()
    with closing(_connect()) as connection:
        row = connection.execute('SELECT logo FROM owner_settings WHERE email = ?', (email,)).fetchone()
    return bytes(row['logo']) if row and row['logo'] else None


def validate_phone(phone):
    if phone and (not re.fullmatch(r'[+()\d\s-]+', phone) or not 7 <= len(re.sub(r'\D', '', phone)) <= 15):
        raise ValueError('Enter a phone number containing 7–15 digits.')


def runtime():
    """Use only preferences already loaded after authentication; pure modules keep defaults."""
    import streamlit as st
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    if get_script_run_ctx(suppress_warning=True) is None:
        return DEFAULTS.copy()
    return {**DEFAULTS, **st.session_state.get('bizmar_preferences', {})}
