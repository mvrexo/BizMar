"""Local owner profiles, keyed by authenticated email; no remote requests."""
from contextlib import closing
from io import BytesIO
import sqlite3
import warnings
from PIL import Image, UnidentifiedImageError
import streamlit as st
from sqlite_db import DB_PATH

DATABASE = DB_PATH


def _email():
    if not st.session_state.get('authenticated'):
        raise PermissionError('Sign in before accessing your profile.')
    email = st.session_state.get('local_owner_email') or st.secrets.get('OWNER_EMAIL', '')
    if not email:
        raise PermissionError('No authenticated owner identity is available.')
    return email.strip().lower()


def _connect():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute('''CREATE TABLE IF NOT EXISTS owner_profiles (
        email TEXT PRIMARY KEY, display_name TEXT NOT NULL,
        business_name TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '', avatar BLOB)''')
    connection.commit()
    return connection


def get_profile():
    email = _email()
    with closing(_connect()) as connection:
        row = connection.execute('SELECT email, display_name, business_name, phone, avatar IS NOT NULL AS has_avatar FROM owner_profiles WHERE email = ?', (email,)).fetchone()
    if row:
        result = dict(row)
        result['avatar_path'] = 'local' if result.pop('has_avatar') else None
        return result
    return dict(email=email, display_name=email.split('@')[0], business_name='', phone='', avatar_path=None)


def _image_bytes(file):
    data = file.getvalue()
    if len(data) > 3 * 1024 * 1024:
        raise ValueError('Image must be smaller than 3 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in ('JPEG', 'PNG', 'WEBP'):
                    raise ValueError('Only JPG, PNG and WEBP are allowed.')
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.thumbnail((512, 512))
                output = BytesIO()
                image.convert('RGBA').save(output, format='PNG')
                return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError('The uploaded file is not a valid image.') from error


def save_profile(name, business, phone, photo=None):
    email = _email()
    name, business, phone = name.strip(), business.strip(), phone.strip()
    if not name or not business:
        raise ValueError('Display name and business name are required.')
    if len(name) > 100 or len(business) > 200 or len(phone) > 50:
        raise ValueError('Use at most 100 characters for name, 200 for business, and 50 for phone.')
    avatar = _image_bytes(photo) if photo is not None else None
    with closing(_connect()) as connection, connection:
        connection.execute('''INSERT INTO owner_profiles (email, display_name, business_name, phone)
            VALUES (?, ?, ?, ?) ON CONFLICT(email) DO UPDATE SET
            display_name=excluded.display_name, business_name=excluded.business_name, phone=excluded.phone''', (email, name, business, phone))
        if avatar is not None:
            connection.execute('UPDATE owner_profiles SET avatar = ? WHERE email = ?', (avatar, email))


def upload_avatar(file):
    profile = get_profile()
    save_profile(profile['display_name'], profile['business_name'], profile['phone'], photo=file)


def remove_avatar():
    email = _email()
    with closing(_connect()) as connection, connection:
        connection.execute('UPDATE owner_profiles SET avatar = NULL WHERE email = ?', (email,))


def avatar_url(profile):
    """Return private image bytes for Streamlit; never expose a public URL."""
    email = _email()
    with closing(_connect()) as connection:
        row = connection.execute('SELECT avatar FROM owner_profiles WHERE email = ?', (email,)).fetchone()
    return bytes(row['avatar']) if row and row['avatar'] else None
