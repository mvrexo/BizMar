"""Owner-authorized Orders operations for the installation's single-business DB.

Authentication stays in app.py. The server-set authenticated session and existing
owner identity guard every public read/write. This is not a multi-tenant API.
"""
from contextlib import closing
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import math
from uuid import uuid4
from zoneinfo import ZoneInfo

import sqlite_db
from owner_profile import _email as profile_identity
from malaysian_states import normalize as state_value, destination
from order_delivery import delivery_policy, quote_pending

STATUSES = ('Pending', 'Completed', 'Cancelled')
SOURCES = ('WhatsApp', 'Facebook', 'Instagram', 'Walk-in', 'Other')
METHODS = ('Cash', 'Online Transfer', 'E-wallet', 'Other')
CENT = Decimal('.01')


def current_owner():
    """Reuse the existing auth providers, including writes from dialog reruns."""
    import streamlit as st
    actor = profile_identity()
    if st.session_state.get('local_owner_email'):
        return actor
    if st.user.is_logged_in and st.user.get('email_verified') is True and str(st.user.get('email','')).strip().lower() == actor:
        return actor
    from auth import is_authorized_supabase_user
    if not is_authorized_supabase_user():
        raise PermissionError('Your session has expired. Sign in again before accessing Orders.')
    return actor


def money(value):
    try:
        result = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Enter a valid monetary amount.') from None
    if not result.is_finite() or result < 0 or result > Decimal('999999999.99'):
        raise ValueError('Monetary amounts must be finite and between RM 0 and RM 999,999,999.99.')
    return result


def canonical_status(value):
    return value if value in STATUSES else 'Pending'


def now():
    return datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).isoformat(timespec='microseconds')


def _authorize():
    actor = current_owner()
    if not actor:
        raise PermissionError('Sign in as an authorized business owner.')
    sqlite_db.initialize()
    return actor


def _audit(connection, identity, action, actor, summary):
    connection.execute('INSERT INTO order_activity(order_id,action,occurred_at,actor,summary) VALUES (?,?,?,?,?)',
                       (identity, action, now(), actor, summary))


def _next_customer_code(connection):
    used = {row['customer_id'] for row in connection.execute(
        'SELECT customer_id FROM customers WHERE customer_id IS NOT NULL'
    )}
    for row in connection.execute(
        'SELECT customer_id FROM customers WHERE customer_id IS NOT NULL ORDER BY id DESC'
    ):
        try:
            candidate = f"C{int(str(row['customer_id']).split('C')[-1]) + 1:03d}"
        except ValueError:
            continue
        if candidate not in used:
            return candidate
    candidate = 'C001'
    while candidate in used:
        candidate = f"C{int(candidate[1:]) + 1:03d}"
    return candidate


def _request(connection, token, actor, operation, payload):
    if not isinstance(token, str) or not 16 <= len(token) <= 128:
        raise ValueError('A valid submission token is required. Reload the form.')
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    row = connection.execute('SELECT * FROM order_requests WHERE token=?', (token,)).fetchone()
    if row and (row['actor'], row['operation'], row['payload_hash']) != (actor, operation, digest):
        raise ValueError('This submission was already used for different data. Reload the form.')
    return digest, row['result_id'] if row else None


def _finish(connection, token, actor, operation, digest, identity):
    connection.execute('INSERT INTO order_requests VALUES (?,?,?,?,?)', (token, actor, operation, digest, identity))


def _customer(connection, customer):
    name, raw = str(customer.get('name', '')).strip(), str(customer.get('phone', '')).strip()
    phone = sqlite_db.normalize_customer_phone(raw)
    if not name or len(name) > 200 or not sqlite_db.validate_customer_phone(raw):
        raise ValueError('Customer name and a valid Malaysian phone number are required.')
    row = connection.execute('SELECT id FROM customers WHERE normalized_phone=? OR phone=? ORDER BY id LIMIT 1', (phone, raw)).fetchone()
    if row is None:
        # Older imports sometimes stored the unnormalized local number in this field.
        row = next((candidate for candidate in connection.execute('SELECT id,phone,phone_number FROM customers ORDER BY id')
                    if sqlite_db.normalize_customer_phone(candidate['phone_number'] or candidate['phone']) == phone), None)
    if row:
        return row['id'], name, phone
    created = sqlite_db._insert(connection, 'customers', dict(name=name, phone=raw, normalized_phone=phone,
                                                             customer_id=_next_customer_code(connection),
                                                             address=str(customer.get('address', '')).strip(), state=state_value(customer.get('state'))))
    return created['id'], name, phone


