from display_preferences import option_labels
from display_preferences import tr
from display_preferences import style_table
from display_preferences import style_figure
from display_preferences import date_input_format
"""FR10/FR11 native widgets and Plotly views, using the shared BizMar theme."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

from advanced_bi import profitability_trend, repeat_customer_insights, MONEY_COLUMNS
from bi_analytics import MALAYSIA_TIMEZONE
from ui_theme import style_bi_chart


@st.cache_data(ttl=10, show_spinner=False)
def _trend_data(orders, items, start, end, aggregation):
    return profitability_trend(orders, items, start, end, aggregation)


@st.cache_data(ttl=10, show_spinner=False)
def _repeat_data(orders, items, customers, start, end):
    return repeat_customer_insights(orders, items, customers, start, end)


def _money_config():
    return {label: st.column_config.NumberColumn(label, format='RM %.2f') for label in
            ('Revenue (RM)', 'Recorded Cost (RM)', 'Gross Profit (RM)')}


def render_long_term_profitability(orders, items, start, end):
    from display_preferences import style_table
    from display_preferences import style_figure
    with st.container(border=True):
        st.subheader(tr('Long-Term Profitability'))
        st.caption(tr('Booked/order-based financial performance from saved line prices and costs. Includes pending and other non-cancelled orders; not cash collected or realized net profit. Malaysia dates; edge periods include only selected dates.'))
        aggregation = st.selectbox(tr('Aggregate by'), ['Daily', 'Weekly', 'Monthly', 'Yearly'],
                                   index=2, key='long_term_profitability_aggregation', format_func=option_labels(['Daily', 'Weekly', 'Monthly', 'Yearly']))
        try:
            trend = _trend_data(orders, items, start, end, aggregation)
        except ValueError as exc:
            st.warning(tr(str(exc)))
            return
        if trend.empty:
            st.info(tr('No valid date range. Select a start date on or before the end date.'))
            return
        if not trend['order_count'].sum():
            st.info(tr('No non-cancelled orders match these dates. The table shows zero-activity periods; margins are undefined.'))
        else:
            chart = trend.melt(id_vars=['period_start', 'period'], value_vars=MONEY_COLUMNS,
                               var_name='Measure', value_name='Amount (RM)')
            chart['Measure'] = chart['Measure'].map(dict(revenue='Revenue', recorded_cost='Recorded Cost', gross_profit='Gross Profit'))
            fig = px.line(chart, x='period_start', y='Amount (RM)', color='Measure', markers=len(trend) <= 120,
                          custom_data=['period'], color_discrete_map={
                              'Revenue': '#819A78', 'Recorded Cost': '#9B82B4', 'Gross Profit': '#C57B8F'})
            fig.update_traces(hovertemplate='%{customdata[0]}<br>RM %{y:,.2f}<extra>%{fullData.name}</extra>', connectgaps=False)
            fig.update_layout(height=330, xaxis_title='Period (Malaysia)', yaxis_title='Booked amount (RM)',
                              legend_title_text='', hovermode='x unified')
            fig.update_yaxes(tickprefix='RM ', tickformat=',.2f')
            st.plotly_chart(style_figure(style_bi_chart(fig)), use_container_width=True)
        if trend[MONEY_COLUMNS].isna().any().any():
            st.warning(tr('Some saved line values are unavailable or invalid. Affected totals are undefined; catalogue values were not substituted.'))
        shown = trend[['period', *MONEY_COLUMNS, 'gross_margin_percent']].rename(columns={
            'period': 'Period', 'revenue': 'Revenue (RM)', 'recorded_cost': 'Recorded Cost (RM)',
            'gross_profit': 'Gross Profit (RM)', 'gross_margin_percent': 'Gross Margin (%)'})
        st.dataframe(style_table(shown), hide_index=True, use_container_width=True,
                     column_config={**_money_config(), 'Gross Margin (%)': st.column_config.NumberColumn(format='%.2f%%')})
        st.caption(tr('Gross profit = revenue minus recorded cost. Gross margin is undefined when revenue is zero or snapshots are unavailable. Weekly periods use ISO week-year and Monday boundaries. At most 5,000 periods are displayed.'))


def render_repeat_customer_insights(orders, items, customers, key, start=None, end=None):
    from display_preferences import style_table
    from display_preferences import date_input_format
    st.subheader(tr('Repeat Customer Insights'))
    if start is None or end is None:
        dates = pd.to_datetime(orders.get('ordered_at', pd.Series(dtype=object)), errors='coerce', utc=True)
        dates = dates.dt.tz_convert(MALAYSIA_TIMEZONE).dt.date.dropna()
        today = datetime.now(ZoneInfo(MALAYSIA_TIMEZONE)).date()
        left, right = st.columns(2)
        start = left.date_input(tr('Repeat insights from'), value=dates.min() if not dates.empty else today, key=f'{key}_from', format=date_input_format())
        end = right.date_input(tr('Repeat insights to'), value=dates.max() if not dates.empty else today, key=f'{key}_to', format=date_input_format())
    if start > end:
        st.warning(tr('Start date must be on or before end date.'))
        return
    insights = _repeat_data(orders, items, customers, start, end)
    st.caption(tr(f'{start:%d %b %Y} to {end:%d %b %Y}, inclusive Malaysia dates. Non-cancelled orders, including pending. Identifiable customers have at least one qualifying order and an existing stable customer ID. Archived known customers are included; registered customers with no scoped orders are excluded.'))
    left, middle, right = st.columns(3)
    left.metric(tr('Identifiable Customers'), insights['identifiable_count'])
    middle.metric(tr('Repeat Customers'), insights['repeat_count'])
    right.metric(tr('Repeat Customer Rate'), f"{insights['repeat_rate']:.1f}%" if insights['repeat_rate'] is not None else 'N/A')
    st.caption(tr('Repeat = at least two unique orders. Rate = repeat / identifiable customers. Monetary totals are booked values, not collected payments. Customers are never matched by name, phone or email.'))
    repeats = insights['repeats']
    labels = {'customer_id': 'Stable Customer ID', 'customer_reference': 'Customer reference',
              'customer_name': 'Customer', 'order_count': 'Orders', 'revenue': 'Revenue (RM)',
              'recorded_cost': 'Recorded Cost (RM)', 'gross_profit': 'Gross Profit (RM)',
              'latest_order_date': 'Most recent order (Malaysia)'}
    if repeats.empty:
        st.info(tr('No repeat customers in the selected period.'))
    else:
        st.dataframe(style_table(repeats.rename(columns=labels)), hide_index=True, use_container_width=True,
                     column_config=_money_config())
        if repeats[MONEY_COLUMNS].isna().any().any():
            st.warning(tr('Some historical snapshots are unavailable; affected financial totals remain undefined.'))
        # Read-only inspection from the same order records; existing customer
        # profile selection, purchase-history filters and CRUD stay untouched.
        names = repeats.set_index('customer_id')['customer_name'].to_dict()
        selected = st.selectbox(tr('Inspect repeat customer order history'), options=repeats['customer_id'].tolist(),
                                format_func=lambda identity: f'{int(identity)} - {names[identity]}', key=f'{key}_history_customer')
        history = insights['identified_orders'].loc[lambda frame: frame['customer_id'].eq(selected)].copy()
        history = history.sort_values(['malaysia_order_date', 'id'], ascending=False)
        with st.expander(tr('Selected customer order history (same date scope)'), expanded=True):
            shown = history.reindex(columns=['id', 'order_code', 'malaysia_order_date', 'status', *MONEY_COLUMNS])
            st.dataframe(style_table(shown.rename(columns={'id': 'Order ID', 'order_code': 'Reference',
                         'malaysia_order_date': 'Order date (Malaysia)', 'status': 'Status',
                         **{name: labels[name] for name in MONEY_COLUMNS}})),
                         hide_index=True, use_container_width=True, column_config=_money_config())
    unresolved = insights['unresolved']
    if not unresolved.empty:
        st.warning(tr(f'{len(unresolved)} qualifying order(s) excluded from all repeat-customer KPIs because the customer reference is missing or no longer exists. No identity was guessed.'))
        with st.expander(tr('Unresolved customer references')):
            st.dataframe(style_table(unresolved.reindex(columns=['id', 'order_code', 'customer_id', 'malaysia_order_date', 'status']).rename(
                columns={'id': 'Order ID', 'order_code': 'Reference', 'customer_id': 'Saved Customer ID',
                         'malaysia_order_date': 'Order date (Malaysia)', 'status': 'Status'})),
                hide_index=True, use_container_width=True)
