"""Continuation regressions: isolated SQLite and mocked Google responses only."""
from dataclasses import replace
from contextlib import closing
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch,Mock
import ast
import json
import unittest
from zoneinfo import ZoneInfo

import test_google_sheets_sync as fixtures
import google_sheets_sync as sync
import google_sheets_sync_ui as ui
import google_forms_importer as importer
import orders_store as store
import sqlite_db
from sync_monitor_store import monitor_data


class SyncCompletionTests(unittest.TestCase):
    setUp=fixtures.GoogleSheetsSyncTests.setUp
    tearDown=fixtures.GoogleSheetsSyncTests.tearDown
    headers=fixtures.GoogleSheetsSyncTests.headers
    make_snapshot=fixtures.GoogleSheetsSyncTests.make_snapshot
    row=fixtures.GoogleSheetsSyncTests.row
    prepare=fixtures.GoogleSheetsSyncTests.prepare

    def test_auto_poll_throttle_manual_force_and_no_duplicate_notifications(self):
        snapshot=self.make_snapshot([self.row()])
        store.confirm_google_sheets_sync(self.config.spreadsheet_id,snapshot.sheet_id)
        with patch.object(sync.google_sheets_connection,'read_snapshot',return_value=snapshot) as reader:
            self.assertEqual(sync.synchronize(self.config)['imported'],1)
            self.assertEqual(sync.synchronize(self.config)['imported'],0)
            self.assertEqual(reader.call_count,1)
            self.assertEqual(sync.synchronize(self.config,force=True)['imported'],0)
            self.assertEqual(reader.call_count,2)
        self.assertEqual(store.order_notification_counts(),dict(total=1,unread=1))

    def test_optional_payment_reference_and_changed_old_rows_do_not_block_new_orders(self):
        base_headers=self.headers()
        reference_header='Payment Reference'
        headers_with_reference=base_headers[:12]+[reference_header]+base_headers[12:]

        def form_row(name,phone,timestamp,reference=''):
            values=self.row(name)
            values[1]=phone
            values[2]=timestamp
            fields=dict(zip(base_headers,values))
            fields[reference_header]=reference
            return {header:fields.get(header,'') for header in headers_with_reference}

        first=form_row('Synthetic Existing One','0123456789','2026-10-27 10:00:00','form-ref-one')
        second=form_row('Synthetic Existing Two','0133456789','2026-10-27 11:00:00','form-ref-two')
        initial=sync.google_sheets_connection.GoogleSheetsSnapshot(
            1234,headers_with_reference,[first,second],[2,3],
        )
        store.confirm_google_sheets_sync(self.config.spreadsheet_id,initial.sheet_id)
        with patch.object(sync.google_sheets_connection,'read_snapshot',return_value=initial):
            initial_result=sync.synchronize(self.config,force=True)
        self.assertEqual(initial_result['imported'],2)
        existing_orders=sqlite_db.all_rows('orders')
        sqlite_db.edit('orders',existing_orders[0]['id'],{'notes':'Owner-entered note'})
        store.record_payment(
            existing_orders[0]['id'],
            dict(amount=10,method='Cash',reference='owner-payment-reference'),
            token='synthetic-owner-payment-001',
        )
        payments_before=sqlite_db.all_rows('payments')

        headers_without_reference=[h for h in headers_with_reference if h!=reference_header]
        third=form_row('Synthetic New Submission','0143456789','2026-10-27 12:00:00')
        changed_rows=[
            {header:row[header] for header in headers_without_reference}
            for row in (first,second,third)
        ]
        changed=sync.google_sheets_connection.GoogleSheetsSnapshot(
            1234,headers_without_reference,changed_rows,[2,3,4],
        )
        with patch.object(sync.google_sheets_connection,'read_snapshot',return_value=changed):
            result=sync.synchronize(self.config,force=True)

        self.assertEqual((result['imported'],result['failed'],result['review_required']),(1,2,True))
        self.assertEqual(len(result['review_preview'].preview.errors),2)
        orders=sqlite_db.all_rows('orders')
        self.assertEqual(len(orders),3)
        self.assertEqual(orders[0]['notes'],'Owner-entered note')
        self.assertEqual(orders[0]['payment_receipt_reference'],'form-ref-one')
        self.assertEqual(orders[1]['payment_receipt_reference'],'form-ref-two')
        self.assertEqual(orders[2]['payment_receipt_reference'],'')
        self.assertEqual(sqlite_db.all_rows('payments'),payments_before)
        history=monitor_data(self.config.spreadsheet_id)['history'][0]
        self.assertEqual((history['result'],history['error_kind'],history['failed_rows']),('Partial','Partial',2))
        self.assertEqual(
            store.google_sheets_sync_state(self.config.spreadsheet_id)['last_error'],
            'Valid new orders were imported; some source rows still require owner review.',
        )

        with patch.object(sync.google_sheets_connection,'read_snapshot',return_value=changed):
            with self.assertRaises(sync.SyncReviewRequired):
                sync.synchronize(self.config,force=True)
        self.assertEqual(len(sqlite_db.all_rows('orders')),3)
        self.assertEqual(sqlite_db.all_rows('payments'),payments_before)

    def test_delivery_source_state_and_address_reach_order_and_owner_edits_are_preserved(self):
        row=self.row('Synthetic Delivery')
        row[2]='2026-10-27 13:00:00'
        row[6]='Delivery'
        row[7]='Unit 8, Synthetic Garden'
        row[8]='Pahang'
        snapshot=self.make_snapshot([row])
        store.confirm_google_sheets_sync(self.config.spreadsheet_id,snapshot.sheet_id)
        with patch.object(sync.google_sheets_connection,'read_snapshot',return_value=snapshot):
            result=sync.synchronize(self.config,force=True)
        self.assertEqual(result['imported'],1)
        order=store.list_orders()[0]
        self.assertEqual(order['delivery_address'],'Unit 8, Synthetic Garden')
        self.assertEqual(order['delivery_state'],'Pahang')
        self.assertEqual(order['state'],'Pahang')
        detail=store.details(order['id'])['order']
        self.assertEqual(detail['delivery_address'],'Unit 8, Synthetic Garden')
        self.assertEqual(detail['delivery_state'],'Pahang')

        with sqlite_db.transaction() as connection:
            connection.execute(
                'UPDATE orders SET delivery_address=?,delivery_state=? WHERE id=?',
                ('Owner-corrected destination','Johor',order['id']),
            )
        with patch.object(sync.google_sheets_connection,'read_snapshot',return_value=snapshot):
            repeat=sync.synchronize(self.config,force=True)
        self.assertEqual(repeat['imported'],0)
        self.assertEqual(repeat['skipped'],1)
        corrected=store.list_orders()[0]
        self.assertEqual(corrected['delivery_address'],'Owner-corrected destination')
        self.assertEqual(corrected['delivery_state'],'Johor')
        self.assertEqual(corrected['state'],'Johor')

    def test_delivery_state_does_not_fall_back_to_residence_when_missing_or_invalid(self):
        headers=self.headers()+['Delivery State']
        base=self.row('Synthetic Missing Destination')
        base[6]='Delivery'
        base[7]='A complete delivery address'
        base[8]='Selangor'
        rows=[]
        for index,destination in enumerate(('', 'Atlantis'),start=1):
            values=list(base)
            values[0]=f'Synthetic Destination {index}'
            values[2]=f'2026-10-27 {13+index}:00:00'
            rows.append(dict(zip(headers,[*values,destination])))
        snapshot=sync.google_sheets_connection.GoogleSheetsSnapshot(1234,headers,rows,[2,3])
        store.confirm_google_sheets_sync(self.config.spreadsheet_id,snapshot.sheet_id)
        with self.assertLogs(importer.logger,level='WARNING') as logs:
            with patch.object(sync.google_sheets_connection,'read_snapshot',return_value=snapshot):
                result=sync.synchronize(self.config,force=True)
        self.assertEqual(result['imported'],2)
        self.assertEqual([row['state'] for row in store.list_orders()],['Not Specified','Not Specified'])
        self.assertEqual(sum('delivery destination state' in line for line in logs.output),2)

    def test_manual_order_edits_and_moved_source_are_protected(self):
        original=self.make_snapshot([self.row()])
        prepared=self.prepare(original)
        result=store.activate_google_sheets_preview(self.config.spreadsheet_id,prepared.sheet_id,prepared.preview.records)
        identity=result['order_ids'][0]
        sqlite_db.edit('orders',identity,dict(notes='Owner edited this manually'))
        repeat=self.prepare(original)
        self.assertFalse(repeat.preview.errors)
        self.assertEqual(repeat.preview.records,[])
        self.assertEqual(sqlite_db.all_rows('orders')[0]['notes'],'Owner edited this manually')
        moved=self.prepare(self.make_snapshot([self.row()],[3]))
        self.assertTrue(moved.preview.errors)
        self.assertEqual(moved.preview.records,[])

    def test_confirmation_failure_rolls_back_activation_orders_and_notices(self):
        second=self.row('Synthetic Second')
        second[2]='2026-10-27 11:00:00'
        prepared=self.prepare(self.make_snapshot([self.row(),second]))
        prepared.preview.records[1]['lines'][0]['product_id']=999999
        with self.assertRaises(ValueError):
            store.activate_google_sheets_preview(self.config.spreadsheet_id,prepared.sheet_id,prepared.preview.records)
        self.assertIsNone(store.google_sheets_sync_state(self.config.spreadsheet_id))
        for table in ('orders','customers','payments','order_items'):
            self.assertEqual(sqlite_db.all_rows(table),[])
        self.assertEqual(store.order_notification_counts()['total'],0)

    def test_stale_preview_and_changed_catalogue_require_fresh_review(self):
        snapshot=self.make_snapshot([self.row()])
        prepared=self.prepare(snapshot)
        changed=self.row();changed[12]='3'
        with patch.object(sync.google_sheets_connection,'read_snapshot',return_value=self.make_snapshot([changed])):
            with self.assertRaises(sync.SyncReviewRequired):ui._commit_confirmed(self.config,prepared)
        self.assertIsNone(store.google_sheets_sync_state(self.config.spreadsheet_id))
        sqlite_db.edit('products',self.product['id'],dict(price=60.))
        with patch.object(sync.google_sheets_connection,'read_snapshot',return_value=snapshot):
            with self.assertRaises(sync.SyncReviewRequired):ui._commit_confirmed(self.config,prepared)

    def test_identical_rows_require_review_then_remain_idempotent(self):
        snapshot=self.make_snapshot([self.row(),self.row()])
        prepared=self.prepare(snapshot)
        with self.assertRaises(ValueError):
            store.activate_google_sheets_preview(self.config.spreadsheet_id,prepared.sheet_id,prepared.preview.records)
        result=store.activate_google_sheets_preview(self.config.spreadsheet_id,prepared.sheet_id,prepared.preview.records,allow_identical_rows=True)
        self.assertEqual(result['imported'],2)
        repeat=self.prepare(snapshot)
        self.assertFalse(repeat.preview.ambiguous_rows)
        self.assertEqual(repeat.preview.records,[])
        self.assertEqual(store.order_notification_counts()['unread'],2)

    def test_file_import_is_linked_without_reimport_or_overwriting_edits(self):
        snapshot=self.make_snapshot([self.row()])
        prepared=self.prepare(snapshot)
        record=dict(prepared.preview.records[0])
        record['import_response_key']=record['forms_response_key']
        original=store.import_google_forms_orders([record])
        identity=original['order_ids'][0]
        sqlite_db.edit('orders',identity,dict(notes='Preserve owner edits'))
        fresh=self.prepare(snapshot)
        self.assertEqual(fresh.preview.records[0]['existing_order_id'],identity)
        result=store.activate_google_sheets_preview(self.config.spreadsheet_id,fresh.sheet_id,fresh.preview.records)
        self.assertEqual((result['imported'],result['linked']),(0,1))
        self.assertEqual(len(sqlite_db.all_rows('orders')),1)
        self.assertEqual(sqlite_db.all_rows('orders')[0]['notes'],'Preserve owner edits')
        self.assertEqual(store.order_notification_counts()['total'],0)
        self.assertEqual(self.prepare(snapshot).preview.records,[])

    def test_timestamp_only_existing_match_requires_explicit_association_review(self):
        prepared=self.prepare(self.make_snapshot([self.row()]))
        record=dict(prepared.preview.records[0]);record['import_response_key']=record['forms_response_key']
        identity=store.import_google_forms_orders([record])['order_ids'][0]
        changed=self.row();changed[2]='2026-10-27T10:00:00'
        fresh=self.prepare(self.make_snapshot([changed]))
        self.assertTrue(fresh.preview.ambiguous_rows)
        self.assertEqual(fresh.preview.records[0]['existing_order_id'],identity)
        with self.assertRaises(ValueError):
            store.activate_google_sheets_preview(self.config.spreadsheet_id,fresh.sheet_id,fresh.preview.records)
        result=store.activate_google_sheets_preview(self.config.spreadsheet_id,fresh.sheet_id,fresh.preview.records,allow_identical_rows=True)
        self.assertEqual(result['linked'],1)

    def test_rounded_sheet_timestamp_requires_phone_date_and_explicit_review(self):
        prepared=self.prepare(self.make_snapshot([self.row()]))
        record=dict(prepared.preview.records[0]);record['import_response_key']=record['forms_response_key']
        identity=store.import_google_forms_orders([record])['order_ids'][0]
        with sqlite_db.transaction() as connection:
            connection.execute('UPDATE orders SET source_submitted_at=?,notes=? WHERE id=?',('2026-10-27 10:00:00.829000','Preserve owner edits',identity))
        changed=self.row();changed[2]='2026-10-27T10:00:01'
        fresh=self.prepare(self.make_snapshot([changed]))
        self.assertEqual(fresh.preview.records[0]['existing_order_id'],identity)
        self.assertTrue(fresh.preview.ambiguous_rows)
        different_phone=list(changed);different_phone[1]='0199999999'
        conflicted=self.prepare(self.make_snapshot([different_phone]))
        self.assertTrue(conflicted.preview.errors)
        with self.assertRaises(ValueError):
            store.activate_google_sheets_preview(self.config.spreadsheet_id,fresh.sheet_id,fresh.preview.records)
        result=store.activate_google_sheets_preview(self.config.spreadsheet_id,fresh.sheet_id,fresh.preview.records,allow_identical_rows=True)
        self.assertEqual((result['imported'],result['linked']),(0,1))
        self.assertEqual(store.order_notification_counts()['total'],0)
        self.assertEqual(sqlite_db.all_rows('orders')[0]['notes'],'Preserve owner edits')
        bad_phone=dict(record);bad_phone['customer']={**record['customer'],'phone':'0199999999'}
        source=store.google_forms_source_records()[0]
        self.assertFalse(sync._review_timestamp_match(source,bad_phone,'2026-10-27T10:00:01+08:00','MDY','Asia/Kuala_Lumpur'))
        bad_date=dict(record);bad_date['order']={**record['order'],'fulfilment_date':'2027-01-01'}
        self.assertFalse(sync._review_timestamp_match(source,bad_date,'2026-10-27T10:00:01+08:00','MDY','Asia/Kuala_Lumpur'))
        self.assertFalse(sync._review_timestamp_match(source,record,'2026-10-27T10:00:02+08:00','MDY','Asia/Kuala_Lumpur'))

    def test_errors_redacted_and_retries_release_lease(self):
        store.confirm_google_sheets_sync(self.config.spreadsheet_id,1234)
        with patch.object(sync.google_sheets_connection,'read_snapshot',side_effect=RuntimeError('private secret / customer identity')):
            with self.assertRaises(RuntimeError):sync.synchronize(self.config)
        state=store.google_sheets_sync_state(self.config.spreadsheet_id)
        self.assertNotIn('private secret',state['last_error'])
        self.assertIsNone(state['lease_token'])
        with patch.object(sync.google_sheets_connection,'read_snapshot',return_value=self.make_snapshot([self.row()])):
            self.assertEqual(sync.synchronize(self.config,force=True)['imported'],1)

    def test_expired_lease_cannot_commit_and_unauthenticated_calls_are_denied(self):
        prepared=self.prepare(self.make_snapshot([self.row()]))
        store.confirm_google_sheets_sync(self.config.spreadsheet_id,prepared.sheet_id)
        token=store.acquire_google_sheets_lease(self.config.spreadsheet_id,prepared.sheet_id)
        with sqlite_db.transaction() as c:
            c.execute("UPDATE google_sheets_sync_state SET lease_until='2000-01-01T00:00:00+08:00'")
        with self.assertRaises(ValueError):sync.commit_preview(self.config,prepared,lease_token=token)
        with patch.object(store,'current_owner',side_effect=PermissionError('Expired')):
            with self.assertRaises(PermissionError):store.list_order_notifications()
            with self.assertRaises(PermissionError):store.mark_order_notification_read(mark_all=True)
            with self.assertRaises(PermissionError):sync.synchronize(self.config)

    def test_notification_persistence_read_all_and_revision(self):
        snapshot=self.make_snapshot([self.row()])
        prepared=self.prepare(snapshot)
        before=store.order_data_revision()
        store.activate_google_sheets_preview(self.config.spreadsheet_id,prepared.sheet_id,prepared.preview.records)
        self.assertNotEqual(store.order_data_revision(),before)
        notification=store.list_order_notifications()[0]
        with closing(sqlite_db._connect()) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM order_notifications WHERE read_at IS NULL').fetchone()[0],1)
        store.mark_order_notification_read(mark_all=True)
        self.assertEqual(store.order_notification_counts()['unread'],0)
        self.assertEqual(store.list_order_notifications()[0]['order_id'],notification['order_id'])

    def test_poll_refreshes_dashboard_after_import_or_other_session_changes(self):
        fake=Mock();fake.session_state={}
        with patch.object(ui,'st',fake),patch.object(sync,'synchronize',return_value={'imported':0}),patch.object(store,'order_data_revision',return_value=(1,)):
            ui._run_poll(self.config)
            fake.rerun.assert_not_called()
        with patch.object(ui,'st',fake),patch.object(sync,'synchronize',return_value={'imported':0}),patch.object(store,'order_data_revision',return_value=(2,)):
            ui._run_poll(self.config)
            fake.cache_data.clear.assert_called_once()
            fake.rerun.assert_called_once()

    def test_partial_poll_keeps_review_preview_for_owner(self):
        fake=Mock();fake.session_state={}
        preview=object()
        with patch.object(ui,'st',fake),patch.object(
            sync,'synchronize',
            return_value={'imported':1,'failed':2,'review_required':True,'review_preview':preview},
        ),patch.object(store,'order_data_revision',return_value=(3,)):
            result=ui._run_poll(self.config,force=True)
        self.assertEqual(fake.session_state[ui._PENDING_KEY],preview)
        self.assertNotIn('review_preview',result)
        self.assertEqual(fake.session_state['google_sheets_manual_result']['failed'],2)
        fake.rerun.assert_called_once()

    def test_fragment_timer_and_notification_link_preserve_auth_flow(self):
        root=Path(__file__).resolve().parents[1]
        tree=ast.parse((root/'google_sheets_sync_ui.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='render_google_sheets_sync')
        self.assertIn("run_every='30s'",ast.unparse(fn.decorator_list[0]))
        app_tree=ast.parse((root/'app.py').read_text(encoding='utf-8'))
        fn=next(n for n in app_tree.body if isinstance(n,ast.FunctionDef) and n.name=='_open_notified_order')
        fake=Mock();fake.session_state={}
        navigate=Mock()
        import order_management
        with patch.object(order_management,'_reset_order_filters') as reset:
            namespace=dict(st=fake,navigate_to=navigate)
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'notification-link','exec'),namespace)
            namespace['_open_notified_order'](123)
            reset.assert_called_once()
            navigate.assert_called_once_with('Order Management')
            self.assertEqual(fake.session_state['om_detail_open_id'],123)


