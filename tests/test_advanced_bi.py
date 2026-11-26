"""FR10/FR11 isolated SQLite fixtures, aggregation and native UI regressions."""
import ast
import base64
from contextlib import closing
from datetime import date
import json
from pathlib import Path
import sqlite3
import sys
import unittest

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from advanced_bi import financial_orders, profitability_trend, repeat_customer_insights

START, END = date(2020, 12, 31), date(2022, 1, 1)


def fixture():
    with closing(sqlite3.connect(':memory:')) as db:
        db.executescript('''
            CREATE TABLE orders (id INTEGER, customer_id INTEGER, ordered_at TEXT, status TEXT, order_code TEXT, payment_status TEXT);
            CREATE TABLE order_items (id INTEGER, order_id INTEGER, quantity INTEGER, unit_price REAL, unit_cost REAL);
            CREATE TABLE customers (id INTEGER, customer_id TEXT, full_name TEXT, name TEXT, archived INTEGER, created_at TEXT, phone TEXT, phone_number TEXT, address TEXT, notes TEXT);
        ''')
        db.executemany('INSERT INTO orders VALUES (?,?,?,?,?,?)', [
            (1, 1, '2020-12-31T12:00:00+08:00', 'Completed', 'TEST1', 'Unpaid'),
            (2, 1, '2021-01-01T12:00:00+08:00', 'Pending', 'TEST2', 'Unpaid'),
            (3, 2, '2021-01-04T12:00:00+08:00', 'Confirmed', 'TEST3', 'Unpaid'),
            (4, 3, '2021-02-01T12:00:00+08:00', 'Completed', 'TEST4', 'Unpaid'),
            (5, 1, '2021-01-01T12:00:00+08:00', 'Cancelled', 'TEST5', 'Unpaid'),
            (6, None, '2021-01-01T12:00:00+08:00', 'Pending', 'TEST6', 'Unpaid'),
            (7, 999, '2021-01-01T12:00:00+08:00', 'Pending', 'TEST7', 'Unpaid'),
            (8, 2, '2022-01-01T12:00:00+08:00', 'Pending', 'TEST8', 'Unpaid'),
        ])
        db.executemany('INSERT INTO order_items VALUES (?,?,?,?,?)', [
            (1, 1, 2, 10, 4), (2, 2, 1, 10, 15),
            (3, 3, 1, 4, 1), (4, 3, 2, 3, 0.5),
            (5, 4, 1, 0, 5), (6, 5, 1, 1000, 0),
            (7, 6, 1, 6, 3), (8, 7, 1, 4, 1), (9, 8, 1, 10, 2),
        ])
        db.executemany('INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?,?)', [
            (1, 'C001', 'Current Name', 'Previous Name', 0, '2020-01-01', '', '', '', ''),
            (2, 'C002', 'Same Name', 'Same Name', 0, '2020-01-01', '', '', '', ''),
            (3, 'C003', 'Same Name', 'Same Name', 1, '2020-01-01', '', '', '', ''),
            (4, 'C004', 'No Orders', 'No Orders', 0, '2020-01-01', '', '', '', ''),
        ])
        return tuple(pd.read_sql_query('SELECT * FROM ' + table, db)
                     for table in ('orders', 'order_items', 'customers'))


