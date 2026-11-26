"""Private receipt storage: server-side secret only. No public receipt URLs."""
from urllib.parse import quote
from uuid import uuid4
import requests
import streamlit as st

BUCKET='payment-receipts'
MAX_BYTES=8*1024*1024
MIME={'jpg':'image/jpeg','jpeg':'image/jpeg','png':'image/png','pdf':'application/pdf'}

def _config():
    from uat_hardening import blocked
    blocked()
    return st.secrets['SUPABASE_URL'].rstrip('/'), st.secrets['SUPABASE_SERVICE_ROLE_KEY']

def upload_payment_receipt(file, order_id):
    from uat_hardening import blocked
    blocked()
    if file is None:
        return None
    ext=file.name.rsplit('.',1)[-1].lower() if '.' in file.name else ''
    if ext not in MIME:
        raise ValueError('Only JPG, PNG and PDF receipts are supported.')
    data=file.getvalue()
    if not data or len(data)>MAX_BYTES:
        raise ValueError('Receipt must be non-empty and at most 8 MB.')
    # Basic file signature check; do not trust file extension alone.
    valid = (ext in ('jpg','jpeg') and data.startswith(bytes.fromhex('FFD8FF'))) or \
            (ext=='png' and data.startswith(bytes.fromhex('89504E470D0A1A0A'))) or \
            (ext=='pdf' and data.startswith(b'%PDF-'))
    if not valid:
        raise ValueError('File contents do not match the selected image/PDF type.')
    base,key=_config()
    path=f'orders/{int(order_id)}/{uuid4().hex}.{ext}'
    resp=requests.post(f'{base}/storage/v1/object/{BUCKET}/{quote(path,safe="/")}',
        data=data,headers={'apikey':key,'Authorization':f'Bearer {key}',
                           'Content-Type':MIME[ext],'x-upsert':'false'},timeout=45)
    if not resp.ok:
        raise RuntimeError(f'Receipt upload failed ({resp.status_code}): {resp.text[:250]}')
    return path

def signed_receipt_url(path):
    from uat_hardening import blocked
    blocked()
    base,key=_config()
    resp=requests.post(f'{base}/storage/v1/object/sign/{BUCKET}/{quote(path,safe="/")}',
        json={'expiresIn':60},headers={'apikey':key,'Authorization':f'Bearer {key}',
                                       'Content-Type':'application/json'},timeout=25)
    if not resp.ok:
        raise RuntimeError(f'Could not sign receipt URL ({resp.status_code}): {resp.text[:250]}')
    signed=resp.json().get('signedURL') or resp.json().get('signedUrl')
    if not signed:
        raise RuntimeError('Supabase did not return a signed URL.')
    return signed if signed.startswith('http') else f'{base}{signed if signed.startswith("/") else "/"+signed}'
