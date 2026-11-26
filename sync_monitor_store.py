"""Owner-guarded read models and credential-free sync attempt accounting."""
from contextlib import closing
import sqlite_db

ERRORS={
    'Connection':'Google Sheets is unavailable. Check the connection and retry.',
    'Validation':'Responses require owner review. No partial batch was imported.',
    'Partial':'Valid new orders were imported; some source rows still require owner review.',
    'Internal':'Synchronization could not finish safely. Retry or review the source.',
    'Interrupted':'The previous attempt ended without a completion report.'}


def begin_attempt(connection,spreadsheet_id,worksheet_id,token,trigger,started,expires):
    if trigger not in ('Automatic','Manual'):
        raise ValueError('Invalid sync trigger.')
    connection.execute("""UPDATE google_sheets_sync_history SET result='Failed',finished_at=?,error_kind='Interrupted',error_summary=?
        WHERE spreadsheet_id=? AND result='Running' AND lease_expires_at<=?""",(started,ERRORS['Interrupted'],str(spreadsheet_id),started))
    connection.execute('''INSERT INTO google_sheets_sync_history
        (spreadsheet_id,worksheet_id,lease_token,started_at,lease_expires_at,trigger)
        VALUES(?,?,?,?,?,?)''',(str(spreadsheet_id),int(worksheet_id),token,started,expires,trigger))


def finish_attempt(connection,spreadsheet_id,token,finished,*,imported=0,associated=0,skipped=0,failed_rows=0,error_kind=''):
    kind=error_kind if error_kind in ERRORS else ('Internal' if error_kind else '')
    connection.execute('''UPDATE google_sheets_sync_history SET finished_at=?,result=?,imported=?,associated=?,skipped=?,failed_rows=?,error_kind=?,error_summary=?
        WHERE spreadsheet_id=? AND lease_token=? AND result='Running' ''',
        (finished,'Partial' if kind=='Partial' else 'Failed' if kind else 'Success',
         int(imported),int(associated),int(skipped),int(failed_rows),kind,
         ERRORS.get(kind,''),str(spreadsheet_id),token))


def monitor_data(spreadsheet_id):
    import orders_store
    orders_store._authorize()
    with closing(sqlite_db._connect()) as connection:
        state=connection.execute('SELECT * FROM google_sheets_sync_state WHERE spreadsheet_id=?',(str(spreadsheet_id),)).fetchone()
        history=[dict(r) for r in connection.execute('SELECT id,started_at,finished_at,trigger,result,imported,associated,skipped,failed_rows,error_kind,error_summary FROM google_sheets_sync_history WHERE spreadsheet_id=? ORDER BY id DESC LIMIT 20',(str(spreadsheet_id),))]
        totals=dict(connection.execute('''SELECT COALESCE(SUM(failed_rows),0) AS failed_imports,COALESCE(SUM(skipped),0) AS skipped_total,
            COALESCE(SUM(CASE WHEN result='Failed' THEN 1 ELSE 0 END),0) AS failed_attempts
            FROM google_sheets_sync_history WHERE spreadsheet_id=?''',(str(spreadsheet_id),)).fetchone())
        linked=connection.execute('SELECT COUNT(*) FROM google_sheets_rows WHERE spreadsheet_id=?',(str(spreadsheet_id),)).fetchone()[0]
        imported=connection.execute('''SELECT COUNT(*) FROM google_sheets_rows r JOIN order_notifications n ON n.source_key=r.response_key
            WHERE r.spreadsheet_id=?''',(str(spreadsheet_id),)).fetchone()[0]
        latest_success=connection.execute("SELECT imported,finished_at FROM google_sheets_sync_history WHERE spreadsheet_id=? AND result='Success' ORDER BY id DESC LIMIT 1",(str(spreadsheet_id),)).fetchone()
    return dict(state=dict(state) if state else {},history=history,total_imported=imported,linked_responses=linked,
                existing_associations=linked-imported,latest_success=dict(latest_success) if latest_success else {},**totals)
