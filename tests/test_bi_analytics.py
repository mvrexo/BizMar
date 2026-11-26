"""FR05/FR08 regressions with in-memory SQLite fixtures and extracted UI."""
import ast
from contextlib import closing
from datetime import date
import importlib.util
import json
from pathlib import Path
import re
import sys
import sqlite3
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('bizmar_bi_test_helpers', ROOT / 'bi_analytics.py')
BI = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BI
SPEC.loader.exec_module(BI)
START, END = date(2026, 1, 1), date(2026, 1, 4)


def fixture():
    with closing(sqlite3.connect(':memory:')) as db:
        db.executescript("""
            CREATE TABLE orders (id INTEGER PRIMARY KEY, ordered_at TEXT, status TEXT);
            CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, price REAL, unit_cost REAL);
            CREATE TABLE order_items (
                id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id),
                product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
                product_name TEXT, quantity INTEGER, unit_price REAL, unit_cost REAL);
            PRAGMA foreign_keys=ON;
        """)
        db.executemany('INSERT INTO orders VALUES (?, ?, ?)', [
            (1, '2026-01-01T00:00:00+08:00', 'Confirmed'),
            (2, '2026-01-03T10:00:00+08:00', 'Pending'),
            (3, '2026-01-03T14:00:00+08:00', 'Completed'),
            (4, '2026-01-02T10:00:00+08:00', 'Cancelled'),
            (5, '2026-01-05T00:00:00+08:00', 'Ready'),
        ])
        db.executemany('INSERT INTO products VALUES (?, ?, ?, ?)', [
            (1, 'Treat', 999., 500.), (2, 'Treat', 999., 0.), (3, 'Cancelled only', 100., 0.),
            (4, 'Retired', 888., 200.),
        ])
        db.executemany('INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?, ?)', [
            (11, 1, 1, 'Treat', 2, 10., 3.),
            (12, 2, 2, 'Treat', 3, 5., 7.),
            (13, 3, 1, 'Treat', 1, 10., 4.),
            (14, 3, 4, 'Retired', 2, 4., 4.),
            (15, 4, 3, 'Cancelled only', 100, 100., 0.),
            (16, 5, 1, 'Treat', 1, 100., 0.),
        ])
        db.execute('DELETE FROM products WHERE id=4')
        return (pd.read_sql_query('SELECT * FROM orders ORDER BY id', db),
                pd.read_sql_query('SELECT * FROM order_items ORDER BY id', db))


class BusinessIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.orders, self.items = fixture()

    def test_best_selling_product_chart_has_no_undefined_title(self):
        app = AppTest.from_file(str(ROOT / 'uat' / 'dashboard_layout_preview.py')).run(timeout=45)
        self.assertFalse(app.exception)
        self.assertTrue(any('Best Selling Product' in item.value for item in app.markdown))
        self.assertTrue(any('Revenue Over Time (Monthly)' in item.value for item in app.markdown))
        cards = [card for item in app.markdown for card in
                 re.findall(r'<div class="nour-stat nour-stat-[^"]+">.*?</div></div>', item.value, re.S)]
        self.assertEqual(len(cards), 4)
        for label in ('Total Orders', 'Total Revenue', 'Total Profits', 'Outstanding Balance'):
            self.assertTrue(any(label in card for card in cards))
        orders_card = next(card for card in cards if 'Total Orders' in card)
        self.assertIn('>1</div>', orders_card)
        insights = {metric.label: metric.value for metric in app.metric}
        self.assertEqual({key: insights[key] for key in (
            'Top-Selling Product', 'Top Sales State', 'Average Order Value',
            'Completion Rate',
        )}, {
            'Top-Selling Product': 'Demo product',
            'Top Sales State': 'Selangor',
            'Average Order Value': 'RM 12,345,678.12',
            'Completion Rate': '0%',
        })
        charts = app.get('plotly_chart')
        self.assertEqual(len(charts), 3)
        sales_chart, product_chart, location_map = (
            json.loads(chart.proto.spec) for chart in charts
        )
        self.assertEqual(sales_chart['data'][0]['type'], 'scatter')
        self.assertIn('lines', sales_chart['data'][0]['mode'])
        self.assertEqual(sales_chart['layout']['xaxis']['tickformat'], '%b %Y')
        self.assertEqual(sales_chart['layout']['yaxis']['title']['text'], 'Revenue (RM)')
        self.assertEqual(location_map['data'][0]['type'], 'choropleth')
        self.assertEqual(len(location_map['data'][0]['locations']), 16)
        sales_title = sales_chart['layout'].get('title', {}).get('text', '')
        product_title = product_chart['layout'].get('title', {}).get('text', '')
        self.assertEqual(sales_title, '')
        self.assertEqual(product_title, '')
        self.assertNotEqual(sales_title, 'undefined')
        self.assertNotEqual(product_title, 'undefined')
        app.segmented_control(key='customer_location_measure').set_value('orders').run(timeout=45)
        self.assertFalse(app.exception)
        self.assertTrue(any('Top 5 States by Orders' in item.value for item in app.markdown))
        order_map = json.loads(app.get('plotly_chart')[2].proto.spec)
        self.assertIn('Orders:', order_map['data'][0]['hovertemplate'])

    def test_daily_counts_and_zero_days(self):
        result = BI.daily_order_volume(self.orders, START, END)
        self.assertEqual(result['date'].dt.date.tolist(),
                         [date(2026, 1, day) for day in range(1, 5)])
        self.assertEqual(result['order_count'].tolist(), [1, 0, 2, 0])

    def test_cancelled_excluded_pending_completed_included(self):
        result = BI.daily_order_volume(self.orders, date(2026, 1, 2), date(2026, 1, 3))
        self.assertEqual(result['order_count'].tolist(), [0, 2])
        self.assertNotIn('id:3', BI.product_profitability(self.orders, self.items, START, END)['product_key'].tolist())

    def test_malaysia_midnight_and_inclusive_boundaries(self):
        orders = pd.DataFrame([
            dict(id=1, status='Pending', ordered_at='2026-01-01T15:59:59+00:00'),
            dict(id=2, status='Pending', ordered_at='2026-01-01T16:00:00+00:00'),
            dict(id=3, status='Completed', ordered_at='2026-01-02T15:59:59+00:00'),
            dict(id=4, status='Ready', ordered_at='2026-01-02T16:00:00+00:00'),
        ])
        result = BI.daily_order_volume(orders, date(2026, 1, 2), date(2026, 1, 2))
        self.assertEqual(result['order_count'].tolist(), [2])
        lines = pd.DataFrame([
            dict(id=i, order_id=i, product_id=1, product_name='Boundary',
                 quantity=1, unit_price=10., unit_cost=2.)
            for i in range(1, 5)
        ])
        self.assertEqual(BI.product_profitability(orders, lines, date(2026, 1, 2), date(2026, 1, 2)).iloc[0]['gross_profit'], 16.)

    def test_order_counts_are_not_item_counts_or_duplicate_counts(self):
        duplicated = pd.concat([self.orders, self.orders.iloc[:1]], ignore_index=True)
        self.assertEqual(BI.daily_order_volume(duplicated, START, END)['order_count'].sum(), 3)

    def test_saved_costs_and_prices_ignore_catalogue_values(self):
        result = BI.product_profitability(self.orders, self.items, START, END)
        row = result[result['product_key'] == 'id:1'].iloc[0]
        self.assertEqual(row['units_sold'], 3)
        self.assertEqual(row['revenue'], 30.)
        self.assertEqual(row['recorded_cost'], 10.)
        self.assertEqual(row['gross_profit'], 20.)

    def test_identical_names_with_distinct_ids_remain_separate(self):
        result = BI.product_profitability(self.orders, self.items, START, END)
        treats = result[result['product_name'] == 'Treat']
        self.assertEqual(set(treats['product_key']), {'id:1', 'id:2'})

    def test_deleted_product_keeps_saved_name_and_financials(self):
        self.assertTrue(pd.isna(self.items.loc[self.items.id == 14, 'product_id'].iloc[0]))
        row = BI.product_profitability(self.orders, self.items, START, END).query("product_key == 'historical:Retired'").iloc[0]
        self.assertEqual(row['product_name'], 'Retired')
        self.assertEqual(row['units_sold'], 2)
        self.assertEqual(row['revenue'], 8.)
        self.assertEqual(row['recorded_cost'], 8.)

    def test_negative_and_zero_profit_sort_numerically(self):
        result = BI.product_profitability(self.orders, self.items, START, END)
        self.assertEqual(result['gross_profit'].tolist(), [20., 0., -6.])
        self.assertEqual(result['product_key'].tolist(), ['id:1', 'historical:Retired', 'id:2'])

    def test_null_references_do_not_merge_with_live_same_name(self):
        lines = self.items.copy()
        lines.loc[lines.id == 14, 'product_name'] = 'Treat'
        result = BI.product_profitability(self.orders, lines, START, END)
        self.assertEqual(set(result['product_key']), {'id:1', 'id:2', 'historical:Treat'})

    def test_same_id_across_saved_name_changes_is_one_product(self):
        lines = self.items.copy()
        lines.loc[lines.id == 13, 'product_name'] = 'Updated saved name'
        row = BI.product_profitability(self.orders, lines, START, END).query("product_key == 'id:1'").iloc[0]
        self.assertEqual(row['gross_profit'], 20.)
        self.assertEqual(row['product_name'], 'Updated saved name')

    def test_empty_reversed_and_outside_ranges(self):
        self.assertEqual(BI.daily_order_volume(pd.DataFrame(), START, END)['order_count'].tolist(), [0, 0, 0, 0])
        self.assertTrue(BI.daily_order_volume(self.orders, END, START).empty)
        for orders, items, start, end in (
            (pd.DataFrame(), pd.DataFrame(), START, END),
            (self.orders, pd.DataFrame(), START, END),
            (self.orders, self.items, END, START),
            (self.orders, self.items, date(2030, 1, 1), date(2030, 1, 2)),
        ):
            self.assertTrue(BI.product_profitability(orders, items, start, end).empty)

    def test_inputs_are_unchanged(self):
        orders, items = self.orders.copy(deep=True), self.items.copy(deep=True)
        BI.daily_order_volume(self.orders, START, END)
        BI.product_profitability(self.orders, self.items, START, END)
        pd.testing.assert_frame_equal(self.orders, orders)
        pd.testing.assert_frame_equal(self.items, items)

    def test_date_filter_contract_and_returned_period(self):
        text = (ROOT / 'app.py').read_text(encoding='utf-8-sig')
        filtering = next(ast.get_source_segment(text, n) for n in ast.parse(text).body
                         if isinstance(n, ast.FunctionDef) and n.name == 'sales_date_filter'
                         and not n.decorator_list)
        prefix = """
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
orders = pd.DataFrame([dict(id=1, status='Pending', ordered_at='2026-01-02T12:00:00+08:00')])
from sales_period import new_state, STATE_KEY
st.session_state[STATE_KEY] = new_state(date(2026, 1, 1))
st.session_state[STATE_KEY]['mode'] = 'Custom'
"""
        for extended, end in ((False, 4), (True, 4), (True, 1)):
            with self.subTest(extended=extended, end=end):
                start = 1
                code = (prefix + f"\nst.session_state[STATE_KEY]['start'] = date(2026, 1, {start})"
                        + f"\nst.session_state[STATE_KEY]['end'] = date(2026, 1, {end})"
                        + '\n' + filtering
                        + "\nresult = sales_date_filter(orders, 'analytics_sales', return_period=" + repr(extended) + ')'
                        + "\nst.session_state['test_result_length'] = len(result)"
                        + "\nst.session_state['test_order_count'] = len(result[0])")
                if extended:
                    code += "\nst.session_state['test_bounds'] = result[2:]"
                app = AppTest.from_string(code).run(timeout=30)
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state['test_result_length'], 4 if extended else 2)
                self.assertEqual(app.session_state['test_order_count'], 0 if end == 1 else 1)
                if extended:
                    self.assertEqual(app.session_state['test_bounds'],
                                     (date(2026, 1, start), date(2026, 1, end)))

    def test_render_charts_and_empty_states(self):
        app_source = (ROOT / 'app.py').read_text(encoding='utf-8-sig')
        renderer = next(ast.get_source_segment(app_source, n) for n in ast.parse(app_source).body
                        if isinstance(n, ast.FunctionDef) and n.name == 'render_bi_requirements')
        theme_source = (ROOT / 'ui_theme.py').read_text(encoding='utf-8-sig')
        style = next(ast.get_source_segment(theme_source, n) for n in ast.parse(theme_source).body
                     if isinstance(n, ast.FunctionDef) and n.name == 'style_bi_chart')
        for empty in (False, True):
            with self.subTest(empty=empty):
                orders = [] if empty else self.orders.to_dict('records')
                # JSON preserves null deleted references without embedding NaN names in code.
                prefix = """
import json, sys
from datetime import date
import pandas as pd
import plotly.express as px
import streamlit as st
daily_order_volume = sys.modules['bizmar_bi_test_helpers'].daily_order_volume
product_profitability = sys.modules['bizmar_bi_test_helpers'].product_profitability
"""
                import json
                orders_json = pd.DataFrame(orders).to_json(orient='records')
                items_json = self.items.to_json(orient='records')
                fixture_code = (prefix + '\n' + style + '\n' + renderer
                                + '\norders = pd.DataFrame(json.loads(' + repr(orders_json) + '))'
                                + '\nitems = pd.DataFrame(json.loads(' + repr(items_json) + '))'
                                + '\nrender_bi_requirements(orders, items, date(2026, 1, 1), date(2026, 1, 4))')
                app = AppTest.from_string(fixture_code).run(timeout=30)
                self.assertFalse(app.exception)
                self.assertEqual(len(app.get('plotly_chart')), 1 if empty else 2)
                if empty:
                    self.assertTrue(any('zero orders' in info.value for info in app.info))
                else:
                    self.assertEqual(app.dataframe[0].value['gross_profit'].tolist(), [20., 0., -6.])


if __name__ == '__main__':
    unittest.main()
