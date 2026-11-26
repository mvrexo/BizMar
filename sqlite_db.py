"""Persistent SQLite data layer for Nour Sweets business records."""
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
import re
import sqlite3

DB_PATH = Path(__file__).parent / 'uat' / 'synthetic.sqlite3'
_INITIALIZED_PATH = None

TABLES = {'products', 'customers', 'orders', 'order_items', 'payments'}
ORDER_STATUSES = ('Pending', 'Confirmed', 'Preparing', 'Ready', 'Completed', 'Cancelled')


def _connect():
    connection = sqlite3.connect(DB_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


@contextmanager
def transaction():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect()
    try:
        connection.execute('BEGIN IMMEDIATE')
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize():
    """Create the local schema without generating business records."""
    global _INITIALIZED_PATH
    import os
    if os.environ.get('BIZMAR_PREVIEW_ONLY') == '1':
        # Preview must never execute the normal initialization/backfill UPDATEs.
        with closing(_connect()) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not TABLES.union({'google_sheets_sync_state', 'google_sheets_rows', 'order_notifications'}).issubset(tables):
                raise RuntimeError('Apply the approved migration before starting preview mode.')
        return
    if _INITIALIZED_PATH == DB_PATH and DB_PATH.exists():
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with transaction() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Dessert',
                price REAL NOT NULL DEFAULT 0 CHECK(price >= 0),
                unit_cost REAL NOT NULL DEFAULT 0 CHECK(unit_cost >= 0),
                image_url TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(name, category)
            );
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT,
                full_name TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                phone_number TEXT,
                normalized_phone TEXT,
                address TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(customer_id),
                UNIQUE(normalized_phone)
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_code TEXT UNIQUE,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                ordered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                due_date TEXT NOT NULL,
                fulfilment_date TEXT NOT NULL,
                fulfilment_method TEXT NOT NULL DEFAULT 'Pickup',
                total_amount REAL NOT NULL DEFAULT 0 CHECK(total_amount >= 0),
                status TEXT NOT NULL DEFAULT 'Pending'
                    CHECK(status IN ('Pending','Confirmed','Preparing','Ready','Completed','Cancelled')),
                payment_status TEXT NOT NULL DEFAULT 'Unpaid'
                    CHECK(payment_status IN ('Unpaid','Partial','Paid')),
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status_updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                unit_price REAL NOT NULL CHECK(unit_price >= 0),
                unit_cost REAL NOT NULL DEFAULT 0 CHECK(unit_cost >= 0),
                subtotal REAL NOT NULL CHECK(subtotal >= 0)
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                paid_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                amount REAL NOT NULL CHECK(amount > 0),
                method TEXT NOT NULL DEFAULT 'Transfer',
                reference TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_orders_due_date ON orders(due_date);
            CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
            CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
            CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(order_id);
            CREATE TABLE IF NOT EXISTS app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        from orders_schema import migrate
        migrate(connection)
        from products_schema import migrate as migrate_products
        migrate_products(connection)
        columns = {row['name'] for row in connection.execute('PRAGMA table_info(customers)').fetchall()}
        for column_name, definition in {
            'customer_id': 'TEXT',
            'full_name': "TEXT NOT NULL DEFAULT ''",
            'phone_number': 'TEXT',
            'normalized_phone': 'TEXT',
            'notes': "TEXT NOT NULL DEFAULT ''",
            'archived': 'INTEGER NOT NULL DEFAULT 0',
        }.items():
            if column_name not in columns:
                connection.execute(f'ALTER TABLE customers ADD COLUMN {column_name} {definition}')
        connection.execute('UPDATE customers SET full_name = COALESCE(full_name, name) WHERE full_name IS NULL OR full_name = ""')
        connection.execute('UPDATE customers SET name = COALESCE(name, full_name) WHERE name IS NULL OR name = ""')
        connection.execute('UPDATE customers SET customer_id = "C" || printf("%03d", id) WHERE customer_id IS NULL')
        connection.execute('UPDATE customers SET phone_number = phone WHERE phone_number IS NULL')
        connection.execute('UPDATE customers SET normalized_phone = phone WHERE normalized_phone IS NULL')
        connection.execute('UPDATE customers SET notes = COALESCE(notes, "") WHERE notes IS NULL')
        connection.execute('UPDATE customers SET archived = COALESCE(archived, 0) WHERE archived IS NULL')
        connection.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_normalized_phone ON customers(normalized_phone) WHERE normalized_phone IS NOT NULL')
    _INITIALIZED_PATH = DB_PATH


