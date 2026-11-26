"""Additive owner communication storage; no business-table backfills."""


def migrate(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS customer_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        order_id INTEGER REFERENCES orders(id),
        template_type TEXT NOT NULL, content TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Draft' CHECK(status IN ('Draft','WhatsApp Opened','Sent')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        whatsapp_opened_at TEXT, sent_at TEXT,
        followup_at TEXT, followup_completed_at TEXT, notes TEXT NOT NULL DEFAULT '',
        version INTEGER NOT NULL DEFAULT 0,
        request_token TEXT NOT NULL UNIQUE, creation_hash TEXT NOT NULL)''')
    connection.execute('''CREATE TABLE IF NOT EXISTS customer_message_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL REFERENCES customer_messages(id),
        event_key TEXT NOT NULL UNIQUE, action TEXT NOT NULL,
        occurred_at TEXT NOT NULL, content TEXT NOT NULL DEFAULT '')''')
    connection.execute('''CREATE TABLE IF NOT EXISTS customer_message_templates (
        template_type TEXT PRIMARY KEY, content TEXT NOT NULL,
        updated_at TEXT NOT NULL)''')
    connection.execute('CREATE INDEX IF NOT EXISTS idx_customer_messages_customer ON customer_messages(customer_id,id DESC)')
    connection.execute('CREATE INDEX IF NOT EXISTS idx_customer_messages_followup ON customer_messages(followup_at) WHERE followup_completed_at IS NULL')
