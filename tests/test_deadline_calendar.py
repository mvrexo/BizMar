"""FR04 calendar regressions; synthetic in-memory and disposable SQLite only."""
import ast
from contextlib import closing
from datetime import date
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from deadline_calendar import (
    calendar_weeks, shift_calendar_month, malaysia_deadline_date,
    prepare_deadline_orders, deadline_day_orders, deadline_month_counts,
)


def fixture():
    with closing(sqlite3.connect(':memory:')) as db:
        db.execute('CREATE TABLE orders (id INTEGER PRIMARY KEY, order_code TEXT, customer TEXT, fulfilment_date TEXT, due_date TEXT, status TEXT)')
        db.executemany('INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)', [
            (1, 'TEST1', 'Synthetic A', '2026-01-02', '2026-01-02', 'Pending'),
            (2, 'TEST2', 'Synthetic B', '2026-01-03', '2026-01-03', 'Confirmed'),
            (3, 'TEST3', 'Synthetic C', '2026-01-03', '2026-01-03', 'Preparing'),
            (4, 'TEST4', 'Synthetic D', '2026-01-01', '2026-01-01', 'Completed'),
            (5, 'TEST5', 'Synthetic E', '2026-01-01', '2026-01-01', 'Cancelled'),
            (6, 'TEST6', 'Synthetic F', None, None, 'Pending'),
            (7, 'TEST7', 'Synthetic G', None, '2026-01-04', 'Ready'),
            (8, 'TEST8', 'Synthetic H', 'invalid', '2026-01-04', 'Pending'),
        ])
        return pd.read_sql_query('SELECT * FROM orders ORDER BY id', db)


