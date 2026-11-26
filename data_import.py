"""Historical data migration for Nour Sweets (owner-only Streamlit page).

Imports are deliberate, previewed, and validated. No writes before confirmation.
"""
from display_preferences import tr
import io
import re
from datetime import datetime
import pandas as pd
import streamlit as st
from sqlite_db import all_rows, add, edit, remove

STATUSES = {'Pending', 'Confirmed', 'Preparing', 'In Production', 'Ready', 'Completed', 'Cancelled'}
CATEGORIES = {'Kuih Raya', 'Kuih Tradisional', 'Dessert'}
PAYMENT_METHODS = {'Transfer', 'Cash', 'E-wallet', 'Other'}

def _clean(value):
    return '' if pd.isna(value) else str(value).strip()


def _key(value):
    return re.sub(r'\s+', ' ', _clean(value)).casefold()


def _phone(value):
    return re.sub(r'[^0-9+]', '', _clean(value))


def _money(value):
    return float(_clean(value).replace(',', ''))


def _read(upload):
    if upload.size > 5 * 1024 * 1024:
        raise ValueError('File exceeds 5 MB. Split it into smaller files.')
    if upload.name.lower().endswith('.csv'):
        raw = upload.getvalue()
        try:
            df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, encoding='utf-8-sig')
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, encoding='cp1252')
    else:
        df = pd.read_excel(io.BytesIO(upload.getvalue()), dtype=str, keep_default_na=False, engine='openpyxl')
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how='all').fillna('')


def _date(value):
    value = _clean(value)
    if not value:
        raise ValueError('date is required')
    # Explicit ISO format avoids ambiguous DD/MM vs MM/DD imports.
    return datetime.strptime(value[:10], '%Y-%m-%d').date().isoformat()


# Unified one-sheet import. One row represents one product line in an order.
MASTER_COLUMNS = [
    'Order Reference', 'Order Date', 'Due Date', 'Customer Name',
    'Customer Phone', 'Customer Address', 'Product Name', 'Category',
    'Selling Price', 'Unit Cost', 'Availability', 'Quantity', 'Unit Price',
    'Status', 'Amount Paid', 'Payment Method'
]


def _master_template():
    return pd.DataFrame([
        ['NS-001','2026-07-10','2026-07-13','Aina','0123456789','Pendang, Kedah',
         'Almond London','Kuih Raya',28,16,'Available',2,28,'Completed',70,'Transfer'],
        ['NS-001','2026-07-10','2026-07-13','Aina','0123456789','Pendang, Kedah',
         'Tart Nenas','Kuih Raya',25,14,'Available',1,25,'Completed',70,'Transfer'],
        ['NS-002','2026-08-01','2026-08-05','Siti','01123456789','Alor Setar, Kedah',
         'Bahulu','Kuih Tradisional',15,8,'Available',3,15,'Pending',0,''],
    ], columns=MASTER_COLUMNS)


