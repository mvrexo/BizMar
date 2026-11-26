import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
class SyntheticLauncherTests(unittest.TestCase):
 def test_real_connections_wal_transactions_and_blocked_paths(self):
  with tempfile.TemporaryDirectory() as temp:
   base=Path(temp);root=base/'NourSweet';(root/'uat').mkdir(parents=True)
   db=root/'uat/synthetic.sqlite3';db.touch()
   launcher=base/'launch_dev.py';shutil.copy2(ROOT.parent/'launch_dev.py',launcher)
   shutil.copy2(ROOT/'sqlite_db.py',root/'sqlite_db.py')
   shutil.copy2(ROOT/'orders_schema.py',root/'orders_schema.py')
   shutil.copy2(ROOT/'sync_monitor_schema.py',root/'sync_monitor_schema.py')
   shutil.copy2(ROOT/'customer_messages_schema.py',root/'customer_messages_schema.py')
   shutil.copy2(ROOT/'malaysian_states.py',root/'malaysian_states.py')
   shutil.copy2(ROOT/'products_schema.py',root/'products_schema.py')
   shutil.copy2(ROOT/'uat_hardening.py',root/'uat_hardening.py')
   config=dict(workspace=str(root),database=str(db),production_database=str(base/'production.sqlite3'),development_localappdata=str(base/'settings'))
   (base/'isolation.json').write_text(json.dumps(config))
   code="""import runpy,sys,sqlite3
from pathlib import Path
namespace=runpy.run_path(sys.argv[1],run_name='guard_test')
config,hook=namespace['configure_isolation']()
database=Path(config['database']);root=Path(config['workspace'])
for path in (root/'nour_sweets.sqlite3',Path(config['production_database']),root/'other.sqlite3',root/'uat/other.sqlite3',':memory:',database.as_uri()):
 try: sqlite3.connect(path)
 except RuntimeError: pass
 else: raise AssertionError('Unexpected database allowed')
con=sqlite3.connect(database)
assert con.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
con.execute('CREATE TABLE fixture(value INTEGER)');con.execute('INSERT INTO fixture VALUES(1)');con.commit()
assert con.execute('SELECT value FROM fixture').fetchone()[0]==1
try: con.execute("ATTACH DATABASE ':memory:' AS bypass")
except sqlite3.DatabaseError: pass
else: raise AssertionError('ATTACH bypass permitted')
con.execute('PRAGMA wal_checkpoint(TRUNCATE)');con.close()
# Real application data-layer initialization, only in this disposable copy.
import sqlite_db
assert sqlite_db.DB_PATH.resolve()==database
assert sqlite_db.all_rows('products') == []
with sqlite_db.transaction() as c:c.execute("INSERT INTO app_metadata VALUES('guard_test','ok')")
"""
   result=subprocess.run([sys.executable,'-I','-B','-c',code,str(launcher)],cwd=base,capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertFalse((root/'nour_sweets.sqlite3').exists())
   self.assertFalse((base/'production.sqlite3').exists())
 def test_manifest_aliases_and_symlink_escapes_rejected(self):
  validate=runpy.run_path(str(ROOT.parent/'launch_dev.py'),run_name='guard_unit')['validate_database_configuration']
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)/'NourSweet';(root/'uat').mkdir(parents=True);db=root/'uat/synthetic.sqlite3';db.touch()
   config=dict(workspace=str(root),database=str(db),production_database=str(Path(temp)/'production.sqlite3'),development_localappdata=str(Path(temp)/'settings'))
   validate(config)
   for other in (root/'nour_sweets.sqlite3',root/'other.sqlite3',Path(config['production_database'])):
    with self.assertRaises(RuntimeError):validate(dict(config,database=str(other)))
   with patch.object(Path,'is_symlink',return_value=True):
    with self.assertRaises(RuntimeError):validate(config)
   with patch.object(Path,'is_junction',return_value=True):
    with self.assertRaises(RuntimeError):validate(config)
   alias=root/'uat/alias.sqlite3'
   try:os.link(db,alias)
   except OSError:self.fail('Could not establish disposable hardlink test')
   with self.assertRaises(RuntimeError):validate(config)