def configured():
    initialize()
    return True


def _check_table(table):
    if table not in TABLES:
        raise ValueError(f'Unsupported database table: {table}')


def normalize_customer_phone(phone):
    digits = re.sub(r'\D', '', str(phone or ''))
    if not digits:
        return ''
    if digits.startswith('60'):
        normalized = digits
    elif digits.startswith('0'):
        normalized = '60' + digits[1:]
    else:
        normalized = '60' + digits if digits.startswith('1') or len(digits) == 9 else digits
    if not re.fullmatch(r'6\d{10,11}', normalized):
        return ''
    return f'+{normalized}'


def validate_customer_phone(phone):
    normalized = normalize_customer_phone(phone)
    return bool(normalized and len(normalized) >= 12)


def next_customer_code():
    with closing(_connect()) as connection:
        row = connection.execute(
            'SELECT customer_id FROM customers WHERE customer_id IS NOT NULL ORDER BY id DESC LIMIT 1'
        ).fetchone()
        if row and row['customer_id']:
            try:
                value = int(str(row['customer_id']).split('C')[-1])
                return f'C{value + 1:03d}'
            except ValueError:
                pass
    return 'C001'


def all_rows(table, select='*', **filters):
    _check_table(table)
    allowed_columns = {
        'products': {'id', 'name', 'category', 'price', 'unit_cost', 'image_url', 'active', 'quantity_per_unit', 'measurement_unit', 'packaging_type', 'weight_grams'},
        'customers': {'id', 'customer_id', 'full_name', 'name', 'phone', 'phone_number', 'normalized_phone', 'address', 'state', 'notes', 'archived', 'created_at'},
        'orders': {
            'id', 'order_code', 'customer_id', 'ordered_at', 'due_date',
            'fulfilment_date', 'fulfilment_method', 'total_amount', 'status',
            'payment_status', 'notes', 'created_at', 'updated_at', 'status_updated_at',
            'customer_state_snapshot', 'delivery_state',
        },
        'order_items': {
            'id', 'order_id', 'product_id', 'product_name', 'quantity',
            'unit_price', 'unit_cost', 'subtotal',
        },
        'payments': {'id', 'order_id', 'paid_at', 'amount', 'method', 'reference'},
    }[table]
    columns = '*' if select == '*' else ', '.join(
        column.strip() for column in select.split(',')
        if column.strip() in allowed_columns
    )
    if columns != '*' and not columns:
        raise ValueError('No valid columns requested.')
    clauses, values = [], []
    for key, value in filters.items():
        if key not in allowed_columns:
            raise ValueError(f'Unsupported filter column: {key}')
        clauses.append(f'"{key}" = ?')
        values.append(value)
    query = f'SELECT {columns} FROM "{table}"'
    if clauses:
        query += ' WHERE ' + ' AND '.join(clauses)
    query += ' ORDER BY id'
    with closing(_connect()) as connection:
        rows = connection.execute(query, values).fetchall()
    return [dict(row) for row in rows]


