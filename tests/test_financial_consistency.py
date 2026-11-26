"""Financial regressions using disposable SQLite modules, never production imports."""
import ast
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from uuid import uuid4

from streamlit.testing.v1 import AppTest

SOURCE_ROOT = Path(__file__).resolve().parents[1]


class FinancialConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='BizMar-financial-test-')
        self.root = Path(self.temp.name)
        shutil.copy2(SOURCE_ROOT / 'sqlite_db.py', self.root / 'sqlite_db.py')
        self.module_name = 'bizmar_test_db_' + uuid4().hex
        spec = importlib.util.spec_from_file_location(self.module_name, self.root / 'sqlite_db.py')
        self.db = importlib.util.module_from_spec(spec)
        sys.modules[self.module_name] = self.db
        spec.loader.exec_module(self.db)
        from uat_fixture import seed_products
        seed_products(self.db)
        self.assertEqual(self.db.DB_PATH.resolve(), self.root / 'uat' / 'synthetic.sqlite3')
        self.product = self.db.all_rows('products')[0]
        self.db.edit('products', self.product['id'], {'price': 20., 'unit_cost': 2.})
        self.customer = {'name': 'Synthetic Customer', 'phone': '0123456789', 'address': ''}
        self.values = {
            'ordered_at': '2026-01-01T12:00:00+08:00', 'due_date': '2026-01-03',
            'fulfilment_date': '2026-01-03', 'status': 'Completed',
            'payment_status': 'Unpaid', 'notes': 'Original note',
        }

    def tearDown(self):
        sys.modules.pop(self.module_name, None)
        self.temp.cleanup()

    def create_order(self, cost=2.):
        return self.db.create_order(self.customer, self.values, [{
            'product_id': self.product['id'], 'quantity': 2,
            'unit_price': 20., 'unit_cost': cost,
        }])

    def retained_line(self, order):
        saved = self.db.order_details(order['id'])['items'][0]
        return {
            'source_item_id': saved['id'], 'product_id': saved['product_id'],
            'quantity': saved['quantity'], 'unit_price': saved['unit_price'],
            'unit_cost': 99.,  # Backend must ignore repricing of a retained cost.
        }

    def ui(self, order):
        text = (SOURCE_ROOT / 'order_management.py').read_text(encoding='utf-8-sig')
        names = {'_money', '_set_line_price', '_init_order_line', '_clear_order_form', '_render_order_form', '_customer_lookup', '_remove_order_item'}
        functions = '\n\n'.join(ast.get_source_segment(text, node)
                                for node in ast.parse(text).body
                                if isinstance(node, ast.FunctionDef) and node.name in names)
        theme = (SOURCE_ROOT / 'ui_theme.py').read_text(encoding='utf-8-sig')
        headings = '\n\n'.join(ast.get_source_segment(theme, n)
                                for n in ast.parse(theme).body
                                if isinstance(n, ast.FunctionDef) and n.name == 'order_section_title')
        prefix = """
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4
import pandas as pd
import streamlit as st
from malaysian_states import CHOICES as STATE_CHOICES, display as state_label
"""
        # UI editing now requires Pending; backend snapshot tests retain legacy coverage.
        with self.db.transaction() as connection:
            connection.execute("UPDATE orders SET status='Pending' WHERE id=?", (order['id'],))
        fixture = (prefix + '\nsqlite_db = sys.modules[' + repr(self.module_name) + ']'
                   + '''
import importlib.util
from pathlib import Path
_spec = importlib.util.spec_from_file_location('orders_ui_store', Path('orders_store.py').resolve())
store = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(store)
store.sqlite_db = sqlite_db
store.current_owner = lambda: 'synthetic-owner@example.test'
'''
                   + '\nSTATUSES = list(store.STATUSES)'
                   + "\nPAYMENT_STATUSES = ['Unpaid', 'Partial', 'Paid']"
                   + "\nFULFILMENT_METHODS = ['Pickup', 'Delivery']\n"
                   + headings + '\n' + functions
                   + "\nst.session_state.setdefault('om_form_token', 'regression-token-0001')"
                   + '\n_render_order_form(' + str(order['id']) + ')')
        return AppTest.from_string(fixture).run(timeout=30)

    def test_backend_preserves_saved_cost_including_zero(self):
        for original_cost in (2., 0.):
            with self.subTest(cost=original_cost):
                order = self.create_order(original_cost)
                self.db.edit('products', self.product['id'], {'unit_cost': 8.})
                self.db.update_order(order['id'], self.customer,
                                     {**self.values, 'notes': 'Unrelated edit'},
                                     [self.retained_line(order)])
                self.assertEqual(self.db.order_details(order['id'])['items'][0]['unit_cost'], original_cost)

    def test_added_duplicate_product_uses_current_cost(self):
        order = self.create_order()
        self.db.edit('products', self.product['id'], {'unit_cost': 8.})
        new_line = {'product_id': self.product['id'], 'quantity': 1,
                    'unit_price': 20., 'unit_cost': 0.}
        self.db.update_order(order['id'], self.customer, self.values,
                             [self.retained_line(order), new_line])
        self.assertEqual([x['unit_cost'] for x in self.db.order_details(order['id'])['items']],
                         [2., 8.])

    def test_foreign_or_duplicate_line_identity_rolls_back(self):
        order = self.create_order()
        other = self.create_order()
        before = self.db.order_details(order['id'])
        for lines in ([self.retained_line(other)],
                      [self.retained_line(order), self.retained_line(order)]):
            with self.subTest(lines=len(lines)), self.assertRaises(ValueError):
                self.db.update_order(order['id'], self.customer, self.values, lines)
            self.assertEqual(self.db.order_details(order['id']), before)

    def test_replacement_product_uses_its_catalogue_cost(self):
        order = self.create_order()
        replacement = self.db.all_rows('products')[1]
        self.db.edit('products', replacement['id'], {'unit_cost': 6.})
        self.db.update_order(order['id'], self.customer, self.values, [{
            'product_id': replacement['id'], 'quantity': 1, 'unit_price': 25., 'unit_cost': 99.,
        }])
        self.assertEqual(self.db.order_details(order['id'])['items'][0]['unit_cost'], 6.)

    def test_ui_unrelated_edit_and_new_item_preserve_distinct_snapshots(self):
        order = self.create_order()
        self.db.edit('products', self.product['id'], {'unit_cost': 8.})
        app = self.ui(order)
        self.assertFalse(app.exception)
        scope = f"om_edit_{order['id']}_regression-token-0001"
        app.text_area(key=scope + '_notes').set_value('Unrelated note change')
        app.button(key=scope + '_add_line').click().run()
        self.assertFalse(app.exception)
        app.button(key=scope + '_save').click().run()
        self.assertFalse(app.exception)
        self.assertEqual([x['unit_cost'] for x in self.db.order_details(order['id'])['items']],
                         [2., 8.])

    def test_ui_remove_then_readd_uses_new_cost(self):
        order = self.db.create_order(self.customer, self.values, [
            {'product_id': self.product['id'], 'quantity': 1, 'unit_price': 20., 'unit_cost': 2.},
            {'product_id': self.product['id'], 'quantity': 1, 'unit_price': 20., 'unit_cost': 3.},
        ])
        self.db.edit('products', self.product['id'], {'unit_cost': 8.})
        app = self.ui(order)
        scope = f"om_edit_{order['id']}_regression-token-0001"
        app.button(key=scope + '_remove_line').click().run()
        # Streamlit 1.57 AppTest retains removed widgets after an immediate rerun.
        # Refresh the script without serializing those already-cleared widget keys.
        app._run()
        app.button(key=scope + '_add_line').click().run()
        app.button(key=scope + '_save').click().run()
        self.assertFalse(app.exception)
        self.assertEqual([x['unit_cost'] for x in self.db.order_details(order['id'])['items']],
                         [2., 8.])

    def test_deleted_catalogue_product_does_not_silently_replace_history(self):
        order = self.create_order()
        self.db.remove('products', self.product['id'])
        self.db.edit('orders', order['id'], {'status': 'Pending'})
        before = self.db.order_details(order['id'])
        app = self.ui(order)
        self.assertFalse(app.exception)
        self.assertTrue(any('no longer in the catalogue' in error.value for error in app.error))
        self.assertEqual(self.db.order_details(order['id']), before)
        self.assertEqual(before['items'][0]['unit_cost'], 2.)

    def test_existing_payment_operations_and_status_remain_unchanged(self):
        order = self.create_order()
        payment = self.db.add('payments', {'order_id': order['id'], 'amount': 10., 'method': 'Cash'})
        self.assertEqual(self.db.order_details(order['id'])['order']['payment_status'], 'Partial')
        self.db.edit('payments', payment['id'], {'amount': 40.})
        self.assertEqual(self.db.order_details(order['id'])['order']['payment_status'], 'Paid')
        self.db.remove('payments', payment['id'])
        self.assertEqual(self.db.order_details(order['id'])['order']['payment_status'], 'Unpaid')


    def test_ledger_status_formula_boundaries(self):
        for total, paid, expected in (
            (40., 0., 'Unpaid'), (40., 10., 'Partial'), (40., 40., 'Paid'),
            (40., 45., 'Paid'), (0., 0., 'Unpaid'),
        ):
            with self.subTest(total=total, paid=paid):
                self.assertEqual(self.db.payment_status_for_total(total, paid), expected)

    def test_new_order_cannot_declare_payment_without_ledger(self):
        order = self.db.create_order(self.customer, {**self.values, 'payment_status': 'Paid'}, [{
            'product_id': self.product['id'], 'quantity': 2, 'unit_price': 20., 'unit_cost': 2.,
        }])
        details = self.db.order_details(order['id'])
        self.assertEqual(details['order']['payment_status'], 'Unpaid')
        self.assertEqual(details['payments'], [])

    def test_legacy_mismatches_untouched_until_explicit_save(self):
        first, second = self.create_order(), self.create_order()
        with self.db.transaction() as c:
            c.execute("UPDATE orders SET payment_status='Paid' WHERE id IN (?, ?)",
                      (first['id'], second['id']))
        self.db._INITIALIZED_PATH = None
        self.db.initialize()
        self.assertEqual(self.db.order_details(first['id'])['order']['payment_status'], 'Paid')
        self.assertEqual(self.db.order_details(second['id'])['order']['payment_status'], 'Paid')
        before_timestamp = self.db.order_details(first['id'])['order']['status_updated_at']
        self.db.edit('orders', first['id'], {'notes': 'Explicit save', 'payment_status': 'Paid'})
        self.assertEqual(self.db.order_details(first['id'])['order']['payment_status'], 'Unpaid')
        self.assertEqual(self.db.order_details(first['id'])['order']['status_updated_at'], before_timestamp)
        self.assertEqual(self.db.order_details(second['id'])['order']['payment_status'], 'Paid')
        self.assertEqual(self.db.all_rows('payments'), [])

    def test_order_total_edits_rederive_status_from_unchanged_payments(self):
        order = self.create_order()
        self.db.add('payments', {'order_id': order['id'], 'amount': 30., 'method': 'Cash'})
        ledger = self.db.order_details(order['id'])['payments']
        line = self.retained_line(order)
        line['quantity'] = 1
        self.db.update_order(order['id'], self.customer,
                             {**self.values, 'payment_status': 'Unpaid'}, [line])
        self.assertEqual(self.db.order_details(order['id'])['order']['payment_status'], 'Paid')
        line = self.retained_line(order)
        line['quantity'] = 4
        self.db.update_order(order['id'], self.customer,
                             {**self.values, 'payment_status': 'Paid'}, [line])
        self.assertEqual(self.db.order_details(order['id'])['order']['payment_status'], 'Partial')
        self.assertEqual(self.db.order_details(order['id'])['payments'], ledger)

    def test_direct_line_changes_keep_status_consistent(self):
        order = self.create_order()
        original = self.db.order_details(order['id'])['items'][0]
        self.db.add('payments', {'order_id': order['id'], 'amount': 30., 'method': 'Cash'})
        extra = self.db.add('order_items', {
            'order_id': order['id'], 'product_id': self.product['id'],
            'quantity': 1, 'unit_price': 20., 'unit_cost': 2.,
        })
        self.db.remove('order_items', original['id'])
        self.assertEqual(self.db.order_details(order['id'])['order']['payment_status'], 'Paid')
        self.db.edit('order_items', extra['id'], {'quantity': 3, 'subtotal': 60.})
        self.assertEqual(self.db.order_details(order['id'])['order']['payment_status'], 'Partial')

    def test_ui_ledger_status_is_read_only_and_render_does_not_reconcile(self):
        order = self.create_order()
        with self.db.transaction() as c:
            c.execute("UPDATE orders SET payment_status='Paid' WHERE id=?", (order['id'],))
        app = self.ui(order)
        self.assertFalse(app.exception)
        self.assertFalse(any(x.label == 'Payment status' for x in app.selectbox))
        self.assertTrue(any('Payment status: Unpaid (ledger-based)' in x.value for x in app.caption))
        self.assertEqual(self.db.order_details(order['id'])['order']['payment_status'], 'Paid')
        scope = f"om_edit_{order['id']}_regression-token-0001"
        app.button(key=scope + '_save').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.db.order_details(order['id'])['order']['payment_status'], 'Unpaid')
        self.assertEqual(self.db.order_details(order['id'])['payments'], [])


