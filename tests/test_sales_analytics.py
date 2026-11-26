from datetime import date
from io import BytesIO
import unittest
import sqlite3
from copy import deepcopy
import pandas as pd
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest
from sales_analytics import analytics,prepare,period_range,previous_period,insights,csv_bytes,excel_report,summary_table

START,END=date(2026,1,1),date(2026,1,7)


def snapshot():
    return dict(products=[dict(id=1,name='Cookie',category='Cookies',price=999,unit_cost=999,active=True,measurement_unit='jar'),dict(id=2,name='Cake',category='Cakes',price=999,unit_cost=999,active=True)],customers=[dict(id=1,name='Private name',phone='0123456789')],
        orders=[dict(id=i,customer_id=customer,ordered_at=day,status=status,total_amount=amount,discount=discount,delivery_fee=fee,delivery_quote_status='Confirmed',fulfilment_method='Delivery',delivery_state='Penang',customer_state_snapshot='Kedah') for i,customer,day,status,amount,discount,fee in [
            (1,1,'2025-12-30T10:00:00+08:00','Completed',10,0,0),
            (2,1,'2026-01-01T16:00:00Z','Completed',105,5,10),
            (3,2,'2026-01-03 00:00:00','Pending',30,0,0),
            (4,3,'2026-01-04T00:00:00+08:00','Cancelled',20,0,0),
            (5,1,'2026-01-06T00:00:00+08:00','Completed',40,0,0)]],
        order_items=[dict(id=i,order_id=o,product_id=p,product_name='Cookie' if p==1 else 'Cake',quantity=q,unit_price=price,unit_cost=cost) for i,o,p,q,price,cost in [(1,1,1,1,10,3),(2,2,1,2,30,10),(3,2,2,1,40,15),(4,3,1,1,30,10),(5,4,1,1,20,5),(6,5,2,1,40,15)]],
        payments=[dict(id=i,order_id=o,amount=amount,method=method,paid_at='2026-01-08T10:00:00+08:00') for i,o,amount,method in [(1,2,20,'Cash'),(2,2,30,'Online Transfer'),(3,3,10,'Cash')]])


