from pathlib import Path
from datetime import date
from io import BytesIO
import tempfile
import sqlite3
import unittest
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from openpyxl import load_workbook
from uat_fixture import build
import orders_store as store
from orders_view import order_frame, filter_orders, date_scope, export_frame, excel_bytes
from orders_schema import migrate
from malaysian_states import STATES, CHOICES as STATE_CHOICES, normalize, destination, display
from orders_list_ui import actions_for


class OrderStateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=build(Path(self.temp.name)/'synthetic.sqlite3')
        self.patches=[patch.object(store,'sqlite_db',self.db),patch.object(store,'current_owner',return_value='synthetic-owner@example.test')]
        for p in self.patches:p.start()
        self.product=self.db.all_rows('products')[0]
        self.serial=0

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def create(self,state='',delivery=None):
        self.serial+=1
        return store.save_order(dict(name=f'Synthetic State {self.serial}',phone=f'01234{self.serial:05d}',state=state),
            dict(ordered_at='2026-10-27',fulfilment_date='2026-12-31',source='WhatsApp',
                 fulfilment_method='Delivery' if delivery is not None else 'Pickup',
                 delivery_address='Explicit synthetic destination' if delivery is not None else '',delivery_state=delivery),
            [dict(product_id=self.product['id'],quantity=1,unit_price=10)],token=f'state-test-create-{self.serial:04d}')

    def test_all_states_and_not_specified_roundtrip_filters(self):
        self.assertEqual(STATES, (
            'Johor', 'Kedah', 'Kelantan', 'Melaka', 'Negeri Sembilan', 'Pahang',
            'Perak', 'Perlis', 'Pulau Pinang', 'Selangor', 'Terengganu', 'Sabah',
            'Sarawak', 'Wilayah Persekutuan Kuala Lumpur',
            'Wilayah Persekutuan Putrajaya', 'Wilayah Persekutuan Labuan',
        ))
        for state in (*STATES,''):
            saved=self.create(state)
            expected=state or 'Not Specified'
            self.assertEqual(store.details(saved['id'])['order']['state'],expected)
        frame=order_frame(store.list_orders())
        self.assertEqual(len(filter_orders(frame,state='All States')),23)
        for state in STATES:
            selected=filter_orders(frame,state=state)
            self.assertEqual(len(selected),1)
            self.assertEqual(selected.iloc[0]['customer_state_snapshot'],state)
        self.assertEqual(len(filter_orders(frame,state='Not Specified')),7)
        for state in STATES:
            saved=self.create('Kelantan',state)
            self.assertEqual(store.details(saved['id'])['order']['state'],state)

    def test_delivery_snapshot_and_residence_remain_independent(self):
        first=self.create('Kedah','Sabah')
        second=self.create('Johor','')
        self.assertEqual(store.details(second['id'])['order']['state'],'Not Specified')
        self.db.edit('customers',first['customer_id'],dict(state='Selangor',address='Changed profile'))
        before=store.details(first['id'])
        self.assertEqual(before['order']['customer_state_snapshot'],'Kedah')
        self.assertEqual(before['order']['state'],'Sabah')
        store.save_order(dict(name=before['order']['customer_name'],phone=before['order']['phone_number'],state='Kedah'),
            dict(ordered_at='2026-10-27',fulfilment_date='2026-12-31',source='Other',fulfilment_method='Delivery',delivery_address='Another explicit destination',delivery_state='Sarawak'),
            [dict(product_id=self.product['id'],quantity=1,unit_price=10,source_item_id=before['items'][0]['id'])],
            token='state-test-edit-00001',order_id=first['id'],version=before['order']['version'])
        self.assertEqual(store.details(first['id'])['order']['state'],'Sarawak')
        self.assertEqual(self.db.all_rows('customers',id=first['customer_id'])[0]['state'],'Selangor')

    def test_combined_filters_exports_and_readonly_filtering(self):
        first=self.create('Kedah')
        self.create('Sabah')
        store.record_payment(first['id'],dict(amount=5,method='Cash'),token='state-payment-00001')
        store.transition(first['id'],'Completed')
        before={t:self.db.all_rows(t) for t in ('orders','customers','payments')}
        frame=order_frame(store.list_orders())
        filtered=filter_orders(date_scope(frame,date(2026,10,27),date(2026,10,27)),state='Kedah',status='Completed',payment='Partial',fulfillment='Pickup',source='WhatsApp',search='State',sort='Highest amount')
        self.assertEqual(filtered.id.tolist(),[first['id']])
        self.assertEqual(export_frame(filtered)['State'].tolist(),['Kedah'])
        book=load_workbook(BytesIO(excel_bytes(filtered)),read_only=True)
        rows=list(book.active.values)
        self.assertEqual(rows[1][rows[0].index('State')],'Kedah')
        csv=pd.read_csv(BytesIO(export_frame(filtered).to_csv(index=False).encode()))
        self.assertEqual(csv['State'].tolist(),['Kedah'])
        self.assertEqual({t:self.db.all_rows(t) for t in before},before)

    def test_legacy_migration_and_invalid_state(self):
        before=self.db.all_rows('orders')
        with self.db.transaction() as connection:
            migrate(connection);migrate(connection)
        self.assertEqual(self.db.all_rows('orders'),before)
        for value in ('California','60123456789'):
            with self.assertRaises(ValueError):normalize(value)
        self.assertEqual(destination(dict(fulfilment_method='Delivery',customer_state_snapshot='Kedah')),'Not Specified')
        with self.assertRaises(ValueError):self.create('Unknown')
        self.assertEqual(len(self.db.all_rows('orders')),6)
        aliases = {
            'Penang': 'Pulau Pinang',
            'Malacca': 'Melaka',
            'Kuala Lumpur': 'Wilayah Persekutuan Kuala Lumpur',
            'W.P. Kuala Lumpur': 'Wilayah Persekutuan Kuala Lumpur',
            'Putrajaya': 'Wilayah Persekutuan Putrajaya',
            'Labuan': 'Wilayah Persekutuan Labuan',
        }
        for alias, expected in aliases.items():
            self.assertEqual(normalize(alias), expected)
            self.assertEqual(display(alias), expected)
        self.assertEqual(display('Unknown state'), 'Not Specified')

    def test_real_legacy_schema_adds_optional_state_without_inference(self):
        connection=sqlite3.connect(Path(self.temp.name)/'old-schema.sqlite3')
        connection.row_factory=sqlite3.Row
        try:
            connection.executescript('''CREATE TABLE customers(id INTEGER PRIMARY KEY,name TEXT,phone TEXT,address TEXT);
            CREATE TABLE orders(id INTEGER PRIMARY KEY,customer_id INTEGER,total_amount REAL,status TEXT);
            CREATE TABLE payments(id INTEGER PRIMARY KEY,amount REAL);
            CREATE TABLE app_metadata(key TEXT PRIMARY KEY,value TEXT);
            INSERT INTO customers VALUES(1,'Legacy synthetic','0123456789','Kedah written in an unstructured address');
            INSERT INTO orders VALUES(1,1,10,'Completed');''')
            migrate(connection)
            customer=dict(connection.execute('SELECT * FROM customers').fetchone())
            order=dict(connection.execute('SELECT * FROM orders').fetchone())
            self.assertEqual(customer['state'],'')
            self.assertEqual(order['customer_state_snapshot'],'')
            self.assertEqual(order['delivery_state'],'')
            self.assertEqual(order['status'],'Completed')
            self.assertEqual(order['total_amount'],10)
            connection.execute("UPDATE orders SET delivery_state='Kedah'")
            migrate(connection)
            self.assertEqual(connection.execute('SELECT delivery_state FROM orders').fetchone()[0],'Kedah')
        finally:
            connection.close()

    def test_contextual_actions_are_valid(self):
        for status in ('Pending','Completed','Cancelled'):
            actions=[a[0] for a in actions_for(dict(status=status,balance=10))]
            self.assertEqual('edit' in actions,status=='Pending')
            self.assertEqual('cancel' in actions,status=='Pending')
            self.assertEqual('payment' in actions,status!='Cancelled')

    def test_row_actions_record_complete_and_confirm_cancel(self):
        import order_management as ui
        saved=self.create('Kedah')
        identity=saved['id']
        with patch.object(ui,'sqlite_db',self.db):
            app=AppTest.from_string('from order_management import render_order_management\nrender_order_management()').run()
            app.button(key=f'om_menu_row_payment_{identity}').click().run()
            app.number_input(key=f'om_payment_amount_{identity}').set_value(2.)
            next(b for b in app.button if b.label=='Save Payment').click().run()
            self.assertEqual(store.details(identity)['order']['payment_status'],'Partial')
            app.button(key=f'om_menu_row_complete_{identity}').click().run()
            self.assertEqual(store.details(identity)['order']['status'],'Completed')
            self.assertEqual(store.details(identity)['order']['payment_status'],'Partial')
            app.button(key=f'om_menu_row_payment_{identity}').click().run()
            app.number_input(key=f'om_payment_amount_{identity}').set_value(8.)
            next(b for b in app.button if b.label=='Save Payment').click().run()
            self.assertEqual(store.details(identity)['order']['payment_status'],'Paid')
            second=self.create('Sabah')
            identity=second['id']
            app.run()
            app.button(key=f'om_menu_row_cancel_{identity}').click().run()
            app.button(key=f'om_keep_{identity}').click().run()
            self.assertEqual(store.details(identity)['order']['status'],'Pending')
            app.button(key=f'om_menu_row_cancel_{identity}').click().run()
            app.button(key=f'om_cancel_confirm_{identity}').click().run()
            self.assertEqual(store.details(identity)['order']['status'],'Cancelled')
            self.assertEqual(len(store.details(identity)['items']),1)
            self.assertFalse(app.exception)

    def test_ui_state_save_edit_chips_pagination_and_row_menu(self):
        import order_management as ui
        with patch.object(ui,'sqlite_db',self.db):
            app=AppTest.from_string('from order_management import render_order_management\nrender_order_management()').run()
            app.button(key='om_add_new').click().run()
            scope='om_add_'+app.session_state['om_form_token']
            self.assertEqual(app.selectbox(key=scope+'_customer_state').options,list(STATE_CHOICES))
            app.text_input(key=scope+'_customer_name').set_value('Synthetic State UI')
            app.text_input(key=scope+'_phone').set_value('0181234567')
            app.selectbox(key=scope+'_customer_state').set_value('Wilayah Persekutuan Kuala Lumpur')
            app.selectbox(key=scope+'_fulfilment_method').set_value('Delivery').run()
            self.assertEqual(app.selectbox(key=scope+'_delivery_state').options,list(STATE_CHOICES))
            app.selectbox(key=scope+'_delivery_state').set_value('Wilayah Persekutuan Putrajaya')
            app.text_area(key=scope+'_delivery_address').set_value('Synthetic destination')
            app.number_input(key=scope+'_price_0').set_value(10.)
            app.button(key=scope+'_save').click().run()
            self.assertFalse(app.exception)
            saved=next(p for p in store.list_orders() if p['customer_name']=='Synthetic State UI')
            self.assertEqual(saved['customer_state_snapshot'],'Wilayah Persekutuan Kuala Lumpur')
            self.assertEqual(saved['delivery_state'],'Wilayah Persekutuan Putrajaya')
            app.selectbox(key='om_state_filter').set_value('Wilayah Persekutuan Putrajaya').run()
            self.assertEqual(app.session_state['om_detail_selected'],saved['id'])
            app.button(key=f'om_menu_row_edit_{saved["id"]}').click().run()
            scope=f'om_edit_{saved["id"]}_'+app.session_state['om_form_token']
            app.selectbox(key=scope+'_delivery_state').set_value('Wilayah Persekutuan Labuan')
            app.button(key=scope+'_save').click().run()
            self.assertEqual(store.details(saved['id'])['order']['state'],'Wilayah Persekutuan Labuan')
            app.button(key='om_chip_om_state_filter').click().run()
            self.assertEqual(app.selectbox(key='om_state_filter').value,'All States')
            for _ in range(24):self.create('Kedah')
            app.run()
            app.button(key='om_next').click().run()
            self.assertEqual(app.number_input(key='om_page').value,2)
            app.selectbox(key='om_state_filter').set_value('Kedah').run()
            self.assertEqual(app.number_input(key='om_page').value,1)
            app.selectbox(key='om_state_filter').set_value('Wilayah Persekutuan Kuala Lumpur').run()
            self.assertTrue(any(x.value=='No orders found for the selected state.' for x in app.info))
            self.assertFalse(app.exception)
