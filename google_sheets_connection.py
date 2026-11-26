"""Read-only diagnostic for the configured Google Forms response spreadsheet."""
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import quote

import requests

from google_forms_importer import _parse_date, _parse_time, suggest_column

SHEETS_READONLY_SCOPE = 'https://www.googleapis.com/auth/spreadsheets.readonly'
SHEETS_API = 'https://sheets.googleapis.com/v4/spreadsheets'


class GoogleSheetsConnectionError(RuntimeError):
    """Safe-to-display connection error without credential or response data."""


@dataclass(frozen=True)
class GoogleSheetsConfig:
    spreadsheet_id: str
    worksheet_name: str
    service_account_file: Path
    sync_interval_seconds: int = 30


@dataclass
class GoogleSheetsReport:
    connected: bool
    worksheet_found: bool
    response_rows: int
    headers: list[str]
    date_formats: dict[str, dict[str, Any]]
    field_mappings: dict[str, str | None]
    unmapped_columns: list[str]


@dataclass(frozen=True)
class GoogleSheetsSnapshot:
    sheet_id: int
    headers: list[str]
    rows: list[dict[str, str]]
    row_numbers: list[int]
    locale: str = ''
    time_zone: str = ''


def load_config(secrets: Mapping[str, Any]) -> GoogleSheetsConfig:
    """Read the Google Sheets settings without exposing their values."""
    section = secrets.get('google_sheets')
    if not isinstance(section, Mapping):
        raise GoogleSheetsConnectionError(
            'The [google_sheets] table is missing from Streamlit secrets.'
        )
    spreadsheet_id = str(section.get('spreadsheet_id', '')).strip()
    worksheet_name = str(section.get('worksheet_name', '')).strip()
    service_account_value = str(section.get('service_account_file', '')).strip()
    if not spreadsheet_id or not worksheet_name or not service_account_value:
        raise GoogleSheetsConnectionError(
            'Set spreadsheet_id, worksheet_name, and service_account_file in [google_sheets].'
        )
    key_path = Path(service_account_value).expanduser()
    if not key_path.is_file():
        raise GoogleSheetsConnectionError(
            'The configured service-account JSON key file was not found. '
            'Correct service_account_file in .streamlit/secrets.toml.'
        )
    interval=section.get('sync_interval_seconds',30)
    if isinstance(interval,bool) or not isinstance(interval,int) or not 30<=interval<=3600:
        raise GoogleSheetsConnectionError('Set sync_interval_seconds to an integer from 30 to 3600.')
    if key_path.resolve().is_relative_to(Path(__file__).resolve().parent):
        raise GoogleSheetsConnectionError('Keep the service-account JSON outside the project folder.')
    return GoogleSheetsConfig(spreadsheet_id, worksheet_name, key_path,interval)


def _column_letter(index: int) -> str:
    if index < 0:
        raise ValueError('Column index must be non-negative.')
    result = ''
    while index >= 0:
        index, remainder = divmod(index, 26)
        result = chr(65 + remainder) + result
        index -= 1
    return result


def _quoted_sheet_range(worksheet: str, a1_range: str) -> str:
    escaped_worksheet = worksheet.replace("'", "''")
    return f"'{escaped_worksheet}'!{a1_range}"


def _response_json(response: requests.Response, operation: str) -> dict[str, Any]:
    if response.status_code in (401, 403, 404):
        if response.status_code == 401:
            hint = 'Verify that the service-account JSON key is active and valid.'
        elif response.status_code == 403:
            hint = (
                'Enable the Google Sheets API in the Cloud project and share the sheet '
                'with the service account email as Viewer.'
            )
        else:
            hint = 'Verify the spreadsheet ID and that the service account can access it.'
        raise GoogleSheetsConnectionError(
            f'{operation} failed with HTTP {response.status_code}. {hint}'
        )
    if not response.ok:
        raise GoogleSheetsConnectionError(
            f'{operation} failed with HTTP {response.status_code}. '
            'Check Google Sheets API availability and try again.'
        )
    try:
        result = response.json()
    except ValueError:
        raise GoogleSheetsConnectionError(
            f'{operation} returned an invalid response from Google.'
        ) from None
    if not isinstance(result, dict):
        raise GoogleSheetsConnectionError(
            f'{operation} returned an unexpected response from Google.'
        )
    return result


