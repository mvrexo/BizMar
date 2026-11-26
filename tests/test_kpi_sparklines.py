from datetime import date
import unittest
import sqlite3
import pandas as pd
from pandas.testing import assert_frame_equal
from kpi_sparklines import daily_kpi_trends, sparkline_html


class KpiSparklineTests(unittest.TestCase):
    def setUp(self):
        self.orders=pd.DataFrame([
            dict(id=1,ordered_at='2026-01-01T16:00:00Z',status='Pending',revenue=100.,profit=60.,balance=100.),
            dict(id=2,ordered_at='2026-01-04T00:00:00+08:00',status='Completed',revenue=50.,profit=-10.,balance=0.),
            dict(id=3,ordered_at='2026-01-03T00:00:00+08:00',status='Cancelled',revenue=900.,profit=900.,balance=900.),
        ])
        self.items=pd.DataFrame([dict(order_id=1,quantity=2,unit_cost=20.),dict(order_id=2,quantity=1,unit_cost=60.)])

    def trend(self,start=date(2026,1,1),end=date(2026,1,4)):
        return daily_kpi_trends(self.orders,self.items,start,end)

    def test_daily_malaysia_values_and_totals_unchanged(self):
        original=self.orders.copy(deep=True)
        result=self.trend()
        self.assertEqual(result['orders'],[0,1,0,1])
        self.assertEqual(result['revenue'],[0,100,0,50])
        self.assertEqual(result['profit'],[0,60,0,-10])
        self.assertIsNone(result['balance'])
        assert_frame_equal(self.orders,original)

    def test_range_and_year_leap_boundaries(self):
        self.assertEqual(self.trend(date(2026,1,3))['revenue'],[0,50])
        self.orders.loc[0,'ordered_at']='2024-02-29T00:00:00+08:00'
        self.assertEqual(self.trend(date(2024,2,28),date(2024,3,1))['orders'],[0,1,0])
        self.orders.loc[0,'ordered_at']='2025-12-31T16:00:00Z'
        self.assertEqual(self.trend(date(2025,12,31),date(2026,1,1))['orders'],[0,1])

    def test_empty_single_day_and_invalid_dates(self):
        self.assertTrue(all(v is None for v in self.trend(date(2026,1,2),date(2026,1,2)).values()))
        self.orders=self.orders.iloc[:0]
        self.assertTrue(all(v is None for v in self.trend().values()))

    def test_missing_historical_cost_does_not_invent_profit(self):
        self.items.loc[0,'unit_cost']=None
        self.assertIsNone(self.trend()['profit'])
        self.assertIsNotNone(self.trend()['revenue'])

    def test_mixed_sqlite_and_google_timestamp_formats(self):
        self.orders.loc[0,'ordered_at']='2026-01-02 00:00:00'
        self.orders.loc[1,'ordered_at']='2026-01-04T00:00:00+08:00'
        self.assertEqual(self.trend()['orders'],[0,1,0,1])
        self.assertEqual(self.trend()['revenue'],[0,100,0,50])

    def test_content_cache_refreshes_on_order_and_payment_change(self):
        before=self.trend()
        self.orders.loc[0,'revenue']=120
        self.orders.loc[0,'balance']=80
        self.assertEqual(self.trend()['revenue'][1],120)
        self.assertEqual(before['revenue'][1],100)

    def test_svg_transparent_smooth_and_empty_states(self):
        markup=sparkline_html([0,100,0,-10],'mint','Total Profits')
        self.assertIn(' C ',markup)
        self.assertIn('fill-opacity="0.12"',markup)
        self.assertNotIn('background',markup)
        self.assertEqual('<div class="bizmar-spark-empty" aria-hidden="true"></div>',sparkline_html(None,'peach','Balance',unavailable=True))
        self.assertIn('Not enough data',sparkline_html(None,'mint','Profit'))

    def test_sqlite_saved_values_not_current_catalog_prices(self):
        with sqlite3.connect(':memory:') as db:
            self.orders.to_sql('orders',db,index=False)
            self.items.to_sql('order_items',db,index=False)
            orders=pd.read_sql_query('SELECT * FROM orders',db)
            items=pd.read_sql_query('SELECT * FROM order_items',db)
            result=daily_kpi_trends(orders,items,date(2026,1,1),date(2026,1,4))
            self.assertEqual(sum(result['revenue']),150)
            self.assertEqual(sum(result['profit']),50)
            self.assertEqual(sum(result['orders']),2)

if __name__=='__main__':unittest.main()
