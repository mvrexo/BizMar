"""FR13 synthetic data, temporary SQLite/configuration and native UI regressions."""
from datetime import date, datetime
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from production_alerts import (DEFAULT_SETTINGS, validate_settings, load_settings,
                               save_settings, aging_alerts, demand_alerts, margin_alerts)
from production_alert_ui import deadline_notifications

NOW = datetime.fromisoformat('2026-10-20T12:00:00+08:00')
TODAY = NOW.date()


def orders():
    # SQLite synthetic fixtures only; no application database imports.
    with closing(sqlite3.connect(':memory:')) as db:
        db.execute('CREATE TABLE orders (id INTEGER, order_code TEXT, customer TEXT, status TEXT, created_at TEXT, ordered_at TEXT, due_date TEXT)')
        db.executemany('INSERT INTO orders VALUES (?,?,?,?,?,?,?)', [
            (1, 'TEST1', 'Synthetic A', 'Pending', '2026-10-18 04:00:00', '2026-10-19T12:00:00+08:00', '2026-10-19'),
            (2, 'TEST2', 'Synthetic B', 'Preparing', '2026-10-18T03:59:59Z', '2026-10-20T12:00:00+08:00', '2026-10-20'),
            (3, 'TEST3', 'Synthetic C', 'Completed', '2026-01-01T00:00:00Z', '2026-10-20T12:00:00+08:00', '2026-10-18'),
            (4, 'TEST4', 'Synthetic D', 'Cancelled', '2026-01-01T00:00:00Z', '2026-10-20T12:00:00+08:00', '2026-10-18'),
        ])
        return pd.read_sql_query('SELECT * FROM orders', db)


def items():
    return pd.DataFrame([
        [1, 1, 10, 'Cake', 30], [2, 2, 11, 'Cake', 31],
        [3, 3, None, 'Cake', 40], [4, 4, 12, 'Cancelled cake', 100],
    ], columns=['id', 'order_id', 'product_id', 'product_name', 'quantity'])


def products():
    return pd.DataFrame([
        [1, 'Low', 10, 9, 1], [2, 'Equal', 10, 8, 1],
        [3, 'Negative', 10, 12, 1], [4, 'Zero', 0, 2, 1],
        [5, 'Missing', 10, None, 1], [6, 'Inactive', 10, 12, 0],
    ], columns=['id', 'name', 'price', 'unit_cost', 'active'])


