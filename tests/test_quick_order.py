# Quick entry regressions: synthetic disposable SQLite only.
import ast
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import quick_order
ACTIVE_DB=None

class QuickOrderTests(unittest.TestCase):
 def setUp(self):
  global ACTIVE_DB
  self.temp=tempfile.TemporaryDirectory(prefix='BizMar-quick-order-')
  path=Path(self.temp.name)/'sqlite_db.py';shutil.copy2(ROOT/'sqlite_db.py',path)
  spec=importlib.util.spec_from_file_location('synthetic_quick_db',path)
  self.db=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.db)
  from uat_fixture import seed_products
  seed_products(self.db)
  ACTIVE_DB=self.db
  self.old_db=quick_order.sqlite_db;quick_order.sqlite_db=self.db
  self.product=self.db.all_rows('products')[0]
  self.db.edit('products',self.product['id'],{'price':20.,'unit_cost':5.})
  self.customer=self.db.add('customers',{'name':'Synthetic Existing','phone':'0123456789','address':'Saved address'})
 def tearDown(self):
  quick_order.sqlite_db=self.old_db;self.temp.cleanup()
 def app(self,with_navigation=False):
  source=(ROOT/'app.py').read_text(encoding='utf-8-sig')
  functions='\n\n'.join(ast.get_source_segment(source,n) for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in ('load','money','render_payment_tracking'))
  code='''import sys,html
import pandas as pd
import streamlit as st
import quick_order
from order_management import render_new_order
sqlite_db=sys.modules['test_quick_order'].ACTIVE_DB
quick_order.sqlite_db=sqlite_db
def fetch():
 return {table:sqlite_db.all_rows(table) for table in ('products','customers','orders','order_items','payments')}
def add(table,payload):return sqlite_db.add(table,payload)
def refresh():st.rerun()
'''+functions+'''
d,products,customers,orders,items,payments=load()
render_new_order(payment_renderer=render_payment_tracking)
'''
  if with_navigation:
   code=code.replace('render_new_order(payment_renderer=render_payment_tracking)',"from navigation import render_primary_navigation\nst.session_state.setdefault('nour_current_page','New Order')\nrender_primary_navigation()\nif st.session_state['nour_current_page']=='Order Management':\n render_new_order(payment_renderer=render_payment_tracking)")
  app=AppTest.from_string(code).run(timeout=30);self.assertFalse(app.exception);return app
 def key(self,app,field):return 'om_add_'+app.session_state['qo_token']+'_'+field
 def stage(self,app,value):
  app.radio(key='qo_stage_widget').set_value(value).run();self.assertFalse(app.exception)
 def select_existing(self,app):app.selectbox(key=self.key(app,'customer_id')).set_value(self.customer['id']).run()
 def save(self,app):
  self.stage(app,'Review & Save');button=app.button(key=self.key(app,'save'));self.assertFalse(button.disabled)
  button.click().run();self.assertFalse(app.exception);return self.db.all_rows('orders')[-1]
 def test_existing_customer_reuse(self):
  app=self.app();self.select_existing(app);before=self.db.all_rows('customers');order=self.save(app)
  self.assertEqual(order['customer_id'],self.customer['id']);self.assertEqual(self.db.all_rows('customers'),before)
 def test_new_customer_only_created_at_save(self):
  app=self.app();app.text_input(key=self.key(app,'customer_name')).set_value('Synthetic New');app.text_input(key=self.key(app,'phone')).set_value('0133456789').run()
  self.assertEqual(len(self.db.all_rows('customers')),1);self.save(app);self.assertEqual(len(self.db.all_rows('customers')),2)
 def test_duplicate_phone_requires_selection(self):
  app=self.app();app.text_input(key=self.key(app,'customer_name')).set_value('Do not overwrite');app.text_input(key=self.key(app,'phone')).set_value('0123456789').run();self.stage(app,'Review & Save')
  self.assertTrue(app.button(key=self.key(app,'save')).disabled);self.assertEqual(self.db.all_rows('customers')[0]['name'],'Synthetic Existing')
 def test_missing_customer_blocks_save(self):
  app=self.app();self.stage(app,'Review & Save');self.assertTrue(app.button(key=self.key(app,'save')).disabled)
 def test_continue_validates_customer(self):
  app=self.app();app.button(key=self.key(app,'next')).click().run();self.assertEqual(app.session_state['qo_stage'],'Customer');self.assertTrue(app.error)
 def test_quantities_prices_and_snapshots(self):
  app=self.app();self.select_existing(app);self.stage(app,'Products');app.number_input(key=self.key(app,'quantity_0')).set_value(3);app.number_input(key=self.key(app,'price_0')).set_value(22.).run();order=self.save(app)
  line=self.db.order_details(order['id'])['items'][0];self.assertEqual((line['quantity'],line['unit_price'],line['subtotal'],line['unit_cost']),(3,22,66,5))
 def test_product_selection_uses_price_callback(self):
  other=self.db.all_rows('products')[1];self.db.edit('products',other['id'],{'price':12.,'unit_cost':3.})
  app=self.app();self.select_existing(app);self.stage(app,'Products');app.selectbox(key=self.key(app,'product_0')).set_value(other['id']).run();self.assertEqual(app.number_input(key=self.key(app,'price_0')).value,12)
  order=self.save(app);self.assertEqual(self.db.order_details(order['id'])['items'][0]['unit_cost'],3)
 def test_zero_price_invalid(self):
  app=self.app();self.select_existing(app);self.stage(app,'Products');app.number_input(key=self.key(app,'price_0')).set_value(0.).run();self.stage(app,'Review & Save');self.assertTrue(app.button(key=self.key(app,'save')).disabled)
 def test_fulfilment_validation_and_saved_dates(self):
  app=self.app();self.select_existing(app);self.stage(app,'Fulfilment');today=datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date()
  app.date_input(key=self.key(app,'fulfilment_date')).set_value(today-timedelta(days=1)).run();self.stage(app,'Review & Save');self.assertTrue(app.button(key=self.key(app,'save')).disabled)
  self.stage(app,'Fulfilment');due=today+timedelta(days=5);app.date_input(key=self.key(app,'fulfilment_date')).set_value(due).run();order=self.save(app)
  self.assertEqual((order['due_date'],order['fulfilment_date']),(due.isoformat(),due.isoformat()));self.assertTrue(order['ordered_at'].endswith('+08:00'))
 def test_review_and_rerun_retain_draft(self):
  app=self.app();self.select_existing(app);self.stage(app,'Products');app.number_input(key=self.key(app,'quantity_0')).set_value(4).run();self.stage(app,'Fulfilment');self.stage(app,'Products')
  self.assertEqual(app.number_input(key=self.key(app,'quantity_0')).value,4);self.stage(app,'Review & Save');app.run();self.assertEqual(app.dataframe[0].value['Quantity'].tolist(),[4])
 def test_add_remove_products(self):
  app=self.app();self.select_existing(app);self.stage(app,'Products');app.button(key=self.key(app,'add_line')).click().run();self.assertEqual(len(app.selectbox),2)
  app.button(key=self.key(app,'remove_line')).click().run();self.assertEqual(len(app.selectbox),1);self.assertFalse(app.exception)
 def test_duplicate_token_replays_saved_order(self):
  state={};today=datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date().isoformat();values=dict(ordered_at=today,due_date=today,fulfilment_date=today);customer=dict(name='Synthetic Existing',phone='0123456789',address='Saved address');lines=[dict(product_id=self.product['id'],quantity=1,unit_price=20,unit_cost=5)]
  first=quick_order.save_order_once(state,'same-token',customer,values,lines);second=quick_order.save_order_once(state,'same-token',customer,values,lines)
  self.assertEqual(first['id'],second['id']);self.assertEqual(len(self.db.all_rows('orders')),1)
 def test_inflight_save_blocked(self):
  with self.assertRaises(ValueError):quick_order.save_order_once({'qo_saving':True},'token',{}, {}, [])
 def test_failed_save_releases_guard(self):
  state={}
  with patch.object(self.db,'create_order',side_effect=ValueError('Synthetic')):
   with self.assertRaises(ValueError):quick_order.save_order_once(state,'token',{}, {}, [])
  self.assertFalse(state['qo_saving']);self.assertNotIn('token',state['qo_saved_results'])
 def test_saved_screen_prevents_repeat_save(self):
  app=self.app();self.select_existing(app);self.save(app);app.run();self.assertFalse(any(b.label=='Save Order' for b in app.button));self.assertEqual(len(self.db.all_rows('orders')),1);self.assertEqual(self.db.all_rows('payments'),[])
 def test_inline_partial_payment_balance_and_replay_guard(self):
  app=self.app();self.select_existing(app);order=self.save(app);app.button(key='qo_record_payment').click().run();self.assertFalse(app.exception);self.assertEqual(len(app.selectbox[0].options),1)
  app.number_input[0].set_value(7.);next(b for b in app.button if b.label=='Record payment').click().run();self.assertFalse(app.exception)
  details=self.db.order_details(order['id']);self.assertEqual(details['order']['payment_status'],'Partial');self.assertEqual(sum(p['amount'] for p in details['payments']),7);self.assertEqual(details['order']['total_amount']-7,13)
  self.assertTrue(next(b for b in app.button if b.label=='Record payment').disabled);app.run();self.assertEqual(len(self.db.all_rows('payments')),1)
 def test_inline_overpayment_blocked(self):
  app=self.app();self.select_existing(app);self.save(app);app.button(key='qo_record_payment').click().run();app.number_input[0].set_value(21.);next(b for b in app.button if b.label=='Record payment').click().run()
  self.assertFalse(app.exception);self.assertTrue(app.error);self.assertEqual(self.db.all_rows('payments'),[])
 def test_existing_order_and_saved_cost_unchanged(self):
  app=self.app();self.select_existing(app);first=self.save(app);before=self.db.order_details(first['id']);self.db.edit('products',self.product['id'],{'unit_cost':9.})
  app.button(key='qo_start_new').click().run();self.select_existing(app);self.save(app);self.assertEqual(self.db.order_details(first['id']),before);self.assertEqual(len(self.db.all_rows('orders')),2)
 def test_cancel_starts_clean_draft_without_writes(self):
  app=self.app();old=app.session_state['qo_token'];app.text_input(key=self.key(app,'customer_name')).set_value('Discard').run();app.button(key='qo_cancel').click().run()
  self.assertNotEqual(app.session_state['qo_token'],old);self.assertEqual(app.text_input(key=self.key(app,'customer_name')).value,'');self.assertEqual(self.db.all_rows('orders'),[])

 def test_no_active_products_has_actionable_empty_state(self):
  for product in self.db.all_rows('products'):self.db.edit('products',product['id'],{'active':0})
  app=self.app();self.select_existing(app);self.stage(app,'Products');self.assertTrue(app.warning)
  self.stage(app,'Review & Save');self.assertTrue(app.button(key=self.key(app,'save')).disabled)
 def test_normalized_phone_matching_unchanged(self):
  result=quick_order.matching_customer(self.db.all_rows('customers'),'+60123456789')
  self.assertEqual(result['id'],self.customer['id'])
 def test_full_payment_sets_paid_from_ledger(self):
  app=self.app();self.select_existing(app);order=self.save(app);app.button(key='qo_record_payment').click().run()
  app.number_input[0].set_value(20.);next(b for b in app.button if b.label=='Record payment').click().run()
  self.assertFalse(app.exception);self.assertEqual(self.db.order_details(order['id'])['order']['payment_status'],'Paid')
 def test_explicit_second_partial_payment_is_allowed(self):
  app=self.app();self.select_existing(app);order=self.save(app);app.button(key='qo_record_payment').click().run()
  app.number_input[0].set_value(7.);next(b for b in app.button if b.label=='Record payment').click().run()
  app.button(key='quick_another_payment').click().run();app.number_input[0].set_value(13.)
  next(b for b in app.button if b.label=='Record payment').click().run()
  self.assertFalse(app.exception);details=self.db.order_details(order['id']);self.assertEqual(len(details['payments']),2);self.assertEqual(details['order']['payment_status'],'Paid')
 def test_draft_survives_primary_navigation(self):
  app=self.app(with_navigation=True)
  app.text_input(key=self.key(app,'customer_name')).set_value('Retained across pages').run()
  app.button(key='nour_nav_PRIMARY_3').click().run();app.button(key='nour_nav_PRIMARY_1').click().run()
  self.assertFalse(app.exception);self.assertEqual(app.text_input(key=self.key(app,'customer_name')).value,'Retained across pages')

if __name__=='__main__':unittest.main()