class DeadlineCalendarTests(unittest.TestCase):
    def setUp(self):
        self.orders = fixture()
        self.today = date(2026, 1, 3)
        self.prepared = prepare_deadline_orders(self.orders, self.today)

    def test_single_and_multiple_orders_on_saved_dates(self):
        self.assertEqual(deadline_day_orders(self.prepared, date(2026, 1, 2))['id'].tolist(), [1])
        self.assertEqual(deadline_day_orders(self.prepared, date(2026, 1, 3))['id'].tolist(), [2, 3])
        counts = deadline_month_counts(self.prepared, date(2026, 1, 1))
        self.assertEqual(counts[date(2026, 1, 1)], 2)
        self.assertEqual(counts[date(2026, 1, 3)], 2)

    def test_month_year_and_leap_year_transitions(self):
        self.assertEqual(shift_calendar_month(date(2026, 12, 1), 1), date(2027, 1, 1))
        self.assertEqual(shift_calendar_month(date(2027, 1, 1), -1), date(2026, 12, 1))
        days = [d for week in calendar_weeks(date(2028, 2, 1)) for d in week if d.month == 2]
        self.assertEqual(len(days), 29)
        self.assertTrue(all(len(week) == 7 for week in calendar_weeks(date(2026, 8, 1))))

    def test_malaysia_midnight_boundaries_and_saved_dates(self):
        self.assertEqual(malaysia_deadline_date('2026-01-02T15:59:59+00:00'), date(2026, 1, 2))
        self.assertEqual(malaysia_deadline_date('2026-01-02T16:00:00+00:00'), date(2026, 1, 3))
        self.assertEqual(malaysia_deadline_date('2026-01-02'), date(2026, 1, 2))
        self.assertEqual(malaysia_deadline_date('2026-01-02T16:00:00'), date(2026, 1, 3))
        for value in (None, pd.NA, '', '  ', 'invalid', '2026-02-30'):
            with self.subTest(value=str(value)):
                self.assertIsNone(malaysia_deadline_date(value))

    def test_deadline_states_exclude_completed_and_cancelled_from_overdue(self):
        states = self.prepared.set_index('id')['deadline_state'].to_dict()
        self.assertEqual(states, {1: 'Overdue', 2: 'Due today', 3: 'Due today',
                                  4: 'Completed', 5: 'Cancelled', 6: 'No deadline',
                                  7: 'Upcoming', 8: 'No deadline'})

    def test_missing_invalid_and_fallback_deadlines(self):
        self.assertEqual(set(self.prepared.loc[self.prepared.calendar_date.isna(), 'id']), {6, 8})
        self.assertEqual(self.prepared.loc[self.prepared.id == 7, 'calendar_date'].iloc[0],
                         date(2026, 1, 4))
        changed = self.orders.copy()
        changed.loc[changed.id == 1, 'due_date'] = '2026-03-01'
        self.assertEqual(prepare_deadline_orders(changed, self.today).iloc[0]['calendar_date'],
                         date(2026, 1, 2))

    def test_empty_month_and_empty_dataset(self):
        self.assertTrue(all(value == 0 for value in deadline_month_counts(self.prepared, date(2030, 1, 1)).values()))
        empty = prepare_deadline_orders(pd.DataFrame(), self.today)
        self.assertTrue(empty.empty)
        self.assertTrue(deadline_day_orders(empty, self.today).empty)
        self.assertTrue(all(value == 0 for value in deadline_month_counts(empty, self.today).values()))

    def test_no_duplicate_orders_and_inputs_unchanged(self):
        original = self.orders.copy(deep=True)
        doubled = pd.concat([self.orders, self.orders], ignore_index=True)
        prepared = prepare_deadline_orders(doubled, self.today)
        self.assertEqual(len(prepared), len(self.orders))
        self.assertEqual(sum(deadline_month_counts(prepared, date(2026, 1, 1)).values()), 6)
        pd.testing.assert_frame_equal(self.orders, original)

    def test_real_order_edit_moves_calendar_without_duplicate_or_other_changes(self):
        with tempfile.TemporaryDirectory(prefix='BizMar-calendar-edit-') as temp:
            root = Path(temp)
            shutil.copy2(ROOT / 'sqlite_db.py', root / 'sqlite_db.py')
            spec = importlib.util.spec_from_file_location('calendar_disposable_db', root / 'sqlite_db.py')
            db = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(db)
            from uat_fixture import seed_products
            seed_products(db)
            self.assertEqual(db.DB_PATH.resolve(), root / 'uat' / 'synthetic.sqlite3')
            product = db.all_rows('products')[0]
            customer = dict(name='Synthetic Test', phone='0123456789', address='')
            order = db.create_order(customer, dict(
                ordered_at='2026-01-01T12:00:00+08:00', due_date='2026-01-03',
                fulfilment_date='2026-01-03', status='Pending',
            ), [dict(product_id=product['id'], quantity=1, unit_price=10., unit_cost=2.)])
            before = prepare_deadline_orders(pd.DataFrame(db.list_orders()), self.today)
            self.assertEqual(len(deadline_day_orders(before, date(2026, 1, 3))), 1)
            saved = db.order_details(order['id'])['items'][0]
            db.update_order(order['id'], customer, dict(due_date='2026-02-05', fulfilment_date='2026-02-05'), [
                dict(source_item_id=saved['id'], product_id=product['id'],
                     quantity=1, unit_price=10., unit_cost=2.),
            ])
            after = prepare_deadline_orders(pd.DataFrame(db.list_orders()), self.today)
            self.assertTrue(deadline_day_orders(after, date(2026, 1, 3)).empty)
            self.assertEqual(len(deadline_day_orders(after, date(2026, 2, 5))), 1)
            self.assertEqual(len(db.all_rows('orders')), 1)
            self.assertEqual(db.order_details(order['id'])['order']['total_amount'], 10.)
            self.assertEqual(db.order_details(order['id'])['items'][0]['unit_cost'], 2.)

    def ui(self, empty=False, board=False):
        source = (ROOT / 'app.py').read_text(encoding='utf-8-sig')
        renderer = next(ast.get_source_segment(source, node) for node in ast.parse(source).body
                        if isinstance(node, ast.FunctionDef) and node.name == 'render_deadline_calendar')
        prefix = """
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from deadline_calendar import (
    shift_calendar_month, calendar_weeks, prepare_deadline_orders,
    deadline_day_orders, deadline_month_counts,
)
from ui_theme import deadline_status_style
def money(value):
    return f'RM {value:,.2f}'
def navigate_to(target):
    st.session_state['test_navigation_target'] = target
st.session_state.setdefault('bizmar_calendar_month', date(2026, 1, 1))
st.session_state.setdefault('bizmar_calendar_date', date(2026, 1, 3))
"""
        records = '[]' if empty else self.orders.to_json(orient='records')
        tail = 'render_deadline_calendar(orders)'
        if board:
            tree = ast.parse(source)
            branch = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
                          and isinstance(n.test, ast.Compare)
                          and isinstance(n.test.left, ast.Name) and n.test.left.id == 'page'
                          and isinstance(n.test.comparators[0], ast.Constant)
                          and n.test.comparators[0].value == 'Production Board')
            tail = ast.unparse(ast.Module(body=branch.body, type_ignores=[]))
        code = (prefix + '\nfrom display_preferences import tr\n' + renderer
                + '\norders = pd.DataFrame(json.loads(' + repr(records) + '))'
                + '\norders = orders.assign(revenue=10.)'
                + '\n' + tail)
        return AppTest.from_string(code).run(timeout=30)

    def test_native_calendar_selection_month_navigation_and_workflow(self):
        app = self.ui()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value['Order reference'].tolist(), ['TEST2', 'TEST3'])
        app.button(key='bizmar_calendar_day_20260102').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value['Order reference'].tolist(), ['TEST1'])
        app.button(key='bizmar_calendar_next').click().run()
        self.assertEqual(app.session_state['bizmar_calendar_month'], date(2026, 2, 1))
        app.button(key='bizmar_calendar_previous').click().run()
        self.assertEqual(app.session_state['bizmar_calendar_month'], date(2026, 1, 1))
        app.button(key='bizmar_calendar_manage_orders').click().run()
        self.assertEqual(app.session_state['test_navigation_target'], 'Order Management')

    def test_date_input_navigates_to_selected_month(self):
        app = self.ui()
        app.date_input[0].set_value(date(2027, 1, 1)).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['bizmar_calendar_month'], date(2027, 1, 1))
        app.button(key='bizmar_calendar_previous').click().run()
        self.assertEqual(app.session_state['bizmar_calendar_month'], date(2026, 12, 1))

    def test_existing_production_stages_render_with_calendar_and_invalid_dates(self):
        app = self.ui(board=True)
        self.assertFalse(app.exception)
        headings = [heading.value for heading in app.markdown]
        for status in ('Pending', 'Confirmed', 'Preparing', 'Ready', 'Completed'):
            self.assertTrue(any(text == f'#### {status}' for text in headings))
        empty = self.ui(empty=True, board=True)
        self.assertFalse(empty.exception)

    def test_empty_calendar_renders_without_business_writes(self):
        app = self.ui(empty=True)
        self.assertFalse(app.exception)
        self.assertTrue(any('No orders yet' in info.value for info in app.info))
        self.assertFalse(app.dataframe)


if __name__ == '__main__':
    unittest.main()