class TrendTests(unittest.TestCase):
    def setUp(self):
        self.orders, self.items, self.customers = fixture()

    def trend(self, aggregation, start=START, end=END):
        return profitability_trend(self.orders, self.items, start, end, aggregation)

    def test_daily_aggregation(self):
        trend = self.trend('Daily', date(2021, 1, 1), date(2021, 1, 1)).iloc[0]
        self.assertEqual((trend.revenue, trend.recorded_cost, trend.gross_profit), (20, 19, 1))

    def test_weekly_aggregation(self):
        week = self.trend('Weekly').iloc[0]
        self.assertEqual((week.revenue, week.recorded_cost, week.gross_profit), (40, 27, 13))

    def test_iso_week_year_boundary(self):
        trend = self.trend('Weekly', START, date(2021, 1, 4))
        self.assertEqual(trend.period.tolist(), ['2020-W53', '2021-W01'])
        self.assertEqual(trend.period_start.tolist(), [date(2020, 12, 28), date(2021, 1, 4)])

    def test_monthly_aggregation(self):
        trend = self.trend('Monthly').set_index('period')
        self.assertEqual(trend.loc['2021-01', 'revenue'], 30)
        self.assertEqual(trend.loc['2021-01', 'recorded_cost'], 21)

    def test_yearly_aggregation(self):
        trend = self.trend('Yearly')
        self.assertEqual(trend.period.tolist(), ['2020', '2021', '2022'])
        self.assertEqual(trend.revenue.tolist(), [20, 30, 10])
        self.assertEqual(trend.recorded_cost.tolist(), [8, 26, 2])

    def test_inclusive_malaysia_boundaries(self):
        frame = self.orders.iloc[:1].copy()
        for stamp, expected in [('2020-12-31T15:59:59Z', 0), ('2020-12-31T16:00:00Z', 1),
                                ('2021-01-01T15:59:59Z', 1), ('2021-01-01T16:00:00Z', 0)]:
            frame['ordered_at'] = stamp
            result = profitability_trend(frame, self.items, date(2021, 1, 1), date(2021, 1, 1))
            self.assertEqual(result.order_count.sum(), expected)

    def test_cancelled_excluded_pending_included(self):
        saved = financial_orders(self.orders, self.items, START, END)
        self.assertNotIn(5, saved.id.tolist())
        self.assertIn(2, saved.id.tolist())
        self.assertEqual(saved.revenue.sum(), 60)

    def test_saved_snapshots_not_existing_derived_or_catalogue_values(self):
        frame = self.orders.copy()
        frame['revenue'], frame['cost'], frame['profit'] = 99999, 88888, 11111
        result = profitability_trend(frame, self.items, START, END, 'Yearly')
        self.assertEqual(result.recorded_cost.sum(), 36)
        self.assertEqual(result.gross_profit.sum(), 24)

    def test_zero_revenue_margin_undefined(self):
        result = self.trend('Monthly').set_index('period').loc['2021-02']
        self.assertTrue(pd.isna(result.gross_margin_percent))
        self.assertEqual(result.gross_profit, -5)

    def test_negative_gross_profit(self):
        selected = financial_orders(self.orders, self.items, START, END)
        self.assertEqual(selected.set_index('id').loc[2, 'gross_profit'], -5)

    def test_invalid_range(self):
        self.assertTrue(self.trend('Daily', END, START).empty)

    def test_zero_periods_and_empty_records(self):
        trend = self.trend('Monthly').set_index('period')
        self.assertEqual(trend.loc['2021-03', 'revenue'], 0)
        self.assertTrue(pd.isna(trend.loc['2021-03', 'gross_margin_percent']))
        result = profitability_trend(self.orders.iloc[:0], self.items.iloc[:0], START, date(2021, 1, 1), 'Daily')
        self.assertEqual(result.order_count.tolist(), [0, 0])

    def test_chronological_sort(self):
        for aggregation in ('Daily', 'Weekly', 'Monthly', 'Yearly'):
            self.assertTrue(self.trend(aggregation).period_start.is_monotonic_increasing)

    def test_duplicate_joins_do_not_inflate_totals(self):
        expected = self.trend('Yearly')
        actual = profitability_trend(pd.concat([self.orders] * 2), pd.concat([self.items] * 2), START, END, 'Yearly')
        pd.testing.assert_frame_equal(expected, actual)

    def test_invalid_missing_cost_not_zero_filled(self):
        lines = self.items.copy()
        lines.loc[0, 'unit_cost'] = None
        trend = profitability_trend(self.orders, lines, START, END, 'Yearly')
        self.assertTrue(pd.isna(trend.iloc[0].recorded_cost))
        self.assertTrue(pd.isna(trend.iloc[0].gross_profit))

    def test_large_range_guard(self):
        with self.assertRaisesRegex(ValueError, '5,000'):
            self.trend('Daily', date(2000, 1, 1), date(2026, 1, 1))
        self.assertEqual(len(self.trend('Yearly', date(2000, 1, 1), date(2026, 1, 1))), 27)


