"""Monthly revenue visualization using the dashboard's already-filtered values."""
from display_preferences import tr
import pandas as pd
import plotly.express as px
import streamlit as st
from display_preferences import style_figure
from ui_theme import style_overview_chart


def monthly_revenue(frame):
    if frame.empty:
        return pd.DataFrame(columns=['Month','Revenue'])
    data=frame.copy()
    if 'status' in data:
        data=data.loc[data['status'].ne('Cancelled')].copy()
    dates=pd.to_datetime(data['ordered_at'],errors='coerce',utc=True).dt.tz_convert('Asia/Kuala_Lumpur')
    data['Month']=dates.dt.strftime('%Y-%m')
    data['Revenue']=pd.to_numeric(data['revenue'],errors='coerce').fillna(0)
    totals=data.dropna(subset=['Month']).groupby('Month')['Revenue'].sum().sort_index()
    if totals.empty:
        return pd.DataFrame(columns=['Month','Revenue'])
    months=pd.period_range(totals.index[0],totals.index[-1],freq='M').astype(str)
    totals=totals.reindex(months,fill_value=0).rename_axis('Month').reset_index()
    totals['Month']=pd.to_datetime(totals['Month'],format='%Y-%m')
    return totals


def render_monthly_revenue(frame,height=320):
    totals=monthly_revenue(frame)
    if totals.empty:
        st.info(tr('No dated sales for this period.'))
        return
    figure=px.line(totals,x='Month',y='Revenue',markers=True,color_discrete_sequence=['#C57B8F'])
    figure.update_traces(line_width=3,fill='tozeroy',fillcolor='rgba(244,154,172,0.15)',hovertemplate='%{x|%B %Y}<br>Revenue: RM %{y:,.2f}<extra></extra>')
    figure.update_layout(height=height,showlegend=False,paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',margin=dict(l=8,r=16,t=12,b=24),xaxis=dict(title='',tickformat='%b %Y',nticks=6),yaxis=dict(title='Revenue (RM)',rangemode='tozero',tickprefix='RM '))
    style_overview_chart(figure)
    st.plotly_chart(style_figure(figure),use_container_width=True,config={'displayModeBar':False,'responsive':True})
