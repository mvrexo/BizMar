"""Payment layout regressions using AST extraction and in-memory fixtures."""
import ast
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

SOURCE = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8-sig')
TREE = ast.parse(SOURCE)
FUNCTIONS = [
    ast.get_source_segment(SOURCE, n) for n in TREE.body
    if isinstance(n, ast.FunctionDef) and n.name in {'money', 'render_payment_tracking'}
]
PREFIX = """
import pandas as pd
import streamlit as st
import html
orders = pd.DataFrame([
    dict(id=7, customer='Synthetic Customer', status='Confirmed', revenue=100., paid=25., balance=75.),
    dict(id=8, customer='Cancelled Fixture', status='Cancelled', revenue=50., paid=10., balance=40.),
])
payments = pd.DataFrame([
    dict(id=3, order_id=7, paid_at='2026-01-02T03:04:00+00:00', amount=25., method='Transfer', reference='Synthetic only'),
    dict(id=1, order_id=7, paid_at='not-a-date', amount=5., method='Cash', reference='Historical fixture'),
])
def add(table, payload):
    # A spy only: no database, network, or storage is imported.
    st.session_state['test_recorded_call'] = (table, payload)
def refresh():
    st.session_state['test_refresh_called'] = True
"""


def make_app(extra=''):
    return AppTest.from_string(
        PREFIX + '\n' + '\n\n'.join(FUNCTIONS) + '\n' + extra
        + '\nrender_payment_tracking()'
    ).run(timeout=30)


class PaymentLayoutTests(unittest.TestCase):
    def test_render_summary_history_and_original_data(self):
        app = make_app()
        self.assertFalse(app.exception)
        self.assertEqual([x.value for x in app.metric[:3]],
                         ['RM 100.00', 'RM 25.00', 'RM 75.00'])
        self.assertEqual(len(app.selectbox[0].options), 1)
        history = app.dataframe[0].value
        self.assertEqual(history['Payment reference'].tolist(), [3, 1])
        self.assertEqual(history['Order ID'].tolist(), [7, 7])
        self.assertEqual(history['Amount (RM)'].tolist(), ['RM 25.00', 'RM 5.00'])
        self.assertEqual(history['Payment date (MYT)'].tolist(),
                         ['02/01/2026 11:04', 'Date unavailable'])
        self.assertEqual(sum(b.label == 'Record payment' for b in app.button), 1)

    def test_existing_overpayment_validation_blocks_submission(self):
        app = make_app()
        app.number_input[0].set_value(76.)
        next(b for b in app.button if b.label == 'Record payment').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('exceeds outstanding balance' in e.value for e in app.error))
        self.assertNotIn('test_recorded_call', app.session_state)

    def test_original_submit_handler_connected_to_spy(self):
        app = make_app()
        app.number_input[0].set_value(12.)
        app.text_input[0].set_value('Synthetic reference')
        next(b for b in app.button if b.label == 'Record payment').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['test_recorded_call'],
                         ('payments', {'order_id': 7, 'amount': 12.,
                                       'method': 'Transfer', 'reference': 'Synthetic reference'}))
        self.assertTrue(app.session_state['test_refresh_called'])

    def test_empty_and_cancelled_only_orders(self):
        for extra in ("orders = orders.iloc[:0]", "orders = orders[orders.status == 'Cancelled']"):
            with self.subTest(extra=extra):
                app = make_app(extra)
                self.assertFalse(app.exception)
                self.assertFalse(any(b.label == 'Record payment' for b in app.button))


if __name__ == '__main__':
    unittest.main()