class ActualSchemaMappingTests(unittest.TestCase):
    def test_actual_61_column_schema_with_synthetic_values(self):
        import google_sheets_connection as connector
        headers=json.loads((Path(__file__).parent/'fixtures/google_forms_headers.json').read_text())
        self.assertEqual(len(headers),61)
        products={}
        for header in headers:
            name=importer.product_name_from_quantity_header(header)
            if name and name not in products:
                products[name]=dict(id=len(products)+1,name=name.title(),price=35.,unit_cost=10.,active=1)
        row={h:'' for h in headers}
        row.update({"Timestamp":'4/5/2026 10:00:00',"Customer's Name":'Synthetic 61 Column',
            'WhatsApp Phone Number':'0123456789','State':'Selangor','Fullfilment Method':'Pickup',
            'Preferred Pickup / Delivery Date':'5/6/2026','Prefeed Time':'2:30 PM','Preferred Time':'14:30',
            'Product & Quantity [Almond London]':'2','Product & Quantity [Almond London — RM35.00]':'2',
            'Amount Paid (RM)':'70','Payment Method':'Online Transfer',
            'Payment Receipt (Upload Proof of Receipt)':'https://example.invalid/unverified-receipt'})
        snapshot=connector.GoogleSheetsSnapshot(123,headers,[row],[2],locale='en_US',time_zone='Asia/Kuala_Lumpur')
        with patch.object(sync.products_store,'list_products',return_value=list(products.values())),patch.object(store,'google_sheets_row_ledger',return_value=[]),patch.object(store,'google_forms_source_records',return_value=[]):
            prepared=sync.prepare_preview(snapshot,'synthetic-sheet')
        self.assertFalse(prepared.preview.errors)
        record=prepared.preview.records[0]
        self.assertEqual(record['lines'][0]['quantity'],2)
        self.assertEqual(record['subtotal'],70.)
        self.assertEqual(record['order']['fulfilment_date'],'2026-05-06')
        self.assertEqual(record['order']['fulfilment_time'],'14:30')
        self.assertIn('unverified-receipt',record['order']['payment_receipt_reference'])

    def test_historical_spelling_and_legacy_text_share_one_quantity(self):
        self.assertEqual(importer.normalize_product_name('Black Cookies — RM35.00'),'blackout cookies')
        self.assertEqual(importer.normalize_product_name('Shortbread'),'shortbread chocolate')
        self.assertEqual(importer._parse_date('04/05/2026','Date','MDY').isoformat(),'2026-04-05')
        with self.assertRaises(ValueError):importer._parse_date('04/05/2026','Date')