def _authorized_session(config: GoogleSheetsConfig):
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.auth.exceptions import DefaultCredentialsError
        from google.oauth2 import service_account
    except ImportError as exc:
        raise GoogleSheetsConnectionError(
            'Google authentication dependency is missing. Install requirements.txt.'
        ) from exc
    try:
        credentials = service_account.Credentials.from_service_account_file(
            str(config.service_account_file),
            scopes=[SHEETS_READONLY_SCOPE],
        )
    except (OSError, ValueError, DefaultCredentialsError):
        raise GoogleSheetsConnectionError(
            'Could not load the service-account JSON key. '
            'Verify service_account_file points to a valid downloaded JSON key.'
        ) from None
    return AuthorizedSession(credentials)


def read_snapshot(
    config: GoogleSheetsConfig,
    *,
    session: Any | None = None,
    max_rows: int = 1000,
) -> GoogleSheetsSnapshot:
    """Read the selected worksheet as text without logging or exposing cell values."""
    if session is None:
        owned_session=_authorized_session(config)
        from google.auth.exceptions import GoogleAuthError
        try:
            with owned_session as owned:
                return read_snapshot(config,session=owned,max_rows=max_rows)
        except GoogleAuthError:
            raise GoogleSheetsConnectionError('Google service-account authentication failed. Verify the configured key and access permissions.') from None
    spreadsheet_url = f'{SHEETS_API}/{quote(config.spreadsheet_id, safe="")}'
    try:
        response = session.get(
            spreadsheet_url,
            params={
                'fields': 'properties(locale,timeZone),sheets(properties(sheetId,title,gridProperties(columnCount)))',
            },
            timeout=30,
        )
        metadata = _response_json(response, 'Spreadsheet access check')
    except requests.RequestException as exc:
        raise GoogleSheetsConnectionError(
            f'Network error during spreadsheet access check ({type(exc).__name__}).'
        ) from None

    worksheet = next(
        (
            sheet.get('properties', {})
            for sheet in metadata.get('sheets', [])
            if isinstance(sheet, dict)
            and sheet.get('properties', {}).get('title') == config.worksheet_name
        ),
        None,
    )
    if worksheet is None:
        raise GoogleSheetsConnectionError(
            f'The configured worksheet "{config.worksheet_name}" was not found.'
        )
    sheet_id = worksheet.get('sheetId')
    column_count = worksheet.get('gridProperties', {}).get('columnCount', 0)
    if not isinstance(sheet_id, int) or not isinstance(column_count, int) or column_count < 1:
        raise GoogleSheetsConnectionError(
            'Google Sheets returned invalid worksheet metadata.'
        )
    end_column = _column_letter(column_count - 1)
    values_url = f'{spreadsheet_url}/values/{quote(_quoted_sheet_range(config.worksheet_name, f"A1:{end_column}"), safe="!:$\'")}'
    try:
        response = session.get(
            values_url,
            params={'valueRenderOption': 'FORMATTED_VALUE'},
            timeout=30,
        )
        data = _response_json(response, 'Worksheet response read')
    except requests.RequestException as exc:
        raise GoogleSheetsConnectionError(
            f'Network error while reading worksheet responses ({type(exc).__name__}).'
        ) from None

    values = data.get('values', [])
    if len(values)>max_rows+1:
        raise GoogleSheetsConnectionError(f'The worksheet exceeds the {max_rows:,}-row synchronization limit. Archive older responses before syncing.')
    if not values or not values[0]:
        raise GoogleSheetsConnectionError('The target worksheet has no header row.')
    headers = [str(value).strip() for value in values[0]]
    if any(not value for value in headers) or len({_header for _header in headers}) != len(headers):
        raise GoogleSheetsConnectionError(
            'Worksheet headings must be non-empty and unique before synchronization.'
        )
    rows, row_numbers = [], []
    for row_number, values_row in enumerate(values[1:], start=2):
        cells = [str(value) for value in values_row[:len(headers)]]
        cells.extend([''] * (len(headers) - len(cells)))
        if not any(value.strip() for value in cells):
            continue
        rows.append(dict(zip(headers, cells)))
        row_numbers.append(row_number)
    if len(rows) > max_rows:
        raise GoogleSheetsConnectionError(
            f'The worksheet exceeds the {max_rows:,}-response synchronization limit.'
        )
    return GoogleSheetsSnapshot(
        sheet_id=sheet_id,
        headers=headers,
        rows=rows,
        row_numbers=row_numbers,
        locale=str(metadata.get('properties',{}).get('locale','')),
        time_zone=str(metadata.get('properties',{}).get('timeZone','')),
    )


