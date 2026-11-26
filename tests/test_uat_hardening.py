import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
import uat_hardening as h
from uat_fixture import build
ROOT=Path(__file__).resolve().parents[1]
class HardeningTests(unittest.TestCase):
 def test_endpoint_policy(self):
  policy={'dedicated_test_project_ref':'t'*20,'production_project_refs':['p'*20]}
  h.validate_endpoint('https://'+'t'*20+'.supabase.co',policy)
  for ref in ('p','x'):
   with self.assertRaises(h.UATBlocked):h.validate_endpoint('https://'+ref*20+'.supabase.co',policy)
  policy['dedicated_test_project_ref']='p'*20
  with self.assertRaises(h.UATBlocked):h.validate_endpoint('https://'+'p'*20+'.supabase.co',policy)
 def test_invalid_policy(self):
  for policy in ({},{'dedicated_test_project_ref':'t'*20,'production_project_refs':[]}):
   with self.assertRaises(h.UATBlocked):h.validate_endpoint('https://'+'t'*20+'.supabase.co',policy)
 def test_media(self):
  for value in ('https://production.invalid/image','//server/image','data:image/png;base64,AAA',r'C:\outside.png',None):
   self.assertTrue(h.local_image(value).endswith('uat-placeholder.svg'))
   st=Mock();h.image(st,value);self.assertEqual(st.image.call_args.args[0],h.local_image(value))
 def test_local_asset(self):
  value=ROOT/'assets'/'uat-placeholder.svg'
  self.assertEqual(h.local_image(value),str(value))
 def test_block_before_any_function_body(self):
  targets={'owner_profile.py':['_client','save_profile','upload_avatar','remove_avatar'],
   'receipt_storage.py':['_config','upload_payment_receipt','signed_receipt_url'],
   'db.py':['request'],'auth.py':['create_owner_account'],'sqlite_db.py':['import_supabase_records']}
  for filename,names in targets.items():
   tree=ast.parse((ROOT/filename).read_text(encoding='utf-8'))
   for node in tree.body:
    if isinstance(node,ast.FunctionDef) and node.name in names:
     # Execute only the guard statements: no imports of Streamlit or remote clients.
     guard=ast.Module(body=node.body[:2],type_ignores=[])
     with self.assertRaises(h.UATBlocked):exec(compile(guard,'guard','exec'),{})
 def test_synthetic_fixture_and_ledger(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'fixture.sqlite3';db=build(path)
   self.assertEqual(len(db.all_rows('orders')),6)
   self.assertEqual(len(db.all_rows('payments')),2)
   self.assertTrue(all(c['name'].startswith('Synthetic Customer') for c in db.all_rows('customers')))
   self.assertEqual({o['payment_status'] for o in db.all_rows('orders')},{'Unpaid','Partial','Paid'})
   self.assertTrue(all(not p.get('image_url') for p in db.all_rows('products')))
   with self.assertRaises(h.UATBlocked):db.import_supabase_records()
   with self.assertRaises(FileExistsError):build(path)
 def test_only_synthetic_database_default(self):
  tree=ast.parse((ROOT/'sqlite_db.py').read_text(encoding='utf-8'))
  node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DB_PATH' for t in n.targets))
  self.assertIn('synthetic.sqlite3',ast.unparse(node))
 def test_all_images_guarded(self):
  source=(ROOT/'app.py').read_text(encoding='utf-8')
  self.assertNotIn('st.image(',source)
  self.assertNotIn('@import url(', (ROOT/'ui_theme.py').read_text(encoding='utf-8'))
