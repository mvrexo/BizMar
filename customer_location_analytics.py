"""Customer-state analytics and verified Malaysian administrative boundaries.

Customers are counted only when they have a non-cancelled order in the selected
period. State assignment prefers the current customer profile; if it is missing
or invalid, the most frequent valid residence snapshot on qualifying orders is
used, with alphabetical state order breaking ties. Delivery destinations are
not treated as customer residence.

Map geometry: geoBoundaries gbOpen Malaysia ADM1 (2017), derived from
OpenStreetMap/Wambacher, ODbL 1.0. See assets/malaysia_adm1.geojson.
"""
from display_preferences import tr
from collections import Counter
import json
import math
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from malaysian_states import STATES, canonical as canonical_state
from sales_period import filter_period

ROOT = Path(__file__).resolve().parent
GEOJSON_PATH = ROOT / 'assets' / 'malaysia_adm1.geojson'
UNKNOWN = 'Unknown'

def normalize_state(value):
    """Return a canonical Malaysian state name, or ``None`` for unknown input."""
    return canonical_state(value)


def _frame(rows):
    return rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)


def _identity(value):
    if value is None or pd.isna(value):
        return None
    return str(value)


def _states_for_customers(customers, orders):
    customer_states = {}
    if 'id' in customers:
        for row in customers.to_dict('records'):
            identity = _identity(row.get('id'))
            if identity is not None:
                customer_states[identity] = normalize_state(row.get('state'))

    snapshot_states = {}
    for row in orders.to_dict('records'):
        identity = _identity(row.get('customer_id'))
        if identity is None:
            continue
        state = normalize_state(row.get('customer_state_snapshot'))
        if state is not None:
            snapshot_states.setdefault(identity, []).append(state)

    assigned = {}
    for identity in orders.get('customer_id', pd.Series(dtype='object')).map(_identity).dropna().unique():
        state = customer_states.get(identity)
        if state is None:
            counts = Counter(snapshot_states.get(identity, []))
            if counts:
                highest = max(counts.values())
                state = min(name for name, count in counts.items() if count == highest)
        assigned[identity] = state or UNKNOWN
    return assigned


def build_location_metrics(customers, orders, start=None, end=None):
    """Aggregate non-cancelled orders in a selected date range without DB writes."""
    customer_frame = _frame(customers)
    order_frame = _frame(orders)
    if start is not None or end is not None:
        if start is None or end is None:
            raise ValueError('Provide both start and end dates for location analytics.')
        order_frame = filter_period(order_frame, start, end)

    if 'status' in order_frame:
        order_frame = order_frame.loc[order_frame['status'].ne('Cancelled')].copy()
    if 'customer_id' not in order_frame:
        order_frame['customer_id'] = pd.Series(dtype='object')
    if 'id' not in order_frame:
        order_frame['id'] = range(len(order_frame))

    assignments = _states_for_customers(customer_frame, order_frame)
    order_frame['_customer_key'] = order_frame['customer_id'].map(_identity)
    order_frame['State'] = order_frame['_customer_key'].map(assignments).fillna(UNKNOWN)

    known_customer_ids = {
        identity for identity, state in assignments.items() if state != UNKNOWN
    }
    known_order_count = int(order_frame['State'].ne(UNKNOWN).sum())
    known_customer_count = len(known_customer_ids)
    unknown_customer_count = len(assignments) - known_customer_count
    unknown_order_count = int(order_frame['State'].eq(UNKNOWN).sum())

    customer_counts = Counter(
        state for state in assignments.values() if state != UNKNOWN
    )
    order_counts = order_frame.loc[order_frame['State'].ne(UNKNOWN), 'State'].value_counts().to_dict()
    rows = []
    for state in STATES:
        customers_in_state = int(customer_counts.get(state, 0))
        orders_in_state = int(order_counts.get(state, 0))
        rows.append({
            'state': state,
            'customer_count': customers_in_state,
            'order_count': orders_in_state,
            'customer_percent': (100 * customers_in_state / known_customer_count) if known_customer_count else 0.,
            'order_percent': (100 * orders_in_state / known_order_count) if known_order_count else 0.,
        })
    return {
        'states': pd.DataFrame(rows),
        'known_customers': known_customer_count,
        'known_orders': known_order_count,
        'unknown_customers': unknown_customer_count,
        'unknown_orders': unknown_order_count,
        'total_customers': len(assignments),
        'total_orders': len(order_frame),
    }


