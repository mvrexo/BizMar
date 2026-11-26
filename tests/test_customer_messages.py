"""Synthetic-only message lifecycle, ledger safety and communication UI tests."""
from contextlib import closing
from datetime import datetime,timedelta
from uuid import uuid4
import unittest
from unittest.mock import patch
from urllib.parse import urlparse,parse_qs
from streamlit.testing.v1 import AppTest
import test_google_sheets_sync as fixtures
import orders_store
import sqlite_db
import customer_messages_store as store
from customer_message_templates import DEFAULTS,render,normalize_phone,whatsapp_url


class CustomerMessagesTests(unittest.TestCase):
    headers=fixtures.GoogleSheetsSyncTests.headers
    make_snapshot=fixtures.GoogleSheetsSyncTests.make_snapshot
    row=fixtures.GoogleSheetsSyncTests.row
    prepare=fixtures.GoogleSheetsSyncTests.prepare

    def setUp(self):
        fixtures.GoogleSheetsSyncTests.setUp(self)
        prepared=self.prepare(self.make_snapshot([self.row()]))
        result=orders_store.activate_google_sheets_preview(self.config.spreadsheet_id,prepared.sheet_id,prepared.preview.records)
        self.order_id=result['order_ids'][0]
        self.customer_id=orders_store.details(self.order_id)['order']['customer_id']

    tearDown=fixtures.GoogleSheetsSyncTests.tearDown

    def draft(self,template='Order Received',content=None,token=None):
        return store.save_draft(self.customer_id,self.order_id,template,content or store.template_message(self.customer_id,self.order_id,template),token=token or uuid4().hex)

    def test_customers_orders_search_and_google_import_visibility_are_live(self):
        self.assertEqual(len(store.inbox()),1)
        self.assertEqual(store.messages(),[])
        reference=orders_store.details(self.order_id)['order']['order_code']
        self.assertEqual(store.inbox(reference)[0]['id'],self.customer_id)
        self.assertEqual(store.inbox('012345')[0]['id'],self.customer_id)
        self.assertEqual(store.inbox('Synthetic Customer')[0]['latest_order']['id'],self.order_id)
        self.assertEqual(store.customer_orders(self.customer_id)[0]['id'],self.order_id)
        self.assertEqual(len(store.inbox()),1)  # No duplicate conversation records.
        self.assertEqual(store.inbox('012 345')[0]['id'],self.customer_id)

    def test_new_google_order_customer_selection_and_existing_draft_context(self):
        second=self.row('Synthetic Second');second[1]='0199999999';second[2]='2026-10-27 11:00:00'
        prepared=self.prepare(self.make_snapshot([self.row(),second]))
        result=orders_store.import_google_sheets_orders(self.config.spreadsheet_id,prepared.sheet_id,prepared.preview.records)
        second_customer=orders_store.details(result['order_ids'][0])['order']['customer_id']
        self.assertEqual(len(store.inbox()),2)
        script='from customer_messages_ui import render_messages\nrender_messages(lambda page:None)'
        app=AppTest.from_string(script).run()
        app.button(key='messages_save_draft').click().run()
        app.selectbox(key='messages_customer_picker').set_value(second_customer).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['messages_customer_id'],second_customer)
        app.button(key=f'messages_select_{self.customer_id}').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['messages_customer_id'],self.customer_id)
        app.segmented_control(key='messages_filter').set_value('Drafts').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(store.messages()),1)

    def test_dynamic_templates_missing_fields_and_unsafe_placeholder_rejection(self):
        body=store.template_message(self.customer_id,self.order_id,'Order Confirmation')
        self.assertIn('Synthetic Customer',body);self.assertIn('RM 110.00',body)
        missing=store.template_message(self.customer_id,None,'Order Received')
        self.assertIn('Not provided',missing)
        for bad in ('{customer_name.__class__}','{unknown}','{customer_name!r}','{order_total:bad}'):
            with self.assertRaises(ValueError):render(bad,{})
        store.save_template('Custom Message','Hello {customer_name}: {order_id}')
        self.assertIn('Hello Synthetic Customer',store.template_message(self.customer_id,self.order_id,'Custom Message'))

    def test_phone_normalization_and_encoded_whatsapp_url(self):
        for phone in ('012-345 6789','+60 12 345 6789','60123456789','0060123456789','123456789'):
            self.assertEqual(normalize_phone(phone),'60123456789')
        for phone in ('','abc','+6512345678','000','123'):
            with self.assertRaises(ValueError):normalize_phone(phone)
        body='Hi & hello?\n<script>alert(1)</script> 😊'
        url=whatsapp_url('0123456789',body)
        self.assertEqual(urlparse(url).hostname,'wa.me')
        self.assertEqual(parse_qs(urlparse(url).query)['text'],[body])
        self.assertNotIn('<script>',url)

    def test_payment_received_requires_verified_ledger_even_if_order_claims_paid(self):
        with sqlite_db.transaction() as connection:
            connection.execute("UPDATE orders SET payment_status='Paid',submitted_amount_paid=110 WHERE id=?",(self.order_id,))
        with self.assertRaises(ValueError):store.template_message(self.customer_id,self.order_id,'Payment Received')
        with self.assertRaises(ValueError):self.draft('Payment Received','Payment received')
        orders_store.record_payment(self.order_id,dict(amount=10,method='Cash'),token=uuid4().hex)
        text=store.template_message(self.customer_id,self.order_id,'Payment Received')
        self.assertIn('Partial',text)
        message=self.draft('Payment Received')
        with sqlite_db.transaction() as connection:connection.execute('DELETE FROM payments WHERE order_id=?',(self.order_id,))
        with self.assertRaises(ValueError):store.launch_url(message['id'])

    def test_draft_idempotence_editing_and_stale_version_protection(self):
        token=uuid4().hex;first=self.draft(token=token);again=self.draft(token=token)
        self.assertEqual(first['id'],again['id']);self.assertEqual(len(store.messages()),1)
        self.assertEqual(len(store.activity_history(self.customer_id)),1)
        with self.assertRaises(ValueError):self.draft(content='Different',token=token)
        updated=store.save_draft(self.customer_id,self.order_id,'Custom Message','Edited',token=uuid4().hex,message_id=first['id'],version=first['version'])
        self.assertEqual(updated['content'],'Edited')
        with self.assertRaises(ValueError):store.save_draft(self.customer_id,self.order_id,'Custom Message','Lost edit',token=uuid4().hex,message_id=first['id'],version=first['version'])

    def test_opened_is_not_sent_manual_sent_and_replay_safety(self):
        before={t:sqlite_db.all_rows(t) for t in ('orders','customers','products','order_items','payments')}
        message=self.draft();event=uuid4().hex
        opened=store.record_opened(message['id'],event,message['version'])
        self.assertEqual(opened['status'],'WhatsApp Opened');self.assertIsNone(opened['sent_at'])
        replay=store.record_opened(message['id'],event,message['version'])
        self.assertEqual(replay['version'],opened['version'])
        with self.assertRaises(ValueError):store.mark_sent(message['id'])
        sent=store.mark_sent(message['id'],confirmed=True)
        self.assertEqual(sent['status'],'Sent');self.assertIsNotNone(sent['sent_at'])
        store.mark_sent(message['id'],confirmed=True)
        self.assertEqual(len(store.activity_history(self.customer_id)),3)
        self.assertEqual({t:sqlite_db.all_rows(t) for t in before},before)

    def test_wrong_order_context_invalid_phone_and_sent_draft_edit_denied(self):
        with self.assertRaises(ValueError):store.save_draft(self.customer_id,999999,'Order Received','Hi',token=uuid4().hex)
        message=self.draft()
        with sqlite_db.transaction() as connection:connection.execute("UPDATE customers SET phone='invalid',phone_number='invalid' WHERE id=?",(self.customer_id,))
        with self.assertRaises(ValueError):store.launch_url(message['id'])
        with self.assertRaises(ValueError):store.record_opened(message['id'],uuid4().hex,message['version'])

    def test_followup_schedule_reschedule_completion_and_myt_counts(self):
        message=self.draft();current=datetime.now(store.MYT)
        store.schedule_followup(message['id'],current-timedelta(hours=2),'Call back')
        self.assertEqual(store.reminder_counts(current)['overdue'],1)
        self.assertEqual(store.followups('Overdue',current)[0]['id'],message['id'])
        self.assertEqual(len(store.inbox(filter_name='Follow-up Needed')),1)
        store.schedule_followup(message['id'],current+timedelta(hours=1),'New time')
        self.assertEqual(store.reminder_counts(current)['overdue'],0)
        self.assertEqual(store.get_message(message['id'])['notes'],'New time')
        store.complete_followup(message['id']);store.complete_followup(message['id'])
        self.assertEqual(store.reminder_counts(current)['upcoming'],0)
        self.assertEqual(store.followups('Completed',current)[0]['id'],message['id'])
        self.assertEqual(len(store.inbox(filter_name='Completed')),1)
        with closing(sqlite_db._connect()) as con:
            self.assertIsNotNone(con.execute('SELECT followup_completed_at FROM customer_messages WHERE id=?',(message['id'],)).fetchone()[0])

    def test_owner_only_reads_writes_templates_and_followups(self):
        with patch.object(orders_store,'current_owner',side_effect=PermissionError('Expired')):
            for call in (store.inbox,store.messages,store.templates,store.followups,lambda:self.draft(),lambda:store.save_template('Custom Message','Hi')):
                with self.assertRaises(PermissionError):call()
            app=AppTest.from_string('from customer_messages_ui import render_messages\nrender_messages(lambda page:None)').run()
            self.assertFalse(app.exception);self.assertTrue(app.error)

    def test_messages_ui_save_edit_open_mark_sent_and_navigation(self):
        import whatsapp_launch
        script="""import streamlit as st
from customer_messages_ui import render_messages
def navigate(page):st.session_state['target']=page
render_messages(navigate)
"""
        with patch.object(whatsapp_launch,'launch_button',return_value=None) as launch:
            app=AppTest.from_string(script).run()
            self.assertFalse(app.exception)
            app.button(key='messages_save_draft').click().run()
            self.assertFalse(app.exception)
            message=store.messages()[0]
            launch.return_value=dict(action='opened',event_id=uuid4().hex,message_id=message['id'],version=message['version'])
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(store.get_message(message['id'])['status'],'WhatsApp Opened')
            app.checkbox(key=f'messages_sent_confirm_{message["id"]}').check().run()
            app.button(key=f'messages_mark_sent_{message["id"]}').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(store.get_message(message['id'])['status'],'Sent')
            app.button(key='messages_view_order').click().run()
            self.assertFalse(app.exception);self.assertEqual(app.session_state['target'],'Order Management')


if __name__=='__main__':unittest.main()
