"""Opt-in local owner authentication. Provision accounts from the terminal."""
import argparse
from contextlib import closing
from getpass import getpass
from pathlib import Path
import re
import sqlite3
import bcrypt

DATABASE = Path(__file__).resolve().parent / 'uat' / 'login.sqlite3'

def valid_email(email):
    return bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email.strip()))

def connect():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE)
    connection.execute('CREATE TABLE IF NOT EXISTS owners (email TEXT PRIMARY KEY, password_hash BLOB NOT NULL)')
    connection.commit()
    return connection

def provision(email, password):
    email = email.strip().lower()
    if not valid_email(email) or not 12 <= len(password.encode('utf-8')) <= 72:
        raise ValueError('Use a valid email and a password of 12 to 72 UTF-8 bytes.')
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    with closing(connect()) as connection, connection:
        connection.execute('INSERT INTO owners VALUES (?, ?)', (email, hashed))

def verify(email, password):
    with closing(connect()) as connection:
        row = connection.execute('SELECT password_hash FROM owners WHERE email = ?', (email.strip().lower(),)).fetchone()
    # Run bcrypt even for unknown users to avoid a fast account lookup response.
    hashed = row[0] if row else bcrypt.hashpw(b'unused-password', bcrypt.gensalt())
    try:
        matched = bcrypt.checkpw(password.encode('utf-8'), hashed)
    except ValueError:
        matched = False
    return bool(row and matched)


def change_password(email, current, replacement):
    if not 12 <= len(replacement.encode('utf-8')) <= 72:
        raise ValueError('Use a password of 12 to 72 UTF-8 bytes.')
    email = email.strip().lower()
    with closing(connect()) as connection, connection:
        row = connection.execute('SELECT password_hash FROM owners WHERE email = ?', (email,)).fetchone()
        try:
            valid = bool(row and bcrypt.checkpw(current.encode('utf-8'), row[0]))
        except ValueError:
            valid = False
        if not valid:
            raise ValueError('Current password is incorrect.')
        hashed = bcrypt.hashpw(replacement.encode('utf-8'), bcrypt.gensalt())
        changed = connection.execute('UPDATE owners SET password_hash = ? WHERE email = ? AND password_hash = ?', (hashed, email, row[0]))
        if changed.rowcount != 1:
            raise ValueError('Password changed in another session. Please try again.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Provision an authorized local BizMar owner.')
    parser.add_argument('--email', required=True)
    args = parser.parse_args()
    password = getpass('Password (12–72 UTF-8 bytes): ')
    if password != getpass('Confirm password: '):
        raise SystemExit('Passwords do not match.')
    provision(args.email, password)
    print('Owner created. Set BIZMAR_AUTH_MODE=sqlite to use local authentication.')
