from display_preferences import option_labels
"""Owner dashboard analytics; receives the existing authenticated fetch snapshot."""
from display_preferences import tr
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from display_preferences import style_figure, style_table
from ui_theme import style_bi_chart
from sales_analytics import (analytics,prepare,period_range,trends,insights,summary_table,
                             csv_bytes,excel_report,DEFINITIONS)
from malaysian_states import STATES
from customer_location_analytics import render_location_map


def money(value):return 'N/A' if value is None or pd.isna(value) else f'RM {value:,.2f}'


def chart(figure,key):
    style_bi_chart(figure)
    figure.update_layout(height=310,legend_title_text='',margin=dict(l=8,r=12,t=10,b=20))
    st.plotly_chart(style_figure(figure),width='stretch',key=key,config={'displayModeBar':False,'responsive':True})


def bars(frame,x,y,key):
    if frame.empty or pd.to_numeric(frame[x],errors='coerce').dropna().empty:
        st.info(tr('No data for the selected filters.'));return
    chart(px.bar(frame,x=x,y=y,color_discrete_sequence=['#88A98A']),key)


def render_sales_analytics(snapshot,*,owner_authorized=False):
    if not owner_authorized:
        st.error(tr('Owner access is required.'));return
    st.markdown(tr('<style>'+(Path(__file__).parent/'styles/sales_analytics.css').read_text(encoding='utf-8')+'</style>'),unsafe_allow_html=True)
    today=datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date()
    with st.container(border=True,key='bizmar_sales_filters'):
        st.subheader(tr('Global Filters'))
        preset=st.selectbox(tr('Order-date period'),['This Month','Today','Last 7 Days','Last Month','This Year','Custom'],key='sales_report_period', format_func=option_labels(['This Month','Today','Last 7 Days','Last Month','This Year','Custom']))
        if preset=='Custom':
            a,b=st.columns(2)
            start=a.date_input(tr('Start date'),today-timedelta(days=29),key='sales_report_start')
            end=b.date_input(tr('End date'),today,key='sales_report_end')
        else:start,end=period_range(preset,today)
        if end<start:st.warning(tr('End date must be on or after start date.'));return
        _,lines,_=prepare(snapshot)
        a,b,c=st.columns(3)
        filters=dict(status=a.selectbox(tr('Order status'),['All','Completed','Pending','Cancelled'],key='sales_report_status', format_func=option_labels(['All','Completed','Pending','Cancelled'])),
                     category=b.selectbox(tr('Category'),['All',*sorted(lines.category.dropna().unique())],key='sales_report_category'))
        available=lines if filters['category']=='All' else lines.loc[lines.category.eq(filters['category'])]
        filters['product']=c.selectbox(tr('Product'),['All',*sorted(available['product'].dropna().unique())],key='sales_report_product')
        a,b=st.columns(2)
        filters['state']=a.selectbox(tr('Malaysian state'),['All',*STATES,'Unknown'],key='sales_report_state')
        filters['fulfilment_method']=b.selectbox(tr('Fulfilment'),['All','Delivery','Pickup','Unknown'],key='sales_report_fulfilment', format_func=option_labels(['All','Delivery','Pickup','Unknown']))
        st.caption(tr(f'Order-date basis · {start:%d %b %Y}–{end:%d %b %Y} · Malaysia (MYT). '+DEFINITIONS['Product filters']))
    report=analytics(snapshot,start,end,filters);selected=report['orders'];kpis=report['kpis']
    if selected.empty:st.info(tr('No orders match the selected filters.'))
    if report['missing_dates']:st.warning(tr(f'{report["missing_dates"]} orders have missing/invalid order dates and cannot be assigned to a period.'))
    st.subheader(tr('Sales KPI Overview'))
    for offset in (0,4):
        for col,(label,value) in zip(st.columns(4),list(kpis.items())[offset:offset+4]):
            with col,st.container(key=f'bizmar_sales_kpi_{offset}_{label.replace(" ","_")}'):
                formatted=(('N/A' if value is None else f'{value:.1f}%') if label in ('Gross Profit Margin','Cancellation Rate') else str(value) if label in ('Total Orders','Completed Orders') else money(value))
                st.metric(tr(label),formatted)
    st.caption(tr('Recognized sales: Completed orders only. Gross profit: discounted product sales minus saved product costs; excludes delivery margin and overheads. N/A indicates missing information.'))

    st.subheader(tr('Revenue & Profit Trends'))
    granularity=st.segmented_control(tr('Chart granularity'),['Daily','Weekly','Monthly'],default='Daily',key='sales_report_granularity', format_func=option_labels(['Daily','Weekly','Monthly'])) or 'Daily'
    series=trends(selected,start,end,granularity)
    left,right=st.columns(2)
    with left:
        st.markdown(tr('**Recognized sales and product gross profit**'))
        figure=go.Figure()
        for field,label,color in [('recognized','Recognized Sales','#C57B8F'),('gross_profit','Product Gross Profit','#819A78')]:
            figure.add_scatter(x=series.Period,y=series[field],name=label,mode='lines+markers',line_color=color,connectgaps=False,hovertemplate='%{x|%d %b %Y}<br>RM %{y:,.2f}<extra>%{fullData.name}</extra>')
        figure.update_yaxes(tickprefix='RM ');chart(figure,'sales_report_trends')
    with right:
        st.markdown(tr('**Product revenue, cost and delivery**'))
        figure=go.Figure()
        for field,label in [('product_revenue','Product Revenue after Discount'),('product_cost','Saved Product Cost'),('delivery_charges','Confirmed Delivery Charges'),('rider_cost','Known Rider Cost')]:
            figure.add_bar(x=series.Period,y=series[field],name=label)
        figure.update_yaxes(tickprefix='RM ');chart(figure,'sales_report_components')
    a,b=report['previous_period']
    st.markdown(tr(f'**Comparable period: {a:%d %b %Y}–{b:%d %b %Y}**'))
    figure=go.Figure()
    for frame,label in [(report['daily'],'Selected period'),(report['previous_daily'],'Previous equal-length period')]:
        figure.add_scatter(x=list(range(1,len(frame)+1)),y=frame.recognized,name=label,connectgaps=False)
    figure.update_xaxes(title='Day of period');figure.update_yaxes(title='Recognized Sales (RM)');chart(figure,'sales_report_comparison')

    st.subheader(tr('Product Performance'))
    products=report['products']
    a,b=st.columns(2)
    with a:
        st.markdown(tr('**Top 10 by selling-unit quantity**'));bars(products.sort_values('Quantity',ascending=False).head(10),'Quantity','Product','sales_report_product_quantity')
    with b:
        st.markdown(tr('**Top 10 by product revenue**'));bars(products.head(10),'Revenue','Product','sales_report_product_revenue')
    if not products.empty:
        categories=products.groupby('Category',as_index=False).Revenue.sum(min_count=1)
        st.markdown(tr('**Category revenue contribution**'));bars(categories,'Revenue','Category','sales_report_category_chart')
        st.dataframe(style_table(products),hide_index=True,width='stretch')
        st.markdown(tr('**Lowest selling-unit counts among sold products**'))
        st.dataframe(style_table(products.sort_values('Quantity').head(10)),hide_index=True,width='stretch')
    sold=set(products.Product)
    dormant=[{'Product':p['name'],'Category':p.get('category','Unknown'),'Selling units':0} for p in snapshot.get('products',[])
             if p.get('active',True) and p['name'] not in sold
             and filters['product'] in ('All',p['name']) and filters['category'] in ('All',p.get('category'))]
    with st.expander(tr('Products with no completed sales in the selected cohort')):
        st.dataframe(pd.DataFrame(dormant),hide_index=True,width='stretch') if dormant else st.info(tr('No unsold matching catalogue products.'))
    st.caption(tr(DEFINITIONS['Units']+' Category and packaging labels use current catalog metadata; transaction prices and costs use saved order items.'))

    st.subheader(tr('Order & Payment Analytics'))
    left,right=st.columns(2)
    with left:
        st.markdown(tr('**Order status distribution**'))
        bars(selected.status.value_counts().rename_axis('Status').reset_index(name='Orders'),'Orders','Status','sales_report_status_chart')
        st.markdown(tr('**Delivery versus Pickup**'))
        bars(selected.fulfilment_method.value_counts().rename_axis('Fulfilment').reset_index(name='Orders'),'Orders','Fulfilment','sales_report_fulfilment_chart')
    with right:
        st.markdown(tr('**Payment status (independent of fulfilment)**'))
        bars(selected.payment_group.value_counts().rename_axis('Payment').reset_index(name='Orders'),'Orders','Payment','sales_report_payment_status')
        st.markdown(tr('**Verified payment methods**'));bars(report['payments'],'Collected','method','sales_report_payment_methods')
    status_daily=selected.groupby(['day','status']).size().rename('Orders').reset_index()
    if not status_daily.empty:chart(px.line(status_daily,x='day',y='Orders',color='status',markers=True),'sales_report_status_trend')
    a,b=st.columns(2);a.metric(tr('Verified Collected Payments'),money(kpis['Verified Collected Payments']));b.metric(tr('Outstanding Payments'),money(kpis['Outstanding Payments']))
    st.caption(tr('Only payments recorded in the owner ledger count as collected. Customer-reported amounts/receipts and Paid labels alone are not receipts. Collected includes receipts for cancelled orders pending reconciliation; outstanding excludes cancelled orders. '+DEFINITIONS['Date basis']))

    st.subheader(tr('Customer & Geographic Insights'))
    customers=report['customers'];geo=report['geography']
    a,b,c=st.columns(3)
    a.metric(tr('Repeat Purchase Rate'),'N/A' if customers.empty else f'{100*customers["Repeat in Period"].mean():.1f}%')
    spending=customers['Recognized Spending']
    b.metric(tr('Average Spending per Customer'),money(None if customers.empty or spending.isna().any() else spending.mean()))
    c.metric(tr('Returning Customers'),int(customers.Type.eq('Returning').sum()))
    left,right=st.columns(2)
    with left:
        st.markdown(tr('**New versus Returning**'));bars(customers.Type.value_counts().rename_axis('Type').reset_index(name='Customers'),'Customers','Type','sales_report_customer_types')
    with right:
        st.markdown(tr('**Top Customers by recognized spending**'));bars(customers.sort_values('Recognized Spending',ascending=False).head(10),'Recognized Spending','Customer','sales_report_top_customers')
    st.dataframe(style_table(customers),hide_index=True,width='stretch')
    st.caption(tr(DEFINITIONS['Customers']+' '+DEFINITIONS['Retention']))
    a,b=st.columns(2)
    with a:
        st.markdown(tr('**Top 5 States by recognized sales**'));bars(geo.loc[geo.Revenue.gt(0)].sort_values('Revenue',ascending=False).head(5),'Revenue','State','sales_report_state_revenue')
    with b:
        st.markdown(tr('**Orders by State**'));bars(geo.loc[geo.Orders.gt(0)],'Orders','State','sales_report_state_orders')
    st.markdown(tr('**Geographic Revenue Distribution**'))
    # Reuse the working map renderer/viewport/assets; metric labels are selectable.
    map_rows=geo.loc[geo.State.ne('Unknown')].rename(columns={'State':'state','Revenue':'revenue'})
    known=map_rows.revenue.sum(min_count=1)
    map_rows['revenue_percent']=100*map_rows.revenue/known if known and pd.notna(known) else 0
    render_location_map({'states':map_rows},metric='revenue')
    st.dataframe(style_table(geo),hide_index=True,width='stretch')

    st.subheader(tr('Business Insights & Export Reports'))
    for message in insights(report,start,end):st.write('• '+tr(message))
    with st.expander(tr('Metric definitions and data limitations')):
        for label,definition in DEFINITIONS.items():st.markdown(tr(f'**{label}:** {definition}'))
        st.write(tr('Customer identity follows saved customer IDs. Records with different IDs are not guessed or merged based on names/phone numbers. Missing costs and unconfirmed rider quotes remain N/A.'))
    metadata=f'Generated {datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).isoformat()} | {start}–{end} | {filters}'
    cols=st.columns(4)
    for col,label,frame,filename in [(cols[0],'Sales summary CSV',summary_table(report),'sales-summary.csv'),(cols[1],'Product CSV',products,'product-performance.csv'),(cols[2],'Customer CSV',customers,'customer-analytics.csv')]:
        exported=frame.copy();exported['Report context']=metadata;exported['Metric definitions']=' | '.join(DEFINITIONS.values())
        col.download_button(tr(label),csv_bytes(exported),filename,'text/csv',width='stretch')
    cols[3].download_button(tr('Monthly Excel'),excel_report(report,start,end,filters),'monthly-sales.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',width='stretch')
