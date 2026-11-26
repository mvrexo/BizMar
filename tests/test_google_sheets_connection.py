"""Synthetic, read-only tests for Google Sheets connection diagnostics."""
from pathlib import Path
import unittest

from google_sheets_connection import (
    GoogleSheetsConfig,
    GoogleSheetsConnectionError,
    _column_letter,
    _inspect_formats,
    load_config,
    test_connection,
)


class GoogleSheetsConnectionTests(unittest.TestCase):
    def test_column_letters_cover_google_sheets_boundaries(self):
        self.assertEqual(
            [_column_letter(index) for index in (0, 25, 26, 27, 51, 52, 701, 702)],
            ['A', 'Z', 'AA', 'AB', 'AZ', 'BA', 'ZZ', 'AAA'],
        )

    def test_date_and_time_formats_are_validated_without_returning_values(self):
        dates = _inspect_formats(
            ['2026-10-28', '28/10/2026', '10/28/2026', 'not a date'],
            'date',
        )
        self.assertEqual(dates['checked'], 4)
        self.assertEqual(dates['valid'], 3)
        self.assertEqual(dates['invalid'], 1)
        self.assertNotIn('2026-10-28', repr(dates))

        times = _inspect_formats(['14:30', '2:30 PM', 'not a time'], 'time')
        self.assertEqual(times['valid'], 2)
        self.assertEqual(times['invalid'], 1)

    def test_missing_service_account_key_fails_without_exposing_its_path(self):
        config = {
            'google_sheets': {
                'spreadsheet_id': 'synthetic-sheet-id',
                'worksheet_name': 'Form Responses 1',
                'service_account_file': str(Path('missing-private-service-key.json')),
            }
        }
        with self.assertRaises(GoogleSheetsConnectionError) as caught:
            load_config(config)
        self.assertIn('was not found', str(caught.exception))
        self.assertNotIn('missing-private-service-key', str(caught.exception))

    def test_connection_reads_only_headers_and_date_columns(self):
        class Response:
            status_code = 200
            ok = True

            def __init__(self, value):
                self.value = value

            def json(self):
                return self.value

        class Session:
            def __init__(self):
                self.calls = []
                self.responses = [
                    {'sheets': [{'properties': {'title': 'Form Responses 1'}}]},
                    {'valueRanges': [{'values': [[
                        'Response ID', 'Timestamp', 'Customer Name', 'Phone Number',
                        'Delivery Date', 'Delivery Method', 'Address',
                        'Chocolate RM25', 'Vanilla RM30', 'Payment Reference',
                    ]]}]},
                    {'valueRanges': [
                        {'values': [['10/28/2026 2:30:45 PM'], ['10/29/2026 9:45:00 AM']]},
                        {'values': [['10/30/2026'], ['31/10/2026']]},
                    ]},
                ]

            def get(self, url, *, params, timeout):
                self.calls.append((url, params, timeout))
                return Response(self.responses.pop(0))

        session = Session()
        report = test_connection(
            GoogleSheetsConfig(
                spreadsheet_id='synthetic-sheet-id',
                worksheet_name='Form Responses 1',
                service_account_file=Path('unused-injected-session.json'),
            ),
            session=session,
        )
        self.assertTrue(report.connected)
        self.assertTrue(report.worksheet_found)
        self.assertEqual(report.response_rows, 2)
        self.assertEqual(len(report.headers), 10)
        self.assertEqual(report.field_mappings['customer_name'], 'Customer Name')
        self.assertEqual(report.field_mappings['phone'], 'Phone Number')
        self.assertEqual(report.field_mappings['payment_receipt_reference'],'Payment Reference')
        self.assertEqual(report.unmapped_columns, ['Chocolate RM25', 'Vanilla RM30'])
        queried_ranges = session.calls[2][1]['ranges']
        self.assertIn("'Form Responses 1'!B2:B", queried_ranges)
        self.assertIn("'Form Responses 1'!E2:E", queried_ranges)
        self.assertFalse(any(
            customer_column in queried_range
            for queried_range in queried_ranges
            for customer_column in ('C2:C', 'D2:D', 'G2:G')
        ))
        self.assertEqual(report.date_formats['Timestamp']['valid'], 2)
        self.assertEqual(report.date_formats['Timestamp']['invalid'], 0)


if __name__ == '__main__':
    unittest.main()
