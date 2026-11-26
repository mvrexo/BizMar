"""Owner-authorized, idempotent synchronization from a Google Forms worksheet."""
from dataclasses import dataclass, replace
import hashlib
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

import google_forms_importer as importer
import google_sheets_connection
import orders_store
import products_store


@dataclass
class SyncPreview:
    sheet_id: int
    preview: importer.ImportPreview
    signature: str
    product_names: dict[int, str]
    spreadsheet_id: str = ''


class SyncReviewRequired(ValueError):
    def __init__(self, message, preview=None):
        super().__init__(message)
        self.preview = preview


def _row_hash(row):
    encoded = json.dumps(
        sorted(((k,str(v).strip()) for k,v in row.items() if str(v).strip()), key=lambda item: item[0].casefold()),
        ensure_ascii=False,
        separators=(',', ':'),
    )
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _date_order(locale):
    region=str(locale).replace('-', '_').split('_')[-1].upper()
    if region in ('US','PH'):return 'MDY'
    if region in ('MY','GB','AU','NZ','IE','SG','IN'):return 'DMY'
    return None


def _review_timestamp_match(source, record, stamp, date_order, time_zone):
    """Formatted Sheets timestamps can round Excel milliseconds to the next second.

    This only proposes an explicit owner-reviewed association, never an auto-link.
    Neighbouring seconds also require the same phone and fulfilment date.
    """
    prior=importer.submission_stamp(source.get('source_submitted_at'),date_order,time_zone)
    if not prior or not stamp:
        return False
    if prior==stamp:
        return True
    import re
    phone=lambda value:re.sub(r'\D','',str(value or '')).removeprefix('60').lstrip('0')
    same_phone=phone(source.get('phone_snapshot')) and phone(source.get('phone_snapshot'))==phone(record['customer'].get('phone'))
    same_date=source.get('fulfilment_date')==record['order'].get('fulfilment_date')
    return bool(same_phone and same_date and abs((datetime.fromisoformat(prior)-datetime.fromisoformat(stamp)).total_seconds())<=1)


