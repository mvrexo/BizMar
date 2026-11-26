# UAT readiness regressions; known limitations are documented, not silently fixed.
import ast
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import quick_order
from production_alerts import load_settings

class UATDuplicateRiskTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='BizMar-UAT-duplicate-')
  path=Path(self.temp.name)/'sqlite_db.py';shutil.copy2(ROOT/'sqlite_db.py',path)
  spec=importlib.util.spec_from_file_location('synthetic_uat_db',path)
  self.db=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.db)
  from uat_fixture import seed_products
  seed_products(self.db)
  self.original=quick_order.sqlite_db;quick_order.sqlite_db=self.db
  self.customer=dict(name='Synthetic UAT',phone='0123456789')
  self.values=dict(ordered_at='2026-10-20T00:00:00+08:00',due_date='2026-10-23',fulfilment_date='2026-10-23')
  self.lines=[dict(product_id=self.db.all_rows('products')[0]['id'],quantity=1,unit_price=20.,unit_cost=5.)]
 def tearDown(self):
  quick_order.sqlite_db=self.original;self.temp.cleanup()
 def save(self,state,token):return quick_order.save_order_once(state,token,self.customer,self.values,self.lines)
 def test_same_session_same_token_is_protected(self):
  state={};self.save(state,'key');self.save(state,'key');self.assertEqual(len(self.db.all_rows('orders')),1)
 def test_documents_fresh_session_does_not_deduplicate_same_token(self):
  self.save({},'key');self.save({},'key');self.assertEqual(len(self.db.all_rows('orders')),2)
 def test_documents_new_token_allows_same_payload(self):
  state={};self.save(state,'first');self.save(state,'second');self.assertEqual(len(self.db.all_rows('orders')),2)
 def test_documents_commit_to_session_record_failure_window(self):
  class FailedReceipt(dict):
   def __setitem__(self,key,value):raise RuntimeError('Synthetic post-commit state failure')
  with self.assertRaises(RuntimeError):self.save({'qo_saved_results':FailedReceipt()},'key')
  self.assertEqual(len(self.db.all_rows('orders')),1)
  self.save({},'key');self.assertEqual(len(self.db.all_rows('orders')),2)

class UATIsolationTests(unittest.TestCase):
 def test_guard_blocks_production_simulations_without_sqlite_import(self):
  launcher=Path(os.environ.get('BIZMAR_UAT_GUARD_SOURCE',ROOT.parent/'launch_dev.py'))
  with tempfile.TemporaryDirectory(prefix='BizMar-UAT-guard-') as temp:
   base=Path(temp);app=base/'application';app.mkdir()
   original=base/'fake-production.sqlite3';original.write_bytes(b'Synthetic production sentinel')
   (app/'uat').mkdir();database=app/'uat'/'synthetic.sqlite3';database.write_bytes(b'Synthetic development sentinel')
   shutil.copy2(launcher,base/'launch_dev.py')
   (base/'isolation.json').write_text(json.dumps(dict(workspace=str(app),production_database=str(original),database=str(database),development_localappdata=str(base/'settings'))))
   code='''import os,runpy,sys
from pathlib import Path
namespace=runpy.run_path(sys.argv[1],run_name='guard_test')
config,hook=namespace['configure_isolation']()
assert 'sqlite_db' not in sys.modules and 'app' not in sys.modules
original=config['production_database']
for event,args in [('sqlite3.connect',(original,)),('open',(original,'wb',os.O_WRONLY)),('os.remove',(original,-1))]:
 try:sys.audit(event,*args)
 except RuntimeError:pass
 else:raise AssertionError('Guard failed')
assert os.environ['LOCALAPPDATA']==config['development_localappdata']
assert not Path(config['development_localappdata']).exists()
'''
   result=subprocess.run([sys.executable,'-I','-B','-c',code,str(base/'launch_dev.py')],cwd=base,capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertEqual(original.read_bytes(),b'Synthetic production sentinel')
 def test_invalid_settings_default_without_creating_directories(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'missing'/'settings.json';settings,warning=load_settings(path)
   self.assertEqual(settings['aging_hours'],48);self.assertIsNone(warning);self.assertFalse(path.parent.exists())

class UATStaticTests(unittest.TestCase):
 def test_all_python_sources_parse_without_application_import(self):
  for path in ROOT.glob('*.py'):compile(path.read_text(encoding='utf-8-sig'),str(path),'exec')
 def test_authentication_gates_still_present(self):
  text=(ROOT/'app.py').read_text(encoding='utf-8-sig')
  self.assertIn('authorized = bool(st.session_state.get("local_owner_email"))',text)
  self.assertIn('else (google_authorized or supabase_authorized)',text)
  self.assertIn('supabase_authorized = False if LOCAL_AUTH else is_authorized_supabase_user()',text)
  self.assertLess(text.index('if not authorized:'),text.index('render_primary_navigation()'))
  self.assertIn('is_authorized_google_user(st.user, st.secrets["OWNER_EMAIL"])',text)
  self.assertIn('is_authorized_supabase_user()',text)
  self.assertNotIn("st.secrets.get('ADMIN_PASSWORD')",text)

if __name__=='__main__':unittest.main()