class RepeatTests(unittest.TestCase):
    def setUp(self):
        self.orders, self.items, self.customers = fixture()

    def insights(self, start=START, end=END):
        return repeat_customer_insights(self.orders, self.items, self.customers, start, end)

    def test_one_time_customer(self):
        result = self.insights()
        self.assertEqual(result['customers'].set_index('customer_id').loc[3, 'order_count'], 1)
        self.assertNotIn(3, result['repeats'].customer_id.tolist())

    def test_two_order_repeat(self):
        self.assertEqual(set(self.insights()['repeats'].customer_id), {1, 2})

    def test_multiple_lines_count_one_order(self):
        result = self.insights()['customers'].set_index('customer_id')
        self.assertEqual(result.loc[2, 'order_count'], 2)
        self.assertEqual(result.loc[2, 'revenue'], 20)

    def test_identical_names_stay_separate(self):
        result = self.insights()['customers']
        self.assertEqual(len(result.loc[result.customer_name.eq('Same Name')]), 2)

    def test_renamed_customer_uses_stable_id_and_current_name(self):
        frame = self.orders.copy()
        frame['customer'] = ['Old A', 'New A', 'Same', 'Same', 'A', '', '', 'Same']
        result = repeat_customer_insights(frame, self.items, self.customers, START, END)
        row = result['repeats'].set_index('customer_id').loc[1]
        self.assertEqual(row.customer_name, 'Current Name')
        self.assertEqual(row.order_count, 2)

    def test_cancelled_excluded_pending_included(self):
        result = self.insights()['identified_orders']
        self.assertNotIn(5, result.id.tolist())
        self.assertIn(2, result.id.tolist())

    def test_missing_and_deleted_references_are_unresolved(self):
        result = self.insights()
        self.assertEqual(set(result['unresolved'].id), {6, 7})
        self.assertEqual(result['identifiable_count'], 3)

    def test_no_name_fallback_for_unknown_ids(self):
        frame = self.orders.copy()
        frame['customer'] = 'Current Name'
        result = repeat_customer_insights(frame, self.items, self.customers, START, END)
        self.assertEqual(set(result['unresolved'].id), {6, 7})

    def test_duplicate_join_prevention(self):
        result = repeat_customer_insights(pd.concat([self.orders] * 2), pd.concat([self.items] * 2),
                                          pd.concat([self.customers] * 2), START, END)
        self.assertEqual(result['repeat_count'], 2)
        self.assertEqual(result['customers'].order_count.sum(), 5)

    def test_rate_and_denominator_scope(self):
        result = self.insights()
        self.assertAlmostEqual(result['repeat_rate'], 200 / 3)
        self.assertNotIn(4, result['customers'].customer_id.tolist())
        self.assertIn(3, result['customers'].customer_id.tolist())  # Archived identity retained.

    def test_date_filter_consistency(self):
        result = self.insights(date(2021, 1, 1), date(2021, 1, 31))
        self.assertEqual(result['identifiable_count'], 2)
        self.assertEqual(result['repeat_count'], 0)
        self.assertEqual(result['repeat_rate'], 0)
        self.assertEqual(result['customers'].revenue.sum(), 20)

    def test_zero_denominator_undefined(self):
        result = self.insights(date(2023, 1, 1), date(2023, 1, 1))
        self.assertIsNone(result['repeat_rate'])
        self.assertEqual(result['identifiable_count'], 0)

    def test_latest_date_and_financial_totals(self):
        row = self.insights()['customers'].set_index('customer_id').loc[1]
        self.assertEqual((row.revenue, row.recorded_cost, row.gross_profit), (30, 23, 7))
        self.assertEqual(row.latest_order_date, date(2021, 1, 1))

    def test_missing_customer_table(self):
        result = repeat_customer_insights(self.orders, self.items, pd.DataFrame(), START, END)
        self.assertEqual(result['identifiable_count'], 0)
        self.assertEqual(len(result['unresolved']), 7)


