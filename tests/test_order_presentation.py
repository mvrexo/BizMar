from datetime import date
from decimal import Decimal
from urllib.parse import quote, unquote
import unittest
from orders_view import order_frame, order_summary, whatsapp_message


class OrderPresentationTests(unittest.TestCase):
    def test_empty_and_malaysia_deadlines(self):
        empty = order_summary(order_frame([]), date(2026,12,31))
        self.assertEqual(empty, dict(total=0,pending=0,completed=0,cancelled=0,outstanding=Decimal(0),today=0,tomorrow=0,overdue=0))
        rows = [dict(status='Pending',balance=10.1,fulfilment_date='2026-12-31'),
                dict(status='Pending',balance=.2,fulfilment_date='2027-01-01'),
                dict(status='Pending',balance=5.,fulfilment_date='2026-12-30'),
                dict(status='Completed',balance=7.,fulfilment_date='2026-12-31'),
                dict(status='Cancelled',balance=100.,fulfilment_date='2026-12-30'),
                dict(status='Completed',balance=-9.,fulfilment_date='2026-12-31')]
        summary = order_summary(order_frame(rows),date(2026,12,31))
        self.assertEqual((summary['today'],summary['tomorrow'],summary['overdue']),(1,1,1))
        self.assertEqual(summary['outstanding'],Decimal('22.3'))
        leap = order_summary(order_frame([dict(status='Pending',balance=0,fulfilment_date='2024-02-29')]), date(2024,2,28))
        self.assertEqual(leap['tomorrow'],1)

    def test_whatsapp_contains_items_and_encoded_text(self):
        order = dict(customer_name='Synthetic A & B',order_code='ORD007',total_amount=30.,balance=12.,fulfilment_method='Delivery',fulfilment_date='2026-12-31',fulfilment_time='14:00')
        text = whatsapp_message(order,[dict(quantity=2,product_name='Cake & Cream'),dict(quantity=1,product_name='Kuih')])
        for value in ('ORD007','2 x Cake & Cream','1 x Kuih','RM 30.00','RM 12.00','2026-12-31','14:00'):
            self.assertIn(value,text)
        self.assertEqual(unquote(quote(text)),text)