def _prepare(connection, order, lines, existing=None):
    if not lines or len(lines) > 100:
        raise ValueError('Add between 1 and 100 product lines.')
    prepared = []
    used = set()
    for item in lines:
        quantity = item.get('quantity')
        if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or not math.isfinite(quantity) or int(quantity) != quantity or not 1 <= quantity <= 100000:
            raise ValueError('Quantity must be a whole number greater than zero (maximum 100,000).')
        product = connection.execute('SELECT * FROM products WHERE id=?', (item.get('product_id'),)).fetchone()
        source = None
        source_id = item.get('source_item_id')
        if existing is not None and source_id is not None:
            source = connection.execute('SELECT * FROM order_items WHERE id=? AND order_id=?', (source_id, existing)).fetchone()
            if source is None or source['product_id'] != item.get('product_id') or source_id in used:
                raise ValueError('A saved product line does not match this order.')
            used.add(source_id)
        if product is None or (not product['active'] and source is None):
            raise ValueError('Choose an active catalogue product for each new line.')
        price = money(item.get('unit_price'))
        # Per-unit cost snapshots may legitimately contain fractions of a cent.
        # Preserve their original precision when editing an unrelated field.
        try:
            cost = Decimal(str(source['unit_cost'] if source is not None else product['unit_cost']))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError('The saved product cost is invalid.') from None
        if not cost.is_finite() or cost < 0 or cost > Decimal('999999999.99'):
            raise ValueError('The saved product cost is invalid.')
        subtotal = money(price * int(quantity))
        prepared.append(dict(product_id=product['id'], product_name=source['product_name'] if source else product['name'],
                             quantity=int(quantity), unit_price=float(price), unit_cost=float(cost), subtotal=float(subtotal)))
    discount, fee = money(order.get('discount', 0)), money(order.get('delivery_fee') or 0)
    subtotal = sum((money(line['subtotal']) for line in prepared), Decimal(0))
    if discount > subtotal:
        raise ValueError('Discount cannot exceed the product subtotal.')
    total = money(subtotal - discount + fee)
    try:
        ordered = date.fromisoformat(str(order['ordered_at'])[:10])
        due = date.fromisoformat(str(order['fulfilment_date'])[:10])
    except (KeyError, ValueError, TypeError):
        raise ValueError('Valid order and fulfillment dates are required.') from None
    if due < ordered:
        raise ValueError('Fulfillment cannot be before the order date.')
    method = order.get('fulfilment_method', 'Pickup')
    address = str(order.get('delivery_address', '')).strip()
    if len(address) > 2000 or len(str(order.get('notes', ''))) > 4000:
        raise ValueError('Delivery address must be at most 2,000 characters and notes at most 4,000 characters.')
    if method not in ('Pickup', 'Delivery') or (method == 'Delivery' and not address):
        raise ValueError('Choose Pickup or Delivery and provide a delivery address when needed.')
    source = order.get('source', 'Other')
    if source not in SOURCES:
        raise ValueError('Choose a supported order source.')
    fulfilment_time = str(order.get('fulfilment_time') or '')
    if fulfilment_time:
        try: time.fromisoformat(fulfilment_time)
        except ValueError: raise ValueError('Enter a valid fulfillment time.') from None
    delivery_state=order.get('delivery_state')
    if existing is not None and 'delivery_state' not in order:
        delivery_state=connection.execute('SELECT delivery_state FROM orders WHERE id=?',(existing,)).fetchone()['delivery_state']
    values = dict(ordered_at=datetime.combine(ordered, time.min, ZoneInfo('Asia/Kuala_Lumpur')).isoformat(),
                  due_date=due.isoformat(), fulfilment_date=due.isoformat(), fulfilment_method=method,
                  fulfilment_time=fulfilment_time, delivery_address=address, source=source,
                  delivery_state=state_value(delivery_state) if method == 'Delivery' else '',
                  discount=float(discount), delivery_fee=float(fee), notes=str(order.get('notes', '')).strip())
    saved=dict(connection.execute('SELECT * FROM orders WHERE id=?',(existing,)).fetchone()) if existing is not None else {}
    if (order.get('import_source') or saved.get('import_source'))=='Google Forms':
        needs_new_quote = (
            quote_pending(saved)
            or (saved.get('free_delivery_applied') and subtotal < Decimal('100'))
            or (saved.get('fulfilment_method') != method and method == 'Delivery' and subtotal < Decimal('100'))
        )
        quote = order.get('confirmed_rider_quote') if 'confirmed_rider_quote' in order else (
            None if needs_new_quote else saved.get('delivery_fee')
        )
        policy=delivery_policy(subtotal,method,quote,order.get('rider_cost',saved.get('rider_cost')))
        values.update(policy)
        total=money(subtotal-discount+money(policy['delivery_fee']))
        values['final_payable_amount']=None if quote_pending(policy) else float(total)
        for field in ('import_source','import_response_key','source_submitted_at','payment_preference','submitted_payment_method','submitted_amount_paid','payment_receipt_reference'):
            value=order.get(field,saved.get(field))
            if value is not None:
                if field=='submitted_amount_paid': value=float(money(value))
                elif len(str(value))>2000: raise ValueError('Imported reference fields must be at most 2,000 characters.')
                values[field]=value
    else:
        values['final_payable_amount']=float(total)
    return values, prepared, total


