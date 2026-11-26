"""Additive operational history only; never backfill or modify business records."""


def migrate(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS google_sheets_sync_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        spreadsheet_id TEXT NOT NULL, worksheet_id INTEGER NOT NULL,
        lease_token TEXT NOT NULL UNIQUE, started_at TEXT NOT NULL,
        lease_expires_at TEXT NOT NULL, finished_at TEXT,
        trigger TEXT NOT NULL CHECK(trigger IN ('Automatic','Manual')),
        result TEXT NOT NULL DEFAULT 'Running' CHECK(result IN ('Running','Success','Partial','Failed')),
        imported INTEGER NOT NULL DEFAULT 0 CHECK(imported>=0),
        associated INTEGER NOT NULL DEFAULT 0 CHECK(associated>=0),
        skipped INTEGER NOT NULL DEFAULT 0 CHECK(skipped>=0),
        failed_rows INTEGER NOT NULL DEFAULT 0 CHECK(failed_rows>=0),
        error_kind TEXT NOT NULL DEFAULT '', error_summary TEXT NOT NULL DEFAULT '')''')
    connection.execute('CREATE INDEX IF NOT EXISTS idx_sheets_history_source ON google_sheets_sync_history(spreadsheet_id,id DESC)')
