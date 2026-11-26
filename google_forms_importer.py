"""Preview and validate Google Forms order exports before transactional import.

When no stable response ID is mapped, a SHA-256 key is derived from the entire
normalized row (not Timestamp alone). Identical rows get deterministic occurrence
numbers and must be explicitly reviewed before import.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import io
import json
import logging
import re
from typing import Any
import unicodedata
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import orders_store
import sqlite_db
from malaysian_states import normalize as normalize_state
from display_preferences import localized_dialog, option_labels, tr

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 1000
logger = logging.getLogger(__name__)

FIELD_LABELS = {
    'response_id': 'Stable response ID',
    'customer_name': 'Customer name',
    'phone': 'Customer phone',
    'ordered_at': 'Order date',
    'submitted_at': 'Form timestamp',
    'fulfilment_date': 'Pickup / delivery date',
    'fulfilment_time': 'Pickup / delivery time',
    'fulfilment_method': 'Fulfilment method',
    'delivery_address': 'Delivery address / location',
    'customer_state': 'Customer state',
    'delivery_state': 'Delivery state',
    'notes': 'Order notes',
    'payment_preference': 'Payment preference',
    'submitted_payment_method': 'Submitted payment method',
    'submitted_amount_paid': 'Submitted amount paid',
    'payment_receipt_reference': 'Unverified payment receipt reference',
    'products_text': 'Legacy product and quantity text',
    'selected_products': 'Legacy selected product names',
    'selected_quantity': 'Legacy product quantity',
}
REQUIRED_FIELDS = ('customer_name', 'phone', 'fulfilment_date')
DATE_FORMATS = (
    '%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f',
    '%Y-%m-%d %I:%M %p', '%Y-%m-%d %I:%M:%S %p',
    '%d/%m/%Y', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %I:%M %p', '%d/%m/%Y %I:%M:%S %p',
    '%m/%d/%Y', '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %I:%M %p', '%m/%d/%Y %I:%M:%S %p',
)


@dataclass
class ImportPreview:
    records: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    already_imported: list[str] = field(default_factory=list)
    ambiguous_rows: list[str] = field(default_factory=list)
    product_mappings: list[tuple[str, str]] = field(default_factory=list)


def read_upload(upload) -> pd.DataFrame:
    """Read an xlsx/CSV upload with the same bounded, text-first approach as Data Import."""
    filename = str(getattr(upload, 'name', '')).lower()
    content = upload.getvalue()
    if len(content) > MAX_FILE_BYTES:
        raise ValueError('File exceeds 5 MB. Split it into smaller files.')
    if filename.endswith('.csv'):
        try:
            decoded = content.decode('utf-8-sig')
            frame = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False, encoding='utf-8-sig')
        except UnicodeDecodeError:
            decoded = content.decode('cp1252')
            frame = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False, encoding='cp1252')
        raw_headers = [header.strip() for header in next(csv.reader(io.StringIO(decoded)), [])]
        if not raw_headers or any(not header for header in raw_headers):
            raise ValueError('Every spreadsheet column must have a heading.')
        if len(set(raw_headers)) != len(raw_headers):
            raise ValueError('Column headings must be unique; rename duplicate headings and try again.')
    elif filename.endswith('.xlsx'):
        frame = pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False, engine='openpyxl')
    else:
        raise ValueError('Choose an Excel (.xlsx) or CSV file.')
    frame.columns = [str(column).strip() for column in frame.columns]
    if not frame.columns.size or any(not column or column.startswith('Unnamed:') for column in frame.columns):
        raise ValueError('Every spreadsheet column must have a heading.')
    if len(set(frame.columns)) != len(frame.columns):
        raise ValueError('Column headings must be unique; rename duplicate headings and try again.')
    if len(frame) > MAX_ROWS:
        raise ValueError(f'Maximum {MAX_ROWS:,} response rows per import.')
    return frame.dropna(how='all').fillna('')


def _text(value) -> str:
    if value is None or pd.isna(value):
        return ''
    return str(value).strip()


def _header_key(value) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', str(value).casefold()).strip()


def suggest_column(field_name: str, columns) -> str | None:
    aliases = {
        'response_id': ('response id', 'responseid', 'submission id'),
        'customer_name': ('customer name', "customer's name", 'name', 'full name', 'your name'),
        'phone': ('whatsapp phone number', 'whatsapp number', 'phone number', 'phone',
                  'mobile number', 'contact number'),
        'ordered_at': ('order date', 'date ordered'),
        'submitted_at': ('timestamp', 'submitted at', 'submission time'),
        'fulfilment_date': ('preferred pickup delivery date', 'preferred pickup date',
                            'preferred delivery date', 'pickup date', 'delivery date',
                            'fulfilment date', 'fulfillment date', 'required date'),
        'fulfilment_time': ('preferred time', 'prefeed time', 'preferred pickup time',
                            'preferred delivery time', 'pickup time', 'delivery time',
                            'fulfilment time', 'fulfillment time'),
        'fulfilment_method': ('fulfilment method', 'fullfilment method',
                              'fulfillment method', 'pickup or delivery', 'delivery method'),
        'delivery_address': ('delivery address delivery only', 'delivery adress delivery only',
                             'delivery address', 'delivery adress', 'address', 'delivery location'),
        'customer_state': ('customer state', 'state'),
        'delivery_state': ('delivery state', 'destination state'),
        'notes': ('special requests notes', 'special requests', 'special request',
                  'order notes', 'notes', 'remarks'),
        'payment_preference': ('payment preference', 'preferred payment method'),
        'submitted_payment_method': ('payment method', 'submitted payment method'),
        'submitted_amount_paid': ('amount paid rm', 'amount paid', 'payment amount',
                                  'amount transferred'),
        'payment_receipt_reference': ('payment receipt upload proof of receipt','payment receipt','receipt url','payment reference'),
        'selected_products': ('products',),
        'selected_quantity': ('product quantity selection',),
    }
    by_key = {_header_key(column): str(column) for column in columns}
    if field_name=='products_text':
        return next((str(c) for c in columns if _header_key(c).startswith('product quantity examples')),None)
    for alias in aliases.get(field_name, ()):
        if _header_key(alias) in by_key:
            return by_key[_header_key(alias)]
    return None


def suggest_columns(field_name: str, columns) -> list[str]:
    """Return all exact historical header variants in preferred order."""
    primary = suggest_column(field_name, columns)
    aliases = {
        'fulfilment_time': ('preferred time', 'prefeed time', 'preferred pickup time',
                            'preferred delivery time', 'pickup time', 'delivery time',
                            'fulfilment time', 'fulfillment time'),
    }
    if field_name not in aliases:
        return [primary] if primary else []
    by_key = {_header_key(column): str(column) for column in columns}
    matches = []
    for alias in aliases[field_name]:
        column = by_key.get(_header_key(alias))
        if column and column not in matches:
            matches.append(column)
    if primary and primary not in matches:
        matches.insert(0, primary)
    return matches


def normalize_product_name(value: str) -> str:
    """Normalize Forms product labels, including broken dashes and RM prices."""
    normalized = unicodedata.normalize('NFKC', str(value)).replace('\ufffd', '')
    normalized = re.sub(r'\s*[—–-]?\s*RM\s*\d+(?:[.,]\d{1,2})?\s*$', '', normalized, flags=re.I)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    normalized=normalized.casefold()
    return {'black cookies':'blackout cookies','shortbread':'shortbread chocolate'}.get(normalized,normalized)


def product_name_from_quantity_header(header: str) -> str | None:
    match = re.match(
        r'^\s*product\s*(?:&\s*)?quantity(?:\s+selection)?\s*\[(.+)\]\s*$',
        str(header),
        flags=re.I | re.S,
    )
    if not match:
        return None
    name = normalize_product_name(match.group(1))
    return name or None


def suggest_product_mapping(columns, products: list[dict]) -> dict[str, int | None]:
    """Match all recognized product grid variants to one active catalogue ID."""
    catalogue = {}
    for product in products:
        if not product.get('active'):
            continue
        key = normalize_product_name(product.get('name', ''))
        if key:
            catalogue.setdefault(key, []).append(int(product['id']))
    mapping = {}
    for column in columns:
        name = product_name_from_quantity_header(str(column))
        if name is None:
            continue
        matches = catalogue.get(name, [])
        mapping[str(column)] = matches[0] if len(matches) == 1 else None
    return mapping


def _parse_date(value, label: str, date_order=None) -> date:
    raw = _text(value)
    if not raw:
        raise ValueError(f'{label} is required')
    try:
        return datetime.fromisoformat(raw.replace('Z', '+00:00')).date()
    except ValueError:
        pass
    matches = set()
    for fmt in DATE_FORMATS:
        if date_order=='MDY' and fmt.startswith('%d/') or date_order=='DMY' and fmt.startswith('%m/'):
            continue
        try:
            matches.add(datetime.strptime(raw, fmt).date())
        except ValueError:
            continue
    if not matches:
        raise ValueError(f'{label} must use an unambiguous date such as YYYY-MM-DD')
    if len(matches) > 1:
        raise ValueError(f'{label} is ambiguous; use YYYY-MM-DD')
    return next(iter(matches))


def _parse_time(value) -> str:
    raw = _text(value)
    if not raw:
        return ''
    try:
        return time.fromisoformat(raw).isoformat(timespec='minutes')
    except ValueError:
        pass
    for fmt in ('%I:%M %p', '%I:%M:%S %p', '%H:%M', '%H:%M:%S'):
        try:
            return datetime.strptime(raw, fmt).time().isoformat(timespec='minutes')
        except ValueError:
            continue
    raise ValueError('Pickup / delivery time must be a valid time')


def submission_stamp(value,date_order=None,time_zone='Asia/Kuala_Lumpur'):
    """Comparable timestamp for review candidates, never a name-only identity."""
    raw=_text(value)
    try:
        parsed=datetime.fromisoformat(raw.replace('Z','+00:00')) if ':' in raw else None
    except ValueError:
        parsed=None
    if parsed is None:
        matches=set()
        for fmt in DATE_FORMATS:
            if '%H' not in fmt and '%I' not in fmt:continue
            if date_order=='MDY' and fmt.startswith('%d/') or date_order=='DMY' and fmt.startswith('%m/'):continue
            try:matches.add(datetime.strptime(raw,fmt))
            except ValueError:pass
        if len(matches)!=1:return None
        parsed=matches.pop()
    if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=ZoneInfo(time_zone or 'Asia/Kuala_Lumpur'))
    return parsed.astimezone(ZoneInfo('Asia/Kuala_Lumpur')).isoformat(timespec='seconds')


def _quantity(value, row_number: int, column: str) -> int:
    raw = _text(value)
    if not raw:
        return 0
    try:
        number = Decimal(raw.replace(',', ''))
    except InvalidOperation:
        raise ValueError(f'Row {row_number}: quantity in "{column}" must be a whole number or blank') from None
    if not number.is_finite() or number < 0 or number > 100000 or number != number.to_integral_value():
        raise ValueError(f'Row {row_number}: quantity in "{column}" must be a whole number from 0 to 100,000')
    return int(number)


def _method(value, default_method) -> str:
    raw = _text(value).casefold()
    if not raw:
        raw = str(default_method or '').strip().casefold()
    if raw in ('pickup', 'pick up', 'collection', 'collect'):
        return 'Pickup'
    if raw in ('delivery', 'deliver', 'courier'):
        return 'Delivery'
    raise ValueError('Fulfilment method must be Pickup or Delivery; map the column or choose a default')


def _row_fingerprint(row: dict[str, str]) -> str:
    canonical = json.dumps(sorted(row.items(), key=lambda pair: pair[0].casefold()),
                           ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def build_preview(frame: pd.DataFrame, field_mapping: dict[str, str | list[str] | None],
                  product_mapping: dict[str, int | str | None], products: list[dict],
                  existing_keys=(), *, default_method: str | None = None,
                  require_all_product_columns: bool = False, date_order=None) -> ImportPreview:
    preview = ImportPreview()
    columns = list(frame.columns)
    for key in REQUIRED_FIELDS:
        mapped = field_mapping.get(key)
        mapped_columns = [mapped] if isinstance(mapped, str) else mapped or []
        if not any(column in columns for column in mapped_columns):
            preview.errors.append(f'Map a spreadsheet column to {FIELD_LABELS[key]}.')
    if not field_mapping.get('ordered_at') and not field_mapping.get('submitted_at'):
        preview.errors.append('Map Order date or Form timestamp so imported orders have an order date.')
    if preview.errors:
        return preview

    product_by_id = {int(product['id']): product for product in products if product.get('active')}
    mapped_products = {}
    for column, identity in product_mapping.items():
        if not identity:
            continue
        if column not in columns:
            preview.errors.append(f'Product mapping references missing column "{column}".')
            continue
        try:
            product_id = int(identity)
        except (ValueError, TypeError):
            preview.errors.append(f'Invalid catalogue product selected for "{column}".')
            continue
        product = product_by_id.get(product_id)
        if product is None:
            preview.errors.append(f'Column "{column}" must map to an active catalogue product.')
            continue
        mapped_products[column] = product
        preview.product_mappings.append((column, str(product['name'])))
    if require_all_product_columns:
        for column, identity in suggest_product_mapping(columns, products).items():
            if identity is None or product_mapping.get(column) is None:
                preview.errors.append(
                    f'Product quantity column "{column}" has no unique active catalogue match.'
                )
    if preview.errors:
        return preview
    if not mapped_products:
        preview.errors.append('Map at least one product quantity column to an active catalogue product.')
        return preview

    nonempty = frame.loc[~frame.apply(lambda row: all(not _text(value) for value in row), axis=1)]
    if nonempty.empty:
        preview.errors.append('The file contains no response rows.')
        return preview
    if len(nonempty) > MAX_ROWS:
        preview.errors.append(f'Maximum {MAX_ROWS:,} response rows per import.')
        return preview
    existing = set(existing_keys)
    row_fingerprints: dict[str, list[int]] = {}
    normalized_rows = {}
    for source_index, row in nonempty.iterrows():
        row_number = int(source_index) + 2
        values = {str(column): _text(row[column]) for column in columns}
        normalized_rows[source_index] = values
        fingerprint = _row_fingerprint(values)
        row_fingerprints.setdefault(fingerprint, []).append(row_number)
    occurrences = {}
    for fingerprint, row_numbers in row_fingerprints.items():
        if len(row_numbers) > 1:
            preview.ambiguous_rows.append(
                f'Rows {", ".join(map(str, row_numbers))} have identical response content. '
                'Review that they represent distinct submissions before importing.'
            )
    response_id_column = field_mapping.get('response_id')
    response_id_rows: dict[str, list[int]] = {}
    if response_id_column in columns:
        for source_index, row in nonempty.iterrows():
            response_id = _text(row[response_id_column])
            if response_id:
                response_id_rows.setdefault(response_id, []).append(int(source_index) + 2)

    for source_index, row in nonempty.iterrows():
        row_number = int(source_index) + 2
        def get(key):
            mapped = field_mapping.get(key)
            mapped_columns = [mapped] if isinstance(mapped, str) else mapped or []
            values = [(column, _text(row[column])) for column in mapped_columns if column in columns]
            populated = [(column, value) for column, value in values if value]
            distinct = {_parse_time(value) if key=='fulfilment_time' else value for _, value in populated}
            if len(distinct) > 1:
                names = ', '.join(f'"{column}"' for column, _ in populated)
                raise ValueError(
                    f'Row {row_number}: conflicting values for {FIELD_LABELS[key]} in {names}'
                )
            return populated[0][1] if populated else ''
        try:
            name, phone = get('customer_name'), get('phone')
            if not name or len(name) > 200:
                raise ValueError('Customer name is required and must be at most 200 characters')
            if not sqlite_db.validate_customer_phone(phone):
                raise ValueError('Enter a valid Malaysian customer phone number')

            submitted_at = get('submitted_at')
            order_date_value = get('ordered_at')
            if order_date_value:
                ordered = _parse_date(order_date_value, 'Order date',date_order)
            elif submitted_at:
                ordered = _parse_date(submitted_at, 'Form timestamp',date_order)
            else:
                raise ValueError('Order date or form timestamp is required')
            due = _parse_date(get('fulfilment_date'), 'Pickup / delivery date',date_order)
            if due < ordered:
                raise ValueError('Pickup / delivery date cannot be before the order date')
            method = _method(get('fulfilment_method'), default_method)
            address = get('delivery_address')
            if method == 'Delivery' and not address:
                raise ValueError('Delivery orders require a mapped delivery address or location')
            if len(address) > 2000 or len(get('notes')) > 4000:
                raise ValueError('Delivery address must be at most 2,000 characters and notes at most 4,000 characters')
            if len(submitted_at) > 2000:
                raise ValueError('Form timestamp must be at most 2,000 characters')
            source_customer_state = get('customer_state')
            source_delivery_state = get('delivery_state')
            try:
                customer_state = normalize_state(source_customer_state)
            except ValueError:
                customer_state = ''
            if not customer_state:
                logger.warning(
                    'Google Forms row %s has a missing or unrecognized customer state.',
                    row_number,
                )
            delivery_state = ''
            if method == 'Delivery':
                delivery_state_column = field_mapping.get('delivery_state')
                if delivery_state_column and delivery_state_column in columns:
                    try:
                        delivery_state = normalize_state(source_delivery_state)
                    except ValueError:
                        delivery_state = ''
                    if not delivery_state:
                        logger.warning(
                            'Google Forms row %s has a missing or unrecognized delivery destination state.',
                            row_number,
                        )
                else:
                    delivery_state = customer_state
                    if not delivery_state:
                        logger.warning(
                            'Google Forms row %s has no valid state for its delivery destination.',
                            row_number,
                        )
            fulfilment_time = _parse_time(get('fulfilment_time'))
            if len(get('payment_preference')) > 2000 or len(get('submitted_payment_method')) > 2000:
                raise ValueError('Submitted payment fields must be at most 2,000 characters')

            product_quantities: dict[int, list[tuple[str, int]]] = {}
            for column, product in mapped_products.items():
                quantity = _quantity(row[column], row_number, column)
                if quantity:
                    product_quantities.setdefault(int(product['id']), []).append((column, quantity))
            catalogue_by_name={}
            for p in product_by_id.values():
                catalogue_by_name.setdefault(normalize_product_name(p['name']),[]).append(p)
            text_entries=[]
            if get('products_text'):
                for entry in re.split(r'[\n;]+',get('products_text')):
                    if not entry.strip():continue
                    match=re.fullmatch(r'(.+?)\s*[-:x×]\s*(\d+)\s*',entry.strip(),flags=re.I)
                    if not match:raise ValueError('Legacy product text requires Product - Quantity entries; review the response')
                    text_entries.append((match[1],match[2]))
            if get('selected_quantity') and get('selected_products'):
                names=re.split(r'[,;\n]+',get('selected_products'))
                if len(names)!=1:raise ValueError('One legacy quantity cannot be assigned to multiple selected products; review the response')
                text_entries.append((names[0],get('selected_quantity')))
            for name,raw_quantity in text_entries:
                matches=catalogue_by_name.get(normalize_product_name(name),[])
                if len(matches)!=1:raise ValueError('A legacy product name has no unique active catalogue match; review the response')
                quantity=_quantity(raw_quantity,row_number,'legacy product text')
                if quantity:product_quantities.setdefault(int(matches[0]['id']),[]).append(('legacy product text',quantity))
            quantities: dict[int, int] = {}
            for product_id, entries in product_quantities.items():
                distinct_quantities = {quantity for _, quantity in entries}
                if len(distinct_quantities) > 1:
                    sources = ', '.join(f'"{column}"={quantity}' for column, quantity in entries)
                    raise ValueError(
                        f'Row {row_number}: conflicting quantity columns for '
                        f'"{product_by_id[product_id]["name"]}": {sources}. '
                        'Review or unmap the overlapping column.'
                    )
                quantities[product_id] = next(iter(distinct_quantities))
            lines = [
                dict(product_id=product_id, quantity=quantity, unit_price=float(product_by_id[product_id]['price']))
                for product_id, quantity in quantities.items() if quantity > 0
            ]
            if not lines:
                raise ValueError('At least one mapped product quantity must be greater than zero')
            subtotal = sum(Decimal(str(line['unit_price'])) * line['quantity'] for line in lines)

            response_id = get('response_id')
            if response_id:
                if len(response_id_rows[response_id]) > 1:
                    raise ValueError(
                        f'Stable response ID duplicates rows {", ".join(map(str, response_id_rows[response_id]))}'
                    )
                identity_hash = hashlib.sha256(response_id.encode('utf-8')).hexdigest()
                response_key = f'google-forms:id:{identity_hash}'
            else:
                fingerprint = _row_fingerprint(normalized_rows[source_index])
                occurrence = occurrences.get(fingerprint, 0) + 1
                occurrences[fingerprint] = occurrence
                response_key = f'google-forms:fallback:v1:{fingerprint}:{occurrence}'

            if response_key in existing:
                preview.already_imported.append(f'Row {row_number}: already imported; will be skipped')
                continue
            if response_id:
                # Stable IDs must be unique within a single export.
                prior = next((record for record in preview.records if record['import_response_key'] == response_key), None)
                if prior:
                    raise ValueError(f'Stable response ID duplicates row {prior["source_row"]}')

            submitted_amount = None
            submitted_amount_raw = get('submitted_amount_paid')
            if submitted_amount_raw:
                try:
                    submitted_amount = Decimal(submitted_amount_raw.replace(',', ''))
                except InvalidOperation:
                    raise ValueError('Submitted amount paid must be a valid amount') from None
                if not submitted_amount.is_finite() or submitted_amount < 0 or submitted_amount > Decimal('999999999.99'):
                    raise ValueError('Submitted amount paid must be between RM 0 and RM 999,999,999.99')

            order = {
                'ordered_at': ordered.isoformat(),
                'fulfilment_date': due.isoformat(),
                'fulfilment_method': method,
                'delivery_address': address,
                'source': 'Other',
                'notes': get('notes'),
                'import_source': 'Google Forms',
                'import_response_key': response_key,
                'source_submitted_at': submitted_at,
                'payment_preference': get('payment_preference'),
                'submitted_payment_method': get('submitted_payment_method'),
                'submitted_amount_paid': float(submitted_amount) if submitted_amount is not None else None,
                'payment_receipt_reference':get('payment_receipt_reference'),
            }
            if fulfilment_time:
                order['fulfilment_time'] = fulfilment_time
            if customer_state:
                order['customer_state'] = customer_state
            if method == 'Delivery':
                order['delivery_state'] = delivery_state
            preview.records.append({
                'source_row': row_number,
                'customer': {'name': name, 'phone': phone, 'address': address,
                             'state': customer_state},
                'order': order,
                'lines': lines,
                'import_response_key': response_key,
                'subtotal': float(subtotal),
                'fulfilment_method': method,
            })
        except (ValueError, TypeError, OverflowError) as error:
            preview.errors.append(f'Row {row_number}: {error}')
    return preview


def import_preview(preview: ImportPreview, *, acknowledge_ambiguous: bool = False):
    if preview.errors:
        raise ValueError('Resolve all row and mapping errors before importing.')
    if preview.ambiguous_rows and not acknowledge_ambiguous:
        raise ValueError('Review and explicitly confirm the identical response rows before importing.')
    if not preview.records:
        raise ValueError('There are no new valid orders to import.')
    return orders_store.import_google_forms_orders(preview.records)


def _close_import_dialog():
    st.session_state['google_forms_import_open'] = False


@localized_dialog('Import Google Forms Orders', width='large', on_dismiss=_close_import_dialog)
def render_google_forms_import() -> None:
    st.caption(tr('Import a Google Forms response export. Map the form columns and review product quantities and totals before saving.'))
    st.info(
        tr('The first setup uses explicit column mapping because Google Forms headings vary. '
           'Export the response sheet as Excel (.xlsx) or CSV; files are processed locally.')
    )
    upload = st.file_uploader(
        tr('Upload Google Forms responses (.xlsx or .csv), max 5 MB'),
        type=['xlsx', 'csv'], key='google_forms_import_upload',
    )
    if upload is None:
        return
    upload_digest = hashlib.sha256(upload.getvalue()).hexdigest()
    try:
        frame = read_upload(upload)
    except Exception as error:
        st.error(tr(f'Unable to read the response file: {error}'))
        return
    if frame.empty:
        st.warning(tr('The file contains no response rows.'))
        return
    st.dataframe(frame.head(100), hide_index=True, width='stretch')
    st.caption(f'{len(frame):,} {tr("responses")}; {tr("preview displays up to")} 100.')
    columns = list(frame.columns)
    products = []
    try:
        import products_store
        products = products_store.list_products()
        existing_keys = orders_store.imported_response_keys()
    except Exception as error:
        st.error(tr(f'Unable to load the catalogue or check imported responses: {error}'))
        return

    mapping_context = json.dumps(
        [columns, [(product['id'], product['name'], product['category']) for product in products if product.get('active')]],
        ensure_ascii=False, separators=(',', ':'),
    )
    mapping_signature = hashlib.sha256(mapping_context.encode('utf-8')).hexdigest()[:12]
    field_mapping = {}

    def field_selector(field_name, container):
        suggested = suggest_column(field_name, columns)
        options = ['Not mapped', *columns]
        index = options.index(suggested) if suggested in options else 0
        selected = container.selectbox(
            tr(FIELD_LABELS[field_name]), options, index=index,
            format_func=lambda option: tr('Not mapped') if option == 'Not mapped' else option,
            key=f'google_forms_map_{mapping_signature}_{field_name}',
        )
        field_mapping[field_name] = None if selected == 'Not mapped' else selected

    core = st.columns(2)
    core_fields = ('customer_name', 'phone', 'ordered_at', 'submitted_at',
                   'fulfilment_date', 'fulfilment_method', 'delivery_address')
    for index, field_name in enumerate(core_fields):
        field_selector(field_name, core[index % 2])
    with st.expander(tr('Optional response fields'), expanded=False):
        optional = st.columns(2)
        for index, field_name in enumerate(('response_id', 'fulfilment_time', 'customer_state',
                                            'delivery_state', 'notes', 'payment_preference',
                                            'submitted_payment_method', 'submitted_amount_paid')):
            field_selector(field_name, optional[index % 2])

    method_fallback = st.selectbox(
        tr('Default for blank or unmapped fulfilment methods'),
        ['Do not assume', 'Pickup', 'Delivery'],
        format_func=option_labels(['Do not assume', 'Pickup', 'Delivery']),
        key=f'google_forms_default_method_{mapping_signature}',
    )
    default_method = None if method_fallback == 'Do not assume' else method_fallback

    active_products = [product for product in products if product.get('active')]
    product_options = {'Ignore this column': None}
    for product in active_products:
        product_options[f"{product['id']} · {product['name']} ({product['category']})"] = int(product['id'])
    suggested_products = {}
    for column in columns:
        header = str(column).casefold()
        matches = [product for product in active_products if str(product['name']).casefold() in header]
        if matches:
            suggested_products[column] = max(matches, key=lambda product: len(str(product['name'])))['id']
    product_mapping = {}
    with st.expander(tr('Map product quantity grid columns'), expanded=True):
        st.caption(tr('Blank quantity cells mean zero. Quantities are multiplied by the current catalogue price.'))
        product_columns = st.columns(2)
        for index, column in enumerate(columns):
            options = list(product_options)
            suggested_id = suggested_products.get(column)
            default = next((label for label, identity in product_options.items()
                            if identity == suggested_id), 'Ignore this column')
            selected = product_columns[index % 2].selectbox(
                f'{tr("Quantity column")}: {column}', options, index=options.index(default),
                format_func=lambda option: tr('Ignore this column') if option == 'Ignore this column' else option,
                key=f'google_forms_product_{mapping_signature}_{index}',
            )
            product_mapping[column] = product_options[selected]

    try:
        preview = build_preview(
            frame, field_mapping, product_mapping, products, existing_keys,
            default_method=default_method,
        )
    except Exception as error:
        st.error(tr(f'Unable to validate the response file: {error}'))
        return

    if preview.product_mappings:
        st.markdown(tr('**Product mapping**'))
        st.dataframe(pd.DataFrame(preview.product_mappings, columns=['Response column', 'Catalogue product']),
                     hide_index=True, width='stretch')
    for error in preview.errors[:30]:
        st.error(tr(error))
    if len(preview.errors) > 30:
        st.caption(f'{len(preview.errors) - 30} {tr("additional validation errors not shown.")}')
    if preview.already_imported:
        st.warning(f'{len(preview.already_imported)} {tr("responses were already imported and will be skipped.")}')
        for duplicate in preview.already_imported[:20]:
            st.caption(tr(duplicate))
    if preview.ambiguous_rows:
        st.warning(tr('No stable response ID was available for identical rows. The fallback keys use a hash of the full row plus its occurrence number; confirm these are separate submissions.'))
        for issue in preview.ambiguous_rows[:20]:
            st.caption(tr(issue))
    if preview.records:
        product_names = {int(product['id']): product['name'] for product in products}
        summary = [{
            'Source row': record['source_row'],
            'Customer': record['customer']['name'],
            'Phone': record['customer']['phone'],
            'Fulfilment': record['fulfilment_method'],
            'Products': ', '.join(
                f"{line['quantity']} × {product_names[line['product_id']]}" for line in record['lines']
            ),
            'Product subtotal (RM)': f"{record['subtotal']:.2f}",
            'Response key': 'Stable ID' if ':id:' in record['import_response_key'] else 'Reviewed row hash',
        } for record in preview.records]
        st.markdown(tr('**Orders ready to import**'))
        st.dataframe(pd.DataFrame(summary), hide_index=True, width='stretch')
        st.info(
            f"{len(preview.records)} {tr('new orders')} · "
            f"{tr('Product subtotal')}: RM {sum(record['subtotal'] for record in preview.records):,.2f} · "
            f"{len(preview.already_imported)} {tr('duplicate responses skipped')}. "
            f"{tr('Imported orders are Pending and Unpaid; submitted payment claims are retained for review, not recorded as payments.')}"
        )
    review_context = json.dumps(
        [upload_digest, field_mapping, product_mapping, preview.records,
         preview.errors, preview.already_imported, preview.ambiguous_rows],
        ensure_ascii=False, sort_keys=True, default=str, separators=(',', ':'),
    )
    review_signature = hashlib.sha256(review_context.encode('utf-8')).hexdigest()[:12]
    reviewed = st.checkbox(
        tr('I reviewed the mapped columns, products, duplicate responses and subtotals.'),
        key=f'google_forms_import_reviewed_{review_signature}',
    )
    ambiguous_reviewed = True
    if preview.ambiguous_rows:
        ambiguous_reviewed = st.checkbox(
            tr('I confirmed the identical response rows represent distinct submissions.'),
            key=f'google_forms_import_ambiguous_reviewed_{review_signature}',
        )
    can_import = bool(preview.records) and not preview.errors and reviewed and ambiguous_reviewed
    if st.button(tr('Import Orders'), type='primary', disabled=not can_import, key='google_forms_import_commit'):
        try:
            with st.spinner(tr('Importing orders in one SQLite transaction...')):
                result = import_preview(preview, acknowledge_ambiguous=ambiguous_reviewed)
            st.cache_data.clear()
            st.session_state['google_forms_import_open'] = False
            st.session_state['om_flash_message'] = tr(
                f"Import complete: {result['imported']} new orders saved; "
                f"{result['skipped']} duplicate responses skipped."
            )
            st.rerun()
        except Exception as error:
            st.error(tr(f'Import failed and no partial order records were saved: {error}'))
