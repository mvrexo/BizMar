import unittest
import pandas as pd
from dashboard_revenue import monthly_revenue


class MonthlyRevenueTests(unittest.TestCase):
    def test_local_month_boundaries_missing_months_and_cancelled_orders(self):
        rows=pd.DataFrame([
            dict(ordered_at='2026-12-31T18:00:00Z',revenue=100,status='Pending'),
            dict(ordered_at='2027-01-10T10:00:00+08:00',revenue=50,status='Completed'),
            dict(ordered_at='2027-03-01T10:00:00+08:00',revenue=20,status='Pending'),
            dict(ordered_at='2027-01-10',revenue=999,status='Cancelled'),
        ])
        result=monthly_revenue(rows)
        self.assertEqual(result['Month'].dt.strftime('%Y-%m').tolist(),['2027-01','2027-02','2027-03'])
        self.assertEqual(result['Revenue'].tolist(),[150,0,20])

    def test_empty_and_invalid_dates(self):
        self.assertTrue(monthly_revenue(pd.DataFrame()).empty)
        self.assertTrue(monthly_revenue(pd.DataFrame([dict(ordered_at='invalid',revenue=10)])).empty)