class CompletedOrderAverageTests(unittest.TestCase):
    def test_completed_pending_cancelled_and_empty_populations(self):
        text = (SOURCE_ROOT / 'app.py').read_text(encoding='utf-8-sig')
        names = {'normalize_customer_phone', 'validate_customer_phone',
                 'customer_category_for_completed', 'customer_summary_frame',
                 'render_customer_management'}
        functions = '\n\n'.join(ast.get_source_segment(text, node)
                                  for node in ast.parse(text).body
                                  if isinstance(node, ast.FunctionDef) and node.name in names)
        prefix = """
import re
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.express as px
import streamlit as st
class BlockBackend:
    def __getattr__(self, name):
        raise AssertionError('Production data access forbidden')
sqlite_db = BlockBackend()
customers = pd.DataFrame([dict(id=1, customer_id='C001', full_name='Synthetic Owner',
    name='Synthetic Owner', phone_number='', phone='', archived=0,
    created_at='2026-01-01', address='')])
"""
        cases = [
            ([('Completed', 20.), ('Completed', 60.), ('Pending', 100.), ('Cancelled', 900.)], 'RM 40.00', 'RM 180.00'),
            ([('Pending', 100.), ('Cancelled', 200.)], 'RM 0.00', 'RM 100.00'),
            ([('Cancelled', 200.)], 'RM 0.00', 'RM 0.00'),
            ([], 'RM 0.00', 'RM 0.00'),
        ]
        for rows, average, spent in cases:
            with self.subTest(statuses=[status for status, _ in rows]):
                orders = [dict(id=i+1, customer_id=1, status=status, revenue=value,
                               ordered_at='2026-01-01T12:00:00+08:00',
                               order_code=f'TEST{i}', payment_status='Unpaid')
                          for i, (status, value) in enumerate(rows)]
                fixture = (prefix + '\n' + functions
                           + '\norders = pd.DataFrame(' + repr(orders)
                           + ", columns=['id','customer_id','status','revenue','ordered_at','order_code','payment_status'])"
                           + '\nrender_customer_management()\nsummary=customer_summary_frame(customers)\nst.session_state["summary_spent"]=float(summary.iloc[0].total_spent)')
                app = AppTest.from_string(fixture).run(timeout=30)
                self.assertFalse(app.exception)
                self.assertEqual(len(app.metric),1)
                self.assertEqual(app.metric[0].label,'Total Customers')
                self.assertEqual(f'RM {app.session_state["summary_spent"]:,.2f}',spent)


if __name__ == '__main__':
    unittest.main()