@st.cache_data(show_spinner=False)
def load_state_geojson():
    """Load and validate real geoBoundaries state polygons bundled with the app."""
    with GEOJSON_PATH.open(encoding='utf-8') as source:
        geojson = json.load(source)
    if geojson.get('type') != 'FeatureCollection':
        raise ValueError('The Malaysia boundary file must be a GeoJSON FeatureCollection.')
    features = geojson.get('features')
    if not isinstance(features, list) or len(features) != len(STATES):
        raise ValueError('The Malaysia state boundary file must contain all 16 ADM1 regions.')
    names = []
    for feature in features:
        properties = feature.get('properties') or {}
        state = normalize_state(properties.get('shapeName'))
        geometry = feature.get('geometry') or {}
        if state is None or geometry.get('type') not in ('Polygon', 'MultiPolygon'):
            raise ValueError('The Malaysia state boundary file contains an invalid state polygon.')
        polygons = [geometry.get('coordinates')] if geometry['type'] == 'Polygon' else geometry.get('coordinates')
        if not polygons:
            raise ValueError('The Malaysia boundary file contains empty geometry.')
        for polygon in polygons:
            if not polygon:
                raise ValueError('The Malaysia boundary file contains an empty polygon.')
            for ring_index, ring in enumerate(polygon):
                if not ring or len(ring) < 4 or ring[0] != ring[-1]:
                    raise ValueError('The Malaysia boundary file contains an invalid polygon ring.')
                for point in ring:
                    if len(point) < 2 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in point[:2]) or not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90):
                        raise ValueError('The Malaysia boundary file contains invalid coordinates.')
                signed_area = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]))
                if signed_area == 0:
                    raise ValueError('The Malaysia boundary file contains a zero-area polygon.')
                # Plotly's D3 geographic renderer expects clockwise exterior rings.
                # The source uses the opposite RFC 7946 convention; uncorrected
                # rings paint the rest of the globe and zero-valued states mask it.
                if (ring_index == 0 and signed_area > 0) or (ring_index > 0 and signed_area < 0):
                    ring.reverse()
        properties['bizmarState'] = state
        names.append(state)
    if set(names) != set(STATES) or len(set(names)) != len(STATES):
        raise ValueError('The Malaysia state boundary file does not match the state catalogue.')
    return geojson


def render_location_map(metrics, metric='customer_count'):
    """Render a responsive choropleth for customer or order counts."""
    if metric not in ('customer_count', 'order_count', 'revenue'):
        raise ValueError('Choose customer_count, order_count or revenue for the map.')
    rows = metrics['states']
    if rows.empty or 'state' not in rows or metric not in rows:
        st.info(tr('No geographical data available'))
        return
    rows = rows.copy()
    rows['state'] = rows['state'].map(normalize_state)
    rows = rows.loc[rows['state'].notna()]
    if rows.empty or pd.to_numeric(rows[metric], errors='coerce').fillna(0).sum() <= 0:
        st.info(tr('No geographical data available'))
        return
    percent_column = {'customer_count':'customer_percent','order_count':'order_percent','revenue':'revenue_percent'}[metric]
    label = {'customer_count':'Customers','order_count':'Orders','revenue':'Recognized Sales (RM)'}[metric]
    try:
        geojson = load_state_geojson()
    except (OSError, ValueError, TypeError):
        st.error(tr('Malaysia map boundaries could not be loaded. Please check the bundled map assets.'))
        return
    figure = px.choropleth(
        rows,
        geojson=geojson,
        locations='state',
        featureidkey='properties.bizmarState',
        color=metric,
        color_continuous_scale=['#F9F7F3', '#88A98A', '#174C35'],
        custom_data=[metric, percent_column],
        labels={metric: label, 'state': 'State'},
    )
    figure.update_traces(
        marker_line_color='#88A98A',
        marker_line_width=.8,
        hovertemplate=(
            '<b>%{location}</b><br>'
            + (f'{label}: %{{customdata[0]:,.2f}}<br>' if metric == 'revenue' else f'{label}: %{{customdata[0]:,}}<br>') +
            'Share of known locations: %{customdata[1]:.1f}%'
            '<extra></extra>'
        ),
    )
    figure.update_geos(
        projection_type='mercator',
        # Explicit Malaysia extents avoid non-finite auto-fit centers in the
        # geographic renderer and include both the peninsula and East Malaysia.
        fitbounds=False,
        center=dict(lon=109.5, lat=4.0),
        projection_rotation_lon=109.5,
        lonaxis_range=[99.0, 120.0],
        lataxis_range=[0.3, 7.8],
        visible=False,
        showcountries=False,
        showcoastlines=False,
        showframe=False,
    )
    figure.update_layout(
        font=dict(family='Inter, Arial, sans-serif', color=(
            '#F5F7F3' if st.session_state.get('bizmar_preferences', {}).get('theme') == 'Dark' else '#40313A'
        )),
        height=470,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor='rgba(0,0,0,0)',
        geo=dict(bgcolor='rgba(0,0,0,0)'),
        coloraxis_colorbar=dict(title=label, thickness=12, len=.72),
    )
    from typography import style_chart_fonts
    st.plotly_chart(
        style_chart_fonts(figure),
        use_container_width=True,
        # Plotly still loads base TopoJSON even with coastlines/countries hidden.
        # Serve the Malaysia-only topology locally rather than relying on its CDN.
        config={'displayModeBar': False, 'scrollZoom': False, 'responsive': True,
                'topojsonURL': './app/static/maps/'},
    )