class AlertRulesTests(unittest.TestCase):
    def test_exact_48_hours_is_not_alert(self):
        aged, _ = aging_alerts(orders(), NOW)
        self.assertNotIn(1, aged.id.tolist())

    def test_more_than_48_hours_is_alert(self):
        aged, _ = aging_alerts(orders(), NOW)
        self.assertEqual(aged.id.tolist(), [2])

    def test_closed_orders_excluded(self):
        self.assertEqual(aging_alerts(orders(), NOW)[0].id.tolist(), [2])

    def test_missing_invalid_date_only_and_numeric_creation(self):
        for value in (None, '', 'bad', '2026-01-01', 'January 1 2026', 123):
            frame = orders().iloc[:1].copy()
            frame['created_at'] = value
            aged, unknown = aging_alerts(frame, NOW)
            self.assertTrue(aged.empty)
            self.assertEqual(len(unknown), 1)

    def test_missing_creation_column(self):
        aged, unknown = aging_alerts(orders().drop(columns='created_at'), NOW)
        self.assertTrue(aged.empty)
        self.assertEqual(len(unknown), 2)

    def test_malaysia_equivalent_instants(self):
        frame = orders().iloc[:1].copy()
        frame['created_at'] = '2026-10-18T12:00:00+08:00'
        self.assertTrue(aging_alerts(frame, NOW)[0].empty)
        with self.assertRaises(ValueError):
            aging_alerts(frame, NOW.replace(tzinfo=None))

    def test_demand_strict_threshold(self):
        result = demand_alerts(orders(), items(), TODAY)
        self.assertEqual(set(result.product_key), {'id:11', 'historical:Cake'})
        self.assertTrue(demand_alerts(orders(), items(), TODAY, units=100).empty)

    def test_duplicate_names_have_distinct_ids(self):
        result = demand_alerts(orders(), items(), TODAY, units=1)
        self.assertEqual(set(result.product_key), {'id:10', 'id:11', 'historical:Cake'})

    def test_deleted_references_group_only_by_saved_name(self):
        lines = items()
        extra = pd.DataFrame([[5, 1, None, 'Cake', 5]], columns=lines.columns)
        result = demand_alerts(orders(), pd.concat([lines, extra]), TODAY)
        self.assertEqual(result.set_index('product_key').loc['historical:Cake', 'ordered_units'], 45)

    def test_demand_cancelled_excluded_completed_included(self):
        result = demand_alerts(orders(), items(), TODAY, units=1)
        self.assertNotIn('id:12', result.product_key.tolist())
        self.assertIn('historical:Cake', result.product_key.tolist())

    def test_rolling_boundaries_malaysia(self):
        frame = orders().iloc[:1].copy()
        for stamp, expected in [('2026-10-13T15:59:59Z', False),
                                ('2026-10-13T16:00:00Z', True),
                                ('2026-10-20T15:59:59Z', True),
                                ('2026-10-20T16:00:00Z', False)]:
            frame['ordered_at'] = stamp
            self.assertEqual(not demand_alerts(frame, items(), TODAY, units=1).empty, expected)

    def test_deduplicates_orders_and_lines_and_reruns(self):
        result = demand_alerts(orders(), items(), TODAY)
        repeated = demand_alerts(pd.concat([orders()] * 2), pd.concat([items()] * 2), TODAY)
        pd.testing.assert_frame_equal(result, repeated)
        self.assertEqual(len(aging_alerts(pd.concat([orders()] * 2), NOW)[0]), 1)

    def test_negative_margin_and_strict_boundary(self):
        low, _ = margin_alerts(products())
        self.assertEqual(set(low.id), {1, 3})
        self.assertEqual(low.iloc[0].gross_margin_percent, -20)

    def test_zero_price_missing_cost_and_inactive(self):
        low, undefined = margin_alerts(products())
        self.assertEqual(set(undefined.id), {4, 5})
        self.assertNotIn(6, low.id.tolist())
        frame = products()
        frame.loc[0, 'price'] = None
        self.assertIn(1, margin_alerts(frame)[1].id.tolist())

    def test_empty_data(self):
        self.assertTrue(aging_alerts(orders().iloc[:0], NOW)[0].empty)
        self.assertTrue(demand_alerts(orders().iloc[:0], items(), TODAY).empty)
        self.assertTrue(margin_alerts(products().iloc[:0])[0].empty)

    def test_source_data_is_unchanged(self):
        source = products()
        original = source.copy(deep=True)
        margin_alerts(source)
        pd.testing.assert_frame_equal(source, original)

    def test_deadlines_preserved_and_no_duplicates(self):
        frame = orders()
        frame['fulfilment_date'] = '2027-01-01'
        overdue, soon = deadline_notifications(pd.concat([frame] * 2), TODAY)
        self.assertEqual(overdue.id.tolist(), [1])
        self.assertEqual(soon.id.tolist(), [2])
        self.assertTrue(deadline_notifications(frame.iloc[:0], TODAY)[0].empty)


