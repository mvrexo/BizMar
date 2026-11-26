from io import BytesIO
import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest
import sqlite_db
import orders_store
from unittest.mock import patch


class OrderManagementUITests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_path = sqlite_db.DB_PATH
        sqlite_db.DB_PATH = Path(self.temp_dir.name) / 'ui_test.sqlite3'
        sqlite_db.initialize()
        from uat_fixture import seed_products
        seed_products(sqlite_db)

    def tearDown(self):
        sqlite_db.DB_PATH = self.original_path
        self.temp_dir.cleanup()

    def test_orders_page_renders_and_add_button_opens_form(self):
        fixture = Path(__file__).with_name('order_management_fixture.py')
        app = AppTest.from_file(str(fixture)).run()
        self.assertFalse(app.exception)
        self.assertTrue(any(caption.value == 'Manage and monitor customer orders.' for caption in app.caption))
        self.assertTrue(any(button.key == 'om_import_orders' for button in app.button))

        app.button(key='om_add_new').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any(subheader.value == 'Add New Order' for subheader in app.subheader))
        form_scope = f"om_add_{app.session_state['om_form_token']}"
        app.text_input(key=f'{form_scope}_customer_name').set_value('UI Test Customer')
        app.text_input(key=f'{form_scope}_phone').set_value('0181234567')
        app.number_input(key=f'{form_scope}_price_0').set_value(12.5)
        app.button(key=f'{form_scope}_save').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(sqlite_db.list_orders()[0]['customer_name'], 'UI Test Customer')
        self.assertEqual(sqlite_db.list_orders()[0]['total_amount'], 12.5)

    def test_import_orders_dialog_uploads_and_commits_a_mapped_response(self):
        fixture = Path(__file__).with_name('order_management_fixture.py')
        app = AppTest.from_file(str(fixture)).run()
        self.assertFalse(app.exception)
        app.button(key='om_import_orders').click().run()
        self.assertFalse(app.exception)
        product = sqlite_db.all_rows('products')[0]
        csv = (
            'Response ID,Timestamp,Name,Phone,Pickup Date,Fulfilment Method,Delivery Address,'
            f'{product["name"]}\n'
            'ui-response-001,2026-10-27 10:00:00,UI Import Customer,0181234567,'
            '2026-10-29,Pickup,,2\n'
        ).encode('utf-8')
        dialog = app.get('dialog')[0]
        dialog.file_uploader[0].upload('responses.csv', csv, 'text/csv').run()
        self.assertFalse(app.exception)
        next(checkbox for checkbox in app.checkbox
             if checkbox.label.startswith('I reviewed the mapped columns')).check().run()
        dialog = app.get('dialog')[0]
        dialog.button(key='google_forms_import_commit').click().run()
        self.assertFalse(app.exception)
        imported = sqlite_db.all_rows('orders')
        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0]['customer_name_snapshot'], 'UI Import Customer')
        self.assertEqual(imported[0]['import_source'], 'Google Forms')
        self.assertEqual(imported[0]['total_amount'], float(product['price']) * 2)

    def test_editing_and_confirming_rider_fee_enables_payment(self):
        fixture = Path(__file__).with_name('order_management_fixture.py')
        product = sqlite_db.all_rows('products')[0]
        sqlite_db.edit('products', product['id'], {'price': 40., 'unit_cost': 12.})
        with patch.object(orders_store, 'current_owner', return_value='synthetic-owner@example.test'):
            created = orders_store.save_order(
                {'name': 'Synthetic Quote Customer', 'phone': '0181234567', 'address': 'Synthetic address'},
                {
                    'ordered_at': '2026-10-27',
                    'fulfilment_date': '2026-10-30',
                    'fulfilment_method': 'Delivery',
                    'delivery_address': 'Synthetic delivery location',
                    'source': 'Other',
                    'import_source': 'Google Forms',
                    'import_response_key': 'google-forms:test:ui-rider-quote',
                },
                [{'product_id': product['id'], 'quantity': 1, 'unit_price': 40}],
                token='ui-rider-quote-create-001',
            )

        app = AppTest.from_file(str(fixture)).run()
        identity = created['id']
        with patch.object(orders_store, 'current_owner', return_value='synthetic-owner@example.test'):
            self.assertTrue(orders_store.details(identity)['order']['quote_pending'])
        self.assertFalse(any(button.key == f'om_record_payment_{identity}' for button in app.button))
        app.button(key=f'om_customer_details_row_{identity}').click().run()
        app.button(key=f'om_edit_{identity}').click().run()
        scope = f'om_edit_{identity}_' + app.session_state['om_form_token']
        app.number_input(key=f'{scope}_delivery_fee').set_value(63.).run()
        self.assertTrue(any(
            checkbox.label == 'I confirm this delivery fee was quoted by the rider.'
            for checkbox in app.checkbox
        ))
        app.checkbox(key=f'{scope}_confirm_rider_quote').check().run()
        app.button(key=f'{scope}_save').click().run()
        self.assertFalse(app.exception)

        with patch.object(orders_store, 'current_owner', return_value='synthetic-owner@example.test'):
            order = orders_store.details(identity)['order']
        self.assertFalse(order['quote_pending'])
        self.assertEqual(order['delivery_fee'], 63)
        self.assertEqual(order['total_amount'], 103)
        app.button(key=f'om_customer_details_row_{identity}').click().run()
        app.button(key=f'om_record_payment_{identity}').click().run()
        app.number_input(key=f'om_payment_amount_{identity}').set_value(63.)
        next(button for button in app.button if button.label == 'Save Payment').click().run()
        self.assertFalse(app.exception)
        with patch.object(orders_store, 'current_owner', return_value='synthetic-owner@example.test'):
            self.assertEqual(orders_store.details(identity)['order']['amount_paid'], 63)


if __name__ == '__main__':
    unittest.main()
