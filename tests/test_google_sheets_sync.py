"""Synthetic sync tests use a disposable SQLite database and mocked sheet rows."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import google_sheets_connection
import google_sheets_sync
import orders_store
import sqlite_db


class GoogleSheetsSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bizmar-sheets-sync-')
        self.db_path = sqlite_db.DB_PATH
        sqlite_db.DB_PATH = Path(self.temp.name) / 'sync.sqlite3'
        self.owner = patch.object(
            orders_store, 'current_owner',
            return_value='synthetic-owner@example.test',
        )
        self.owner.start()
        self.product_owner=patch('products_store.current_owner',return_value='synthetic-owner@example.test')
        self.product_owner.start()
        sqlite_db.initialize()
        from uat_fixture import seed_products
        seed_products(sqlite_db)
        self.product = sqlite_db.all_rows('products')[0]
        sqlite_db.edit(
            'products', self.product['id'], {'name': 'Demo Tart', 'price': 55.0, 'unit_cost': 20.0},
        )
        self.product = sqlite_db.all_rows('products', id=self.product['id'])[0]
        self.config = google_sheets_connection.GoogleSheetsConfig(
            spreadsheet_id='synthetic-sheet-0123456789',
            worksheet_name='Form Responses 1',
            service_account_file=Path('unused-injected-session.json'),
        )

    def tearDown(self):
        self.product_owner.stop()
        self.owner.stop()
        sqlite_db.DB_PATH = self.db_path
        self.temp.cleanup()

    def headers(self):
        return [
            "Customer's Name",
            'WhatsApp Phone Number',
            'Timestamp',
            'Preferred Pickup / Delivery Date',
            'Preferred Time',
            'Prefeed Time',
            'Fullfilment Method',
            'Delivery Adress (Delivery Only)',
            'State',
            'Special Requests / Notes',
            'Payment Method',
            'Amount Paid (RM)',
            f'Product & Quantity [{self.product["name"]} \ufffd - RM 55.00]',
            f'Product Quantity Selection [{self.product["name"]}]',
            'Products',
        ]

    def make_snapshot(self, rows, row_numbers=None):
        headers = self.headers()
        return google_sheets_connection.GoogleSheetsSnapshot(
            sheet_id=1234,
            headers=headers,
            rows=[dict(zip(headers, row)) for row in rows],
            row_numbers=row_numbers or list(range(2, 2 + len(rows))),
        )

    def row(self, name='Synthetic Customer', quantity='2', alternate='', preferred='2:30 PM', prefeed=''):
        return [
            name, '0123456789', '2026-10-27 10:00:00', '2026-10-28',
            preferred, prefeed, 'Pickup', '', 'Selangor', 'Synthetic note',
            'Online Transfer', '55.00', quantity, alternate, '',
        ]

    def prepare(self, snapshot):
        return google_sheets_sync.prepare_preview(snapshot, self.config.spreadsheet_id)

    def test_exact_headers_price_suffix_blank_cells_and_overlapping_columns(self):
        prepared = self.prepare(self.make_snapshot([self.row(quantity='', alternate='2')]))
        self.assertEqual(prepared.preview.errors, [])
        self.assertEqual(prepared.preview.records[0]['lines'][0]['quantity'], 2)
        self.assertEqual(prepared.preview.records[0]['subtotal'], 110.0)
        self.assertEqual(prepared.preview.records[0]['order']['fulfilment_time'], '14:30')
        self.assertEqual(prepared.preview.records[0]['order']['submitted_payment_method'], 'Online Transfer')
        self.assertEqual(prepared.preview.records[0]['order']['submitted_amount_paid'], 55.0)
        self.assertIsNone(prepared.preview.records[0]['order'].get('delivery_quote_status'))

    def test_same_quantity_columns_are_not_added_and_conflicts_are_blocked(self):
        equal = self.prepare(self.make_snapshot([self.row(quantity='2', alternate='2')]))
        self.assertFalse(equal.preview.errors)
        self.assertEqual(equal.preview.records[0]['lines'][0]['quantity'], 2)

        conflict = self.prepare(self.make_snapshot([self.row(quantity='2', alternate='3')]))
        self.assertTrue(any('conflicting quantity columns' in error for error in conflict.preview.errors))
        self.assertEqual(conflict.preview.records, [])

    def test_same_timestamp_gets_distinct_row_identity_and_duplicates_are_reviewed(self):
        rows = [self.row('Synthetic One'), self.row('Synthetic Two')]
        prepared = self.prepare(self.make_snapshot(rows))
        self.assertFalse(prepared.preview.errors)
        keys = [record['import_response_key'] for record in prepared.preview.records]
        self.assertNotEqual(keys[0], keys[1])
        self.assertIn(':row:2', keys[0])
        self.assertIn(':row:3', keys[1])

        duplicate = self.prepare(self.make_snapshot([self.row(), self.row()], [4, 5]))
        self.assertTrue(duplicate.preview.ambiguous_rows)
        with self.assertRaises(google_sheets_sync.SyncReviewRequired):
            google_sheets_sync.commit_preview(self.config, duplicate)

    def test_explicit_confirmation_idempotency_notifications_and_read_state(self):
        prepared = self.prepare(self.make_snapshot([self.row()]))
        orders_store.confirm_google_sheets_sync(self.config.spreadsheet_id, prepared.sheet_id)
        first = google_sheets_sync.commit_preview(self.config, prepared)
        self.assertEqual(first['imported'], 1)
        self.assertEqual(sqlite_db.all_rows('payments'), [])
        order = sqlite_db.all_rows('orders')[0]
        self.assertEqual((order['status'], order['payment_status']), ('Pending', 'Unpaid'))
        self.assertEqual(len(orders_store.list_order_notifications(unread_only=True)), 1)

        repeated = self.prepare(self.make_snapshot([self.row()]))
        self.assertEqual(repeated.preview.records, [])
        second = google_sheets_sync.commit_preview(self.config, repeated)
        self.assertEqual(second['imported'], 0)
        self.assertEqual(len(sqlite_db.all_rows('orders')), 1)
        self.assertEqual(orders_store.order_notification_counts()['unread'], 1)

        notification = orders_store.list_order_notifications()[0]
        self.assertEqual(notification['order_id'], order['id'])
        self.assertEqual(notification['customer_name'], 'Synthetic Customer')
        orders_store.mark_order_notification_read(notification['id'])
        self.assertEqual(orders_store.order_notification_counts()['unread'], 0)

    def test_import_matches_archived_customer_without_recreating_or_unarchiving(self):
        customer = sqlite_db.add('customers', {
            'customer_id': 'C001',
            'name': 'Archived Customer',
            'full_name': 'Archived Customer',
            'phone': '0123456789',
            'phone_number': '0123456789',
            'normalized_phone': '+60123456789',
            'address': 'Existing address',
            'state': 'Selangor',
            'archived': 1,
        })
        prepared = self.prepare(self.make_snapshot([self.row()]))
        orders_store.confirm_google_sheets_sync(self.config.spreadsheet_id, prepared.sheet_id)
        result = google_sheets_sync.commit_preview(self.config, prepared)

        customers = sqlite_db.all_rows('customers')
        self.assertEqual(result['imported'], 1)
        self.assertEqual(len(customers), 1)
        self.assertEqual(customers[0]['id'], customer['id'])
        self.assertEqual(customers[0]['archived'], 1)
        self.assertEqual(sqlite_db.all_rows('orders')[0]['customer_id'], customer['id'])

    def test_edited_source_row_blocks_sync_without_overwriting_order(self):
        original = self.make_snapshot([self.row()])
        prepared = self.prepare(original)
        orders_store.confirm_google_sheets_sync(self.config.spreadsheet_id, prepared.sheet_id)
        google_sheets_sync.commit_preview(self.config, prepared)
        edited = self.row()
        edited[9] = 'Changed synthetic note'
        changed = self.prepare(self.make_snapshot([edited]))
        self.assertTrue(any('changed since its last sync' in error for error in changed.preview.errors))
        self.assertEqual(changed.preview.records, [])
        self.assertEqual(sqlite_db.all_rows('orders')[0]['notes'], 'Synthetic note')

    def test_concurrent_sync_lease_and_pause_enforce_confirmation(self):
        orders_store.confirm_google_sheets_sync(self.config.spreadsheet_id, 1234)
        first = orders_store.acquire_google_sheets_lease(self.config.spreadsheet_id, 1234)
        self.assertIsNotNone(first)
        self.assertIsNone(orders_store.acquire_google_sheets_lease(self.config.spreadsheet_id, 1234))
        orders_store.finish_google_sheets_sync(self.config.spreadsheet_id, first)
        orders_store.pause_google_sheets_sync(self.config.spreadsheet_id)
        with self.assertRaises(PermissionError):
            orders_store.acquire_google_sheets_lease(self.config.spreadsheet_id, 1234)


if __name__ == '__main__':
    unittest.main()