def prepare_preview(snapshot, spreadsheet_id):
    """Validate only unprocessed rows; never rewrite or re-parse imported orders."""
    products = products_store.list_products()
    existing_sources=orders_store.google_forms_source_records()
    existing_keys={r['import_response_key']:r for r in existing_sources}
    field_mapping = {field: importer.suggest_column(field, snapshot.headers) for field in importer.FIELD_LABELS}
    field_mapping['fulfilment_time'] = importer.suggest_columns('fulfilment_time',snapshot.headers)
    product_mapping = importer.suggest_product_mapping(snapshot.headers,products)
    ledger = {int(row['row_number']):row for row in orders_store.google_sheets_row_ledger(spreadsheet_id,snapshot.sheet_id)}
    previous_hashes = {row['content_hash']:int(row['row_number']) for row in ledger.values()}
    row_hashes = {number:_row_hash(row) for number,row in zip(snapshot.row_numbers,snapshot.rows)}
    pending_rows=[]
    pending_numbers=[]
    skipped=[]
    errors=[]
    moved=[]
    for number,row in zip(snapshot.row_numbers,snapshot.rows):
        previous=ledger.get(number)
        if previous:
            if previous['content_hash']==row_hashes[number]:
                skipped.append(f'Row {number}: already synchronized; will be skipped')
            else:
                errors.append(f'Source row {number} changed since its last sync. Review the edited response; the existing order will not be overwritten.')
            continue
        if row_hashes[number] in previous_hashes:
            moved.append(f'Source row {number} matches previously imported row {previous_hashes[row_hashes[number]]}. Moved responses cannot be imported automatically.')
            continue
        pending_rows.append(row)
        pending_numbers.append(number)
    if pending_rows:
        frame=pd.DataFrame(pending_rows,columns=snapshot.headers,index=[n-2 for n in pending_numbers])
        preview=importer.build_preview(frame,field_mapping,product_mapping,products,default_method=None,
            require_all_product_columns=True,date_order=_date_order(snapshot.locale))
    else:
        preview=importer.ImportPreview()
    preview.errors.extend(errors)
    preview.errors.extend(moved)
    preview.already_imported.extend(skipped)
    for record in preview.records:
        number=int(record['source_row'])
        key=f'google-sheets:v1:{spreadsheet_id}:{snapshot.sheet_id}:row:{number}'
        canonical_key=record['import_response_key']
        record['forms_response_key']=canonical_key
        exact=existing_keys.get(canonical_key)
        stamp=importer.submission_stamp(record['order'].get('source_submitted_at'),_date_order(snapshot.locale),snapshot.time_zone)
        candidates=[r for r in existing_sources if _review_timestamp_match(r,record,stamp,_date_order(snapshot.locale),snapshot.time_zone)]
        if exact:
            record['existing_order_id']=int(exact['id'])
            record['existing_order_key']=exact['import_response_key']
            record['existing_order_reference']=exact['order_code']
        elif candidates:
            if len(candidates)!=1:
                preview.errors.append(f'Source row {number} matches multiple existing response timestamps. Review the existing orders before enabling sync.')
            else:
                record['existing_order_id']=int(candidates[0]['id'])
                record['existing_order_key']=candidates[0]['import_response_key']
                record['existing_order_reference']=candidates[0]['order_code']
                record['link_requires_review']=True
                preview.ambiguous_rows.append(f'Source row {number} may already be {candidates[0]["order_code"]}. Confirm this association; the existing order will not be overwritten.')
        elif stamp:
            # A manual phone/date edit must not turn a near-timestamp response
            # into an apparently new order. Stop rather than guess an association.
            for source in existing_sources:
                prior=importer.submission_stamp(source.get('source_submitted_at'),_date_order(snapshot.locale),snapshot.time_zone)
                if prior and abs((datetime.fromisoformat(prior)-datetime.fromisoformat(stamp)).total_seconds())<=1:
                    preview.errors.append(f'Source row {number} has a nearby existing response timestamp but different customer or fulfilment details. Review before importing; it cannot safely be classified as new.')
                    break
        record['import_response_key']=key
        record['sync_source']={'row_number':number,'content_hash':row_hashes[number]}
    signature_data=[spreadsheet_id,snapshot.sheet_id,snapshot.headers,snapshot.locale,snapshot.time_zone,
                    list(zip(snapshot.row_numbers,row_hashes.values())),
                    [(p['id'],p['price'],p['active']) for p in products],
                    [(r['source_row'],r.get('existing_order_id'),r.get('link_requires_review',False)) for r in preview.records],
                    preview.errors,preview.ambiguous_rows]
    signature=hashlib.sha256(json.dumps(signature_data,separators=(',',':')).encode()).hexdigest()
    return SyncPreview(snapshot.sheet_id,preview,signature,{int(p['id']):str(p['name']) for p in products},str(spreadsheet_id))


def verify_preview(config,prepared):
    """Re-read before a manual commit so confirmation covers the current source."""
    if prepared.spreadsheet_id!=config.spreadsheet_id:
        raise SyncReviewRequired('The preview belongs to a different spreadsheet. Preview it again.')
    fresh=prepare_preview(google_sheets_connection.read_snapshot(config),config.spreadsheet_id)
    if fresh.signature!=prepared.signature:
        raise SyncReviewRequired('The sheet or catalogue changed after preview. Refresh the preview before confirming.',fresh)
    return fresh


def safe_sync_error(error):
    if isinstance(error,(SyncReviewRequired,google_sheets_connection.GoogleSheetsConnectionError)):
        return str(error)
    return 'Synchronization could not finish safely. No partial orders were saved. Retry or review a fresh preview.'


def _review_source_rows(messages):
    rows=set()
    unscoped=False
    for message in messages:
        match=re.search(r'\bsource row\s+(\d+)\b',message,re.I)
        if match:
            rows.add(int(match.group(1)))
            continue
        match=re.match(r'\s*row\s+(\d+)\s*:',message,re.I)
        if match:
            rows.add(int(match.group(1)))
            continue
        match=re.match(r'\s*rows?\s+(\d+(?:\s*,\s*\d+)*)\b',message,re.I)
        if match:
            rows.update(int(number) for number in re.findall(r'\d+',match.group(1)))
            continue
        unscoped=True
    return rows,unscoped