class SalesAnalyticsTests(unittest.TestCase):
    def setUp(self):self.data=snapshot()
    def report(self,**filters):return analytics(self.data,START,END,filters)

    def test_recognition_and_payment_separation(self):
        k=self.report()['kpis']
        self.assertEqual(k['Recognized Sales Revenue'],145)
        self.assertEqual(k['Total Orders'],4)
        self.assertEqual(k['Completed Orders'],2)
        self.assertEqual(k['Pending Revenue'],30)
        self.assertEqual(k['Verified Collected Payments'],60)
        self.assertEqual(k['Outstanding Payments'],115)
        self.assertEqual(k['Average Order Value'],72.5)
        self.assertEqual(k['Cancellation Rate'],25)

    def test_profit_uses_saved_costs_and_excludes_delivery(self):
        k=self.report()['kpis']
        self.assertEqual(k['Gross Profit'],85)
        self.assertAlmostEqual(k['Gross Profit Margin'],100*85/135)

    def test_item_filters_do_not_duplicate_order_or_payment(self):
        report=self.report(product='Cookie')
        self.assertEqual(report['kpis']['Recognized Sales Revenue'],105)
        self.assertEqual(report['kpis']['Verified Collected Payments'],60)
        self.assertEqual(report['products'].Product.tolist(),['Cookie'])
        self.assertEqual(report['products'].Revenue.tolist(),[60])

    def test_all_filters_and_geographic_normalization(self):
        self.assertEqual(self.report(state='Pulau Pinang',status='Completed',category='Cakes',fulfilment_method='Delivery')['kpis']['Total Orders'],2)
        self.assertEqual(self.report(state='Kedah')['kpis']['Total Orders'],0)
        geo=self.report()['geography'].set_index('State')
        self.assertEqual(geo.loc['Pulau Pinang','Revenue'],145)
        self.assertEqual(geo.loc['Pulau Pinang','Orders'],4)
        self.assertEqual(len(geo),17)

    def test_customer_repeat_and_privacy(self):
        customers=self.report()['customers'];row=customers.loc[customers.Customer.eq('Customer 1')].iloc[0]
        self.assertEqual(row.Type,'Returning');self.assertTrue(row['Repeat in Period'])
        self.assertEqual(row['Recognized Spending'],145)
        self.assertNotIn('Private name',customers.to_csv());self.assertNotIn('0123456789',customers.to_csv())

    def test_missing_cost_and_pending_quote(self):
        self.data['order_items'][1]['unit_cost']=None
        self.assertIsNone(self.report()['kpis']['Gross Profit'])
        self.assertEqual(self.report()['kpis']['Recognized Sales Revenue'],145)
        self.data['orders'][1]['delivery_quote_status']='Pending'
        self.assertIsNone(self.report()['kpis']['Recognized Sales Revenue'])

    def test_claims_and_payment_labels_not_receipts(self):
        self.data['orders'][1].update(payment_status='Paid',submitted_amount_paid=105)
        self.data['payments']=[]
        self.assertEqual(self.report()['kpis']['Verified Collected Payments'],0)
        self.assertEqual(self.report()['orders'].set_index('id').loc[2,'payment_group'],'Unpaid')

    def test_missing_payment_snapshot_is_unknown_not_zero(self):
        del self.data['payments']
        self.assertIsNone(self.report()['kpis']['Verified Collected Payments'])
        self.assertIsNone(self.report()['kpis']['Outstanding Payments'])

    def test_chronology_timezone_and_previous_period(self):
        report=self.report()
        self.assertEqual(report['daily'].recognized.tolist(),[0,105,0,0,0,40,0])
        self.assertEqual(report['previous_period'],(date(2025,12,25),date(2025,12,31)))
        self.assertEqual(report['previous_kpis']['Recognized Sales Revenue'],10)
        self.assertEqual(period_range('Last Month',date(2024,3,15)),(date(2024,2,1),date(2024,2,29)))

    def test_exports_reconcile_and_no_formula_injection(self):
        report=self.report();csv=pd.read_csv(BytesIO(csv_bytes(summary_table(report))))
        self.assertEqual(csv.set_index('Metric').loc['Recognized Sales Revenue','Value'],145)
        workbook=load_workbook(BytesIO(excel_report(report,START,END,{})))
        self.assertEqual(workbook['Monthly'].cell(2,2).value,145)
        self.assertIn('Definitions',workbook.sheetnames)
        self.assertIn("'=SUM",csv_bytes(pd.DataFrame({'name':['=SUM(A1:A2)']})).decode('utf-8-sig'))

    def test_empty_data_and_immutable_input(self):
        original=deepcopy(self.data);self.report();self.assertEqual(self.data,original)
        empty=analytics({},START,END,{})
        self.assertEqual(empty['kpis']['Total Orders'],0)
        self.assertIsNone(empty['kpis']['Average Order Value'])
        self.assertTrue(empty['products'].empty)

    def test_snapshot_refresh_after_import_and_payment(self):
        self.assertEqual(self.report()['kpis']['Recognized Sales Revenue'],145)
        self.data['orders'][2]['status']='Completed'
        self.assertEqual(self.report()['kpis']['Recognized Sales Revenue'],175)
        self.data['payments'].append(dict(id=9,order_id=5,amount=40,method='Cash',paid_at='2026-01-08'))
        self.assertEqual(self.report()['kpis']['Verified Collected Payments'],100)

    def test_sqlite_snapshot_read_only_aggregation(self):
        with sqlite3.connect(':memory:') as db:
            for table,rows in self.data.items():pd.DataFrame(rows).to_sql(table,db,index=False)
            db.execute('PRAGMA query_only=ON')
            loaded={table:pd.read_sql_query(f'SELECT * FROM {table}',db).to_dict('records') for table in self.data}
            self.assertEqual(analytics(loaded,START,END,{})['kpis']['Recognized Sales Revenue'],145)

    def test_insights_are_computed(self):
        text=' '.join(insights(self.report(),START,END))
        self.assertIn('Pulau Pinang',text);self.assertIn('RM 145.00',text)
        self.assertIn('2025',text);self.assertIn('25.0%',text)

    def test_owner_gate(self):
        app=AppTest.from_string('from sales_analytics_ui import render_sales_analytics\nrender_sales_analytics({},owner_authorized=False)').run()
        self.assertFalse(app.exception);self.assertEqual(len(app.metric),0)
        self.assertIn('Owner access',app.error[0].value)

    def test_ui_historical_and_empty(self):
        for data in (snapshot(),{}):
            app=AppTest.from_string('import streamlit as st\nfrom sales_analytics_ui import render_sales_analytics\nrender_sales_analytics(st.session_state["fixture"],owner_authorized=True)')
            app.session_state['fixture']=data
            app.session_state['sales_report_period']='Custom'
            app.session_state['sales_report_start']=START;app.session_state['sales_report_end']=END
            app.run(timeout=40)
            self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertEqual(len(app.metric),13)

if __name__=='__main__':unittest.main()