def _update_order_totals(connection, order_id, *, allow_incomplete=False):
    from decimal import Decimal, ROUND_HALF_UP
    row = connection.execute('SELECT discount, delivery_fee FROM orders WHERE id = ?', (order_id,)).fetchone()
    if row is None:
        return
    subtotal = sum((Decimal(str(line[0])) for line in connection.execute('SELECT subtotal FROM order_items WHERE order_id = ?', (order_id,))), Decimal('0'))
    total = (subtotal - Decimal(str(row['discount'])) + Decimal(str(row['delivery_fee']))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    if total < 0 and not allow_incomplete:
        raise ValueError('Discount cannot exceed the items subtotal plus delivery fee.')
    connection.execute('UPDATE orders SET total_amount = ?, updated_at = ? WHERE id = ?',
                       (float(max(total, 0)), datetime.now().astimezone().isoformat(timespec='seconds'), order_id))
    _update_payment_status(connection, order_id)


def payment_status_for_total(total_amount, recorded_payments):
    """Ledger-only status: no payment is Unpaid; positive shortfall is Partial."""
    from decimal import Decimal, ROUND_HALF_UP
    total = Decimal(str(total_amount)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    paid = Decimal(str(recorded_payments)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    return 'Paid' if paid >= total and paid > 0 else 'Partial' if paid > 0 else 'Unpaid'


def _update_payment_status(connection, order_id):
    order = connection.execute(
        'SELECT total_amount FROM orders WHERE id = ?', (order_id,)
    ).fetchone()
    if not order:
        return
    from decimal import Decimal
    paid = sum((Decimal(str(row[0])) for row in connection.execute(
        'SELECT amount FROM payments WHERE order_id = ?', (order_id,))), Decimal(0))
    status = payment_status_for_total(order['total_amount'], paid)
    connection.execute(
        'UPDATE orders SET payment_status = ?, updated_at = ? WHERE id = ?',
        (status, datetime.now().astimezone().isoformat(timespec='seconds'), order_id),
    )


def _insert(connection, table, payload):
    _check_table(table)
    columns = {
        'products': {'name', 'category', 'price', 'unit_cost', 'image_url', 'active', 'quantity_per_unit', 'measurement_unit', 'packaging_type', 'weight_grams'},
        'customers': {'customer_id', 'full_name', 'name', 'phone', 'phone_number', 'normalized_phone', 'address', 'state', 'notes', 'archived'},
        'orders': {
            'order_code', 'customer_id', 'ordered_at', 'due_date', 'fulfilment_date',
            'fulfilment_method', 'total_amount', 'status', 'payment_status', 'notes', 'customer_state_snapshot', 'delivery_state',
        },
        'order_items': {
            'order_id', 'product_id', 'product_name', 'quantity',
            'unit_price', 'unit_cost', 'subtotal',
        },
        'payments': {'order_id', 'paid_at', 'amount', 'method', 'reference'},
    }[table]
    unknown = set(payload) - columns
    if unknown:
        raise ValueError(f'Unsupported {table} field(s): {", ".join(sorted(unknown))}')
    values = dict(payload)
    if table == 'orders':
        from settings_store import runtime
        preferences = runtime()
        values.setdefault('status', preferences['status'])
        if values['status'] == 'Cancelled' and not preferences['cancellation']:
            raise ValueError('Order cancellation is disabled in Settings.')
    if table == 'orders':
        values.setdefault('fulfilment_date', values.get('due_date'))
        # New orders have no payment entries; legacy caller declarations are ignored.
        values['payment_status'] = 'Unpaid'
        from malaysian_states import normalize as state_value
        residence = connection.execute('SELECT state FROM customers WHERE id=?', (values.get('customer_id'),)).fetchone()
        values['customer_state_snapshot'] = state_value(values.get('customer_state_snapshot', residence['state'] if residence else ''))
        values['delivery_state'] = state_value(values.get('delivery_state')) if values.get('fulfilment_method') == 'Delivery' else ''
    if table == 'customers':
        from malaysian_states import normalize as state_value
        values['state'] = state_value(values.get('state'))
        name = str(values.get('full_name') or values.get('name') or '').strip()
        phone = str(values.get('phone_number') or values.get('phone') or '').strip()
        if name and not values.get('full_name'):
            values['full_name'] = name
        if name and not values.get('name'):
            values['name'] = name
        if phone and not values.get('phone_number'):
            values['phone_number'] = phone
        if phone and not values.get('phone'):
            values['phone'] = phone
        values.setdefault('normalized_phone', normalize_customer_phone(phone))
        values['normalized_phone'] = values.get('normalized_phone') or normalize_customer_phone(phone)
        values.setdefault('address', '')
        values.setdefault('notes', '')
        values.setdefault('archived', 0)
        values['customer_id'] = values.get('customer_id') or next_customer_code()
    if table == 'order_items':
        product = connection.execute(
            'SELECT name, unit_cost FROM products WHERE id = ?', (values.get('product_id'),)
        ).fetchone() if values.get('product_id') is not None else None
        values.setdefault('product_name', product['name'] if product else 'Custom item')
        values.setdefault('unit_cost', float(product['unit_cost']) if product else 0)
        values.setdefault('subtotal', float(values['quantity']) * float(values['unit_price']))
    fields = list(values)
    placeholders = ', '.join('?' for _ in fields)
    quoted_fields = ', '.join(f'"{field}"' for field in fields)
    cursor = connection.execute(
        f'INSERT INTO "{table}" ({quoted_fields}) VALUES ({placeholders})',
        [values[field] for field in fields],
    )
    row_id = cursor.lastrowid
    if table == 'orders':
        from settings_store import runtime
        order_code = values.get('order_code') or f"{runtime()['prefix']}{row_id:03d}"
        if not values.get('order_code'):
            base, suffix = order_code, 1
            while connection.execute('SELECT 1 FROM orders WHERE order_code = ? AND id != ?', (order_code, row_id)).fetchone():
                order_code = f'{base}-{suffix}'
                suffix += 1
        connection.execute('UPDATE orders SET order_code = ? WHERE id = ?', (order_code, row_id))
    elif table == 'order_items':
        _update_order_totals(connection, int(values['order_id']), allow_incomplete=True)
    elif table == 'payments':
        _update_payment_status(connection, int(values['order_id']))
    return dict(connection.execute(f'SELECT * FROM "{table}" WHERE id = ?', (row_id,)).fetchone())


def add(table, payload):
    records = payload if isinstance(payload, list) else [payload]
    if not records:
        return []
    with transaction() as connection:
        inserted = [_insert(connection, table, record) for record in records]
    return inserted if isinstance(payload, list) else inserted[0]


def edit(table, row_id, payload):
    _check_table(table)
    if table == 'orders' and payload.get('status') == 'Cancelled':
        from settings_store import runtime
        if not runtime()['cancellation']:
            with closing(_connect()) as connection:
                existing = connection.execute('SELECT status FROM orders WHERE id = ?', (row_id,)).fetchone()
            if existing and existing['status'] != 'Cancelled':
                raise ValueError('Order cancellation is disabled in Settings.')
    allowed = {
        'products': {'name', 'category', 'price', 'unit_cost', 'image_url', 'active', 'quantity_per_unit', 'measurement_unit', 'packaging_type', 'weight_grams'},
        'customers': {'customer_id', 'full_name', 'name', 'phone', 'phone_number', 'normalized_phone', 'address', 'state', 'notes', 'archived'},
        'orders': {
            'customer_id', 'ordered_at', 'due_date', 'fulfilment_date',
            'fulfilment_method', 'status', 'payment_status', 'notes', 'customer_state_snapshot', 'delivery_state',
        },
        'order_items': {'product_id', 'product_name', 'quantity', 'unit_price', 'unit_cost', 'subtotal'},
        'payments': {'paid_at', 'amount', 'method', 'reference'},
    }[table]
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f'Unsupported {table} field(s): {", ".join(sorted(unknown))}')
    if not payload:
        return []
    with transaction() as connection:
        current = connection.execute(f'SELECT * FROM "{table}" WHERE id = ?', (row_id,)).fetchone()
        if not current:
            raise ValueError(f'{table.rstrip("s").title()} not found.')
        values = dict(payload)
        if table == 'customers':
            if 'state' in values:
                from malaysian_states import normalize as state_value
                values['state'] = state_value(values['state'])
            if values.get('full_name') and not values.get('name'):
                values['name'] = values['full_name']
            if values.get('name') and not values.get('full_name'):
                values['full_name'] = values['name']
            if values.get('phone_number') and not values.get('phone'):
                values['phone'] = values['phone_number']
            if values.get('phone') and not values.get('phone_number'):
                values['phone_number'] = values['phone']
            if not values.get('normalized_phone'):
                values['normalized_phone'] = normalize_customer_phone(values.get('phone_number') or values.get('phone') or current['phone'])
            if not values.get('customer_id'):
                values['customer_id'] = current['customer_id'] or next_customer_code()
            if values.get('archived') is None:
                values['archived'] = current['archived']
        if table == 'orders':
            values.pop('payment_status', None)
            if 'due_date' in values:
                values.setdefault('fulfilment_date', values['due_date'])
        assignments = [f'"{key}" = ?' for key in values]
        params = list(values.values())
        if table == 'orders':
            assignments.append('"updated_at" = ?')
            params.append(datetime.now().astimezone().isoformat(timespec='seconds'))
            if 'status' in values and values['status'] != current['status']:
                assignments.append('"status_updated_at" = ?')
                params.append(datetime.now().astimezone().isoformat(timespec='seconds'))
        connection.execute(
            f'UPDATE "{table}" SET {", ".join(assignments)} WHERE id = ?',
            [*params, row_id],
        )
        if table == 'orders':
            _update_payment_status(connection, int(row_id))
        if table == 'order_items':
            _update_order_totals(connection, int(current['order_id']))
        if table == 'payments':
            _update_payment_status(connection, int(current['order_id']))
        return [dict(row) for row in connection.execute(
            f'SELECT * FROM "{table}" WHERE id = ?', (row_id,)
        ).fetchall()]


def remove(table, row_id):
    _check_table(table)
    with transaction() as connection:
        related_order_id = None
        if table == 'order_items':
            item = connection.execute(
                'SELECT order_id FROM order_items WHERE id = ?', (row_id,)
            ).fetchone()
            related_order_id = int(item['order_id']) if item else None
        elif table == 'payments':
            payment = connection.execute(
                'SELECT order_id FROM payments WHERE id = ?', (row_id,)
            ).fetchone()
            related_order_id = int(payment['order_id']) if payment else None
        connection.execute(f'DELETE FROM "{table}" WHERE id = ?', (row_id,))
        if table == 'order_items':
            if related_order_id is not None:
                _update_order_totals(connection, related_order_id)
        if table == 'payments':
            if related_order_id is not None:
                _update_payment_status(connection, related_order_id)


def remove_customer(customer_id):
    """Delete an unreferenced customer or archive one with retained history."""
    with transaction() as connection:
        customer = connection.execute(
            'SELECT id FROM customers WHERE id = ?', (customer_id,),
        ).fetchone()
        if customer is None:
            raise ValueError('Customer no longer exists. Refresh and try again.')

        referenced = False
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
        ).fetchall()
        for table_row in tables:
            table = table_row['name']
            quoted_table = '"' + table.replace('"', '""') + '"'
            foreign_keys = connection.execute(
                f'PRAGMA foreign_key_list({quoted_table})',
            ).fetchall()
            for foreign_key in foreign_keys:
                if foreign_key['table'] != 'customers':
                    continue
                column = '"' + foreign_key['from'].replace('"', '""') + '"'
                count = connection.execute(
                    f'SELECT 1 FROM {quoted_table} WHERE {column} = ? LIMIT 1',
                    (customer_id,),
                ).fetchone()
                if count:
                    referenced = True
                    break
            if referenced:
                break

        if referenced:
            connection.execute(
                'UPDATE customers SET archived = 1 WHERE id = ?', (customer_id,),
            )
            return 'archived'
        connection.execute('DELETE FROM customers WHERE id = ?', (customer_id,))
        return 'deleted'


def create_order(customer, order, items):
    """Insert a customer if needed and save the order and lines atomically."""
    if not customer.get('name', '').strip() or not customer.get('phone', '').strip():
        raise ValueError('Customer name and phone number are required.')
    if not items:
        raise ValueError('Add at least one product to the order.')
    with transaction() as connection:
        raw_phone = customer['phone'].strip()
        normalized_phone = normalize_customer_phone(raw_phone)
        existing = connection.execute(
            'SELECT id FROM customers WHERE normalized_phone = ? OR phone = ? ORDER BY id LIMIT 1',
            (normalized_phone or raw_phone, raw_phone),
        ).fetchone()
        if existing:
            customer_id = int(existing['id'])
            connection.execute(
                'UPDATE customers SET name = ?, full_name = ?, phone = ?, phone_number = ?, normalized_phone = ?, address = ? WHERE id = ?',
                (
                    customer['name'].strip(),
                    customer['name'].strip(),
                    raw_phone,
                    raw_phone,
                    normalized_phone or raw_phone,
                    customer.get('address', '').strip(),
                    customer_id,
                ),
            )
        else:
            customer_id = _insert(connection, 'customers', {
                'name': customer['name'].strip(),
                'full_name': customer['name'].strip(),
                'phone': raw_phone,
                'phone_number': raw_phone,
                'normalized_phone': normalized_phone or raw_phone,
                'address': customer.get('address', '').strip(),
                'notes': customer.get('notes', ''),
                'state': customer.get('state', ''),
            })['id']
        values = dict(order)
        values['customer_id'] = customer_id
        created = _insert(connection, 'orders', values)
        for item in items:
            line = dict(item)
            line['order_id'] = created['id']
            _insert(connection, 'order_items', line)
        _update_order_totals(connection, int(created['id']))
        return dict(connection.execute(
            'SELECT * FROM orders WHERE id = ?', (created['id'],)
        ).fetchone())


def update_order(order_id, customer, order, items):
    """Update order/customer and replace all lines in one transaction."""
    if not customer.get('name', '').strip() or not customer.get('phone', '').strip():
        raise ValueError('Customer name and phone number are required.')
    if not items:
        raise ValueError('An order must contain at least one product.')
    with transaction() as connection:
        current = connection.execute(
            'SELECT customer_id, status FROM orders WHERE id = ?', (order_id,)
        ).fetchone()
        if not current:
            raise ValueError('Order not found.')
        from settings_store import runtime
        if order.get('status') == 'Cancelled' and current['status'] != 'Cancelled' and not runtime()['cancellation']:
            raise ValueError('Order cancellation is disabled in Settings.')
        saved_items = {
            int(row['id']): row for row in connection.execute(
                'SELECT id, product_id, unit_cost FROM order_items WHERE order_id = ?',
                (order_id,),
            )
        }
        prepared_items = []
        used_sources = set()
        for item in items:
            line = dict(item)
            source_id = line.pop('source_item_id', None)
            if source_id is not None:
                source = saved_items.get(int(source_id))
                if source is None or source['product_id'] != line.get('product_id'):
                    raise ValueError('An existing order line does not match this order/product.')
                if int(source_id) in used_sources:
                    raise ValueError('An existing order line cannot be reused twice.')
                used_sources.add(int(source_id))
                # Saved costs, including zero, are immutable for retained lines.
                line['unit_cost'] = source['unit_cost']
            else:
                # New/replacement lines snapshot the current catalogue cost at save time.
                product = connection.execute(
                    'SELECT unit_cost FROM products WHERE id = ?', (line.get('product_id'),)
                ).fetchone()
                if product is not None:
                    line['unit_cost'] = product['unit_cost']
            prepared_items.append(line)
        raw_phone = customer['phone'].strip()
        normalized_phone = normalize_customer_phone(raw_phone)
        connection.execute(
            '''UPDATE customers
               SET name = ?, full_name = ?, phone = ?, phone_number = ?, normalized_phone = ?, address = ?
               WHERE id = ?''',
            (
                customer['name'].strip(),
                customer['name'].strip(),
                raw_phone,
                raw_phone,
                normalized_phone or raw_phone,
                customer.get('address', '').strip(),
                current['customer_id'],
            ),
        )
        values = dict(order)
        values.pop('payment_status', None)
        values['updated_at'] = datetime.now().astimezone().isoformat(timespec='seconds')
        if values.get('status', current['status']) != current['status']:
            values['status_updated_at'] = values['updated_at']
        assignments = ', '.join(f'"{key}" = ?' for key in values)
        connection.execute(
            f'UPDATE orders SET {assignments} WHERE id = ?',
            [*values.values(), order_id],
        )
        connection.execute('DELETE FROM order_items WHERE order_id = ?', (order_id,))
        for item in prepared_items:
            line = dict(item)
            line['order_id'] = order_id
            _insert(connection, 'order_items', line)
        _update_order_totals(connection, int(order_id))


def delete_order(order_id):
    with transaction() as connection:
        connection.execute('DELETE FROM orders WHERE id = ?', (order_id,))


def order_details(order_id):
    with closing(_connect()) as connection:
        row = connection.execute("""
            SELECT o.*, c.name AS customer_name, c.phone AS phone_number,
                   c.address AS customer_address
            FROM orders o JOIN customers c ON c.id = o.customer_id
            WHERE o.id = ?
        """, (order_id,)).fetchone()
        if not row:
            return None
        return {
            'order': dict(row),
            'items': [dict(item) for item in connection.execute(
                'SELECT * FROM order_items WHERE order_id = ? ORDER BY id', (order_id,)
            )],
            'payments': [dict(payment) for payment in connection.execute(
                'SELECT * FROM payments WHERE order_id = ? ORDER BY paid_at, id', (order_id,)
            )],
        }


def list_orders():
    with closing(_connect()) as connection:
        rows = connection.execute("""
            SELECT o.id, o.order_code, o.customer_id, c.name AS customer_name,
                   c.phone AS phone_number, c.address AS customer_address,
                   o.ordered_at AS order_date, o.due_date, o.fulfilment_date,
                   o.fulfilment_method, o.total_amount, o.status,
                   o.payment_status, o.notes, o.created_at, o.updated_at,
                   o.status_updated_at,
                   COALESCE(GROUP_CONCAT(DISTINCT oi.product_name), '') AS products
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            LEFT JOIN order_items oi ON oi.order_id = o.id
            GROUP BY o.id
            ORDER BY o.ordered_at DESC, o.id DESC
        """).fetchall()
        return [dict(row) for row in rows]


def next_order_code():
    with closing(_connect()) as connection:
        last_id = connection.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'orders'"
        ).fetchone()
        next_id = int(last_id['seq']) + 1 if last_id else 1
        from settings_store import runtime
        return f"{runtime()['prefix']}{next_id:03d}"


