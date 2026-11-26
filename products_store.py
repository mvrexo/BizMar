"""Atomic local product saves using the existing owner guard and canonical DB."""
import math
import sqlite_db
import storage
from orders_store import current_owner
from products_schema import FIELDS, migrate

UNITS = ('pieces', 'servings', 'g', 'kg', 'ml', 'litres')
PACKAGING = ('Unit', 'Box', 'Jar', 'Pack', 'Tray', 'Whole', 'Cup', 'Other')


def initialize():
    import os
    if os.environ.get('BIZMAR_PREVIEW_ONLY') == '1':
        sqlite_db.initialize()
        return
    sqlite_db.initialize()
    with sqlite_db.transaction() as connection:
        migrate(connection)


def list_products():
    current_owner()
    initialize()
    return sqlite_db.all_rows('products')


def get_product(identity):
    current_owner()
    initialize()
    rows = sqlite_db.all_rows('products', id=int(identity))
    if not rows:
        raise ValueError('Product no longer exists.')
    return rows[0]


def set_active(identity, active):
    current_owner()
    initialize()
    with sqlite_db.transaction() as connection:
        result = connection.execute('UPDATE products SET active = ? WHERE id = ?', (int(bool(active)), int(identity)))
        if result.rowcount != 1:
            raise ValueError('Product no longer exists.')


def save_product(payload, photo=None, product_id=None):
    current_owner()
    values = dict(payload)
    if set(values) - ({'name', 'category', 'price', 'unit_cost', 'image_url', 'active'} | FIELDS):
        raise ValueError('Unsupported product fields.')
    if not str(values.get('name', '')).strip():
        raise ValueError('Product name is required.')
    values['name'] = values['name'].strip()
    if len(values['name']) > 150:
        raise ValueError('Product name must contain at most 150 characters.')
    if not str(values.get('category', '')).strip() or len(values['category']) > 80:
        raise ValueError('Enter a category with at most 80 characters.')
    values['category'] = values['category'].strip()
    for field in ('price', 'unit_cost'):
        value = float(values[field])
        if not math.isfinite(value) or value < 0:
            raise ValueError('Product price and cost must be finite and non-negative.')
        values[field] = value
    if 'quantity_per_unit' in values:
        quantity = float(values['quantity_per_unit'])
        if not math.isfinite(quantity) or not 0 < quantity <= 1_000_000:
            raise ValueError('Quantity per selling unit must be positive and at most 1,000,000.')
        values['quantity_per_unit'] = quantity
    for field, choices in (('measurement_unit', UNITS), ('packaging_type', PACKAGING)):
        if field in values and values[field] not in choices:
            raise ValueError(f'Choose a valid {field.replace("_", " ")}.')
    if values.get('weight_grams') is not None:
        weight = float(values['weight_grams'])
        if not math.isfinite(weight) or not 0 < weight <= 1_000_000:
            raise ValueError('Weight must be positive and at most 1,000,000 grams.')
        values['weight_grams'] = weight
    values['image_url'] = str(values.get('image_url') or '').strip() or None
    initialize()
    new_image = None
    try:
        with sqlite_db.transaction() as connection:
            if product_id is None:
                product_id = sqlite_db._insert(connection, 'products', values)['id']
            elif connection.execute('SELECT id FROM products WHERE id = ?', (product_id,)).fetchone() is None:
                raise ValueError('Product no longer exists.')
            if photo is not None:
                new_image = storage.upload_product_image(photo, product_id)
                values['image_url'] = new_image
            fields = ', '.join(f'"{key}" = ?' for key in values)
            connection.execute(f'UPDATE products SET {fields} WHERE id = ?', (*values.values(), product_id))
        return product_id
    except Exception:
        if new_image:
            (storage.ROOT / new_image).unlink(missing_ok=True)
        raise