def _ledger(connection, identity):
    return sum((money(row['amount']) for row in connection.execute('SELECT amount FROM payments WHERE order_id=?', (identity,))), Decimal(0))


def _payment(connection, identity, payment, total, actor):
    if quote_pending(dict(connection.execute('SELECT delivery_quote_status FROM orders WHERE id=?',(identity,)).fetchone())):
        raise ValueError('Confirm the rider quote before recording a payment.')
    amount = money(payment.get('amount', 0))
    if amount <= 0:
        raise ValueError('Record a payment only when money was received; amount must be positive.')
    if amount + _ledger(connection, identity) > total:
        raise ValueError('Payment exceeds the outstanding balance.')
    method = payment.get('method')
    if method == 'Transfer':
        method = 'Online Transfer'  # Accept legacy callers without rewriting saved history.
    if method not in METHODS:
        raise ValueError('Choose a payment method.')
    try:
        paid_at = datetime.fromisoformat(str(payment.get('paid_at') or now()))
        if paid_at.tzinfo is None:
            paid_at = paid_at.replace(tzinfo=ZoneInfo('Asia/Kuala_Lumpur'))
    except ValueError: raise ValueError('Enter a valid payment date.') from None
    cursor = connection.execute('INSERT INTO payments(order_id,paid_at,amount,method,reference,notes) VALUES (?,?,?,?,?,?)',
        (identity, paid_at.isoformat(), float(amount), method, str(payment.get('reference','')).strip(), str(payment.get('notes','')).strip()))
    sqlite_db._update_payment_status(connection, identity)
    _audit(connection, identity, 'Payment recorded', actor, f'RM {amount:.2f} via {method}')
    return cursor.lastrowid


def save_order(customer, order, lines, *, token, order_id=None, version=None, payment=None, acknowledge_overpayment=False):
    actor = _authorize()
    with sqlite_db.transaction() as connection:
        return _save_order(connection, actor, customer, order, lines, token=token, order_id=order_id,
                           version=version, payment=payment, acknowledge_overpayment=acknowledge_overpayment)


def import_google_forms_orders(records):
    """Atomically create validated Google Forms orders; imported payment claims are not ledger payments."""
    actor = _authorize()
    keys = [record.get('import_response_key') for record in records]
    if any(not isinstance(key, str) or not key or len(key) > 2000 for key in keys):
        raise ValueError('Every imported order needs a valid Google Forms response key.')
    if len(set(keys)) != len(keys):
        raise ValueError('The import contains duplicate response keys. Resolve duplicate rows before importing.')

    created = []
    skipped = 0
    with sqlite_db.transaction() as connection:
        for record in records:
            response_key = record['import_response_key']
            if connection.execute('SELECT 1 FROM orders WHERE import_response_key=?', (response_key,)).fetchone():
                skipped += 1
                continue
            order = dict(record['order'])
            if order.get('import_source') != 'Google Forms' or order.get('import_response_key') != response_key:
                raise ValueError('Invalid Google Forms import metadata.')
            lines = []
            for line in record['lines']:
                product = connection.execute('SELECT id,price,active FROM products WHERE id=?', (line.get('product_id'),)).fetchone()
                if product is None or not product['active']:
                    raise ValueError('A mapped product is no longer active. Refresh the preview.')
                if money(product['price']) != money(line.get('unit_price')):
                    raise ValueError('A mapped product price changed after preview. Refresh and review the new total.')
                lines.append(dict(line, unit_price=float(money(product['price']))))
            result = _save_order(
                connection, actor, record['customer'], order, lines,
                token=uuid4().hex,
            )
            created.append(int(result['id']))
    return {'imported': len(created), 'skipped': skipped, 'order_ids': created}