def _master_validate(df, existing):
    problems=[]
    missing=[c for c in MASTER_COLUMNS if c not in df.columns]
    if missing: return ['Missing columns: '+', '.join(missing)]
    if len(df)>1000: return ['Maximum 1,000 rows per import.']
    customers={_phone(c.get('phone')):c for c in existing['customers'] if _phone(c.get('phone'))}
    products={_key(p.get('name')):p for p in existing['products']}
    customer_file={}; product_file={}; orders_file={}
    old_refs=set()
    for order in existing['orders']:
        match=re.search(r'\[HISTORICAL_IMPORT_REF:([^\]]+)\]',_clean(order.get('notes')))
        if match: old_refs.add(match.group(1))
    for ix,row in df.iterrows():
        n=ix+2
        try:
            ref=_clean(row['Order Reference']); phone=_phone(row['Customer Phone'])
            cname=_clean(row['Customer Name']); pname=_clean(row['Product Name'])
            pk=_key(pname); cat=_clean(row['Category']); status=_clean(row['Status'])
            if not ref or not phone or not cname or not pname:
                raise ValueError('Order Reference, customer name/phone and product name are required')
            if ']' in ref or '[' in ref: raise ValueError('Order Reference cannot contain [ or ]')
            if ref in old_refs: raise ValueError('Order Reference already imported: '+ref)
            if cat not in CATEGORIES: raise ValueError('Invalid product category')
            if status not in STATUSES: raise ValueError('Invalid order status')
            if _key(row['Availability']) not in ('available','inactive'):
                raise ValueError('Availability must be Available or Inactive')
            ordered=_date(row['Order Date']); due=_date(row['Due Date'])
            if due<ordered: raise ValueError('Due Date is earlier than Order Date')
            price=_money(row['Selling Price']); cost=_money(row['Unit Cost'])
            unit_price=_money(row['Unit Price']); qty=_money(row['Quantity'])
            paid=_money(row['Amount Paid']); method=_clean(row['Payment Method'])
            if min(price,cost,unit_price,paid)<0 or qty<=0 or not qty.is_integer():
                raise ValueError('Prices/payments must be non-negative; quantity must be a positive integer')
            if paid>0 and method not in PAYMENT_METHODS:
                raise ValueError('Payment Method required and must match template when Amount Paid > 0')
            if method and method not in PAYMENT_METHODS: raise ValueError('Invalid Payment Method')
            cust_sig=(cname.casefold(),_clean(row['Customer Address']))
            if phone in customer_file and customer_file[phone]!=cust_sig:
                raise ValueError('Same phone has conflicting customer name/address in file')
            customer_file[phone]=cust_sig
            if phone in customers and _key(customers[phone].get('name'))!=_key(cname):
                raise ValueError('Existing phone belongs to a different customer name')
            product_sig=(cat,price,cost,_key(row['Availability']))
            if pk in product_file and product_file[pk]!=product_sig:
                raise ValueError('Same product has conflicting category/prices/availability in file')
            product_file[pk]=product_sig
            order_sig=(phone,ordered,due,status,paid,method)
            if ref in orders_file and orders_file[ref]!=order_sig:
                raise ValueError('Same Order Reference has conflicting order/payment details')
            orders_file[ref]=order_sig
        except (ValueError,TypeError) as exc:
            problems.append(f'Row {n}: {exc}')
    if not problems:
        for ref,grp in df.groupby('Order Reference',sort=False):
            total=sum(_money(r['Quantity'])*_money(r['Unit Price']) for _,r in grp.iterrows())
            if _money(grp.iloc[0]['Amount Paid'])>total+0.001:
                problems.append(f'Order {ref}: Amount Paid exceeds order total')
    return problems


def _master_insert(df):
    # Revalidate against fresh local SQLite data before any write.
    fresh={t:all_rows(t) for t in ('customers','products','orders')}
    issues=_master_validate(df,fresh)
    if issues: raise ValueError('Database changed since preview: '+'; '.join(issues[:5]))
    customer_map={_phone(c.get('phone')):c for c in fresh['customers'] if _phone(c.get('phone'))}
    product_map={_key(p.get('name')):p for p in fresh['products']}
    counters={'customers':0,'products':0,'orders':0,'order_items':0,'payments':0}
    # Existing products and customers are never overwritten.
    for _,r in df.iterrows():
        phone=_phone(r['Customer Phone']); key=_key(r['Product Name'])
        if phone not in customer_map:
            customer_map[phone]=add('customers',{'name':_clean(r['Customer Name']),
                'phone':phone,'address':_clean(r['Customer Address'])})
            counters['customers']+=1
        if key not in product_map:
            product_map[key]=add('products',{'name':_clean(r['Product Name']),
                'category':_clean(r['Category']),'price':_money(r['Selling Price']),
                'unit_cost':_money(r['Unit Cost']),
                'active':_key(r['Availability'])=='available'})
            counters['products']+=1
    for ref,group in df.groupby('Order Reference',sort=False):
        first=group.iloc[0]; created=None
        try:
            created=add('orders',{'customer_id':customer_map[_phone(first['Customer Phone'])]['id'],
                'ordered_at':_date(first['Order Date'])+'T12:00:00+08:00',
                'due_date':_date(first['Due Date']),
                'status':'Preparing' if _clean(first['Status'])=='In Production' else _clean(first['Status']),
                'notes':f'[HISTORICAL_IMPORT_REF:{ref}]'})
            lines=[]
            for _,r in group.iterrows():
                product=product_map[_key(r['Product Name'])]
                lines.append({'order_id':created['id'],'product_id':product['id'],
                    'quantity':int(_money(r['Quantity'])),'unit_price':_money(r['Unit Price']),
                    'unit_cost':float(product.get('unit_cost') or 0)})
            add('order_items',lines)
            paid=_money(first['Amount Paid'])
            if paid>0:
                add('payments',{'order_id':created['id'],'amount':paid,
                    'method':_clean(first['Payment Method']),
                    'reference':'Historical import '+ref})
                counters['payments']+=1
            counters['orders']+=1; counters['order_items']+=len(lines)
        except Exception:
            if created:
                try: remove('orders',created['id'])
                except Exception: pass
            raise
    return counters


