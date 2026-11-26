"""Read-only deadline calendar helpers; no database or Streamlit imports."""
from calendar import Calendar
from datetime import date
import re

import pandas as pd
from bi_analytics import MALAYSIA_TIMEZONE


def shift_calendar_month(month, offset):
    """Return the first day of an adjacent month, including year transitions."""
    index = month.year * 12 + month.month - 1 + offset
    year, zero_month = divmod(index, 12)
    return date(year, zero_month + 1, 1)


def calendar_weeks(month):
    """Monday-first month grid; dates outside this month are placeholders."""
    return Calendar(firstweekday=0).monthdatescalendar(month.year, month.month)


def malaysia_deadline_date(value):
    """Saved YYYY-MM-DD dates stay local; timestamp values convert to Malaysia.

    Naive timestamps are interpreted as UTC, matching the analytics policy.
    Missing and invalid values remain unassigned.
    """
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None
    try:
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            return None
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize('UTC')
        return timestamp.tz_convert(MALAYSIA_TIMEZONE).date()
    except (ValueError, TypeError, OverflowError):
        return None


def prepare_deadline_orders(orders, today):
    """Classify unique saved orders without mutating their values or records."""
    result = orders.copy()
    if 'id' in result:
        result = result.drop_duplicates('id', keep='first').copy()
    empty = pd.Series('', index=result.index, dtype='object')
    fulfilment = result.get('fulfilment_date', empty)
    due = result.get('due_date', empty)
    missing = fulfilment.isna() | fulfilment.astype('string').str.strip().eq('').fillna(True)
    result['saved_deadline'] = fulfilment.mask(missing, due)
    result['calendar_date'] = result['saved_deadline'].map(malaysia_deadline_date)
    if 'status' not in result:
        result['status'] = pd.Series(index=result.index, dtype='object')

    def state(row):
        if row['status'] in ('Completed', 'Cancelled'):
            return row['status']
        if row['calendar_date'] is None:
            return 'No deadline'
        if row['calendar_date'] < today:
            return 'Overdue'
        if row['calendar_date'] == today:
            return 'Due today'
        return 'Upcoming'

    result['deadline_state'] = result.apply(state, axis=1) if not result.empty else empty
    result['calendar_reference'] = result.get('order_code', empty).fillna('').astype(str)
    if 'id' in result:
        result['calendar_reference'] = result['calendar_reference'].mask(
            result['calendar_reference'].str.strip().eq(''),
            result['id'].map(lambda value: f'Order #{int(value)}'),
        )
    result['calendar_customer'] = result.get('customer', result.get('customer_name', empty)).fillna('')
    return result


def deadline_day_orders(prepared, selected_date):
    """One row per saved order on a calendar date."""
    return prepared.loc[prepared['calendar_date'].eq(selected_date)].copy()


def deadline_month_counts(prepared, month):
    """Counts include all statuses, including completed and cancelled orders."""
    return {
        day: int(prepared['calendar_date'].eq(day).sum())
        for week in calendar_weeks(month) for day in week
        if day.month == month.month
    }
