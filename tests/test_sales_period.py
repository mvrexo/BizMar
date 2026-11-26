"""Period boundaries, transactional selection and native calendar regressions."""
from datetime import date
import unittest
import pandas as pd
from streamlit.testing.v1 import AppTest
from sales_period import (new_state, switch_mode, choose_date, shift_view, apply_custom,
                          cancel_custom, period_bounds, utc_bounds, filter_period)

UI = '''
import streamlit as st
from datetime import date
import pandas as pd
from sales_period import sales_date_filter, new_state, STATE_KEY
if STATE_KEY not in st.session_state:
    st.session_state[STATE_KEY] = new_state(date(2024, 2, 28))
orders = pd.DataFrame([{'id': 1, 'ordered_at': '2024-02-29T10:00:00+08:00'},
                       {'id': 2, 'ordered_at': '2024-03-03T10:00:00+08:00'}])
result = sales_date_filter(orders, 'test', return_period=True)
st.session_state['result'] = (result[0]['id'].tolist(), *result[1:])
'''


class PeriodTests(unittest.TestCase):
    def test_calendar_boundaries(self):
        self.assertEqual(period_bounds('Day', date(2024, 2, 29)), (date(2024, 2, 29),)*2)
        self.assertEqual(period_bounds('Month', date(2024, 2, 12)), (date(2024, 2, 1), date(2024, 2, 29)))
        self.assertEqual(period_bounds('Month', date(2025, 2, 12))[1], date(2025, 2, 28))
        self.assertEqual(period_bounds('Month', date(2026, 12, 1))[1], date(2026, 12, 31))
        for day in (date(2024, 12, 30), date(2025, 1, 1), date(2025, 1, 5)):
            self.assertEqual(period_bounds('Week', day), (date(2024, 12, 30), date(2025, 1, 5)))

    def test_malaysia_half_open_boundaries(self):
        frame = pd.DataFrame({'ordered_at': ['2024-02-28T15:59:59Z', '2024-02-28T16:00:00Z',
             '2024-02-29T23:59:59.999999+08:00', '2024-02-29T16:00:00Z', 'invalid', None]})
        self.assertEqual(filter_period(frame, date(2024, 2, 29), date(2024, 2, 29)).index.tolist(), [1, 2])
        self.assertEqual(str(utc_bounds(date(2024, 2, 29), date(2024, 2, 29))[1]), '2024-02-29 16:00:00+00:00')
        with self.assertRaises(ValueError): utc_bounds(date(2026, 2, 2), date(2026, 2, 1))
        self.assertTrue(filter_period(pd.DataFrame(), date(2024, 1, 1), date(2024, 1, 1)).empty)
        original = frame.copy(deep=True)
        self.assertTrue(filter_period(frame, date(2000, 1, 1), date(2000, 1, 2)).empty)
        pd.testing.assert_frame_equal(frame, original)

    def test_custom_apply_cancel_and_reverse_selection(self):
        state = new_state(date(2024, 2, 28))
        switch_mode(state, 'Custom')
        choose_date(state, date(2024, 12, 31))
        self.assertFalse(apply_custom(state))
        choose_date(state, date(2025, 1, 3))
        self.assertEqual(state['end'], date(2024, 2, 28))
        self.assertTrue(apply_custom(state))
        self.assertEqual((state['start'], state['end']), (date(2024, 12, 31), date(2025, 1, 3)))
        choose_date(state, date(2025, 3, 1))
        choose_date(state, date(2025, 2, 1))
        self.assertEqual(state['draft'], (date(2025, 2, 1), None))
        cancel_custom(state)
        self.assertEqual(state['draft'], state['custom'])

    def test_modes_remember_independent_selections(self):
        state = new_state(date(2024, 2, 28))
        switch_mode(state, 'Week')
        choose_date(state, date(2025, 1, 1))
        switch_mode(state, 'Month')
        choose_date(state, date(2024, 2, 1))
        switch_mode(state, 'Week')
        self.assertEqual((state['start'], state['end']), (date(2024, 12, 30), date(2025, 1, 5)))
        switch_mode(state, 'Month')
        self.assertEqual(state['end'], date(2024, 2, 29))
        shift_view(state, -1)
        self.assertEqual(state['view'], date(2024, 1, 1))
        shift_view(state, -1)
        self.assertEqual(state['view'], date(2023, 12, 1))
        shift_view(state, 1, years=True)
        self.assertEqual(state['view'], date(2024, 12, 1))

    def test_native_modes_and_live_data(self):
        app = AppTest.from_string(UI).run()
        self.assertFalse(app.exception)
        app.date_input[0].set_value(date(2024, 2, 29)).run()
        self.assertEqual(app.session_state['result'][0], [1])
        app.button(key='test_mode_week').click().run()
        app.button(key='test_date_2024-03-03').click().run()
        self.assertEqual(app.session_state['result'], ([1, 2], 'Week', date(2024, 2, 26), date(2024, 3, 3)))
        self.assertEqual(sum(b.proto.type == 'primary' for b in app.button if b.key.startswith('test_date_')), 7)
        app.button(key='test_mode_month').click().run()
        self.assertEqual(len(app.date_input), 0)
        self.assertEqual(len([b for b in app.button if b.key.startswith('test_month_')]), 12)
        app.button(key='test_month_2').click().run()
        self.assertEqual(app.session_state['result'], ([1], 'Month', date(2024, 2, 1), date(2024, 2, 29)))
        app.button(key='test_mode_custom').click().run()
        app.button(key='test_date_2024-02-27').click().run()
        self.assertTrue(app.button(key='test_apply').disabled)
        app.button(key='test_date_2024-02-29').click().run()
        app.button(key='test_cancel').click().run()
        self.assertEqual(app.session_state['result'][2:], (date(2024, 2, 28),)*2)
        app.button(key='test_date_2024-02-27').click().run()
        app.button(key='test_date_2024-03-02').click().run()
        app.button(key='test_apply').click().run()
        self.assertEqual(app.session_state['result'], ([1], 'Custom', date(2024, 2, 27), date(2024, 3, 2)))
        self.assertFalse(app.exception)

    def test_custom_calendar_across_year_and_navigation_persistence(self):
        app = AppTest.from_string(UI.replace('new_state(date(2024, 2, 28))', 'new_state(date(2024, 12, 30))')).run()
        app.button(key='test_mode_custom').click().run()
        app.button(key='test_date_2024-12-31').click().run()
        app.button(key='test_date_2025-01-03').click().run()
        app.button(key='test_apply').click().run()
        self.assertEqual(app.session_state['result'], ([], 'Custom', date(2024, 12, 31), date(2025, 1, 3)))
        app.button(key='test_mode_month').click().run()
        app.button(key='test_next').click().run()
        app.button(key='test_month_2').click().run()
        self.assertEqual(app.session_state['result'][2:], (date(2025, 2, 1), date(2025, 2, 28)))
        app.button(key='test_mode_custom').click().run()
        self.assertEqual(app.session_state['result'][2:], (date(2024, 12, 31), date(2025, 1, 3)))
        self.assertFalse(app.exception)

    def test_selected_period_shared_with_analytics(self):
        app = AppTest.from_string(UI.replace("result = sales_date_filter(orders, 'test',", "widget_key = st.session_state.get('test_page', 'test')\nresult = sales_date_filter(orders, widget_key,")).run()
        app.button(key='test_mode_month').click().run()
        app.button(key='test_month_2').click().run()
        expected = app.session_state['result']
        app.session_state['test_page'] = 'analytics_sales'
        app.run()
        self.assertEqual(app.session_state['result'], expected)
        self.assertFalse(app.exception)

    def test_original_shortcuts_and_custom_modes_coexist(self):
        app = AppTest.from_string(UI).run()
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date()
        for key, label, start, end in (
            ('test_today', 'Today', today, today),
            ('test_yesterday', 'Yesterday', today - timedelta(days=1), today - timedelta(days=1)),
            ('test_7d', '7D', today - timedelta(days=6), today),
        ):
            app.button(key=key).click().run()
            self.assertEqual(app.session_state['result'][1:], (label, start, end))
        app.button(key='test_mode_month').click().run()
        self.assertEqual(app.session_state['result'][1], 'Month')
        self.assertFalse(app.exception)



if __name__ == '__main__':
    unittest.main()