class SettingsTests(unittest.TestCase):
    def test_absent_file_load_creates_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'missing' / 'settings.json'
            self.assertEqual(load_settings(path), (DEFAULT_SETTINGS, None))
            self.assertFalse(path.parent.exists())

    def test_invalid_file_defaults_and_warns_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'settings.json'
            for text in ('bad', '{}', '[]', '{"aging_hours": NaN}'):
                path.write_text(text)
                settings, warning = load_settings(path)
                self.assertEqual(settings, DEFAULT_SETTINGS)
                self.assertIsNotNone(warning)
                self.assertEqual(path.read_text(), text)

    def test_validation(self):
        for key, value in [('aging_hours', 0), ('aging_hours', True), ('aging_hours', float('nan')),
                           ('demand_units', -1), ('demand_units', 1.5), ('demand_days', 0),
                           ('margin_percent', 101), ('margin_percent', '20')]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_settings(dict(DEFAULT_SETTINGS, **{key: value}))
        self.assertEqual(validate_settings(DEFAULT_SETTINGS)['demand_days'], 7)

    def test_save_and_restart_persistence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'BizMar' / 'settings.json'
            expected = dict(DEFAULT_SETTINGS, aging_hours=72, demand_days=14)
            save_settings(expected, path)
            self.assertEqual(load_settings(path)[0], expected)
            code = 'import json,sys; from production_alerts import load_settings; print(json.dumps(load_settings(sys.argv[1])[0]))'
            result = subprocess.run([sys.executable, '-B', '-c', code, str(path)], cwd=ROOT,
                                    capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout), expected)
            self.assertEqual(set(json.loads(path.read_text())), set(DEFAULT_SETTINGS))

    def test_failed_replace_preserves_existing_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'settings.json'
            save_settings(DEFAULT_SETTINGS, path)
            before = path.read_bytes()
            with patch('production_alerts.os.replace', side_effect=OSError('Synthetic failure')):
                with self.assertRaises(OSError):
                    save_settings(dict(DEFAULT_SETTINGS, aging_hours=72), path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(temp).iterdir()), [path])

    def test_invalid_save_creates_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'missing' / 'settings.json'
            with self.assertRaises(ValueError):
                save_settings(dict(DEFAULT_SETTINGS, margin_percent=-1), path)
            self.assertFalse(path.parent.exists())

    def test_settings_ui_only_explicit_save_writes(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'LOCALAPPDATA': temp}):
            app = AppTest.from_string('from production_alert_ui import render_alert_settings\nrender_alert_settings()').run()
            self.assertFalse(app.exception)
            path = Path(temp) / 'BizMar' / 'production_alert_settings.json'
            self.assertFalse(path.exists())
            app.number_input(key='production_alert_aging_hours').set_value(72.0)
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(load_settings(path)[0]['aging_hours'], 72)

    def test_notifications_render_with_synthetic_data_no_writes(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'LOCALAPPDATA': temp}):
            code = '''from test_production_alerts import orders, items, products, NOW
from production_alert_ui import render_production_alerts
render_production_alerts(orders(), items(), products(), lambda target: None, now=NOW)
'''
            with patch.dict(os.environ, {'PYTHONPATH': str(ROOT / 'tests')}):
                sys.path.insert(0, str(ROOT / 'tests'))
                try:
                    app = AppTest.from_string(code).run()
                finally:
                    sys.path.remove(str(ROOT / 'tests'))
            self.assertFalse(app.exception)
            self.assertEqual([s.value for s in app.subheader],
                             ['Order Aging (1)', 'High Demand (2)', 'Low Profit Margin (2)', 'Deadline Alerts (2)', 'Pending Orders (1)', 'Overdue Payments (0)'])
            self.assertFalse((Path(temp) / 'BizMar').exists())

    def test_empty_notifications_and_functional_navigation(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'LOCALAPPDATA': temp}):
            code = '''import streamlit as st
import pandas as pd
from datetime import datetime
from production_alert_ui import render_production_alerts
def navigate(target):
    st.session_state['test_target'] = target
render_production_alerts(pd.DataFrame(columns=['id','status','due_date']), pd.DataFrame(), pd.DataFrame(), navigate, now=datetime.fromisoformat('2026-10-20T12:00:00+08:00'))
'''
            app = AppTest.from_string(code).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.success), 6)
            for key, target in [('alerts_open_orders', 'Order Management'),
                                ('alerts_open_products', 'Products'), ('alerts_open_settings', 'Settings')]:
                app.button(key=key).click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state['test_target'], target)
            self.assertFalse((Path(temp) / 'BizMar').exists())


if __name__ == '__main__':
    unittest.main()