def commit_preview(config, prepared, *, acknowledge_ambiguous=False, lease_token=None):
    import os
    if os.environ.get('BIZMAR_PREVIEW_ONLY') == '1':
        raise PermissionError('Preview mode does not permit importing orders.')
    if prepared.spreadsheet_id != config.spreadsheet_id:
        raise SyncReviewRequired('The preview belongs to a different spreadsheet.')
    preview = prepared.preview
    if preview.errors:
        raise SyncReviewRequired('Resolve the preview errors before synchronization.', prepared)
    if preview.ambiguous_rows and not acknowledge_ambiguous:
        raise SyncReviewRequired(
            'Review and explicitly confirm ambiguous duplicate rows before synchronization.',
            prepared,
        )
    return orders_store.import_google_sheets_orders(
        config.spreadsheet_id,
        prepared.sheet_id,
        preview.records, allow_identical_rows=acknowledge_ambiguous, lease_token=lease_token,
    )


def synchronize(config, *, force=False):
    """Poll once under a SQLite lease; invalid or edited rows are never auto-imported."""
    import os
    if os.environ.get('BIZMAR_PREVIEW_ONLY') == '1':
        raise PermissionError('Preview mode does not permit live synchronization.')
    state = orders_store.google_sheets_sync_state(config.spreadsheet_id)
    if not state or not state.get('confirmed_at'):
        raise PermissionError('Google Sheets synchronization requires owner confirmation.')
    if not force and state.get('last_attempt_at') and (datetime.now(ZoneInfo('Asia/Kuala_Lumpur'))-datetime.fromisoformat(state['last_attempt_at'])).total_seconds()<config.sync_interval_seconds:
        return {'waiting':True,'imported':0,'order_ids':[]}
    lease = orders_store.acquire_google_sheets_lease(
        config.spreadsheet_id, state['worksheet_id'], min_interval=0 if force else config.sync_interval_seconds,
        trigger='Manual' if force else 'Automatic',
    )
    if lease is None:
        return {'syncing': True, 'imported': 0, 'order_ids': []}
    skipped=0
    failed_rows=0
    try:
        report = google_sheets_connection.read_snapshot(config)
        if int(report.sheet_id) != int(state['worksheet_id']):
            raise SyncReviewRequired(
                'The configured worksheet changed. Pause synchronization and review a new preview.'
            )
        prepared = prepare_preview(report, config.spreadsheet_id)
        skipped=len(prepared.preview.already_imported)
        review_messages=prepared.preview.errors+prepared.preview.ambiguous_rows
        review_rows,unscoped_review=_review_source_rows(review_messages)
        review_records=[
            record for record in prepared.preview.records
            if record.get('link_requires_review')
        ]
        review_rows.update(int(record['source_row']) for record in review_records)
        safe_records=[
            record for record in prepared.preview.records
            if int(record['source_row']) not in review_rows
        ]
        failed_rows=len(review_rows) or (
            max(0,len(report.rows)-skipped) if review_messages else 0
        )
        review_required=bool(review_messages or review_records)
        if review_required and (unscoped_review or not safe_records):
            message=(
                'Google Sheets sync found ambiguous rows; review them before importing.'
                if prepared.preview.ambiguous_rows and not prepared.preview.errors
                else 'Google Sheets sync needs owner review; no orders were imported.'
            )
            raise SyncReviewRequired(message,prepared)

        committable=prepared
        if review_required:
            committable=replace(
                prepared,
                preview=replace(
                    prepared.preview,records=safe_records,errors=[],ambiguous_rows=[],
                ),
            )
        result = commit_preview(config, committable, lease_token=lease)
        result.update(
            skipped=skipped,failed=failed_rows,
            associated=result.get('linked',0),review_required=review_required,
        )
        if review_required:
            result['review_preview']=prepared
        orders_store.finish_google_sheets_sync(
            config.spreadsheet_id, lease, new_orders=result['imported'],associated=result.get('linked',0),skipped=skipped,
            failed_rows=failed_rows,review_required=review_required,
        )
        return result
    except Exception as error:
        orders_store.finish_google_sheets_sync(
            config.spreadsheet_id, lease, error=safe_sync_error(error),skipped=skipped,failed_rows=failed_rows,
            error_kind='Connection' if isinstance(error,google_sheets_connection.GoogleSheetsConnectionError) else ('Validation' if isinstance(error,SyncReviewRequired) else 'Internal'),
        )
        raise