class AdvancedUIRegressionTests(unittest.TestCase):
    def prefix(self):
        return '''import sys
from datetime import date
fixture = sys.modules['test_advanced_bi'].fixture
orders, items, customers = fixture()
'''

    def test_all_aggregations_chart_table_reconcile(self):
        code = self.prefix() + '''from advanced_bi_ui import render_long_term_profitability
render_long_term_profitability(orders, items, date(2020,12,31), date(2022,1,1))
'''
        app = AppTest.from_string(code).run()
        for aggregation in ('Daily', 'Weekly', 'Monthly', 'Yearly'):
            app.selectbox(key='long_term_profitability_aggregation').set_value(aggregation).run()
            self.assertFalse(app.exception)
            shown = app.dataframe[0].value
            spec = json.loads(app.get('plotly_chart')[0].proto.spec)
            for trace in spec['data']:
                values = trace['y']
                if isinstance(values, dict):
                    values = np.frombuffer(base64.b64decode(values['bdata']), dtype=values['dtype'])
                column = trace['name'] + ' (RM)'
                np.testing.assert_allclose(values, shown[column].tolist())
            self.assertEqual(shown['Revenue (RM)'].sum(), 60)

    def test_long_term_empty_and_invalid_states(self):
        for empty, invalid in ((True, False), (False, True)):
            code = self.prefix() + 'from advanced_bi_ui import render_long_term_profitability\n'
            code += 'render_long_term_profitability(orders' + ('.iloc[:0]' if empty else '') + ', items, '
            code += 'date(2022,1,1), date(2020,12,31))' if invalid else 'date(2020,12,31), date(2022,1,1))'
            app = AppTest.from_string(code).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.get('plotly_chart')), 0)
            self.assertTrue(app.info)

    def test_repeat_ui_and_history_selection(self):
        code = self.prefix() + '''from advanced_bi_ui import render_repeat_customer_insights
render_repeat_customer_insights(orders, items, customers, 'test_repeat', date(2020,12,31), date(2022,1,1))
'''
        app = AppTest.from_string(code).run()
        self.assertFalse(app.exception)
        self.assertEqual([m.value for m in app.metric], ['3', '2', '66.7%'])
        self.assertEqual(set(app.dataframe[1].value['Order ID']), {1, 2})
        app.selectbox(key='test_repeat_history_customer').set_value(2).run()
        self.assertFalse(app.exception)
        self.assertEqual(set(app.dataframe[1].value['Order ID']), {3, 8})
        self.assertEqual(set(app.dataframe[2].value['Order ID']), {6, 7})

    def test_customer_insights_date_controls_and_empty_state(self):
        code = self.prefix() + '''from advanced_bi_ui import render_repeat_customer_insights
render_repeat_customer_insights(orders, items, customers, 'test_repeat')
'''
        app = AppTest.from_string(code).run()
        self.assertFalse(app.exception)
        app.date_input(key='test_repeat_from').set_value(date(2021, 1, 1))
        app.date_input(key='test_repeat_to').set_value(date(2021, 1, 31)).run()
        self.assertFalse(app.exception)
        self.assertEqual([m.value for m in app.metric], ['2', '0', '0.0%'])
        self.assertTrue(any('No repeat' in info.value for info in app.info))

    def test_simplified_customer_directory_preserves_analytics_helpers(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8-sig')
        names = {'normalize_customer_phone', 'validate_customer_phone', 'customer_category_for_completed',
                 'customer_summary_frame', 'render_customer_management'}
        definitions = '\n\n'.join(ast.get_source_segment(source, node) for node in ast.parse(source).body
                                   if isinstance(node, ast.FunctionDef) and node.name in names)
        code = self.prefix() + '''import streamlit as st
import pandas as pd
import plotly.express as px
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from advanced_bi import financial_orders
from advanced_bi_ui import render_repeat_customer_insights
class BlockBackend:
    def __getattr__(self,name):raise AssertionError('Database access forbidden in render regression')
sqlite_db=BlockBackend()
orders = financial_orders(orders, items, date(2020,12,31), date(2022,1,1))
orders['profit'] = orders['gross_profit']
''' + definitions + '\nrender_customer_management()'
        app = AppTest.from_string(code).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric),1)
        self.assertEqual(app.metric[0].label,'Total Customers')
        self.assertFalse(any(exp.label=='Purchase History' for exp in app.expander))
        self.assertEqual(len(app.get('plotly_chart')),0)


if __name__ == '__main__':
    unittest.main()
