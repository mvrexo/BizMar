"""Build synthetic data from application schema only; never reads a database snapshot."""
import ast
from pathlib import Path
from datetime import date,timedelta
import types
from contextlib import closing
from datetime import datetime
from zoneinfo import ZoneInfo


def seed_products(database):
    """Explicit test setup only; refuse the application's canonical database."""
    canonical = Path(__file__).resolve().parent / 'uat' / 'synthetic.sqlite3'
    if database.DB_PATH.resolve() == canonical.resolve():
        raise ValueError('Test catalogue cannot be seeded into the application database.')
    if not database.all_rows('products'):
        database.add('products', [dict(name=f'Synthetic Product {index + 1:02d}', category=('Kuih Raya','Kuih Tradisional','Dessert')[index % 3]) for index in range(15)])

def build(destination):
    destination=Path(destination).resolve()
    if destination.exists(): raise FileExistsError('Refusing to overwrite any database.')
    source=Path(__file__).with_name('sqlite_db.py')
    tree=ast.parse(source.read_text(encoding='utf-8'))
    for n in tree.body:
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DB_PATH' for t in n.targets):
            n.value=ast.Call(func=ast.Name(id='Path',ctx=ast.Load()),args=[ast.Constant(str(destination))],keywords=[])
    mod=types.ModuleType('synthetic_fixture_db');mod.__file__=str(source)
    exec(compile(ast.fix_missing_locations(tree),str(source),'exec'),mod.__dict__)
    seed_products(mod)
    today=datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date()
    # Explicit synthetic catalogue above; never copies saved products.
    products=mod.all_rows('products')
    for i,status in enumerate(('Pending','Confirmed','Preparing','Ready','Completed','Cancelled')):
        due=(today+timedelta(days=i-2)).isoformat()
        saved=mod.create_order({'name':f'Synthetic Customer {i+1}','phone':f'0100000{i+1:03d}','address':'Synthetic UAT address'},
            {'due_date':due,'fulfilment_date':due,'status':status,'notes':'SYNTHETIC UAT ONLY'},
            [{'product_id':products[i%len(products)]['id'],'quantity':i+1,'unit_price':20.,'unit_cost':8.}])
        if i in (1,4):
            mod.add('payments',{'order_id':saved['id'],'amount':10. if i==1 else saved['total_amount'],'method':'Cash','reference':'SYNTHETIC UAT'})
    with closing(mod._connect()) as con:
        assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not con.execute('PRAGMA foreign_key_check').fetchall()
    return mod
