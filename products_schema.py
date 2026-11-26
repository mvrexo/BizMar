"""Additive catalogue metadata; historical order line snapshots stay untouched."""
FIELDS = {'quantity_per_unit', 'measurement_unit', 'packaging_type', 'weight_grams'}


def migrate(connection):
    columns = {row[1] for row in connection.execute('PRAGMA table_info(products)')}
    for name, definition in {
        'quantity_per_unit': 'REAL NOT NULL DEFAULT 1 CHECK(quantity_per_unit > 0)',
        'measurement_unit': "TEXT NOT NULL DEFAULT 'pieces'",
        'packaging_type': "TEXT NOT NULL DEFAULT 'Unit'",
        'weight_grams': 'REAL CHECK(weight_grams IS NULL OR weight_grams > 0)',
    }.items():
        if name not in columns:
            connection.execute(f'ALTER TABLE products ADD COLUMN {name} {definition}')
    connection.execute("INSERT OR REPLACE INTO app_metadata (key,value) VALUES ('products_schema_version','1')")