def _format_label(value: str, kind: str) -> str:
    value = value.strip()
    if kind == 'time':
        if re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2})?', value):
            return '24-hour time'
        if re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2})?\s*[AaPp][Mm]', value):
            return '12-hour time with AM/PM'
        return 'other time format'
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return 'YYYY-MM-DD'
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}[ T].+', value):
        return 'ISO date-time'
    if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}(?:\s+.+)?', value):
        return 'slash-separated date/time'
    return 'other date format'


def _inspect_formats(values: list[str], kind: str) -> dict[str, Any]:
    valid = 0
    formats: dict[str, int] = {}
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        try:
            (_parse_time(text) if kind == 'time' else _parse_date(text, 'Date'))
        except ValueError:
            pass
        else:
            valid += 1
        label = _format_label(text, kind)
        formats[label] = formats.get(label, 0) + 1
    return {
        'checked': sum(formats.values()),
        'valid': valid,
        'invalid': sum(formats.values()) - valid,
        'formats': formats,
    }


def test_connection(
    config: GoogleSheetsConfig,
    *,
    session: Any | None = None,
) -> GoogleSheetsReport:
    """Read sheet metadata, column headers, and only timestamp/date/time columns."""
    if session is None:
        owned_session=_authorized_session(config)
        from google.auth.exceptions import GoogleAuthError
        try:
            with owned_session as owned:
                return test_connection(config,session=owned)
        except GoogleAuthError:
            raise GoogleSheetsConnectionError('Google service-account authentication failed. Verify the configured key and access permissions.') from None

    spreadsheet_url = f'{SHEETS_API}/{quote(config.spreadsheet_id, safe="")}'
    try:
        metadata_response = session.get(
            spreadsheet_url,
            params={
                'fields': 'spreadsheetId,properties(title),sheets(properties(sheetId,title))',
            },
            timeout=30,
        )
        metadata = _response_json(metadata_response, 'Spreadsheet access check')
    except requests.RequestException as exc:
        raise GoogleSheetsConnectionError(
            f'Network error during spreadsheet access check ({type(exc).__name__}). '
            'Check the network and try again.'
        ) from None

    sheets = metadata.get('sheets', [])
    worksheet_found = any(
        sheet.get('properties', {}).get('title') == config.worksheet_name
        for sheet in sheets
        if isinstance(sheet, dict)
    )
    if not worksheet_found:
        return GoogleSheetsReport(
            connected=True,
            worksheet_found=False,
            response_rows=0,
            headers=[],
            date_formats={},
            field_mappings={},
            unmapped_columns=[],
        )

    values_url = f'{spreadsheet_url}/values:batchGet'
    try:
        header_response = session.get(
            values_url,
            params={
                'ranges': _quoted_sheet_range(config.worksheet_name, '1:1'),
                'majorDimension': 'ROWS',
                'valueRenderOption': 'FORMATTED_VALUE',
            },
            timeout=30,
        )
        header_data = _response_json(header_response, 'Worksheet header read')
    except requests.RequestException as exc:
        raise GoogleSheetsConnectionError(
            f'Network error while reading worksheet headers ({type(exc).__name__}).'
        ) from None
    value_ranges = header_data.get('valueRanges', [])
    header_row = value_ranges[0].get('values', [[]])[0] if value_ranges else []
    headers = [str(value).strip() for value in header_row]
    if not headers or any(not header for header in headers):
        raise GoogleSheetsConnectionError(
            'The target worksheet has no complete header row.'
        )

    importer_fields = (
        'response_id', 'customer_name', 'phone', 'ordered_at', 'submitted_at',
        'fulfilment_date', 'fulfilment_time', 'fulfilment_method',
        'delivery_address', 'customer_state', 'delivery_state', 'notes',
        'payment_preference', 'submitted_payment_method', 'submitted_amount_paid',
        'payment_receipt_reference',
    )
    field_mappings = {
        field: suggest_column(field, headers)
        for field in importer_fields
    }
    mapped_headers = {header for header in field_mappings.values() if header}
    unmapped_columns = [header for header in headers if header not in mapped_headers]

    date_columns = {}
    for field in ('submitted_at', 'ordered_at', 'fulfilment_date', 'fulfilment_time'):
        column = field_mappings.get(field)
        if column:
            date_columns.setdefault(column, 'time' if field == 'fulfilment_time' else 'date')
    timestamp_column = field_mappings.get('submitted_at') or headers[0]
    timestamp_index = headers.index(timestamp_column)
    ranges_by_column = {timestamp_index: 'timestamp'}
    for header in date_columns:
        ranges_by_column.setdefault(headers.index(header), 'date')
    ranges = [
        _quoted_sheet_range(
            config.worksheet_name,
            f'{_column_letter(index)}2:{_column_letter(index)}',
        )
        for index in ranges_by_column
    ]
    try:
        columns_response = session.get(
            values_url,
            params={
                'ranges': ranges,
                'majorDimension': 'COLUMNS',
                'valueRenderOption': 'FORMATTED_VALUE',
            },
            timeout=30,
        )
        column_data = _response_json(columns_response, 'Response date-column read')
    except requests.RequestException as exc:
        raise GoogleSheetsConnectionError(
            f'Network error while reading response date columns ({type(exc).__name__}).'
        ) from None

    column_values = column_data.get('valueRanges', [])
    response_rows = 0
    date_formats: dict[str, dict[str, Any]] = {}
    for (column_index, role), value_range in zip(ranges_by_column.items(), column_values):
        rows = value_range.get('values', [])
        values = [str(value[0]) for value in rows if value and str(value[0]).strip()]
        if role == 'timestamp':
            response_rows = len(values)
        for header, kind in date_columns.items():
            if headers[column_index] == header:
                date_formats[header] = _inspect_formats(values, kind)

    return GoogleSheetsReport(
        connected=True,
        worksheet_found=True,
        response_rows=response_rows,
        headers=headers,
        date_formats=date_formats,
        field_mappings=field_mappings,
        unmapped_columns=unmapped_columns,
    )


def main() -> int:
    """Run the read-only diagnostic using the active Streamlit secrets file."""
    try:
        import streamlit as st

        config = load_config(st.secrets)
        report = test_connection(config)
    except GoogleSheetsConnectionError as exc:
        print(f'Connection status: FAILED\nError: {exc}')
        return 1

    print(f'Connection status: {"CONNECTED" if report.connected else "FAILED"}')
    print(f'Worksheet found: {"Yes" if report.worksheet_found else "No"}')
    print(f'Response rows (non-empty timestamp cells): {report.response_rows}')
    print(f'Columns: {len(report.headers)}')
    print('Headers: ' + ' | '.join(report.headers))
    print('Importer field mappings:')
    for field, column in report.field_mappings.items():
        print(f'  {field}: {column or "not auto-recognized; manual mapping available"}')
    print(
        'Unmapped headers to review for product quantity columns: '
        + ', '.join(report.unmapped_columns)
    )
    print('Date/time validation:')
    for column, result in report.date_formats.items():
        format_summary = ', '.join(
            f'{label} ({count})' for label, count in result['formats'].items()
        )
        print(
            f'  {column}: {result["valid"]}/{result["checked"]} valid; '
            f'{result["invalid"]} invalid; formats: {format_summary or "no values"}'
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
