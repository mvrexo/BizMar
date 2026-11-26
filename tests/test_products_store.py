from io import BytesIO
from pathlib import Path
import json
import ast
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
import products_store as store
import storage
import sqlite_db
from uat_fixture import build
from uat_hardening import UATBlocked


class ProductPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = build(self.root / 'synthetic.sqlite3')
        self.patches = [patch.object(store, 'sqlite_db', self.db),
            patch.object(store, 'current_owner', return_value='synthetic-owner@example.test'),
            patch('orders_store.current_owner', return_value='synthetic-owner@example.test'),
            patch.object(storage, 'ROOT', self.root),
            patch.object(storage, 'IMAGE_DIR', self.root / 'assets/uploads/products')]
        for p in self.patches: p.start()
        self.fields = dict(name='Synthetic Test Product', category='Dessert', price=12.5, unit_cost=4.25, active=True)

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def photo(self):
        output = BytesIO()
        Image.new('RGB', (20, 30), 'green').save(output, 'PNG')
        return output

    def test_create_edit_and_fresh_process_persistence(self):
        identity = store.save_product(self.fields)
        self.assertIsNone(self.db.all_rows('products', id=identity)[0]['image_url'])
        store.save_product(dict(self.fields, name='Edited Synthetic Product', active=False), photo=self.photo(), product_id=identity)
        row = self.db.all_rows('products', id=identity)[0]
        self.assertEqual((row['price'], row['unit_cost'], row['category'], row['active']), (12.5, 4.25, 'Dessert', 0))
        path = self.root / row['image_url']
        self.assertTrue(path.is_file())
        code = 'import sqlite3,json,sys; c=sqlite3.connect(sys.argv[1]); print(json.dumps(c.execute("SELECT name,image_url FROM products WHERE id=?",(int(sys.argv[2]),)).fetchone()))'
        saved = json.loads(subprocess.check_output([sys.executable, '-c', code, str(self.db.DB_PATH), str(identity)], text=True))
        self.assertEqual(saved, [row['name'], row['image_url']])
        self.assertEqual(len(self.db.all_rows('orders')), 6)
        self.assertEqual(len(self.db.all_rows('payments')), 2)

    def test_create_with_image_and_invalid_image_rollback(self):
        identity = store.save_product(self.fields, photo=self.photo())
        original = self.db.all_rows('products', id=identity)[0]
        before = len(self.db.all_rows('products'))
        with self.assertRaises(ValueError):
            store.save_product(dict(self.fields, name='Invalid Synthetic'), photo=BytesIO(b'not image'))
        with self.assertRaises(ValueError):
            store.save_product(dict(self.fields, name='Invalid edit'), photo=BytesIO(b'not image'), product_id=identity)
        self.assertEqual(len(self.db.all_rows('products')), before)
        self.assertEqual(self.db.all_rows('products', id=identity)[0], original)

    def test_owner_gate_and_remote_guards(self):
        with patch.object(store, 'current_owner', side_effect=PermissionError):
            with self.assertRaises(PermissionError): store.save_product(self.fields)
        import db
        from receipt_storage import upload_payment_receipt
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'auth.py').read_text(encoding='utf-8'))
        registration = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'create_owner_account')
        with self.assertRaises(UATBlocked):
            exec(compile(ast.Module(body=registration.body[:2], type_ignores=[]), 'registration-guard', 'exec'), {})
        for call in (lambda: db.request('products'),
                     self.db.import_supabase_records, lambda: upload_payment_receipt(None, 1)):
            with self.assertRaises(UATBlocked): call()

    def test_database_failure_removes_new_image_and_rolls_back(self):
        with self.db.transaction() as connection:
            connection.execute("CREATE TRIGGER reject_image BEFORE UPDATE OF image_url ON products WHEN NEW.image_url IS NOT NULL BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
        before = len(self.db.all_rows('products'))
        with self.assertRaises(Exception):
            store.save_product(self.fields, photo=self.photo())
        self.assertEqual(len(self.db.all_rows('products')), before)
        self.assertEqual(list((self.root / 'assets/uploads/products').glob('*.png')), [])

    def test_replace_remove_and_shared_image_reference(self):
        first = store.save_product(self.fields, photo=self.photo())
        original = self.db.all_rows('products', id=first)[0]['image_url']
        second = store.save_product(dict(self.fields, name='Shared Synthetic', image_url=original))
        store.save_product(self.fields, photo=self.photo(), product_id=first)
        replaced = self.db.all_rows('products', id=first)[0]['image_url']
        self.assertNotEqual(original, replaced)
        self.assertTrue((self.root / original).is_file())
        self.assertEqual(self.db.all_rows('products', id=second)[0]['image_url'], original)
        store.save_product(dict(self.fields, image_url=None), product_id=first)
        self.assertIsNone(self.db.all_rows('products', id=first)[0]['image_url'])
        self.assertTrue((self.root / original).is_file())
        self.assertTrue((self.root / replaced).is_file())
        self.assertEqual(len(self.db.all_rows('orders')), 6)

    def test_upload_formats_and_size(self):
        for format in ('PNG', 'JPEG', 'WEBP'):
            image = BytesIO()
            Image.new('RGB', (20, 40)).save(image, format)
            result = storage.validated_image_bytes(image)
            with Image.open(BytesIO(result)) as decoded:
                self.assertEqual(decoded.size, (20, 40))
                self.assertEqual(decoded.format, 'PNG')
        with self.assertRaises(ValueError):
            storage.validated_image_bytes(BytesIO(b'x' * (storage.MAX_BYTES + 1)))


if __name__ == '__main__': unittest.main()
