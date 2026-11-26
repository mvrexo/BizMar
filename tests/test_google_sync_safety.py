"""Configuration and transport safety; no private configuration or network."""
from pathlib import Path
import unittest
import test_uat_auth_preflight as auth_fixtures
import uat_auth_preflight as preflight
from google_sheets_connection import GoogleSheetsConfig,GoogleSheetsConnectionError,read_snapshot


class GoogleSyncSafetyTests(unittest.TestCase):
    def test_preflight_allows_only_narrow_readonly_sheets_settings(self):
        secrets,approval=auth_fixtures.fixture()
        secrets['google_sheets']=dict(spreadsheet_id='synthetic-sheet-id',worksheet_name='Form Responses 1',
            service_account_file=str(Path(__file__).resolve().parents[2]/'outside-test-key.json'),sync_interval_seconds=30)
        self.assertEqual(preflight.validate_configuration(secrets,approval)['status'],'passed')
        secrets['google_sheets']['service_role_key']='forbidden'
        with self.assertRaises(preflight.PreflightError):preflight.validate_configuration(secrets,approval)
        secrets['google_sheets'].pop('service_role_key')
        secrets['google_sheets']['sync_interval_seconds']=1
        with self.assertRaises(preflight.PreflightError):preflight.validate_configuration(secrets,approval)
        secrets['google_sheets']['sync_interval_seconds']=30
        secrets['google_sheets']['service_account_file']=str(Path(__file__).resolve().parents[1]/'key.json')
        with self.assertRaises(preflight.PreflightError):preflight.validate_configuration(secrets,approval)

    def test_snapshot_locale_and_row_limit_do_not_silently_truncate(self):
        class Response:
            ok=True;status_code=200
            def __init__(self,data):self.data=data
            def json(self):return self.data
        class Session:
            def __init__(self):self.calls=0
            def get(self,*args,**kwargs):
                self.calls+=1
                return Response({'properties':{'locale':'en_US','timeZone':'Asia/Kuala_Lumpur'},
                    'sheets':[{'properties':{'title':'Form Responses 1','sheetId':5,'gridProperties':{'columnCount':1}}}]}
                    if self.calls==1 else {'values':[['Timestamp'],['one'],['two']]})
        config=GoogleSheetsConfig('synthetic','Form Responses 1',Path('unused.json'))
        with self.assertRaises(GoogleSheetsConnectionError):read_snapshot(config,session=Session(),max_rows=1)
        snapshot=read_snapshot(config,session=Session(),max_rows=2)
        self.assertEqual(snapshot.locale,'en_US')
        self.assertEqual(snapshot.row_numbers,[2,3])
