from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import sqlite_db
from streamlit.testing.v1 import AppTest
from customer_directory import directory_rows,save_customer
from malaysian_states import STATES

UI='''
import sqlite_db
from customer_directory import render_customers
render_customers(sqlite_db.all_rows('customers'),store=sqlite_db,on_saved=lambda:None,normalize_phone=sqlite_db.normalize_customer_phone)
'''


class CustomerDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='bizmar-customer-directory-')
        self.path=patch.object(sqlite_db,'DB_PATH',Path(self.temp.name)/'test.sqlite3');self.path.start()
        sqlite_db.initialize()

    def tearDown(self):self.path.stop();self.temp.cleanup()

    def create(self,name='Zara',phone='0123456789'):
        save_customer(sqlite_db,dict(name=name,phone=phone,address='Test address',state='Kedah'))
        return sqlite_db.all_rows('customers')[-1]

    def test_listing_search_sort_and_literal_queries(self):
        self.create();self.create('Amy','0133456789')
        rows=sqlite_db.all_rows('customers')
        self.assertEqual([r['customer_name'] for r in directory_rows(rows)],['Amy','Zara'])
        self.assertEqual(len(directory_rows(rows,'zArA')),1)
        self.assertEqual(len(directory_rows(rows,'+60 12-345 6789',sqlite_db.normalize_customer_phone)),1)
        self.assertEqual(directory_rows(rows,'['),[])

    def test_validation_and_duplicates(self):
        self.create()
        for values in [dict(name='',phone='0133456789',address='A',state='Kedah'),dict(name='A',phone='abc',address='A',state='Kedah'),dict(name='A',phone='0133456789',address='',state='Kedah'),dict(name='A',phone='0133456789',address='A',state='')]:
            with self.assertRaises(ValueError):save_customer(sqlite_db,values)
        with self.assertRaisesRegex(ValueError,'already registered'):
            self.create('Duplicate','+60 12-345 6789')
        self.assertEqual(len(sqlite_db.all_rows('customers')),1)

    def test_edit_preserves_ids_orders_snapshots_and_notes(self):
        customer=self.create();identity=customer['id']
        sqlite_db.edit('customers',identity,{'notes':'Keep this note'})
        with sqlite_db.transaction() as db:
            db.execute('INSERT INTO orders(customer_id,ordered_at,due_date,fulfilment_date,delivery_address,customer_name_snapshot,phone_snapshot,customer_state_snapshot) VALUES (?,?,?,?,?,?,?,?)',(identity,'2026-01-01','2026-01-02','2026-01-02','Original address','Original name','Original phone','Kedah'))
        before=sqlite_db.all_rows('orders')
        save_customer(sqlite_db,dict(name='Updated',phone='0143456789',address='New address',state='Johor'),identity)
        after=sqlite_db.all_rows('customers')[0]
        self.assertEqual(after['id'],identity);self.assertEqual(after['customer_id'],customer['customer_id'])
        self.assertEqual(after['notes'],'Keep this note')
        self.assertEqual(sqlite_db.all_rows('orders'),before)

    def test_edit_duplicate_and_archived_duplicate(self):
        first=self.create();second=self.create('Other','0133456789')
        sqlite_db.edit('customers',first['id'],{'archived':1})
        self.assertEqual(len(directory_rows(sqlite_db.all_rows('customers'))),1)
        with self.assertRaises(ValueError):save_customer(sqlite_db,dict(name='Other',phone='0123456789',address='A',state='Kedah'),second['id'])

    def test_remove_unreferenced_customer_permanently_and_refreshes_ui(self):
        customer=self.create()
        app=AppTest.from_string(UI).run()
        self.assertEqual(app.metric[0].value,'1')
        app.text_input(key='directory_search').set_value('Zara').run()
        app.button(key=f'directory_remove_{customer["id"]}').click().run()
        self.assertIn('Zara',app.text[0].value)
        self.assertIn('Customers with orders or other linked records',app.caption[0].value)
        self.assertEqual(sqlite_db.all_rows('customers'),[customer])

        app.button(key='directory_remove_cancel').click().run()
        self.assertEqual(sqlite_db.all_rows('customers'),[customer])
        self.assertEqual(app.metric[0].value,'1')

        app.button(key=f'directory_remove_{customer["id"]}').click().run()
        app.button(key='directory_remove_confirm').click().run()
        self.assertEqual(sqlite_db.all_rows('customers'),[])
        self.assertEqual(app.metric[0].value,'0')
        self.assertTrue(any('Customer removed successfully.' in item.value for item in app.success))
        app.text_input(key='directory_search').set_value('Zara').run()
        self.assertTrue(any('No customers yet.' in item.value for item in app.info))
        self.assertFalse(app.exception)

    def test_remove_customer_with_orders_payments_and_messages_archives_history(self):
        customer=self.create()
        with sqlite_db.transaction() as connection:
            order_id=connection.execute(
                '''INSERT INTO orders(customer_id,ordered_at,due_date,fulfilment_date,
                                      total_amount,status)
                   VALUES(?,?,?,?,?,'Completed')''',
                (customer['id'],'2026-10-27','2026-10-29','2026-10-29',25.),
            ).lastrowid
            payment_id=connection.execute(
                'INSERT INTO payments(order_id,amount,method) VALUES(?,?,?)',
                (order_id,25.,'Transfer'),
            ).lastrowid
            connection.execute(
                '''INSERT INTO customer_messages
                   (customer_id,order_id,template_type,content,created_at,updated_at,
                    request_token,creation_hash)
                   VALUES(?,?,?,?,?,?,?,?)''',
                (customer['id'],order_id,'Order Received','Synthetic message',
                 '2026-10-27','2026-10-27','customer-remove-message-token',
                 'synthetic-message-hash'),
            )
        orders_before=sqlite_db.all_rows('orders')
        payments_before=sqlite_db.all_rows('payments')
        with sqlite_db.transaction() as connection:
            messages_before=[
                dict(row) for row in connection.execute(
                    'SELECT * FROM customer_messages WHERE customer_id=?',(customer['id'],)
                ).fetchall()
            ]
        app=AppTest.from_string(UI).run()
        app.button(key=f'directory_remove_{customer["id"]}').click().run()
        app.button(key='directory_remove_confirm').click().run()
        archived=sqlite_db.all_rows('customers',id=customer['id'])[0]
        self.assertEqual(archived['archived'],1)
        self.assertEqual(directory_rows(sqlite_db.all_rows('customers')),[])
        self.assertEqual(sqlite_db.all_rows('orders'),orders_before)
        self.assertEqual(sqlite_db.all_rows('payments'),payments_before)
        with sqlite_db.transaction() as connection:
            self.assertEqual(
                [dict(row) for row in connection.execute(
                    'SELECT * FROM customer_messages WHERE customer_id=?',(customer['id'],)
                ).fetchall()],
                messages_before,
            )
            self.assertEqual(connection.execute('SELECT id FROM payments').fetchone()['id'],payment_id)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM customer_messages').fetchone()[0],1)
        self.assertTrue(any('Customer archived to preserve linked records.' in item.value for item in app.success))
        self.assertFalse(app.exception)

    def test_add_edit_and_cancel_ui(self):
        app=AppTest.from_string(UI).run()
        self.assertFalse(app.exception)
        app.button(key='directory_add').click().run()
        app.text_input[1].set_value('Anna');app.text_input[2].set_value('0123456789')
        app.text_area[0].set_value('Test address');app.selectbox[0].set_value('Kedah')
        next(button for button in app.button if button.label=='Save Customer').click().run()
        self.assertFalse(app.exception)
        customer=sqlite_db.all_rows('customers')[0]
        self.assertEqual(app.metric[0].value,'1')
        app.button(key=f'directory_edit_{customer["id"]}').click().run()
        self.assertEqual(app.text_input[1].value,'Anna')
        app.text_input[1].set_value('Changed');next(b for b in app.button if b.label=='Cancel').click().run()
        self.assertEqual(sqlite_db.all_rows('customers')[0]['name'],'Anna')
        app.button(key=f'directory_edit_{customer["id"]}').click().run()
        app.text_input[1].set_value('Changed');next(b for b in app.button if b.label=='Save Customer').click().run()
        self.assertEqual(sqlite_db.all_rows('customers')[0]['name'],'Changed')

    def test_exact_state_options_legacy_display_and_canonical_save(self):
        customer=self.create()
        with sqlite_db.transaction() as connection:
            connection.execute('UPDATE customers SET state=? WHERE id=?',('Penang',customer['id']))
        app=AppTest.from_string(UI).run()
        app.button(key=f'directory_edit_{customer["id"]}').click().run()
        state=app.get('selectbox')[0]
        self.assertEqual(state.options,['Select a state',*STATES])
        self.assertEqual(state.value,'Pulau Pinang')
        self.assertEqual(sqlite_db.all_rows('customers')[0]['state'],'Penang')
        state.set_value('Wilayah Persekutuan Kuala Lumpur')
        next(button for button in app.button if button.label=='Save Customer').click().run()
        self.assertEqual(sqlite_db.all_rows('customers')[0]['state'],'Wilayah Persekutuan Kuala Lumpur')
        self.assertFalse(app.exception)
        with patch('display_preferences.runtime',return_value={'language':'Bahasa Melayu'}):
            malay=AppTest.from_string(UI).run()
            malay.button(key=f'directory_edit_{customer["id"]}').click().run()
        self.assertEqual(malay.get('selectbox')[0].options,['Pilih negeri',*STATES])
        self.assertEqual(malay.get('selectbox')[0].value,'Wilayah Persekutuan Kuala Lumpur')

    def test_empty_search_pagination_and_minimal_features(self):
        app=AppTest.from_string(UI).run();self.assertFalse(app.exception)
        self.assertEqual(len(app.metric),1);self.assertEqual(len(app.get('plotly_chart')),0)
        for i in range(17):self.create(f'Customer {i:02d}',f'011{10000000+i}')
        app.run();self.assertEqual(app.metric[0].value,'17')
        self.assertEqual(sum(b.key.startswith('directory_edit_') for b in app.button if b.key),15)
        app.number_input(key='directory_page').set_value(2).run()
        self.assertEqual(sum(b.key.startswith('directory_edit_') for b in app.button if b.key),2)
        app.text_input(key='directory_search').set_value('Customer 00').run()
        self.assertEqual(sum(b.key.startswith('directory_edit_') for b in app.button if b.key),1)

    def test_english_and_malay_labels_validation(self):
        from display_preferences import MALAY
        with patch('display_preferences.runtime',return_value={'language':'Bahasa Melayu'}):
            app=AppTest.from_string(UI).run();self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].label,'Jumlah Pelanggan')
            app.button(key='directory_add').click().run()
            next(b for b in app.button if b.label=='Simpan Pelanggan').click().run()
            self.assertEqual(app.error[0].value,MALAY['Customer name is required.'])
            customer=self.create()
            app=AppTest.from_string(UI).run()
            app.button(key=f'directory_remove_{customer["id"]}').click().run()
            self.assertIn('Buang '+customer['name']+'?',app.text[0].value)
            self.assertIn(MALAY['Confirm Remove'],[button.label for button in app.button])
            self.assertIn(MALAY['Cancel'],[button.label for button in app.button])
            self.assertIn(MALAY['Customers with orders or other linked records will be archived to preserve their history; only customers with no linked records are permanently deleted.'],app.caption[0].value)

if __name__=='__main__':unittest.main()
