"""Read-only FR13 rules and explicit-save local FYP settings; no database imports."""
from datetime import date, datetime, timedelta
import json
import math
import os
from pathlib import Path
import re
import tempfile

import pandas as pd
from bi_analytics import MALAYSIA_TIMEZONE, _period_orders

DEFAULT_SETTINGS = dict(aging_hours=48, demand_units=30, demand_days=7, margin_percent=20)


def validate_settings(values):
    """Reject unknown keys, booleans, nonfinite values and unreasonable ranges."""
    if not isinstance(values, dict) or set(values) != set(DEFAULT_SETTINGS):
        raise ValueError('Exactly the four production alert settings are required.')
    limits = dict(aging_hours=(1, 8760), demand_units=(1, 1000000),
                  demand_days=(1, 366), margin_percent=(0, 100))
    result = {}
    for key, (minimum, maximum) in limits.items():
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'{key} must be a finite number.')
        if not minimum <= value <= maximum:
            raise ValueError(f'{key} must be between {minimum} and {maximum}.')
        if key in ('demand_units', 'demand_days') and int(value) != value:
            raise ValueError(f'{key} must be a whole number.')
        result[key] = int(value) if key in ('demand_units', 'demand_days') else float(value)
    return result


def settings_path():
    """Resolve only; never create directories while loading or importing."""
    local = os.environ.get('LOCALAPPDATA')
    if not local:
        raise OSError('LOCALAPPDATA is unavailable; local alert settings cannot be stored.')
    return Path(local) / 'BizMar' / 'production_alert_settings.json'


def load_settings(path=None):
    """Return validated settings and an optional safe warning, without writes."""
    try:
        target = Path(path) if path is not None else settings_path()
        if not target.exists():
            return DEFAULT_SETTINGS.copy(), None
        return validate_settings(json.loads(target.read_text(encoding='utf-8'))), None
    except (OSError, ValueError, TypeError, OverflowError):
        return DEFAULT_SETTINGS.copy(), 'Alert settings could not be read or are invalid. Safe defaults are in use; save valid settings to replace the configuration.'


def save_settings(values, path=None):
    """Explicit Owner Save only. Validate before creating anything; atomic replace."""
    validated = validate_settings(values)
    target = Path(path) if path is not None else settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                         prefix='.production-alerts-', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(validated, handle, allow_nan=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def creation_timestamp(value):
    """Require saved time-of-day precision; SQLite naive timestamps mean UTC."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return None
    if not isinstance(value, (str, datetime, pd.Timestamp)):
        return None
    if isinstance(value, str) and not re.search(r'[T\s]\d{2}:\d{2}', value.strip()):
        return None
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp):
            return None
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize('UTC')
        return stamp.tz_convert(MALAYSIA_TIMEZONE)
    except (ValueError, TypeError, OverflowError):
        return None


def aging_alerts(orders, now, hours=48):
    """Return aged orders and unassessable active orders. No fabricated dates."""
    current = pd.Timestamp(now)
    if current.tzinfo is None:
        raise ValueError('The current time must be timezone-aware.')
    active = orders.copy()
    if active.empty:
        return active, active.copy()
    active = active.drop_duplicates('id')
    active = active.loc[~active['status'].isin(['Completed', 'Cancelled'])].copy()
    saved = active.get('created_at', pd.Series(None, index=active.index, dtype=object))
    active['created_local'] = saved.map(creation_timestamp)
    active['age_hours'] = active['created_local'].map(
        lambda value: (current - value).total_seconds() / 3600 if pd.notna(value) else float('nan'))
    unknown = active.loc[active['age_hours'].isna()].copy()
    return active.loc[active['age_hours'].gt(hours)].sort_values('age_hours', ascending=False), unknown


def demand_alerts(orders, items, today, days=7, units=30):
    """Noncancelled order demand by inclusive Malaysia order date, not inventory."""
    columns = ['product_key', 'product_name', 'ordered_units']
    start = today - timedelta(days=days - 1)
    if orders.empty or items.empty:
        return pd.DataFrame(columns=columns)
    selected = _period_orders(orders.drop_duplicates('id'), start, today)
    lines = items.drop_duplicates('id').loc[lambda rows: rows['order_id'].isin(selected['id'])].copy()
    if lines.empty:
        return pd.DataFrame(columns=columns)
    lines = lines.sort_values('id', kind='stable')
    names = lines['product_name'].fillna('').astype(str).str.strip()
    lines['product_name'] = names.mask(names.eq(''), 'Unnamed product')
    lines['product_key'] = [
        'id:' + str(int(row['product_id'])) if pd.notna(row['product_id']) else
        ('historical:' + row['product_name'] if row['product_name'] != 'Unnamed product'
         else 'historical-line:' + str(row['id'])) for _, row in lines.iterrows()]
    lines['ordered_units'] = pd.to_numeric(lines['quantity'], errors='coerce')
    lines = lines.loc[lines['ordered_units'].map(lambda value: pd.notna(value) and math.isfinite(value) and value > 0)]
    result = lines.groupby('product_key', as_index=False).agg(
        product_name=('product_name', 'last'), ordered_units=('ordered_units', 'sum'))
    return result.loc[result['ordered_units'].gt(units)].sort_values(
        ['ordered_units', 'product_key'], ascending=[False, True]).reset_index(drop=True)


def margin_alerts(products, threshold=20):
    """Current active catalogue gross margins only; undefined values stay separate."""
    active = products.copy()
    if active.empty:
        return active, active.copy()
    active = active.drop_duplicates('id')
    active = active.loc[active['active'].eq(1)].copy()
    for column in ('price', 'unit_cost'):
        active[column] = pd.to_numeric(active[column], errors='coerce')
    valid = active['price'].map(lambda v: pd.notna(v) and math.isfinite(v) and v > 0)
    valid &= active['unit_cost'].map(lambda v: pd.notna(v) and math.isfinite(v) and v >= 0)
    undefined = active.loc[~valid].copy()
    active = active.loc[valid].copy()
    active['gross_margin_percent'] = (active['price'] - active['unit_cost']) / active['price'] * 100
    return active.loc[active['gross_margin_percent'].lt(threshold)].sort_values('gross_margin_percent'), undefined