def import_supabase_records():
    from uat_hardening import blocked
    blocked()
    """One-time, atomic migration of existing Supabase business records."""
    import db as supabase_db

    legacy = {
        table: supabase_db.all_rows(table)
        for table in ('products', 'customers', 'orders', 'order_items', 'payments')
    }
    with transaction() as connection:
        already_imported = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'supabase_imported_at'"
        ).fetchone()
        if already_imported:
            raise ValueError('Supabase records have already been imported into this database.')
        existing_business_data = sum(
            connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in ('customers', 'orders', 'order_items', 'payments')
        )
        if existing_business_data:
            raise ValueError(
                'Local customer/order/payment data already exists. Migration only runs on a fresh local database.'
            )
        customized_catalogue = connection.execute("""
            SELECT COUNT(*) FROM products
            WHERE price != 0 OR unit_cost != 0 OR image_url IS NOT NULL
        """).fetchone()[0]
        if customized_catalogue:
            raise ValueError(
                'Local product prices or images are already configured. Migration will not overwrite them.'
            )

        customer_ids = {}
        for customer in legacy['customers']:
            cursor = connection.execute(
                'INSERT INTO customers (name, phone, address, created_at) VALUES (?, ?, ?, ?)',
                (
                    customer.get('name') or 'Unknown customer',
                    customer.get('phone') or '',
                    customer.get('address') or '',
                    customer.get('created_at') or datetime.now().astimezone().isoformat(timespec='seconds'),
                ),
            )
            customer_ids[int(customer['id'])] = int(cursor.lastrowid)

        product_ids = {}
        for product in legacy['products']:
            name = product.get('name') or 'Unnamed product'
            category = product.get('category') or 'Dessert'
            existing = connection.execute(
                'SELECT id FROM products WHERE name = ? AND category = ?', (name, category)
            ).fetchone()
            values = (
                float(product.get('price') or 0),
                float(product.get('unit_cost') or 0),
                product.get('image_url'),
                int(bool(product.get('active', True))),
            )
            if existing:
                product_id = int(existing['id'])
                connection.execute(
                    'UPDATE products SET price=?, unit_cost=?, image_url=?, active=? WHERE id=?',
                    (*values, product_id),
                )
            else:
                cursor = connection.execute(
                    """INSERT INTO products (name, category, price, unit_cost, image_url, active)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (name, category, *values),
                )
                product_id = int(cursor.lastrowid)
            product_ids[int(product['id'])] = product_id

        order_ids = {}
        for legacy_order in legacy['orders']:
            old_customer_id = int(legacy_order['customer_id'])
            if old_customer_id not in customer_ids:
                raise ValueError(f"Order {legacy_order['id']} references a missing customer.")
            status = legacy_order.get('status') or 'Pending'
            if status == 'In Production':
                status = 'Preparing'
            if status not in ORDER_STATUSES:
                status = 'Pending'
            created_at = legacy_order.get('ordered_at') or datetime.now().astimezone().isoformat(timespec='seconds')
            due_date = legacy_order.get('due_date') or created_at[:10]
            cursor = connection.execute(
                """INSERT INTO orders
                   (customer_id, ordered_at, due_date, fulfilment_date, fulfilment_method,
                    status, payment_status, notes, created_at, updated_at, status_updated_at)
                   VALUES (?, ?, ?, ?, 'Pickup', ?, 'Unpaid', ?, ?, ?, ?)""",
                (
                    customer_ids[old_customer_id], created_at, due_date, due_date, status,
                    legacy_order.get('notes') or '', created_at, created_at, created_at,
                ),
            )
            new_id = int(cursor.lastrowid)
            order_ids[int(legacy_order['id'])] = new_id
            connection.execute(
                'UPDATE orders SET order_code = ? WHERE id = ?',
                (f'ORD{new_id:03d}', new_id),
            )

        for item in legacy['order_items']:
            old_order_id = int(item['order_id'])
            if old_order_id not in order_ids:
                raise ValueError(f"Order item {item['id']} references a missing order.")
            old_product_id = int(item['product_id'])
            if old_product_id not in product_ids:
                raise ValueError(f"Order item {item['id']} references a missing product.")
            product_id = product_ids[old_product_id]
            product = connection.execute(
                'SELECT name FROM products WHERE id = ?', (product_id,)
            ).fetchone()
            quantity = int(item['quantity'])
            unit_price = float(item['unit_price'])
            connection.execute(
                """INSERT INTO order_items
                   (order_id, product_id, product_name, quantity, unit_price, unit_cost, subtotal)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    order_ids[old_order_id], product_id, product['name'], quantity,
                    unit_price, float(item.get('unit_cost') or 0), quantity * unit_price,
                ),
            )

        for payment in legacy['payments']:
            old_order_id = int(payment['order_id'])
            if old_order_id not in order_ids:
                raise ValueError(f"Payment {payment['id']} references a missing order.")
            connection.execute(
                """INSERT INTO payments (order_id, paid_at, amount, method, reference)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    order_ids[old_order_id],
                    payment.get('paid_at') or datetime.now().astimezone().isoformat(timespec='seconds'),
                    float(payment['amount']),
                    payment.get('method') or 'Transfer',
                    payment.get('reference') or '',
                ),
            )

        for order_id in order_ids.values():
            _update_order_totals(connection, order_id)
            _update_payment_status(connection, order_id)
        connection.execute(
            "INSERT INTO app_metadata (key, value) VALUES ('supabase_imported_at', ?)",
            (datetime.now().astimezone().isoformat(timespec='seconds'),),
        )
        return {
            'products': len(product_ids),
            'customers': len(customer_ids),
            'orders': len(order_ids),
            'order_items': len(legacy['order_items']),
            'payments': len(legacy['payments']),
        }


initialize()