def google_sheets_sync_state(spreadsheet_id):
    _authorize()
    with closing(sqlite_db._connect()) as connection:
        row = connection.execute(
            'SELECT * FROM google_sheets_sync_state WHERE spreadsheet_id=?',
            (str(spreadsheet_id),),
        ).fetchone()
        return dict(row) if row else None


def google_sheets_row_ledger(spreadsheet_id, worksheet_id):
    _authorize()
    with closing(sqlite_db._connect()) as connection:
        return [
            dict(row) for row in connection.execute(
                '''SELECT row_number,content_hash,order_id,response_key
                   FROM google_sheets_rows WHERE spreadsheet_id=? AND worksheet_id=?''',
                (str(spreadsheet_id), int(worksheet_id)),
            )
        ]


def confirm_google_sheets_sync(spreadsheet_id, worksheet_id):
    _authorize()
    with sqlite_db.transaction() as connection:
        connection.execute(
            """INSERT INTO google_sheets_sync_state
               (spreadsheet_id,worksheet_id,confirmed_at,last_error)
               VALUES (?,?,?, '')
               ON CONFLICT(spreadsheet_id) DO UPDATE SET
               worksheet_id=excluded.worksheet_id,
               confirmed_at=excluded.confirmed_at,last_error=''""",
            (str(spreadsheet_id), int(worksheet_id), now()),
        )


def pause_google_sheets_sync(spreadsheet_id):
    _authorize()
    with sqlite_db.transaction() as connection:
        connection.execute(
            '''UPDATE google_sheets_sync_state
               SET confirmed_at=NULL,lease_token=NULL,lease_until=NULL
               WHERE spreadsheet_id=?''',
            (str(spreadsheet_id),),
        )


def acquire_google_sheets_lease(spreadsheet_id, worksheet_id, *, seconds=180, min_interval=0, trigger='Automatic'):
    _authorize()
    token = uuid4().hex
    with sqlite_db.transaction() as connection:
        state = connection.execute(
            'SELECT * FROM google_sheets_sync_state WHERE spreadsheet_id=?',
            (str(spreadsheet_id),),
        ).fetchone()
        if state is None or state['confirmed_at'] is None:
            raise PermissionError('Google Sheets synchronization has not been confirmed by the owner.')
        if int(state['worksheet_id']) != int(worksheet_id):
            raise ValueError('The confirmed Google Sheets worksheet has changed; review and confirm it again.')
        if state['lease_until'] and state['lease_until'] > now():
            return None
        if min_interval and state['last_attempt_at'] and (datetime.now(ZoneInfo('Asia/Kuala_Lumpur'))-datetime.fromisoformat(state['last_attempt_at'])).total_seconds()<min_interval:
            return None
        expiry = datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).replace(microsecond=0)
        from datetime import timedelta
        expiry = (expiry + timedelta(seconds=seconds)).isoformat()
        connection.execute(
            '''UPDATE google_sheets_sync_state SET lease_token=?,lease_until=?,last_attempt_at=?,last_error=''
               WHERE spreadsheet_id=?''',
            (token, expiry, now(), str(spreadsheet_id)),
        )
        from sync_monitor_store import begin_attempt
        begin_attempt(connection,spreadsheet_id,worksheet_id,token,trigger,now(),expiry)
    return token


def finish_google_sheets_sync(spreadsheet_id, token, *, new_orders=0, error='', associated=0, skipped=0, failed_rows=0, error_kind='', review_required=False):
    _authorize()
    with sqlite_db.transaction() as connection:
        state = connection.execute(
            'SELECT lease_token FROM google_sheets_sync_state WHERE spreadsheet_id=?',
            (str(spreadsheet_id),),
        ).fetchone()
        if state is None or state['lease_token'] != token:
            raise ValueError('The Google Sheets synchronization lease has expired.')
        review_message = 'Valid new orders were imported; some source rows still require owner review.'
        sync_error = error or (review_message if review_required else '')
        synced_at = now() if not error else None
        connection.execute(
            '''UPDATE google_sheets_sync_state
               SET last_synced_at=COALESCE(?,last_synced_at),
                   last_new_orders=?,last_error=?,lease_token=NULL,lease_until=NULL
               WHERE spreadsheet_id=?''',
            (synced_at, int(new_orders) if not error else 0, sync_error[:1000], str(spreadsheet_id)),
        )
        from sync_monitor_store import finish_attempt
        finish_attempt(
            connection,spreadsheet_id,token,now(),imported=new_orders,
            associated=associated,skipped=skipped,failed_rows=failed_rows,
            error_kind=error_kind or ('Internal' if error else ('Partial' if review_required else '')),
        )


