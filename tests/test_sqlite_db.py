import tempfile
import unittest
from pathlib import Path

import sqlite_db


class SQLiteOrderTests(unittest.TestCase):
    def test_new_database_does_not_generate_business_records(self):
        sqlite_db.DB_PATH = Path(self.temp_dir.name) / 'empty.sqlite3'
        sqlite_db.initialize()
        for table in sqlite_db.TABLES:
            self.assertEqual(sqlite_db.all_rows(table),[])
        sqlite_db._INITIALIZED_PATH = None
        sqlite_db.initialize()
        self.assertEqual(sqlite_db.all_rows('products'),[])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_path = sqlite_db.DB_PATH
        sqlite_db.DB_PATH = Path(self.temp_dir.name) / 'test.sqlite3'
        sqlite_db.initialize()
        from uat_fixture import seed_products
        seed_products(sqlite_db)

    def tearDown(self):
        sqlite_db.DB_PATH = self.original_path
        self.temp_dir.cleanup()

    def _create_order(self):
        products = sqlite_db.all_rows('products')
        return sqlite_db.create_order(
            {'name': 'Test Customer', 'phone': '0123456789', 'address': ''},
            {
                'ordered_at': '2026-10-20T09:00:00+08:00',
                'due_date': '2026-10-23',
                'fulfilment_date': '2026-10-23',
                'fulfilment_method': 'Pickup',
                'status': 'Pending',
                'payment_status': 'Unpaid',
                'notes': 'Test order',
            },
            [
                {
                    'product_id': products[0]['id'],
                    'quantity': 2,
                    'unit_price': 12.5,
                    'unit_cost': 5,
                },
                {
                    'product_id': products[1]['id'],
                    'quantity': 1,
                    'unit_price': 8,
                    'unit_cost': 3,
                },
            ],
        )

    def test_order_and_items_commit_and_persist(self):
        created = self._create_order()
        self.assertEqual(created['order_code'], 'ORD001')
        self.assertEqual(created['total_amount'], 33)
        detail = sqlite_db.order_details(created['id'])
        self.assertEqual(len(detail['items']), 2)
        self.assertEqual(sqlite_db.list_orders()[0]['total_amount'], 33)

    def test_failed_item_rolls_back_customer_and_order(self):
        product = sqlite_db.all_rows('products')[0]
        with self.assertRaises(Exception):
            sqlite_db.create_order(
                {'name': 'Rollback Customer', 'phone': '0123'},
                {
                    'ordered_at': '2026-10-20T09:00:00+08:00',
                    'due_date': '2026-10-23',
                    'fulfilment_date': '2026-10-23',
                    'fulfilment_method': 'Pickup',
                    'status': 'Pending',
                    'payment_status': 'Unpaid',
                    'notes': '',
                },
                [
                    {'product_id': product['id'], 'quantity': 1, 'unit_price': 5, 'unit_cost': 2},
                    {'product_id': 999999, 'quantity': 1, 'unit_price': 5, 'unit_cost': 2},
                ],
            )
        self.assertEqual(sqlite_db.all_rows('customers'), [])
        self.assertEqual(sqlite_db.all_rows('orders'), [])

    def test_payment_updates_status_and_delete_cascades(self):
        created = self._create_order()
        sqlite_db.add('payments', {
            'order_id': created['id'],
            'amount': 10,
            'method': 'Cash',
            'reference': 'deposit',
        })
        self.assertEqual(sqlite_db.order_details(created['id'])['order']['payment_status'], 'Partial')
        sqlite_db.delete_order(created['id'])
        self.assertEqual(sqlite_db.all_rows('orders'), [])
        self.assertEqual(sqlite_db.all_rows('order_items'), [])
        self.assertEqual(sqlite_db.all_rows('payments'), [])

    def test_status_change_updates_timestamp(self):
        created = self._create_order()
        sqlite_db.edit('orders', created['id'], {'status': 'Preparing'})
        updated = sqlite_db.order_details(created['id'])['order']
        self.assertEqual(updated['status'], 'Preparing')
        self.assertTrue(updated['status_updated_at'])

    def test_edit_replaces_items_and_recalculates_total(self):
        created = self._create_order()
        product = sqlite_db.all_rows('products')[2]
        sqlite_db.update_order(
            created['id'],
            {'name': 'Updated Customer', 'phone': '0199999999', 'address': 'Kedah'},
            {
                'ordered_at': '2026-10-20T09:00:00+08:00',
                'due_date': '2026-10-25',
                'fulfilment_date': '2026-10-25',
                'fulfilment_method': 'Delivery',
                'status': 'Confirmed',
                'payment_status': 'Unpaid',
                'notes': 'Updated',
            },
            [{
                'product_id': product['id'],
                'product_name': product['name'],
                'quantity': 3,
                'unit_price': 9,
                'unit_cost': 4,
                'subtotal': 27,
            }],
        )
        details = sqlite_db.order_details(created['id'])
        self.assertEqual(details['order']['total_amount'], 27)
        self.assertEqual(details['order']['customer_name'], 'Updated Customer')
        self.assertEqual(len(details['items']), 1)


if __name__ == '__main__':
    unittest.main()
