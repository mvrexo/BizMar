"""FR10/FR11 read-only analytics over saved SQLite snapshots. No I/O."""
from datetime import timedelta

import pandas as pd
from bi_analytics import MALAYSIA_TIMEZONE, _period_orders

MONEY_COLUMNS = ['revenue', 'recorded_cost', 'gross_profit']
TREND_COLUMNS = ['period_start', 'period', *MONEY_COLUMNS, 'gross_margin_percent', 'order_count']


def financial_orders(orders, items, start, end):
    """One row per qualifying order, one contribution per saved order-line ID.

    No catalogue lookup. Missing/invalid snapshots remain undefined, never
    silently zero-filled. A saved order with no lines has zero booked value.
    """
    selected = _period_orders(orders.drop_duplicates('id') if 'id' in orders else orders, start, end)
    selected = selected.drop(columns=[*MONEY_COLUMNS, 'gross_margin_percent'], errors='ignore').copy()
    for column in MONEY_COLUMNS:
        selected[column] = pd.Series(0.0, index=selected.index)
    if selected.empty or start > end:
        return selected.iloc[:0].copy()
    if not items.empty:
        lines = items.drop_duplicates('id').loc[lambda frame: frame['order_id'].isin(selected['id'])].copy()
        if not lines.empty:
            for column in ('quantity', 'unit_price', 'unit_cost'):
                lines[column] = pd.to_numeric(lines[column], errors='coerce')
                lines[column] = lines[column].where(lines[column].between(0, float('inf'), inclusive='left'))
            lines['revenue'] = lines['quantity'] * lines['unit_price']
            lines['recorded_cost'] = lines['quantity'] * lines['unit_cost']
            totals = lines.groupby('order_id')[['revenue', 'recorded_cost']].agg(_complete_sum)
            for column in ('revenue', 'recorded_cost'):
                has_lines = selected['id'].isin(totals.index)
                selected.loc[has_lines, column] = selected.loc[has_lines, 'id'].map(totals[column])
    # Order-level adjustments are kept separate from historical product snapshots.
    for field, sign in (('discount', -1), ('delivery_fee', 1)):
        if field in selected:
            selected['revenue'] = selected['revenue'] + sign * pd.to_numeric(selected[field], errors='coerce').fillna(0)
    selected['gross_profit'] = selected['revenue'] - selected['recorded_cost']
    selected['malaysia_order_date'] = pd.to_datetime(
        selected['ordered_at'], errors='coerce', utc=True
    ).dt.tz_convert(MALAYSIA_TIMEZONE).dt.date
    return selected


def _complete_sum(values):
    return values.sum(min_count=len(values))


def _period_start(day, aggregation):
    if aggregation == 'Daily':
        return day
    if aggregation == 'Weekly':
        return day - timedelta(days=day.weekday())
    if aggregation == 'Monthly':
        return day.replace(day=1)
    return day.replace(month=1, day=1)


def _next_period(day, aggregation):
    if aggregation == 'Daily':
        return day + timedelta(days=1)
    if aggregation == 'Weekly':
        return day + timedelta(days=7)
    if aggregation == 'Monthly':
        return day.replace(year=day.year + 1, month=1) if day.month == 12 else day.replace(month=day.month + 1)
    return day.replace(year=day.year + 1)


def profitability_trend(orders, items, start, end, aggregation='Monthly', max_periods=5000):
    """Zero-filled selected range, clipped edge periods, ISO Monday weeks.

    Refuse excessive output rather than silently truncate or change granularity.
    """
    if aggregation not in ('Daily', 'Weekly', 'Monthly', 'Yearly'):
        raise ValueError('Choose Daily, Weekly, Monthly or Yearly aggregation.')
    if start > end:
        return pd.DataFrame(columns=TREND_COLUMNS)
    first, last = _period_start(start, aggregation), _period_start(end, aggregation)
    periods, current = [], first
    while True:
        periods.append(current)
        if len(periods) > max_periods:
            raise ValueError('Selected range exceeds 5,000 periods. Narrow the dates or choose a coarser aggregation.')
        if current == last:
            break
        current = _next_period(current, aggregation)
    selected = financial_orders(orders, items, start, end)
    result = pd.DataFrame({'period_start': periods})
    if selected.empty:
        for column in MONEY_COLUMNS:
            result[column] = 0.0
        result['order_count'] = 0
    else:
        selected['period_start'] = selected['malaysia_order_date'].map(lambda day: _period_start(day, aggregation))
        grouped = selected.groupby('period_start')[MONEY_COLUMNS].agg(_complete_sum)
        grouped['order_count'] = selected.groupby('period_start')['id'].nunique()
        result = result.merge(grouped, on='period_start', how='left')
        no_orders = result['order_count'].isna()
        result.loc[no_orders, MONEY_COLUMNS] = 0.0
        result['order_count'] = result['order_count'].fillna(0).astype(int)
    def label(day):
        if aggregation == 'Weekly':
            year, week, _ = day.isocalendar()
            return f'{year}-W{week:02d}'
        return day.strftime({'Daily': '%Y-%m-%d', 'Monthly': '%Y-%m', 'Yearly': '%Y'}[aggregation])
    result['period'] = result['period_start'].map(label)
    result['gross_margin_percent'] = result['gross_profit'].div(result['revenue'].where(result['revenue'].ne(0))) * 100
    return result[TREND_COLUMNS]


def repeat_customer_insights(orders, items, customers, start, end):
    """Denominator = known stable customer IDs with >=1 qualifying scoped order.

    Registered customers with no scoped orders are not in the denominator.
    Archived known IDs remain identifiable. Unknown IDs never group by name.
    """
    selected = financial_orders(orders, items, start, end)
    columns = ['customer_id', 'customer_reference', 'customer_name', 'order_count',
               *MONEY_COLUMNS, 'latest_order_date']
    known = customers.drop_duplicates('id').copy() if 'id' in customers else pd.DataFrame(columns=['id'])
    if not selected.empty:
        identified = selected['customer_id'].notna() & selected['customer_id'].isin(known['id'])
        unresolved = selected.loc[~identified].copy()
        selected = selected.loc[identified].copy()
    else:
        unresolved = selected.copy()
    if selected.empty:
        summary = pd.DataFrame(columns=columns)
    else:
        grouped = selected.groupby('customer_id')[MONEY_COLUMNS].agg(_complete_sum)
        grouped['order_count'] = selected.groupby('customer_id')['id'].nunique()
        grouped['latest_order_date'] = selected.groupby('customer_id')['malaysia_order_date'].max()
        summary = grouped.reset_index()
        names, references = {}, {}
        for _, row in known.iterrows():
            def text(value):
                return '' if pd.isna(value) else str(value).strip()
            names[row['id']] = text(row.get('full_name', '')) or text(row.get('name', '')) or 'Unnamed customer'
            references[row['id']] = text(row.get('customer_id', '')) or f"Customer #{int(row['id'])}"
        summary['customer_name'] = summary['customer_id'].map(names)
        summary['customer_reference'] = summary['customer_id'].map(references)
        summary = summary[columns].sort_values(['order_count', 'customer_id'], ascending=[False, True]).reset_index(drop=True)
    repeats = summary.loc[summary['order_count'].ge(2)].copy()
    count = len(summary)
    return dict(customers=summary, repeats=repeats, unresolved=unresolved,
                identifiable_count=count, repeat_count=len(repeats),
                repeat_rate=len(repeats) / count * 100 if count else None,
                identified_orders=selected)