def order_notification_counts():
    _authorize()
    with closing(sqlite_db._connect()) as connection:
        row = connection.execute(
            '''SELECT COUNT(*) AS total,
                      SUM(CASE WHEN read_at IS NULL THEN 1 ELSE 0 END) AS unread
               FROM order_notifications'''
        ).fetchone()
        return {'total': int(row['total'] or 0), 'unread': int(row['unread'] or 0)}


def order_data_revision():
    """Cheap, non-PII revision for refreshing other active owner sessions."""
    _authorize()
    with closing(sqlite_db._connect()) as connection:
        orders=connection.execute("SELECT COUNT(*),COALESCE(MAX(id),0),COALESCE(SUM(version),0),COALESCE(MAX(updated_at),'') FROM orders").fetchone()
        notices=connection.execute('SELECT COUNT(*),COUNT(read_at) FROM order_notifications').fetchone()
        return tuple(orders)+tuple(notices)


def import_google_sheets_orders(spreadsheet_id, worksheet_id, records, *, allow_identical_rows=False, lease_token=None):
    """Atomically import new rows and notifications; never overwrite existing orders."""
    actor=_authorize()
    with sqlite_db.transaction() as connection:
        return _import_google_sheets_orders(connection,actor,spreadsheet_id,worksheet_id,records,
            allow_identical_rows=allow_identical_rows,lease_token=lease_token)


def activate_google_sheets_preview(spreadsheet_id, worksheet_id, records, *, allow_identical_rows=False):
    """Enable sync only as part of the successfully confirmed import transaction."""
    actor=_authorize()
    with sqlite_db.transaction() as connection:
        previous=connection.execute('SELECT lease_until FROM google_sheets_sync_state WHERE spreadsheet_id=?',(str(spreadsheet_id),)).fetchone()
        if previous and previous['lease_until'] and previous['lease_until']>now():
            raise ValueError('Another owner session is synchronizing. Retry shortly.')
        connection.execute("""INSERT INTO google_sheets_sync_state(spreadsheet_id,worksheet_id,confirmed_at,last_attempt_at)
            VALUES(?,?,?,?) ON CONFLICT(spreadsheet_id) DO UPDATE SET worksheet_id=excluded.worksheet_id,
            confirmed_at=excluded.confirmed_at,last_attempt_at=excluded.last_attempt_at,lease_token=NULL,lease_until=NULL""",
            (str(spreadsheet_id),int(worksheet_id),now(),now()))
        return _import_google_sheets_orders(connection,actor,spreadsheet_id,worksheet_id,records,
            allow_identical_rows=allow_identical_rows)


