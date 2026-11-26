from io import BytesIO
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

import google_forms_importer as importer
import orders_store
import sqlite_db
from malaysian_states import STATES


class Upload:
    def __init__(self, name, content):
        self.name = name
        self._content = content

    def getvalue(self):
        return self._content


class GoogleFormsImporterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bizmar-google-forms-')
        self.db_path = sqlite_db.DB_PATH
        sqlite_db.DB_PATH = Path(self.temp.name) / 'orders.sqlite3'
        self.owner = patch.object(orders_store, 'current_owner', return_value='synthetic-owner@example.test')
        self.owner.start()
        sqlite_db.initialize()
        from uat_fixture import seed_products
        seed_products(sqlite_db)
        self.product = sqlite_db.all_rows('products')[0]
        sqlite_db.edit('products', self.product['id'], {'price': 55., 'unit_cost': 20.})
        self.product = sqlite_db.all_rows('products', id=self.product['id'])[0]

    def tearDown(self):
        self.owner.stop()
        sqlite_db.DB_PATH = self.db_path
        self.temp.cleanup()

    def frame(self, rows):
        return pd.DataFrame(rows, columns=[
            'Response ID', 'Timestamp', 'Name', 'Phone', 'Due Date', 'Method',
            'Address', self.product['name'],
        ])

    def mappings(self, *, response_id=True):
        return {
            'response_id': 'Response ID' if response_id else None,
            'customer_name': 'Name',
            'phone': 'Phone',
            'ordered_at': None,
            'submitted_at': 'Timestamp',
            'fulfilment_date': 'Due Date',
            'fulfilment_method': 'Method',
            'delivery_address': 'Address',
        }

    def preview(self, frame, *, response_id=True, existing_keys=()):
        return importer.build_preview(
            frame, self.mappings(response_id=response_id),
            {self.product['name']: self.product['id']},
            sqlite_db.all_rows('products'), existing_keys, default_method='Pickup',
        )

    def test_reads_csv_and_xlsx_and_rejects_large_files(self):
        frame = self.frame([['id-1', '2026-10-27 10:00:00', 'Aina', '0123456789',
                             '2026-10-28', 'Pickup', '', '2']])
        csv = Upload('responses.csv', frame.to_csv(index=False).encode('utf-8-sig'))
        self.assertEqual(importer.read_upload(csv).shape, frame.shape)
        output = BytesIO()
        frame.to_excel(output, index=False)
        excel = Upload('responses.xlsx', output.getvalue())
        self.assertEqual(importer.read_upload(excel).shape, frame.shape)
        with self.assertRaisesRegex(ValueError, 'exceeds 5 MB'):
            importer.read_upload(Upload('responses.csv', b'x' * (5 * 1024 * 1024 + 1)))
        with self.assertRaisesRegex(ValueError, 'headings must be unique'):
            importer.read_upload(Upload('duplicate.csv', b'Name,Name\nAina,Siti\n'))

    def test_import_accepts_all_official_state_names_and_logs_unknown_as_unspecified(self):
        columns=['Response ID','Timestamp','Name','Phone','Due Date','Method',
                 'Address',self.product['name'],'Customer State','Delivery State']
        rows=[
            [f'state-{index}', '2026-10-27', f'Synthetic State {index}',
             f'011{index:08d}', '2026-10-28', 'Delivery',
             'Synthetic delivery address', '1', state, state]
            for index,state in enumerate(STATES,1)
        ]
        frame=pd.DataFrame(rows,columns=columns)
        mapping=self.mappings()
        mapping.update(customer_state='Customer State',delivery_state='Delivery State')
        preview=importer.build_preview(
            frame,mapping,{self.product['name']:self.product['id']},
            sqlite_db.all_rows('products'),default_method='Pickup',
        )
        self.assertFalse(preview.errors)
        self.assertEqual(len(preview.records),len(STATES))
        self.assertEqual([record['customer']['state'] for record in preview.records],list(STATES))
        importer.import_preview(preview)
        self.assertEqual([row['state'] for row in sqlite_db.all_rows('customers')],list(STATES))
        self.assertEqual([row['delivery_state'] for row in sqlite_db.all_rows('orders')],list(STATES))

        invalid=frame.iloc[[0]].copy()
        invalid.loc[invalid.index[0],'Customer State']='Atlantis'
        invalid.loc[invalid.index[0],'Delivery State']='Atlantis'
        with self.assertLogs(importer.logger,level='WARNING') as logs:
            invalid_preview=importer.build_preview(
                invalid,mapping,{self.product['name']:self.product['id']},
                sqlite_db.all_rows('products'),default_method='Pickup',
            )
        self.assertFalse(invalid_preview.errors)
        self.assertEqual(invalid_preview.records[0]['customer']['state'],'')
        self.assertEqual(invalid_preview.records[0]['order']['delivery_state'],'')
        self.assertTrue(any('missing or unrecognized customer state' in message for message in logs.output))
        self.assertTrue(any('missing or unrecognized delivery destination state' in message for message in logs.output))

    def test_blank_grid_cell_is_zero_and_catalogue_price_is_used(self):
        frame = self.frame([
            ['id-1', '2026-10-27', 'Aina', '0123456789', '2026-10-28', 'Pickup', '', '2'],
            ['id-2', '2026-10-27', 'Siti', '01123456789', '2026-10-29', 'Pickup', '', ''],
        ])
        preview = self.preview(frame)
        self.assertEqual(len(preview.records), 1)
        self.assertEqual(preview.errors, ['Row 3: At least one mapped product quantity must be greater than zero'])
        with self.assertRaisesRegex(ValueError, 'Resolve all row and mapping errors'):
            importer.import_preview(preview)
        self.assertEqual(sqlite_db.all_rows('orders'), [])
        record = preview.records[0]
        self.assertEqual(record['lines'][0]['unit_price'], 55.)
        self.assertEqual(record['subtotal'], 110.)

    def test_delivery_policy_pickup_free_and_awaiting_quote(self):
        frame = self.frame([
            ['pickup', '2026-10-27', 'Aina', '0123456789', '2026-10-28', 'Pickup', '', '1'],
            ['free', '2026-10-27', 'Siti', '01123456789', '2026-10-29', 'Delivery', 'Kedah address', '2'],
            ['quote', '2026-10-27', 'Mira', '01334567890', '2026-10-30', 'Delivery', 'Penang address', '1'],
        ])
        preview = self.preview(frame)
        self.assertFalse(preview.errors)
        result = importer.import_preview(preview)
        self.assertEqual(result['imported'], 3)
        saved = sqlite_db.all_rows('orders')
        by_customer = {row['customer_name_snapshot']: row for row in saved}
        self.assertEqual(by_customer['Aina']['delivery_fee'], 0)
        self.assertEqual(by_customer['Aina']['delivery_quote_status'], 'Confirmed')
        self.assertEqual(by_customer['Siti']['free_delivery_applied'], 1)
        self.assertEqual(by_customer['Siti']['delivery_quote_status'], 'Confirmed')
        self.assertEqual(by_customer['Mira']['delivery_quote_status'], 'Awaiting Rider Quote')
        self.assertTrue(all(row['status'] == 'Pending' and row['payment_status'] == 'Unpaid' for row in saved))
        self.assertEqual(len(sqlite_db.all_rows('payments')), 0)
        customers = sqlite_db.all_rows('customers')
        self.assertEqual(len({customer['customer_id'] for customer in customers}), len(customers))

    def test_edit_confirms_quote_before_payment_and_keeps_pending_without_confirmation(self):
        frame = self.frame([
            ['quote-edit', '2026-10-27', 'Mira', '01334567890', '2026-10-30',
             'Delivery', 'Penang address', '1'],
        ])
        preview = self.preview(frame)
        saved = importer.import_preview(preview)
        identity = saved['order_ids'][0]
        detail = orders_store.details(identity)
        order = detail['order']
        lines = [
            dict(product_id=item['product_id'], quantity=item['quantity'],
                 unit_price=item['unit_price'])
            for item in detail['items']
        ]
        customer = {
            'name': order['customer_name'],
            'phone': order['phone_number'],
            'address': order['customer_address'],
            'state': order['customer_state_snapshot'],
        }
        edits = dict(
            ordered_at=order['ordered_at'],
            fulfilment_date=order['fulfilment_date'],
            fulfilment_method='Delivery',
            delivery_address=order['delivery_address'],
            delivery_state=order['delivery_state'],
            source=order['source'],
            discount=order['discount'],
            delivery_fee=63,
            notes=order['notes'],
        )
        orders_store.save_order(
            customer, edits, lines, token='quote-edit-unconfirmed-001',
            order_id=identity, version=order['version'],
        )
        still_pending = orders_store.details(identity)['order']
        self.assertEqual(still_pending['delivery_quote_status'], 'Awaiting Rider Quote')
        self.assertEqual(still_pending['delivery_fee'], 0)
        self.assertTrue(still_pending['quote_pending'])

        confirmed = orders_store.details(identity)['order']
        edits['confirmed_rider_quote'] = 63
        orders_store.save_order(
            customer, edits, lines, token='quote-edit-confirmed-001',
            order_id=identity, version=confirmed['version'],
        )
        final = orders_store.details(identity)['order']
        self.assertFalse(final['quote_pending'])
        self.assertEqual(final['delivery_fee'], 63)
        self.assertEqual(final['total_amount'], 118)
        orders_store.record_payment(
            identity, {'amount': 63, 'method': 'Cash'}, token='quote-edit-payment-001',
        )
        final = orders_store.details(identity)['order']
        self.assertEqual(final['amount_paid'], 63)
        self.assertEqual(final['balance'], 55)

    def test_form_payment_claim_is_not_a_verified_ledger_payment(self):
        frame = self.frame([
            ['id-paid', '2026-10-27', 'Aina', '0123456789', '2026-10-28', 'Pickup', '', '1'],
        ])
        frame['Amount Paid'] = ['20']
        mapping = self.mappings()
        mapping['submitted_amount_paid'] = 'Amount Paid'
        preview = importer.build_preview(
            frame, mapping, {self.product['name']: self.product['id']},
            sqlite_db.all_rows('products'), default_method='Pickup',
        )
        importer.import_preview(preview)
        saved = sqlite_db.all_rows('orders')[0]
        self.assertEqual(saved['submitted_amount_paid'], 20.)
        self.assertEqual(saved['payment_status'], 'Unpaid')
        self.assertEqual(sqlite_db.all_rows('payments'), [])

    def test_fallback_does_not_use_timestamp_alone_and_flags_identical_rows(self):
        frame = self.frame([
            ['', '2026-10-27 10:00:00', 'Aina', '0123456789', '2026-10-28', 'Pickup', '', '1'],
            ['', '2026-10-27 10:00:00', 'Siti', '01123456789', '2026-10-28', 'Pickup', '', '1'],
        ])
        preview = self.preview(frame, response_id=False)
        keys = [record['import_response_key'] for record in preview.records]
        self.assertEqual(len(set(keys)), 2)
        self.assertFalse(preview.ambiguous_rows)

        duplicates = pd.concat([frame.iloc[[0]], frame.iloc[[0]]], ignore_index=True)
        ambiguous = self.preview(duplicates, response_id=False)
        self.assertTrue(ambiguous.ambiguous_rows)
        with self.assertRaisesRegex(ValueError, 'explicitly confirm'):
            importer.import_preview(ambiguous)
        self.assertEqual(sqlite_db.all_rows('orders'), [])
        importer.import_preview(ambiguous, acknowledge_ambiguous=True)
        self.assertEqual(len(sqlite_db.all_rows('orders')), 2)

    def test_existing_response_key_is_skipped_on_repeat_import(self):
        frame = self.frame([['id-1', '2026-10-27', 'Aina', '0123456789',
                             '2026-10-28', 'Pickup', '', '1']])
        preview = self.preview(frame)
        self.assertEqual(importer.import_preview(preview)['imported'], 1)
        second = self.preview(frame, existing_keys=orders_store.imported_response_keys())
        self.assertEqual(second.records, [])
        self.assertEqual(len(second.already_imported), 1)
        self.assertEqual(len(second.already_imported), 1)
        result = orders_store.import_google_forms_orders(preview.records)
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(len(sqlite_db.all_rows('orders')), 1)

    def test_transaction_rolls_back_if_catalogue_changes_after_preview(self):
        frame = self.frame([
            ['first', '2026-10-27', 'Aina', '0123456789', '2026-10-28', 'Pickup', '', '1'],
            ['second', '2026-10-27', 'Siti', '01123456789', '2026-10-29', 'Pickup', '', '1'],
        ])
        preview = self.preview(frame)
        sqlite_db.edit('products', self.product['id'], {'price': 56.})
        with self.assertRaisesRegex(ValueError, 'price changed'):
            importer.import_preview(preview)
        self.assertEqual(sqlite_db.all_rows('orders'), [])
        self.assertEqual(sqlite_db.all_rows('customers'), [])
        self.assertEqual(sqlite_db.all_rows('order_items'), [])
        with closing(sqlite_db._connect()) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM order_activity').fetchone()[0], 0)

    def test_duplicate_stable_ids_and_ambiguous_dates_require_resolution(self):
        duplicate_ids = self.frame([
            ['same-id', '2026-10-27', 'Aina', '0123456789', '2026-10-28', 'Pickup', '', '1'],
            ['same-id', '2026-10-27', 'Siti', '01123456789', '2026-10-29', 'Pickup', '', '1'],
        ])
        duplicate_preview = self.preview(duplicate_ids)
        self.assertTrue(any('Stable response ID duplicates' in error for error in duplicate_preview.errors))
        ambiguous_date = self.frame([
            ['id-date', '04/05/2026', 'Aina', '0123456789', '2026-10-28', 'Pickup', '', '1'],
        ])
        date_preview = self.preview(ambiguous_date)
        self.assertTrue(any('ambiguous' in error for error in date_preview.errors))
        self.assertEqual(sqlite_db.all_rows('orders'), [])


if __name__ == '__main__':
    unittest.main()
