"""Additive Orders migration. Legacy statuses remain readable and map to Pending."""
ORDER_FIELDS = {
    'source': "TEXT NOT NULL DEFAULT 'Other'",
    'discount': 'REAL NOT NULL DEFAULT 0 CHECK(discount >= 0)',
    'delivery_fee': 'REAL NOT NULL DEFAULT 0 CHECK(delivery_fee >= 0)',
    'fulfilment_time': "TEXT NOT NULL DEFAULT ''",
    'delivery_address': "TEXT NOT NULL DEFAULT ''",
    'customer_name_snapshot': "TEXT NOT NULL DEFAULT ''",
    'phone_snapshot': "TEXT NOT NULL DEFAULT ''",
    'customer_state_snapshot': "TEXT NOT NULL DEFAULT ''",
    'delivery_state': "TEXT NOT NULL DEFAULT ''",
    'delivery_quote_status': "TEXT NOT NULL DEFAULT 'Confirmed'",
    'rider_cost': 'REAL CHECK(rider_cost IS NULL OR rider_cost >= 0)',
    'free_delivery_applied': 'INTEGER NOT NULL DEFAULT 0',
    'final_payable_amount': 'REAL',
    'import_source': "TEXT NOT NULL DEFAULT ''",
    'import_response_key': 'TEXT',
    'source_submitted_at': "TEXT NOT NULL DEFAULT ''",
    'payment_preference': "TEXT NOT NULL DEFAULT ''",
    'submitted_payment_method': "TEXT NOT NULL DEFAULT ''",
    'submitted_amount_paid': 'REAL',
    'payment_receipt_reference': "TEXT NOT NULL DEFAULT ''",
    'completed_at': 'TEXT', 'cancelled_at': 'TEXT',
    'cancellation_reason': "TEXT NOT NULL DEFAULT ''",
    'version': 'INTEGER NOT NULL DEFAULT 0',
    'submission_token': 'TEXT', 'external_order_id': 'TEXT', 'synced_at': 'TEXT',
}
PAYMENT_FIELDS = {'notes': "TEXT NOT NULL DEFAULT ''", 'submission_token': 'TEXT'}


def migrate(connection):
    customer_columns = {row['name'] for row in connection.execute('PRAGMA table_info(customers)')}
    if customer_columns and 'state' not in customer_columns:
        connection.execute("ALTER TABLE customers ADD COLUMN state TEXT NOT NULL DEFAULT ''")
    for table, fields in (('orders', ORDER_FIELDS), ('payments', PAYMENT_FIELDS)):
        columns = {row['name'] for row in connection.execute(f'PRAGMA table_info({table})')}
        for name, definition in fields.items():
            if name not in columns:
                connection.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
    connection.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_order_submission ON orders(submission_token) WHERE submission_token IS NOT NULL')
    connection.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_submission ON payments(submission_token) WHERE submission_token IS NOT NULL')
    connection.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_order_external ON orders(source, external_order_id) WHERE external_order_id IS NOT NULL')
    connection.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_order_import_response ON orders(import_response_key) WHERE import_response_key IS NOT NULL')
    connection.execute('''CREATE TABLE IF NOT EXISTS order_activity (
        id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
        action TEXT NOT NULL, occurred_at TEXT NOT NULL, actor TEXT NOT NULL,
        summary TEXT NOT NULL)''')
    connection.execute('''CREATE TABLE IF NOT EXISTS order_requests (token TEXT PRIMARY KEY, actor TEXT NOT NULL, operation TEXT NOT NULL, payload_hash TEXT NOT NULL, result_id INTEGER NOT NULL)''')
    migrate_google_sheets(connection)
    connection.execute('CREATE INDEX IF NOT EXISTS idx_order_activity_order ON order_activity(order_id, id)')
    connection.execute("INSERT OR IGNORE INTO app_metadata(key,value) VALUES ('orders_schema_version','1')")
    connection.execute("INSERT OR IGNORE INTO app_metadata(key,value) VALUES ('orders_state_schema_version','1')")
    connection.execute("INSERT OR IGNORE INTO app_metadata(key,value) VALUES ('orders_file_import_schema_version','1')")


def migrate_google_sheets(connection):
    """Only additive sync tables and their version marker; no business DML."""
    connection.execute('''CREATE TABLE IF NOT EXISTS google_sheets_sync_state (
        spreadsheet_id TEXT PRIMARY KEY, worksheet_id INTEGER NOT NULL,
        confirmed_at TEXT, last_synced_at TEXT, last_error TEXT NOT NULL DEFAULT '',
        last_new_orders INTEGER NOT NULL DEFAULT 0,
        lease_token TEXT, lease_until TEXT)''')
    sync_columns={row['name'] for row in connection.execute('PRAGMA table_info(google_sheets_sync_state)')}
    if 'last_attempt_at' not in sync_columns:
        connection.execute('ALTER TABLE google_sheets_sync_state ADD COLUMN last_attempt_at TEXT')
    connection.execute('''CREATE TABLE IF NOT EXISTS google_sheets_rows (
        spreadsheet_id TEXT NOT NULL, worksheet_id INTEGER NOT NULL,
        row_number INTEGER NOT NULL, content_hash TEXT NOT NULL,
        order_id INTEGER NOT NULL REFERENCES orders(id),
        response_key TEXT NOT NULL UNIQUE,
        imported_at TEXT NOT NULL,
        PRIMARY KEY(spreadsheet_id, worksheet_id, row_number))''')
    connection.execute('''CREATE TABLE IF NOT EXISTS order_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id),
        source_key TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        read_at TEXT)''')
    connection.execute("INSERT OR IGNORE INTO app_metadata(key,value) VALUES ('google_sheets_sync_schema_version','1')")
    from sync_monitor_schema import migrate as migrate_monitor
    migrate_monitor(connection)
    from customer_messages_schema import migrate as migrate_messages
    migrate_messages(connection)