def _import_google_sheets_orders(connection, actor, spreadsheet_id, worksheet_id, records, *, allow_identical_rows=False, lease_token=None):
    for record in records:
        source = record.get('sync_source', {})
        if (
            not isinstance(source.get('row_number'), int)
            or source['row_number'] < 2
            or not isinstance(source.get('content_hash'), str)
            or len(source['content_hash']) != 64
            or not record.get('import_response_key')
        ):
            raise ValueError('A valid Google Sheets source row identity is required.')
    keys = [record['import_response_key'] for record in records]
    if len(set(keys)) != len(keys):
        raise ValueError('The response contains duplicate Google Sheets row identities.')

    created = []
    linked = []
    state = connection.execute(
        'SELECT worksheet_id,confirmed_at,lease_token,lease_until FROM google_sheets_sync_state WHERE spreadsheet_id=?',
        (str(spreadsheet_id),),
    ).fetchone()
    if state is None or state['confirmed_at'] is None:
        raise PermissionError('Review the preview and confirm Google Sheets synchronization first.')
    if int(state['worksheet_id']) != int(worksheet_id):
        raise ValueError('The confirmed worksheet changed. Review and confirm it again.')

    if lease_token is not None and (state['lease_token']!=lease_token or not state['lease_until'] or state['lease_until']<=now()):
        raise ValueError('The synchronization lease expired. Retry with a fresh preview.')
    imported_hashes=set()

    for record in records:
        source = record['sync_source']
        row_number = source['row_number']
        content_hash = source['content_hash']
        existing = connection.execute(
            '''SELECT content_hash,order_id FROM google_sheets_rows
               WHERE spreadsheet_id=? AND worksheet_id=? AND row_number=?''',
            (str(spreadsheet_id), int(worksheet_id), row_number),
        ).fetchone()
        if existing:
            if existing['content_hash'] != content_hash:
                raise ValueError(
                    f'Source row {row_number} changed since its last sync. '
                    'Review the edited response; the existing order was not changed.'
                )
            continue
        moved = connection.execute(
            '''SELECT row_number FROM google_sheets_rows
               WHERE spreadsheet_id=? AND worksheet_id=? AND content_hash=? LIMIT 1''',
            (str(spreadsheet_id), int(worksheet_id), content_hash),
        ).fetchone()
        if moved and not (allow_identical_rows and content_hash in imported_hashes):
            raise ValueError(
                f'Source row {row_number} duplicates prior row {moved["row_number"]}. '
                'Review the possible moved or duplicate response before importing.'
            )
        response_key = record['import_response_key']
        canonical_key=record.get('forms_response_key',response_key)
        linked_order=None
        if record.get('existing_order_id'):
            linked_order=connection.execute("SELECT * FROM orders WHERE id=? AND import_source='Google Forms'",(record['existing_order_id'],)).fetchone()
            if linked_order is None or linked_order['import_response_key']!=record.get('existing_order_key'):
                raise ValueError('An existing response association changed. Review a fresh preview.')
            if record.get('link_requires_review') and not allow_identical_rows:
                raise ValueError('Explicit owner review is required before linking a possible existing response.')
        else:
            linked_order=connection.execute('SELECT * FROM orders WHERE import_response_key=?',(canonical_key,)).fetchone()
        if linked_order and connection.execute('SELECT 1 FROM google_sheets_rows WHERE spreadsheet_id=? AND worksheet_id=? AND order_id=?',
                (str(spreadsheet_id),int(worksheet_id),linked_order['id'])).fetchone():
            raise ValueError('This existing order is already associated with a source row. Review the duplicate response.')
        order = dict(record['order'])
        if (
            order.get('import_source') != 'Google Forms'
            or order.get('import_response_key') != canonical_key
        ):
            raise ValueError('Invalid Google Forms synchronization metadata.')
        lines = []
        for line in record['lines']:
            product = connection.execute(
                'SELECT id,price,active FROM products WHERE id=?',
                (line.get('product_id'),),
            ).fetchone()
            if product is None or not product['active']:
                raise ValueError('A mapped product is no longer active. Refresh the preview.')
            if money(product['price']) != money(line.get('unit_price')):
                raise ValueError(
                    'A mapped product price changed after preview. Refresh and review the new total.'
                )
            lines.append(dict(line, unit_price=float(money(product['price']))))
        saved = linked_order or _save_order(
            connection, actor, record['customer'], order, lines, token=uuid4().hex,
        )
        connection.execute(
            '''INSERT INTO google_sheets_rows
               (spreadsheet_id,worksheet_id,row_number,content_hash,order_id,response_key,imported_at)
               VALUES (?,?,?,?,?,?,?)''',
            (
                str(spreadsheet_id), int(worksheet_id), row_number, content_hash,
                int(saved['id']), response_key, now(),
            ),
        )
        if linked_order:
            linked.append(int(saved['id']))
        else:
            connection.execute(
                '''INSERT INTO order_notifications(order_id,source_key,created_at)
                   VALUES (?,?,?)''',
                (int(saved['id']), response_key, now()),
            )
            created.append(int(saved['id']))
        imported_hashes.add(content_hash)
    connection.execute(
        '''UPDATE google_sheets_sync_state SET last_synced_at=?,last_new_orders=?,last_error=''
           WHERE spreadsheet_id=?''',
        (now(), len(created), str(spreadsheet_id)),
    )
    return {'imported': len(created), 'order_ids': created, 'linked':len(linked)}


def list_order_notifications(unread_only=False):
    _authorize()
    query = '''SELECT n.id,n.order_id,n.created_at,n.read_at,o.order_code,
                      COALESCE(o.customer_name_snapshot,c.name,'') AS customer_name
               FROM order_notifications n
               JOIN orders o ON o.id=n.order_id
               JOIN customers c ON c.id=o.customer_id'''
    if unread_only:
        query += ' WHERE n.read_at IS NULL'
    query += ' ORDER BY n.id DESC'
    with closing(sqlite_db._connect()) as connection:
        return [dict(row) for row in connection.execute(query)]


