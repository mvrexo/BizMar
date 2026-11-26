from datetime import date
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import orders_store as store
import sqlite_db


class OrdersStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bizmar-orders-')
        self.path = sqlite_db.DB_PATH
        sqlite_db.DB_PATH = Path(self.temp.name) / 'orders.sqlite3'
        self.auth = patch.object(store, 'current_owner', return_value='synthetic-owner@example.test')
        self.auth.start()
        sqlite_db.initialize()
        from uat_fixture import seed_products
        seed_products(sqlite_db)
        self.product = sqlite_db.all_rows('products')[0]
        sqlite_db.edit('products', self.product['id'], {'price': 10., 'unit_cost': 3.})
        self.customer = dict(name='Synthetic Customer', phone='0123456789', address='Synthetic address')
        self.order = dict(ordered_at='2026-10-26', fulfilment_date='2026-10-28', source='WhatsApp', fulfilment_method='Pickup')
        self.lines = [dict(product_id=self.product['id'], quantity=2, unit_price=10)]

    def tearDown(self):
        self.auth.stop()
        sqlite_db.DB_PATH = self.path
        self.temp.cleanup()

    def create(self, **kwargs):
        return store.save_order(self.customer, self.order, self.lines, token='create-synthetic-0001', **kwargs)

    def test_multi_item_and_atomic_initial_payment(self):
        self.lines.append(dict(product_id=self.product['id'], quantity=1, unit_price=5))
        self.order.update(discount=3, delivery_fee=4)
        created = self.create(payment=dict(amount=10, method='Cash'))
        self.assertEqual(created['total_amount'], 26)
        self.assertEqual(created['status'], 'Pending')
        detail = store.details(created['id'])
        self.assertEqual(detail['order']['balance'], 16)
        self.assertEqual(detail['order']['payment_status'], 'Partial')
        self.assertEqual(len(detail['items']), 2)
        self.assertEqual(len(detail['payments']), 1)
        self.assertEqual(len(detail['activity']), 2)
        self.assertEqual(self.create(payment=dict(amount=10, method='Cash'))['id'], created['id'])
        self.assertEqual(len(store.list_orders()), 1)

    def test_failed_payment_rolls_back_entire_order(self):
        with self.assertRaises(ValueError): self.create(payment=dict(amount=21, method='Cash'))
        self.assertEqual(sqlite_db.all_rows('orders'), [])
        self.assertEqual(sqlite_db.all_rows('customers'), [])
        self.assertEqual(sqlite_db.all_rows('order_items'), [])

    def test_completion_is_independent_and_repeat_protected(self):
        created = self.create()
        store.transition(created['id'], 'Completed')
        detail = store.details(created['id'])
        self.assertTrue(detail['order']['completed_at'])
        self.assertEqual(detail['order']['payment_status'], 'Unpaid')
        with self.assertRaises(ValueError): store.transition(created['id'], 'Completed')
        with self.assertRaises(ValueError): store.save_order(self.customer, self.order, self.lines, token='edit-synthetic-0001', order_id=created['id'], version=0)

    def test_cancel_preserves_items_and_payments(self):
        created = self.create(payment=dict(amount=5, method='Cash'))
        store.transition(created['id'], 'Cancelled', 'Customer request')
        detail = store.details(created['id'])
        self.assertEqual(detail['order']['status'], 'Cancelled')
        self.assertEqual(detail['order']['cancellation_reason'], 'Customer request')
        self.assertTrue(detail['order']['cancelled_at'])
        self.assertEqual(len(detail['items']), 1)
        self.assertEqual(len(detail['payments']), 1)
        with self.assertRaises(ValueError): store.record_payment(created['id'], dict(amount=1, method='Cash'), token='payment-synthetic-001')

    def test_payment_ledger_idempotency_decimal_rounding(self):
        self.lines[0].update(quantity=1, unit_price='.90')
        created = self.create()
        first = store.record_payment(created['id'], dict(amount='.30', method='Transfer'), token='payment-synthetic-001')
        self.assertEqual(store.record_payment(created['id'], dict(amount='.30', method='Transfer'), token='payment-synthetic-001'), first)
        store.record_payment(created['id'], dict(amount='.60', method='Cash'), token='payment-synthetic-002')
        self.assertEqual(store.details(created['id'])['order']['payment_status'], 'Paid')
        self.assertEqual(store.details(created['id'])['order']['balance'], 0)
        self.assertEqual(sqlite_db.all_rows('orders')[0]['payment_status'], 'Paid')
        with self.assertRaises(ValueError): store.record_payment(created['id'], dict(amount='.40', method='Cash'), token='payment-synthetic-001')

    def test_edit_preserves_cost_payments_and_version(self):
        sqlite_db.edit('products', self.product['id'], {'unit_cost': 3.125})
        created = self.create(payment=dict(amount=15, method='Cash'))
        detail = store.details(created['id'])
        lines = [dict(self.lines[0], unit_price=5, source_item_id=detail['items'][0]['id'])]
        sqlite_db.edit('products', self.product['id'], {'unit_cost': 99.})
        with self.assertRaises(ValueError):
            store.save_order(self.customer,self.order,lines,token='edit-synthetic-0001',order_id=created['id'],version=0)
        saved = store.save_order(self.customer,self.order,lines,token='edit-synthetic-0001',order_id=created['id'],version=0,acknowledge_overpayment=True)
        detail = store.details(saved['id'])
        self.assertEqual(detail['items'][0]['unit_cost'], 3.125)
        self.assertEqual(detail['order']['balance'], -5.)
        self.assertEqual(len(detail['payments']), 1)
        with self.assertRaises(ValueError):
            store.save_order(self.customer,self.order,lines,token='edit-synthetic-0002',order_id=created['id'],version=0,acknowledge_overpayment=True)

    def test_validation_and_unauthorized_access(self):
        for change in (dict(discount=-1),dict(discount=100),dict(source='Invalid'),dict(fulfilment_method='Delivery'),dict(fulfilment_date='2026-10-01')):
            with self.subTest(change=change), self.assertRaises(ValueError):
                store.save_order(self.customer,dict(self.order,**change),self.lines,token='create-invalid-0001')
        with patch.object(store,'current_owner',side_effect=PermissionError('Unauthorized')):
            for operation in (store.list_orders,lambda:self.create(),lambda:store.details(1),lambda:store.transition(1,'Completed'),lambda:store.record_payment(1,{},token='unauthorized-0001')):
                with self.assertRaises(PermissionError): operation()
        self.assertEqual(store.list_orders(), [])

    def test_legacy_mapping_and_repeatable_migration(self):
        legacy = sqlite_db.create_order(self.customer, dict(ordered_at='2026-10-26',fulfilment_date='2026-10-28',due_date='2026-10-28',status='Preparing'),self.lines)
        self.assertEqual(store.details(legacy['id'])['order']['status'], 'Pending')
        self.assertEqual(sqlite_db.all_rows('orders')[0]['status'], 'Preparing')
        from orders_schema import migrate
        with sqlite_db.transaction() as connection:
            migrate(connection);migrate(connection)
        self.assertEqual(len(sqlite_db.all_rows('orders')), 1)
        store.transition(legacy['id'],'Completed')
        self.assertEqual(store.details(legacy['id'])['order']['status'], 'Completed')

    def test_concurrent_submission_and_payment_limits(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            created = list(pool.map(lambda _: self.create(), range(2)))
        self.assertEqual(created[0]['id'], created[1]['id'])
        self.assertEqual(len(store.list_orders()), 1)
        def pay(index):
            try:
                store.record_payment(created[0]['id'], dict(amount=15, method='Cash'), token=f'race-payment-000{index}')
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(pay,range(2)))
        self.assertEqual(sum(results),1)
        self.assertEqual(store.details(created[0]['id'])['order']['balance'],5.)

    def test_database_error_rolls_back_customer_order_and_request(self):
        with sqlite_db.transaction() as connection:
            connection.execute("CREATE TRIGGER fail_order_item BEFORE INSERT ON order_items BEGIN SELECT RAISE(ABORT,'Synthetic database error'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.create()
        for table in ('orders','order_items','payments','customers'):
            self.assertEqual(sqlite_db.all_rows(table),[])
        with sqlite_db.transaction() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM order_requests').fetchone()[0],0)

    def test_additive_migration_preserves_legacy_records(self):
        from orders_schema import migrate
        with closing(sqlite3.connect(Path(self.temp.name)/'legacy.sqlite3')) as connection:
            connection.row_factory = sqlite3.Row
            connection.executescript("""CREATE TABLE orders(id INTEGER PRIMARY KEY,status TEXT,total_amount REAL);
                CREATE TABLE payments(id INTEGER PRIMARY KEY,order_id INTEGER,amount REAL);
                CREATE TABLE app_metadata(key TEXT PRIMARY KEY,value TEXT);
                INSERT INTO orders VALUES (1,'Ready',25.5);
                INSERT INTO payments VALUES (1,1,10.5);""")
            migrate(connection)
            migrate(connection)
            order = connection.execute('SELECT * FROM orders').fetchone()
            self.assertEqual((order['status'],order['total_amount'],order['discount'],order['delivery_fee']),('Ready',25.5,0,0))
            self.assertEqual(connection.execute('SELECT amount FROM payments').fetchone()[0],10.5)

    def test_legacy_local_phone_reuses_customer_for_international_format(self):
        customer = sqlite_db.add('customers',dict(name='Legacy customer',phone='0123456789',normalized_phone='0123456789'))
        self.customer['phone'] = '+60123456789'
        saved = self.create()
        self.assertEqual(saved['customer_id'],customer['id'])
        self.assertEqual(len(sqlite_db.all_rows('customers')),1)


if __name__ == '__main__': unittest.main()
