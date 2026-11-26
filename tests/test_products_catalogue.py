from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import products_store as store
import products_ui as ui
from uat_fixture import build

SCRIPT = 'from products_ui import render_products\nrender_products()'


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = build(Path(self.temp.name) / 'synthetic.sqlite3')
        self.patches = [patch.object(store, 'sqlite_db', self.db), patch.object(store, 'current_owner', return_value='synthetic-owner@example.test')]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def test_add_edit_archive_reactivate_search_and_views(self):
        app = AppTest.from_string(SCRIPT).run()
        self.assertFalse(app.exception)
        self.assertEqual([title.value for title in app.title], ['Product'])
        self.assertFalse(any('Your bakes, beautifully organised.' in caption.value for caption in app.caption))
        self.assertEqual([m.label for m in app.metric], ['Total Products','Active Products','Categories'])
        app.button(key='catalogue_add').click().run()
        self.assertFalse(app.exception)
        app.text_input(key='catalogue_editor_name').set_value('Synthetic Brownie Box')
        app.number_input(key='catalogue_editor_price').set_value(30.)
        app.number_input(key='catalogue_editor_cost').set_value(12.)
        app.number_input(key='catalogue_editor_quantity').set_value(6.)
        app.selectbox(key='catalogue_editor_packaging').set_value('Box')
        app.number_input(key='catalogue_editor_weight').set_value(240.)
        app.button(key='catalogue_editor_save').click().run()
        self.assertFalse(app.exception)
        row = next(p for p in store.list_products() if p['name'] == 'Synthetic Brownie Box')
        self.assertEqual((row['quantity_per_unit'], row['packaging_type'], row['weight_grams']), (6.,'Box',240.))
        self.assertIsNone(row['image_url'])
        app.text_input(key='catalogue_search').set_value('brownie').run()
        self.assertEqual(len([b for b in app.button if b.label == 'Details']), 1)
        # Segmented control is represented as a button group by AppTest.
        app.session_state['catalogue_view'] = 'List'
        app.run()
        self.assertFalse(app.exception)
        app.button(key=f'catalogue_edit_{row["id"]}').click().run()
        app.number_input(key='catalogue_editor_price').set_value(35.)
        app.button(key='catalogue_editor_save').click().run()
        self.assertEqual(store.get_product(row['id'])['price'],35.)
        app.button(key=f'catalogue_details_{row["id"]}').click().run()
        app.button(key='catalogue_status_confirm').click().run()
        self.assertFalse(store.get_product(row['id'])['active'])
        app.button(key=f'catalogue_details_{row["id"]}').click().run()
        app.button(key='catalogue_status_confirm').click().run()
        self.assertTrue(store.get_product(row['id'])['active'])
        self.assertEqual(len(self.db.all_rows('orders')),6)
        app.text_input(key='catalogue_search').set_value('no matching synthetic item').run()
        self.assertTrue(any('No matching products' in m.value for m in app.info))

    def test_migration_idempotent_and_historical_prices(self):
        before = self.db.all_rows('order_items')
        product = store.list_products()[0]
        store.save_product(dict(name=product['name'], category=product['category'], price=99., unit_cost=20., quantity_per_unit=24., measurement_unit='pieces', packaging_type='Jar', weight_grams=500.), product_id=product['id'])
        store.set_active(product['id'],False)
        store.initialize()
        store.initialize()
        self.assertEqual(self.db.all_rows('order_items'),before)
        self.assertEqual(store.get_product(product['id'])['quantity_per_unit'],24.)
        self.assertEqual(len(store.list_products()),15)

    def test_validation_and_filters(self):
        product = store.list_products()[0]
        payload = {k:product[k] for k in ('name','category','price','unit_cost')}
        for fields in ({'quantity_per_unit':0},{'weight_grams':float('nan')},{'measurement_unit':'bad'},{'packaging_type':'bad'}):
            with self.assertRaises(ValueError): store.save_product(dict(payload,**fields), product_id=product['id'])
        self.assertTrue(ui.filter_products([product], product['name'].swapcase()))
        self.assertEqual(ui.filter_products([product],category='Unknown'),[])
        store.set_active(product['id'],False)
        self.assertEqual(ui.filter_products([store.get_product(product['id'])],availability='Active'),[])

    def test_new_products_in_orders_and_saved_price_snapshots(self):
        import orders_store
        payload = dict(name='Synthetic Order Box', category='Dessert', price=30., unit_cost=12., quantity_per_unit=6., measurement_unit='pieces', packaging_type='Box', weight_grams=None)
        identity = store.save_product(payload)
        with patch.object(orders_store, 'sqlite_db', self.db), patch.object(orders_store, 'current_owner', return_value='synthetic-owner@example.test'):
            order = dict(ordered_at='2026-10-26', fulfilment_date='2026-10-28', fulfilment_method='Pickup', source='Other')
            customer = dict(name='Synthetic New Owner Customer', phone='0123456789')
            lines = [dict(product_id=identity, quantity=2, unit_price=30.)]
            created = orders_store.save_order(customer, order, lines, token='synthetic-product-order-0001')
            before = orders_store.details(created['id'])['items']
            store.save_product(dict(payload,price=40.,unit_cost=15.), product_id=identity)
            store.set_active(identity,False)
            self.assertEqual(orders_store.details(created['id'])['items'],before)
            with self.assertRaises(ValueError):
                orders_store.save_order(customer,order,lines,token='synthetic-product-order-0002')
            store.set_active(identity,True)
            lines[0]['unit_price'] = 40.
            next_order = orders_store.save_order(customer,order,lines,token='synthetic-product-order-0003')
            self.assertEqual(next_order['total_amount'],80.)
            self.assertEqual(orders_store.details(next_order['id'])['items'][0]['unit_cost'],15.)

    def test_editor_cancel_does_not_save_changes(self):
        product = store.list_products()[0]
        app = AppTest.from_string(SCRIPT).run()
        app.button(key=f'catalogue_edit_{product["id"]}').click().run()
        app.text_input(key='catalogue_editor_name').set_value('Unsaved Synthetic Draft')
        app.button(key='catalogue_editor_cancel').click().run()
        self.assertEqual(store.get_product(product['id']),product)
        self.assertFalse(app.exception)