def mark_order_notification_read(notification_id=None, *, mark_all=False):
    _authorize()
    with sqlite_db.transaction() as connection:
        if mark_all:
            connection.execute(
                'UPDATE order_notifications SET read_at=? WHERE read_at IS NULL', (now(),),
            )
        elif notification_id is not None:
            connection.execute(
                'UPDATE order_notifications SET read_at=? WHERE id=? AND read_at IS NULL',
                (now(), int(notification_id)),
            )
        else:
            raise ValueError('Choose a notification or mark all notifications as read.')


def _save_order(connection, actor, customer, order, lines, *, token, order_id=None, version=None, payment=None, acknowledge_overpayment=False):
    """Private transactional core shared by manual saves and confirmed file imports."""
    operation = 'create' if order_id is None else f'edit:{order_id}'
    payload = dict(customer=customer, order=order, lines=lines, payment=payment, version=version,
                   acknowledge_overpayment=acknowledge_overpayment)
    digest, replay = _request(connection, token, actor, operation, payload)
    if replay is not None:
        return dict(connection.execute('SELECT * FROM orders WHERE id=?', (replay,)).fetchone())
    previous = connection.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone() if order_id is not None else None
    if order_id is not None:
        if previous is None or canonical_status(previous['status']) != 'Pending':
            raise ValueError('Only Pending orders can be edited.')
        if version is None or int(previous['version']) != int(version):
            raise ValueError('This order changed in another session. Reload its details before editing.')
        if payment is not None:
            raise ValueError('Use Record Payment to add a transaction to an existing order.')
    values, prepared, total = _prepare(connection, order, lines, order_id)
    customer_id, name, phone = _customer(connection, customer)
    if 'state' in customer:
        residence = state_value(customer['state'])
    elif previous is not None:
        residence = previous['customer_state_snapshot']
    else:
        residence = connection.execute('SELECT state FROM customers WHERE id=?', (customer_id,)).fetchone()['state']
    values.update(customer_id=customer_id, customer_name_snapshot=name, phone_snapshot=phone,
                  customer_state_snapshot=residence,
                  total_amount=float(total), updated_at=now())
    if previous is not None:
        paid = _ledger(connection, order_id)
        if paid > total and not acknowledge_overpayment:
            raise ValueError(f'Payments exceed the new total by RM {paid-total:.2f}. Explicitly acknowledge the overpayment; payment history will be retained.')
        values['version'] = int(previous['version']) + 1
        fields = ','.join(f'{field}=?' for field in values)
        connection.execute(f'UPDATE orders SET {fields} WHERE id=?', (*values.values(), order_id))
        connection.execute('DELETE FROM order_items WHERE order_id=?', (order_id,))
        identity = order_id
    else:
        stamp = now()
        values.update(status='Pending', payment_status='Unpaid', created_at=stamp, status_updated_at=stamp, submission_token=token)
        fields = ','.join(values)
        placeholders = ','.join('?' for _ in values)
        identity = connection.execute(f'INSERT INTO orders({fields}) VALUES ({placeholders})', tuple(values.values())).lastrowid
        from settings_store import runtime
        prefix = runtime()['prefix']
        reference = f'{prefix}{identity:03d}'
        while connection.execute('SELECT 1 FROM orders WHERE order_code=?', (reference,)).fetchone():
            reference += '-N'
        connection.execute('UPDATE orders SET order_code=? WHERE id=?', (reference, identity))
    for line in prepared:
        fields = ','.join(line)
        connection.execute(f'INSERT INTO order_items(order_id,{fields}) VALUES (?,{",".join("?" for _ in line)})', (identity,*line.values()))
    sqlite_db._update_payment_status(connection, identity)
    summary = f'Total RM {total:.2f}; {len(prepared)} product line(s)'
    if previous is not None:
        changed = [field for field in values if field not in ('version','updated_at') and previous[field] != values[field]]
        summary += '; Changed: ' + (', '.join(changed) if changed else 'product lines')
        if _ledger(connection, identity) > total:
            summary += '; acknowledged overpayment retained'
    _audit(connection, identity, 'Order edited' if previous is not None else 'Order created', actor, summary)
    if payment is not None:
        _payment(connection, identity, payment, total, actor)
    _finish(connection, token, actor, operation, digest, identity)
    return dict(connection.execute('SELECT * FROM orders WHERE id=?', (identity,)).fetchone())


