"""Small, query-free trends from the dashboard's filtered SQLite snapshots."""
from html import escape
import math

import pandas as pd
import streamlit as st


@st.cache_data(show_spinner=False, max_entries=64)
def daily_kpi_trends(orders, raw_items, start, end):
    """Content-keyed cache: any order/payment-derived KPI change invalidates it.

    Revenue/profit deliberately reuse load()'s existing definitions, not cash
    collection. Outstanding history is unavailable: audit summaries do not retain
    complete historical totals, cancellation and payment reversal snapshots.
    """
    result = {key: None for key in ('orders', 'revenue', 'profit', 'balance')}
    if orders.empty or start > end:
        return result
    data = orders.copy()
    dates = pd.to_datetime(data['ordered_at'], errors='coerce', utc=True, format='mixed')
    data['day'] = dates.dt.tz_convert('Asia/Kuala_Lumpur').dt.tz_localize(None).dt.normalize()
    data = data.loc[data['status'].ne('Cancelled') & data['day'].between(pd.Timestamp(start), pd.Timestamp(end))]
    # Invalid dates cannot be assigned to a day without inventing information.
    if data.empty or dates.loc[orders['status'].ne('Cancelled')].isna().any():
        return result
    days = pd.date_range(start, end, freq='D')
    if len(days) < 2:
        return result
    grouped = data.groupby('day')
    result['orders'] = grouped.size().reindex(days, fill_value=0).astype(float).tolist()
    for key in ('revenue', 'profit'):
        values = pd.to_numeric(data[key], errors='coerce')
        if not values.map(lambda value: pd.notna(value) and math.isfinite(value)).all():
            continue
        if key == 'profit':
            # Never substitute today's catalog cost for a missing saved cost.
            if raw_items.empty or not {'order_id', 'quantity', 'unit_cost'}.issubset(raw_items.columns):
                continue
            lines = raw_items.loc[raw_items['order_id'].isin(data['id'])].copy()
            costs = pd.to_numeric(lines['unit_cost'], errors='coerce')
            quantities = pd.to_numeric(lines['quantity'], errors='coerce')
            if (not set(data['id']).issubset(set(lines['order_id']))
                    or not (costs.map(lambda v: pd.notna(v) and math.isfinite(v))
                            & quantities.map(lambda v: pd.notna(v) and math.isfinite(v) and v > 0)).all()):
                continue
        result[key] = data.assign(value=values).groupby('day')['value'].sum().reindex(days, fill_value=0).tolist()
    return result


def sparkline_html(values, tone, label, *, unavailable=False):
    """Inline SVG keeps the chart inside the existing HTML card, without iframes.

    Monotone cubic interpolation has zero tangents at extrema: smoothing cannot
    introduce fabricated peaks. Original daily samples are retained in the path.
    """
    if values is None or len(values) < 2:
        if unavailable:
            return '<div class="bizmar-spark-empty" aria-hidden="true"></div>'
        return '<div class="bizmar-spark-empty" role="note">Not enough data</div>'
    low, high = min(0, min(values)), max(0, max(values))
    span = high - low or 1
    points = [(2 + i * 296 / (len(values)-1), 46-(value-low)*40/span) for i, value in enumerate(values)]
    slopes = [(points[i+1][1]-points[i][1])/(points[i+1][0]-points[i][0]) for i in range(len(points)-1)]
    tangents = [slopes[0]] + [0 if a*b <= 0 else 2*a*b/(a+b) for a,b in zip(slopes,slopes[1:])] + [slopes[-1]]
    path = f'M {points[0][0]:.3f},{points[0][1]:.3f}'
    for i, ((x,y),(nx,ny)) in enumerate(zip(points,points[1:])):
        step=(nx-x)/3
        path += f' C {x+step:.3f},{y+tangents[i]*step:.3f} {nx-step:.3f},{ny-tangents[i+1]*step:.3f} {nx:.3f},{ny:.3f}'
    tone = tone if tone in ('lavender','pink','mint','peach') else 'mint'
    title = escape(label + ': daily trend for selected period')
    return (f'<svg class="bizmar-spark bizmar-spark-{tone}" viewBox="0 0 300 50" preserveAspectRatio="none" role="img" aria-label="{title}">'
            f'<title>{title}</title><path d="{path} L 298,49 L 2,49 Z" fill="currentColor" fill-opacity="0.12" stroke="none"/>'
            f'<path d="{path}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linecap="round"/></svg>')
