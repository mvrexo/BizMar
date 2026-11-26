"""Customer fallback regressions: AST-extracted functions, synthetic data only."""
import ast
from contextlib import closing
from datetime import datetime
from pathlib import Path
import re
import sqlite3
import unittest
from zoneinfo import ZoneInfo

import pandas as pd
from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / 'app.py'
SOURCE = APP_PATH.read_text(encoding='utf-8-sig')
FUNCTION_NAMES = {
    'normalize_customer_phone', 'validate_customer_phone',
    'customer_category_for_completed', 'customer_summary_frame',
    'render_customer_management',
}
TREE = ast.parse(SOURCE)
FUNCTIONS = [node for node in TREE.body
             if isinstance(node, ast.FunctionDef) and node.name in FUNCTION_NAMES]


def empty_orders():
    return pd.DataFrame(columns=[
        'id', 'customer_id', 'status', 'revenue', 'ordered_at',
        'order_code', 'payment_status',
    ])


def customer_fixture():
    # No connection is ever opened to a filesystem database.
    with closing(sqlite3.connect(':memory:')) as connection:
        connection.execute(
            'CREATE TABLE customers (id INTEGER, customer_id TEXT, full_name TEXT, '
            'name TEXT, phone_number TEXT, phone TEXT, archived INTEGER, '
            'created_at TEXT, address TEXT)'
        )
        connection.executemany(
            'INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            [
                (1, 'C001', 'Preferred Name', 'Legacy Name', '', '0123456789', 0, '2026-01-01', ''),
                (2, 'C002', '', 'Fallback Name', None, '0133456789', 0, '2026-01-01', ''),
                (3, 'C003', '   ', 'Blank Fallback', '', '0143456789', 0, '2026-01-01', ''),
                (4, 'C004', None, None, None, None, 0, '2026-01-01', ''),
            ],
        )
        return pd.read_sql_query('SELECT * FROM customers', connection)


class CustomerSummaryTests(unittest.TestCase):
    def setUp(self):
        self.namespace = {'pd': pd, 'orders': empty_orders()}
        exec(compile(ast.Module(body=FUNCTIONS[:], type_ignores=[]),
                     str(APP_PATH), 'exec'), self.namespace)
        self.summarize = self.namespace['customer_summary_frame']

    def test_names_and_phone_fallbacks_without_mutating_input(self):
        frame = customer_fixture()
        original = frame.copy(deep=True)
        result = self.summarize(frame)
        self.assertEqual(result['customer_name'].tolist(),
                         ['Preferred Name', 'Fallback Name', 'Blank Fallback', ''])
        self.assertEqual(result['phone_number'].tolist(),
                         ['0123456789', '0133456789', '0143456789', ''])
        pd.testing.assert_frame_equal(frame, original)

    def test_missing_name_columns(self):
        frame = customer_fixture()
        for dropped, expected in (
            (['full_name'], ['Legacy Name', 'Fallback Name', 'Blank Fallback', '']),
            (['name'], ['Preferred Name', '', '', '']),
            (['full_name', 'name'], ['', '', '', '']),
        ):
            with self.subTest(dropped=dropped):
                self.assertEqual(
                    self.summarize(frame.drop(columns=dropped))['customer_name'].tolist(),
                    expected,
                )

    def test_nulls_whitespace_and_precedence(self):
        frame = pd.concat([customer_fixture().iloc[:1]] * 8, ignore_index=True)
        frame['id'] = range(1, 9)
        frame['full_name'] = [None, pd.NA, float('nan'), '', ' \t\n ', '  Preferred  ', 'Valid', '']
        frame['name'] = ['A', 'B', 'C', 'D', 'E', 'Legacy', None, ' \t ']
        self.assertEqual(self.summarize(frame)['customer_name'].tolist(),
                         ['A', 'B', 'C', 'D', 'E', '  Preferred  ', 'Valid', ''])

    def test_non_default_index_alignment(self):
        frame = customer_fixture()
        frame.index = [40, 10, 90, 20]
        self.assertEqual(self.summarize(frame)['customer_name'].tolist(),
                         ['Preferred Name', 'Fallback Name', 'Blank Fallback', ''])

    def test_empty_frames(self):
        for frame in (pd.DataFrame(), customer_fixture().iloc[:0]):
            with self.subTest(columns=list(frame.columns)):
                result = self.summarize(frame)
                self.assertTrue(result.empty)
                self.assertIn('archived', result)

    def test_order_aggregates_unchanged(self):
        self.namespace['orders'] = pd.DataFrame([
            {'id': 1, 'customer_id': 1, 'status': 'Completed', 'revenue': 25, 'ordered_at': '2026-01-01'},
            {'id': 2, 'customer_id': 1, 'status': 'Pending', 'revenue': 15, 'ordered_at': '2026-01-02'},
            {'id': 3, 'customer_id': 1, 'status': 'Cancelled', 'revenue': 100, 'ordered_at': '2026-01-03'},
        ])
        row = self.summarize(customer_fixture()).iloc[0]
        self.assertEqual(row['total_orders'], 2)
        self.assertEqual(row['completed_orders'], 1)
        self.assertEqual(row['total_spent'], 40)
        self.assertEqual(row['last_purchase'], '2026-01-02')
        self.assertEqual(row['category'], 'New Customer')

    def test_customer_page_renders_with_synthetic_data(self):
        function_source = '\n\n'.join(ast.get_source_segment(SOURCE, node) for node in FUNCTIONS)
        # All backend calls are blocked. No clicks or submissions are performed.
        prefix = """
import pandas as pd
nan = float('nan')
import streamlit as st
import plotly.express as px
from datetime import datetime
from zoneinfo import ZoneInfo
import re
class BlockBackend:
    def __getattr__(self, name):
        raise AssertionError('Database access forbidden in render regression')
sqlite_db = BlockBackend()
orders = pd.DataFrame(columns=['id', 'customer_id', 'status', 'revenue', 'ordered_at', 'order_code', 'payment_status'])
"""
        for empty in (False, True):
            with self.subTest(empty=empty):
                records = [] if empty else customer_fixture().to_dict('records')
                fixture = (prefix + '\n' + function_source
                           + '\ncustomers = pd.DataFrame(' + repr(records) + ')'
                           + '\nrender_customer_management()\n')
                app = AppTest.from_string(fixture).run(timeout=30)
                self.assertFalse(app.exception, str(app.exception))
                self.assertEqual(len(app.metric),1)
                self.assertEqual(app.metric[0].label,'Total Customers')
                self.assertEqual(len(app.get('plotly_chart')),0)


if __name__ == '__main__':
    unittest.main()