def transition(order_id, target, reason=''):
    actor = _authorize()
    if len(str(reason)) > 2000:
        raise ValueError('Cancellation reason must be at most 2,000 characters.')
    if target not in ('Completed', 'Cancelled'):
        raise ValueError('Choose Completed or Cancelled.')
    with sqlite_db.transaction() as connection:
        order = connection.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
        if order is None or canonical_status(order['status']) != 'Pending':
            raise ValueError('Only a Pending order can be completed or cancelled. Reload the details.')
        if target=='Completed' and quote_pending(dict(order)):
            raise ValueError('Confirm the rider quote before completing this order.')
        if target == 'Cancelled':
            from settings_store import runtime
            if not runtime()['cancellation']:
                raise ValueError('Order cancellation is disabled in Settings.')
        stamp = now()
        connection.execute('UPDATE orders SET status=?,status_updated_at=?,updated_at=?,version=version+1,completed_at=?,cancelled_at=?,cancellation_reason=? WHERE id=?',
                           (target,stamp,stamp,stamp if target=='Completed' else None,stamp if target=='Cancelled' else None,str(reason).strip() if target=='Cancelled' else '',order_id))
        _audit(connection, order_id, f'Order {target.lower()}', actor, str(reason).strip() if target=='Cancelled' else 'Fulfilled; payment status unchanged')


def record_payment(order_id, payment, *, token):
    actor = _authorize()
    with sqlite_db.transaction() as connection:
        digest, replay = _request(connection, token, actor, f'payment:{order_id}', payment)
        if replay is not None:
            return replay
        order = connection.execute('SELECT total_amount,status FROM orders WHERE id=?', (order_id,)).fetchone()
        if order is None or canonical_status(order['status']) == 'Cancelled':
            raise ValueError('New payments cannot be recorded against a missing or cancelled order.')
        identity = _payment(connection, order_id, payment, money(order['total_amount']), actor)
        connection.execute('UPDATE orders SET version=version+1 WHERE id=?', (order_id,))
        _finish(connection, token, actor, f'payment:{order_id}', digest, identity)
        return identity


def _enrich(order, paid):
    result = dict(order)
    result['legacy_status'] = result['status']
    result['status'] = canonical_status(result['status'])
    result['amount_paid'] = float(paid)
    result['balance'] = float(money(result['total_amount']) - paid)
    result['payment_status'] = sqlite_db.payment_status_for_total(money(result['total_amount']), paid)
    result['customer_name'] = result.get('customer_name_snapshot') or result.get('customer_name', '')
    result['phone_number'] = result.get('phone_snapshot') or result.get('phone_number', '')
    result['state'] = destination(result)
    result['quote_pending']=quote_pending(result)
    result['final_payable_amount']=None if result['quote_pending'] else float(result['total_amount'])
    return result


def list_orders():
    _authorize()
    with closing(sqlite_db._connect()) as connection:
        rows = connection.execute('''SELECT o.*,c.name AS customer_name,c.phone AS phone_number,
            COALESCE((SELECT GROUP_CONCAT(product_name, ', ') FROM order_items WHERE order_id=o.id),'') AS products,
            (SELECT COUNT(*) FROM order_items WHERE order_id=o.id) AS item_count,
            (SELECT product_name FROM order_items WHERE order_id=o.id ORDER BY id LIMIT 1) AS first_product
            FROM orders o JOIN customers c ON c.id=o.customer_id ORDER BY o.ordered_at DESC,o.id DESC''').fetchall()
        paid = {}
        for row in connection.execute('SELECT order_id,amount FROM payments'):
            paid[row['order_id']] = paid.get(row['order_id'], Decimal(0)) + money(row['amount'])
        return [_enrich(row, paid.get(row['id'], Decimal(0))) for row in rows]


def imported_response_keys():
    _authorize()
    with closing(sqlite_db._connect()) as connection:
        return {row['import_response_key'] for row in connection.execute(
            "SELECT import_response_key FROM orders WHERE import_source='Google Forms' AND import_response_key IS NOT NULL"
        )}


def google_forms_source_records():
    _authorize()
    with closing(sqlite_db._connect()) as connection:
        return [dict(row) for row in connection.execute("SELECT id,order_code,import_response_key,source_submitted_at,phone_snapshot,fulfilment_date FROM orders WHERE import_source='Google Forms'")]


def details(order_id):
    _authorize()
    result = sqlite_db.order_details(order_id)
    if result is None:
        return None
    paid = sum((money(p['amount']) for p in result['payments']), Decimal(0))
    result['order'] = _enrich(result['order'], paid)
    with closing(sqlite_db._connect()) as connection:
        result['activity'] = [dict(row) for row in connection.execute('SELECT action,occurred_at,actor,summary FROM order_activity WHERE order_id=? ORDER BY id', (order_id,))]
    return result
