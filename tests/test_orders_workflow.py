"""Orders owner workflows on disposable synthetic databases only."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import date

from streamlit.testing.v1 import AppTest
import sqlite_db
import orders_store as store
from orders_view import order_frame,filter_orders,date_scope,export_frame,excel_bytes

FIXTURE = Path(__file__).with_name('order_management_fixture.py')


class OrdersWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bizmar-orders-ui-')
        self.old = sqlite_db.DB_PATH
        sqlite_db.DB_PATH = Path(self.temp.name) / 'orders.sqlite3'
        sqlite_db.initialize()
        from uat_fixture import seed_products
        seed_products(sqlite_db)
        self.product = sqlite_db.all_rows('products')[0]
        sqlite_db.edit('products',self.product['id'],dict(price=10.,unit_cost=3.))

    def tearDown(self):
        sqlite_db.DB_PATH = self.old
        self.temp.cleanup()

    def seed(self, name='Synthetic Customer', phone='0123456789', source='WhatsApp', day='2026-10-26'):
        with patch.object(store,'current_owner',return_value='synthetic-owner@example.test'):
            return store.save_order(dict(name=name,phone=phone),dict(ordered_at=day,fulfilment_date='2026-12-31',source=source),
                                    [dict(product_id=self.product['id'],quantity=2,unit_price=10)],token='seed-'+phone+'-'+day)

    def app(self):
        app = AppTest.from_file(str(FIXTURE)).run(timeout=30)
        self.assertFalse(app.exception)
        return app

    def open_details(self, app, order):
        app.button(key=f'om_customer_details_row_{order["id"]}').click().run()
        self.assertIn(f'Order Details · {order["order_code"]}', [item.value for item in app.subheader])

    def test_multi_item_create_deposit_delivery_and_calendar(self):
        app = self.app()
        app.button(key='om_add_new').click().run()
        scope = 'om_add_'+app.session_state['om_form_token']
        app.text_input(key=scope+'_customer_name').set_value('Synthetic Delivery')
        app.text_input(key=scope+'_phone').set_value('0181234567')
        app.selectbox(key=scope+'_fulfilment_method').set_value('Delivery').run()
        app.text_area(key=scope+'_delivery_address').set_value('Synthetic delivery address')
        app.button(key=scope+'_add_line').click().run()
        app.number_input(key=scope+'_quantity_0').set_value(2)
        app.number_input(key=scope+'_price_0').set_value(10.)
        app.number_input(key=scope+'_quantity_1').set_value(3)
        app.number_input(key=scope+'_price_1').set_value(5.)
        app.number_input(key=scope+'_discount').set_value(3.)
        app.number_input(key=scope+'_delivery_fee').set_value(4.)
        app.number_input(key=scope+'_deposit').set_value(10.).run()
        app.button(key=scope+'_save').click().run()
        self.assertFalse(app.exception)
        saved = sqlite_db.all_rows('orders')[0]
        self.assertEqual(saved['total_amount'],36.)
        self.assertEqual(saved['status'],'Pending')
        self.assertEqual(len(sqlite_db.all_rows('order_items')),2)
        self.assertEqual(len(sqlite_db.all_rows('payments')),1)
        self.assertEqual(saved['delivery_address'],'Synthetic delivery address')
        from deadline_calendar import prepare_deadline_orders
        import pandas as pd
        scheduled = prepare_deadline_orders(pd.DataFrame([saved]),date(2026,10,26))
        self.assertEqual(scheduled.iloc[0]['calendar_date'],date.fromisoformat(saved['fulfilment_date']))
        # Verify the actual Dashboard loader and long-term analytics see the grand total.
        import ast
        source = (FIXTURE.parent.parent/'app.py').read_text(encoding='utf-8')
        loader = next(ast.get_source_segment(source,node) for node in ast.parse(source).body
                      if isinstance(node,ast.FunctionDef) and node.name=='load')
        namespace = dict(pd=pd,fetch=lambda:{table:sqlite_db.all_rows(table) for table in
                                          ('products','customers','orders','order_items','payments')})
        exec(loader,namespace)
        _,_,_,dashboard,lines,_ = namespace['load']()
        self.assertEqual(dashboard.iloc[0]['revenue'],36.)
        self.assertEqual(dashboard.iloc[0]['balance'],26.)
        from advanced_bi import financial_orders
        financial = financial_orders(dashboard,lines,date.min,date.max)
        self.assertEqual(financial.iloc[0]['revenue'],36.)
        self.assertEqual(financial.iloc[0]['gross_profit'],21.)
        self.assertTrue(any(saved['order_code'] in item.value for item in app.success))

    def test_complete_and_cancel_dialog_keep_history(self):
        first = self.seed()
        app = self.app()
        self.assertEqual(app.session_state['om_status_filter'],'All')
        self.open_details(app, first)
        app.button(key=f'om_cancel_{first["id"]}').click().run()
        app.button(key=f'om_keep_{first["id"]}').click().run()
        self.assertEqual(sqlite_db.all_rows('orders')[0]['status'],'Pending')
        self.open_details(app, first)
        app.button(key=f'om_cancel_{first["id"]}').click().run()
        app.text_area(key=f'om_cancel_reason_{first["id"]}').set_value('Synthetic cancellation')
        app.button(key=f'om_cancel_confirm_{first["id"]}').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(sqlite_db.all_rows('orders')[0]['status'],'Cancelled')
        self.assertEqual(len(sqlite_db.all_rows('order_items')),1)
        self.assertFalse(any(button.label=='Mark Completed' for button in app.button))
        second = self.seed(phone='0191234567')
        app = self.app()
        self.open_details(app, second)
        self.assertFalse(any(item.label=='View Details' for item in app.selectbox))
        self.assertNotIn('nour_orders_actions', [item.key for item in app.get('container')])
        app.button(key=f'om_complete_{second["id"]}').click().run()
        self.assertTrue(any('marked Completed' in toast.value for toast in app.toast))
        saved = next(row for row in sqlite_db.all_rows('orders') if row['id']==second['id'])
        self.assertEqual(saved['status'],'Completed')
        self.assertTrue(saved['completed_at'])
        self.assertEqual(saved['payment_status'],'Unpaid')

    def test_partial_and_full_payment_forms(self):
        created = self.seed()
        identity = created['id']
        app = self.app()
        self.open_details(app, created)
        app.button(key=f'om_record_payment_{identity}').click().run()
        app.number_input(key=f'om_payment_amount_{identity}').set_value(5.)
        next(button for button in app.button if button.label=='Save Payment').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(sqlite_db.all_rows('orders')[0]['payment_status'],'Partial')
        app.button(key=f'om_record_payment_{identity}').click().run()
        app.number_input(key=f'om_payment_amount_{identity}').set_value(15.)
        next(button for button in app.button if button.label=='Save Payment').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(sqlite_db.all_rows('orders')[0]['payment_status'],'Paid')
        self.assertEqual(len(sqlite_db.all_rows('payments')),2)
        self.assertFalse(any(button.label=='Record Payment' for button in app.button))

    def test_edit_pending_and_search_filters(self):
        saved = self.seed()
        app = self.app()
        self.open_details(app, saved)
        app.button(key=f'om_edit_{saved["id"]}').click().run()
        scope = f'om_edit_{saved["id"]}_'+app.session_state['om_form_token']
        app.number_input(key=scope+'_quantity_0').set_value(3)
        app.date_input(key=scope+'_fulfilment_date').set_value(date(2027,1,2))
        app.button(key=scope+'_save').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(sqlite_db.all_rows('orders')[0]['total_amount'],30)
        self.assertEqual(sqlite_db.all_rows('orders')[0]['fulfilment_date'],'2027-01-02')
        app.text_input(key='om_search').set_value('No match').run()
        self.assertFalse(app.exception)
        self.assertTrue(any('No orders match' in value.value for value in app.info))
        app.text_input(key='om_search').set_value(self.product['name']).run()
        self.assertFalse(app.exception)
        self.assertFalse(any(item.label=='View Details' for item in app.selectbox))
        self.assertTrue(any(button.key.startswith('om_customer_details_row_') for button in app.button))
        app.date_input(key='om_date_from').set_value(date(2026,10,27)).run()
        self.assertEqual(app.metric[0].value,'0')
        app.button(key='om_reset_filters').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value,'1')
        self.assertEqual(app.text_input(key='om_search').value,'')
        self.assertIsNone(app.date_input(key='om_date_from').value)

    def test_filter_export_empty_and_spreadsheet_injection(self):
        self.seed(name='=DANGEROUS()',source='Instagram')
        with patch.object(store,'current_owner',return_value='synthetic-owner@example.test'):
            frame = order_frame(store.list_orders())
        self.assertEqual(len(filter_orders(frame,search=self.product['name'],source='Instagram',fulfillment='Pickup',payment='Unpaid')),1)
        self.assertTrue(filter_orders(frame,payment='Paid').empty)
        self.assertTrue(date_scope(frame,date(2026,10,27),date(2026,10,26)).empty)
        exported = export_frame(frame)
        self.assertEqual(exported.iloc[0]['Customer'],"'=DANGEROUS()")
        self.assertNotIn('id',exported.columns)
        self.assertTrue(excel_bytes(frame).startswith(b'PK'))
        self.assertTrue(filter_orders(order_frame([]),search='Synthetic').empty)
        self.assertTrue(export_frame(order_frame([])).empty)

    def test_remove_middle_item_retains_draft_and_saved_snapshots(self):
        app = self.app()
        app.button(key='om_add_new').click().run()
        scope = 'om_add_'+app.session_state['om_form_token']
        app.text_input(key=scope+'_customer_name').set_value('Synthetic Three Lines')
        app.text_input(key=scope+'_phone').set_value('0123456789')
        app.number_input(key=scope+'_price_0').set_value(10.)
        app.button(key=scope+'_add_line').click().run()
        app.number_input(key=scope+'_price_1').set_value(20.)
        app.button(key=scope+'_add_line').click().run()
        app.number_input(key=scope+'_price_2').set_value(30.)
        app.button(key=scope+'_remove_item_1').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.number_input(key=scope+'_price_1').value,30.)
        app.button(key=scope+'_save').click().run()
        self.assertFalse(app.exception)
        lines=sqlite_db.all_rows('order_items')
        self.assertEqual([line['unit_price'] for line in lines],[10.,30.])
        self.assertEqual(sqlite_db.all_rows('orders')[0]['total_amount'],40.)

    def test_empty_orders_message_and_zero_balance(self):
        app=self.app()
        self.assertTrue(any(item.value=='No orders yet. Create your first order to get started.' for item in app.info))
        self.assertEqual([item.value for item in app.metric],['0','0','0','0'])
        self.assertEqual(len(sqlite_db.all_rows('orders')),0)

    def test_status_tabs_and_outstanding_ignore_cancelled_orders(self):
        first=self.seed()
        second=self.seed(phone='0191234567')
        with patch.object(store,'current_owner',return_value='synthetic-owner@example.test'):
            store.transition(second['id'],'Cancelled')
        app=self.app()
        self.assertEqual(app.metric[3].value,'1')
        app.session_state['om_status_filter']='Cancelled'
        app.run()
        self.assertEqual(app.session_state['om_detail_selected'],second['id'])
        app.session_state['om_status_filter']='Pending'
        app.run()
        self.assertEqual(app.session_state['om_detail_selected'],first['id'])
        app.button(key='om_reset_filters').click().run()
        self.assertEqual(app.session_state['om_status_filter'],'All')


if __name__ == '__main__': unittest.main()