def render_data_import():
    st.title(tr('Import All Data · One Excel File'))
    st.caption(tr('One Google Sheets table for customers, products, orders, dates and payments.'))
    st.warning(tr('Back up the local SQLite database before a large import. A failed import can leave some records saved. Check records before retrying.'))
    st.info(tr('One row per product within an order. Repeat Order Reference and payment amount for multi-product orders. The payment is saved only once per order.'))
    template=_master_template()
    from io import BytesIO
    bio=BytesIO()
    with pd.ExcelWriter(bio,engine='openpyxl') as writer:
        template.to_excel(writer,index=False,sheet_name='Master Orders')
        ws=writer.sheets['Master Orders'];ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
        for column in ws.columns:
            letter=column[0].column_letter
            ws.column_dimensions[letter].width=min(28,max(15,max(len(str(c.value or '')) for c in column)+2))
    st.download_button(tr('↓ Download One-File Excel Template'),bio.getvalue(),
                       file_name='NourSweets_Master_Orders.xlsx',
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.caption(tr('Template includes 3 sample rows. Replace sample data before importing. Dates must use YYYY-MM-DD.'))
    upload=st.file_uploader(tr('Upload one Excel (.xlsx) or CSV file, max 5 MB'),
                            type=['xlsx','csv'],key='master_import_upload')
    if upload is None: return
    try:
        df=_read(upload)
        if df.empty: st.warning(tr('No rows found.'));return
        st.dataframe(df.head(100),hide_index=True,use_container_width=True)
        st.caption(tr(f'{len(df)} product rows. Preview shows first 100.'))
        existing={t:all_rows(t) for t in ('customers','products','orders')}
        issues=_master_validate(df,existing)
        if issues:
            st.error(tr(f'{len(issues)} validation issue(s). Nothing imported.'))
            for issue in issues[:30]: st.write('• '+issue)
            return
        new_phones=set(_phone(v) for v in df['Customer Phone']) - set(_phone(c.get('phone')) for c in existing['customers'])
        new_products=set(_key(v) for v in df['Product Name']) - set(_key(p.get('name')) for p in existing['products'])
        st.success(tr('Validation passed. No changes made yet.'))
        st.info(tr(f'Preview: {len(new_phones)} new customers · {len(new_products)} new products · '
                f'{df["Order Reference"].nunique()} orders · {len(df)} order items. '
                'Existing customers/products will be reused, not overwritten.'))
        agree=st.checkbox(tr('I have reviewed the file and backed up my data.'),key='master_import_confirm')
        if st.button(tr('Import All Data to SQLite'),type='primary',disabled=not agree,key='master_import_commit'):
            try:
                with st.spinner('Importing customers, products, orders and payments...'):
                    result=_master_insert(df)
                st.cache_data.clear()
                st.success(tr('Import complete: '+', '.join(f'{v} {k}' for k,v in result.items())))
            except Exception as exc:
                st.error(tr(f'Import stopped: {exc}. Some records may have been written. Check SQLite before retrying.'))
    except Exception as exc:
        st.error(tr(f'Unable to process file: {exc}'))


# -------------------------------------------------------------
# Owner-initiated cleanup: ONLY orders marked by this importer.
# Never delete unrelated/manual orders, customers, or products.
# -------------------------------------------------------------
def render_import_cleanup():
    import json
    import zipfile
    from io import BytesIO

    st.divider()
    st.subheader(tr('Remove Previously Imported Orders'))
    st.caption(tr('This cleanup only targets orders with [HISTORICAL_IMPORT_REF:...] in their notes. Manually created orders are not included.'))
    st.warning(tr('Deleting an imported order also removes its order items and payments. Customers and products are retained because they may be shared with other orders.'))
    try:
        snapshot = {table: all_rows(table) for table in ('customers', 'products', 'orders', 'order_items', 'payments')}
    except Exception as exc:
        st.error(tr(f'Unable to inspect database for cleanup: {exc}'))
        return
    imported = []
    for order in snapshot['orders']:
        match = re.search(r'\[HISTORICAL_IMPORT_REF:([^\]]+)\]', _clean(order.get('notes')))
        if match:
            imported.append({'id': int(order['id']), 'reference': match.group(1),
                             'ordered_at': order.get('ordered_at'), 'status': order.get('status')})
    if not imported:
        st.info(tr('No orders marked as historical imports were found. Other records will not be deleted automatically.'))
        return
    st.dataframe(pd.DataFrame(imported), hide_index=True, use_container_width=True)
    st.caption(tr(f'{len(imported)} imported order(s) eligible for cleanup.'))
    archive = BytesIO()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for table, rows in snapshot.items():
            z.writestr(table + '.json', json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    st.download_button(tr('Download SQLite Data Backup (ZIP)'), archive.getvalue(),
                       file_name='bizmar_before_import_cleanup.zip', mime='application/zip',
                       key='historical_cleanup_backup')
    selected = st.multiselect(tr('Imported orders to delete'),
                              options=[x['id'] for x in imported],
                              format_func=lambda oid: next(f"#{x['id']} · {x['reference']}" for x in imported if x['id'] == oid),
                              key='historical_cleanup_ids')
    confirmation = st.text_input(tr('Type DELETE IMPORTED ORDERS to confirm'),
                                 key='historical_cleanup_phrase')
    acknowledged = st.checkbox(tr('I have downloaded the backup and understand deletion cannot be undone automatically.'),
                               key='historical_cleanup_ack')
    ready = bool(selected) and confirmation == 'DELETE IMPORTED ORDERS' and acknowledged
    if st.button(tr('Permanently Delete Selected Imported Orders'), type='primary',
                 disabled=not ready, key='historical_cleanup_delete'):
        try:
            # Recheck each order immediately before deleting. Remove payments first
            # (FK without ON DELETE CASCADE), then items, then the order.
            current = {int(o['id']): o for o in all_rows('orders')}
            for oid in selected:
                current_order = current.get(int(oid))
                if not current_order or not re.search(r'\[HISTORICAL_IMPORT_REF:([^\]]+)\]',
                                                      _clean(current_order.get('notes'))):
                    raise ValueError(f'Order #{oid} is no longer an eligible historical import. Nothing further deleted.')
            for oid in selected:
                for payment in snapshot['payments']:
                    if int(payment['order_id']) == int(oid):
                        remove('payments', payment['id'])
                for item in snapshot['order_items']:
                    if int(item['order_id']) == int(oid):
                        remove('order_items', item['id'])
                remove('orders', oid)
            st.cache_data.clear()
            st.success(tr(f'Deleted {len(selected)} imported order(s) and their associated payment/item records. Customers and products were preserved.'))
            st.rerun()
        except Exception as exc:
            st.error(tr(f'Cleanup stopped: {exc}. Some records may already have been deleted. Inspect SQLite and use the backup before retrying.'))

