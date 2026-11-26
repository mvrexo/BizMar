"""Pure BizMar BI aggregations. No database, authentication or Streamlit imports."""
import pandas as pd

MALAYSIA_TIMEZONE = 'Asia/Kuala_Lumpur'
PROFIT_COLUMNS = [
    'product_key', 'product_id', 'product_name', 'units_sold',
    'revenue', 'recorded_cost', 'gross_profit',
]


def _period_orders(orders, start, end):
    """Include all non-cancelled statuses by inclusive Malaysia order date.

    Naive timestamps are interpreted as UTC, matching the established app policy.
    Invalid timestamps are excluded. No source data is mutated.
    """
    if orders.empty:
        return orders.copy()
    dates = pd.to_datetime(orders['ordered_at'], errors='coerce', utc=True)
    dates = dates.dt.tz_convert(MALAYSIA_TIMEZONE).dt.date
    return orders.loc[
        orders['status'].ne('Cancelled') & dates.notna()
        & dates.ge(start) & dates.le(end)
    ].copy()


def daily_order_volume(orders, start, end):
    """Count unique orders, not items, including zero days within the period."""
    if start > end:
        return pd.DataFrame(columns=['date', 'order_count'])
    days = pd.date_range(start=start, end=end, freq='D', name='date')
    selected = _period_orders(orders, start, end)
    if selected.empty:
        counts = pd.Series(0, index=days, dtype='int64', name='order_count')
    else:
        selected['date'] = pd.to_datetime(
            selected['ordered_at'], errors='coerce', utc=True
        ).dt.tz_convert(MALAYSIA_TIMEZONE).dt.tz_localize(None).dt.normalize()
        counts = selected.groupby('date')['id'].nunique().reindex(days, fill_value=0)
        counts = counts.astype('int64').rename('order_count')
    return counts.reset_index()


def product_profitability(orders, items, start, end):
    """Rank gross profit using saved quantity, selling-price and cost snapshots.

    A retained product ID defines identity regardless of name changes. Deleted
    product references are grouped by saved name, separately from live IDs.
    Original IDs cannot be recovered after ON DELETE SET NULL.
    """
    if start > end or orders.empty or items.empty:
        return pd.DataFrame(columns=PROFIT_COLUMNS)
    selected = _period_orders(orders, start, end)
    lines = items.loc[items['order_id'].isin(selected['id'])].copy()
    if lines.empty:
        return pd.DataFrame(columns=PROFIT_COLUMNS)
    if 'id' in lines:
        lines = lines.sort_values('id', kind='stable')
    names = lines['product_name'].fillna('').astype(str).str.strip()
    lines['product_name'] = names.mask(names.eq(''), 'Unnamed product')
    keys = []
    for index, row in lines.iterrows():
        if pd.notna(row['product_id']):
            keys.append('id:' + str(int(row['product_id'])))
        elif str(row['product_name']) != 'Unnamed product':
            keys.append('historical:' + row['product_name'])
        else:
            keys.append('historical-line:' + str(row.get('id', index)))
    lines['product_key'] = keys
    for column in ('quantity', 'unit_price', 'unit_cost'):
        lines[column] = pd.to_numeric(lines[column], errors='raise')
    lines['revenue'] = lines['quantity'] * lines['unit_price']
    lines['recorded_cost'] = lines['quantity'] * lines['unit_cost']
    lines['gross_profit'] = lines['quantity'] * (lines['unit_price'] - lines['unit_cost'])
    ranking = lines.groupby('product_key', as_index=False, sort=False).agg(
        product_id=('product_id', 'first'),
        product_name=('product_name', 'last'),
        units_sold=('quantity', 'sum'),
        revenue=('revenue', 'sum'),
        recorded_cost=('recorded_cost', 'sum'),
        gross_profit=('gross_profit', 'sum'),
    )
    ranking = ranking.sort_values(
        ['gross_profit', 'revenue', 'product_key'],
        ascending=[False, False, True], kind='stable',
    ).reset_index(drop=True)
    return ranking[PROFIT_COLUMNS]
