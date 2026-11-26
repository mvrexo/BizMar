"""Read-only, order-date analytics over the existing SQLite fetch snapshot."""
from datetime import date, datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo
import math
import pandas as pd
import streamlit as st
from customer_location_analytics import normalize_state
from malaysian_states import STATES

DEFINITIONS = {
    'Date basis':'Order creation date in Asia/Kuala_Lumpur; payments are lifetime ledger receipts for the selected order cohort, not payment-date cash flow.',
    'Recognized revenue':'Completed order totals after discounts and confirmed delivery charges. Pending and Cancelled excluded.',
    'Gross profit':'Completed product revenue after order discount minus saved item costs. Excludes delivery income/costs and overheads; not net profit.',
    'Product filters':'Order KPIs include whole orders containing matching items; product reports include only matching completed line items. Product sales are before order-level discounts and delivery.',
    'Units':'Quantity is selling units, kept separate per product. Current catalog packaging is descriptive only; historical packaging conversions are unavailable.',
    'Customers':'Stable customer IDs; new = first non-cancelled order in the selected period; returning = a purchase before the period. Repeat = two or more selected non-cancelled orders.',
    'Retention':'Observed return purchases, not a forecast or a full acquisition-cohort retention model.',
}


def numeric(value):
    try:
        result=float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):return None


def total(values):
    values=list(values)
    return None if any(pd.isna(v) for v in values) else float(sum(values))


def period_range(preset, today):
    if preset=='Today':return today,today
    if preset=='Last 7 Days':return today-timedelta(days=6),today
    if preset=='This Month':return today.replace(day=1),today
    if preset=='Last Month':
        end=today.replace(day=1)-timedelta(days=1)
        return end.replace(day=1),end
    if preset=='This Year':return today.replace(month=1,day=1),today
    raise ValueError('Custom range requires dates.')


def previous_period(start,end):
    return start-timedelta(days=(end-start).days+1),start-timedelta(days=1)


@st.cache_data(show_spinner=False,max_entries=8)
def prepare(snapshot):
    """Never merge payments onto lines: each order is represented once."""
    catalog={p['id']:p for p in snapshot.get('products',[])}
    lines=[]
    for source in snapshot.get('order_items',[]):
        row=dict(source);product=catalog.get(row.get('product_id'),{})
        quantity,price,cost=(numeric(row.get(k)) for k in ('quantity','unit_price','unit_cost'))
        row.update(product=str(row.get('product_name') or product.get('name') or 'Unknown product'),
                   category=str(product.get('category') or 'Unknown category'),
                   unit='selling units', packaging=str(product.get('packaging_type') or 'Unknown'),
                   catalog_unit=str(product.get('measurement_unit') or 'Unknown'),
                   quantity=quantity, line_revenue=None if quantity is None or price is None else quantity*price,
                   line_cost=None if quantity is None or cost is None else quantity*cost)
        lines.append(row)
    line_frame=pd.DataFrame(lines,columns=list(dict.fromkeys(['order_id','product_id','product','category','quantity','line_revenue','line_cost','unit','packaging','catalog_unit']+[k for r in lines for k in r])))
    payments=pd.DataFrame(snapshot.get('payments',[]))
    if payments.empty:payments=pd.DataFrame(columns=['id','order_id','amount','method','paid_at'])
    payments=payments.copy();payments['amount']=payments['amount'].map(numeric)
    line_groups={identity:group for identity,group in line_frame.groupby('order_id')}
    ledger_groups={identity:group for identity,group in payments.groupby('order_id')}
    orders=[]
    for source in snapshot.get('orders',[]):
        row=dict(source);saved=line_groups.get(row['id'],line_frame.iloc[:0])
        subtotal=total(saved.line_revenue) if not saved.empty else None
        cost=total(saved.line_cost) if not saved.empty else None
        discount=numeric(row.get('discount',0))
        fee=numeric(row.get('delivery_fee',0)) if row.get('delivery_quote_status','Confirmed')=='Confirmed' else None
        product_net=None if subtotal is None or discount is None else subtotal-discount
        payable=numeric(row.get('total_amount'))
        if fee is None:payable=None
        elif payable is None:payable=None if product_net is None else product_net+fee
        ledger=ledger_groups.get(row['id'],payments.iloc[:0])
        paid=total(ledger.amount) if 'payments' in snapshot else None
        state_field='delivery_state' if row.get('fulfilment_method')=='Delivery' else 'customer_state_snapshot'
        row.update(status=row.get('status') if row.get('status') in ('Completed','Cancelled') else 'Pending',
                   state=normalize_state(row.get(state_field)) or 'Unknown',
                   fulfilment_method=row.get('fulfilment_method') or 'Unknown',
                   product_revenue=product_net,delivery_charges=fee,product_cost=cost,
                   rider_cost=numeric(row.get('rider_cost')),recognized=payable,
                   gross_profit=None if product_net is None or cost is None else product_net-cost,
                   collected=paid,outstanding=None if payable is None or paid is None else max(payable-paid,0),
                   payment_group='Unknown' if payable is None or paid is None else 'Paid' if paid>=payable else 'Unpaid' if paid==0 else 'Partially Paid')
        orders.append(row)
    columns=['id','customer_id','ordered_at','status','state','fulfilment_method','product_revenue','delivery_charges','product_cost','rider_cost','recognized','gross_profit','collected','outstanding','payment_group']
    frame=pd.DataFrame(orders,columns=list(dict.fromkeys(columns+[k for r in orders for k in r])))
    frame['day']=pd.to_datetime(frame.ordered_at,errors='coerce',utc=True,format='mixed').dt.tz_convert('Asia/Kuala_Lumpur').dt.tz_localize(None).dt.normalize()
    return frame,line_frame,payments


def select_orders(frame,lines,start,end,filters):
    selected=frame.loc[frame.day.between(pd.Timestamp(start),pd.Timestamp(end))].copy()
    for field in ('status','state','fulfilment_method'):
        value=filters.get(field,'All')
        if value!='All':selected=selected.loc[selected[field].eq(value)]
    matching=lines
    for field in ('product','category'):
        value=filters.get(field,'All')
        if value!='All':matching=matching.loc[matching[field].eq(value)]
    if any(filters.get(k,'All')!='All' for k in ('product','category')):
        selected=selected.loc[selected.id.isin(matching.order_id)]
    return selected,matching.loc[matching.order_id.isin(selected.id)].copy()


def summarize(selected):
    completed=selected.loc[selected.status.eq('Completed')]
    active=selected.loc[selected.status.ne('Cancelled')]
    recognized=total(completed.recognized)
    profit=total(completed.gross_profit)
    product_net=total(completed.product_revenue)
    count=len(selected)
    return {
        'Recognized Sales Revenue':recognized,'Total Orders':count,
        'Average Order Value':recognized/len(completed) if recognized is not None and len(completed) else None,
        'Gross Profit':profit,'Gross Profit Margin':100*profit/product_net if profit is not None and product_net else None,
        'Completed Orders':len(completed),'Pending Revenue':total(selected.loc[selected.status.eq('Pending'),'recognized']),
        'Cancellation Rate':100*selected.status.eq('Cancelled').sum()/count if count else None,
        'Verified Collected Payments':total(selected.collected),
        'Outstanding Payments':total(active.outstanding),
    }


def trends(selected,start,end,frequency='Daily'):
    completed=selected.loc[selected.status.eq('Completed')].copy()
    days=pd.date_range(start,end,freq='D')
    fields=['recognized','product_revenue','delivery_charges','product_cost','rider_cost','gross_profit']
    daily=pd.DataFrame(index=days)
    for field in fields:
        daily[field]=completed.groupby('day')[field].agg(total).reindex(days,fill_value=0)
    rule={'Daily':'D','Weekly':'W-SUN','Monthly':'MS'}[frequency]
    result=daily.resample(rule).agg(total)
    return result.rename_axis('Period').reset_index()


def product_report(lines,selected):
    sold=lines.loc[lines.order_id.isin(selected.loc[selected.status.eq('Completed'),'id'])].copy()
    columns=['Product','Category','Unit','Quantity','Revenue','Cost','Gross Profit','Catalog Packaging','Catalog Measurement (current)']
    if sold.empty:return pd.DataFrame(columns=columns)
    grouped=sold.groupby(['product','category','unit'],dropna=False).agg(Quantity=('quantity',total),Revenue=('line_revenue',total),Cost=('line_cost',total),packaging=('packaging','first'),catalog_unit=('catalog_unit','first')).reset_index()
    grouped['Gross Profit']=grouped.Revenue-grouped.Cost
    return grouped.rename(columns={'product':'Product','category':'Category','unit':'Unit','packaging':'Catalog Packaging','catalog_unit':'Catalog Measurement (current)'}).sort_values('Revenue',ascending=False)


def customer_report(selected,history,start):
    active=selected.loc[selected.status.ne('Cancelled') & selected.customer_id.notna()]
    prior=history.loc[history.status.ne('Cancelled') & history.day.lt(pd.Timestamp(start))]
    rows=[]
    for identity,group in active.groupby('customer_id'):
        completed=group.loc[group.status.eq('Completed')]
        rows.append({'Customer':f'Customer {identity}','Orders':len(group),'Completed Orders':len(completed),
                     'Recognized Spending':total(completed.recognized),'Type':'Returning' if identity in set(prior.customer_id) else 'New',
                     'Repeat in Period':len(group)>1})
    return pd.DataFrame(rows,columns=['Customer','Orders','Completed Orders','Recognized Spending','Type','Repeat in Period'])


@st.cache_data(show_spinner=False,max_entries=24)
def analytics(snapshot,start,end,filters):
    history,lines,ledger=prepare(snapshot)
    selected,scoped_lines=select_orders(history,lines,start,end,filters)
    previous_start,previous_end=previous_period(start,end)
    previous,previous_lines=select_orders(history,lines,previous_start,previous_end,filters)
    products=product_report(scoped_lines,selected)
    previous_products=product_report(previous_lines,previous)
    completed=selected.loc[selected.status.eq('Completed')]
    geo=[]
    for state in (*STATES,'Unknown'):
        group=selected.loc[selected.state.eq(state)]
        sales=group.loc[group.status.eq('Completed')]
        geo.append({'State':state,'Orders':len(group),'Revenue':total(sales.recognized)})
    payments=ledger.loc[ledger.order_id.isin(selected.id)].copy()
    methods=payments.groupby('method',dropna=False).amount.agg(total).rename('Collected').reset_index()
    return dict(orders=selected,products=products,previous_products=previous_products,
                customers=customer_report(selected,history,start),geography=pd.DataFrame(geo),
                payments=methods,kpis=summarize(selected),previous_kpis=summarize(previous),
                daily=trends(selected,start,end),monthly=trends(selected,start,end,'Monthly'),
                previous_daily=trends(previous,previous_start,previous_end),
                previous_period=(previous_start,previous_end),
                missing_dates=int(history.day.isna().sum()))


def insights(report,start,end):
    rows=[];products=report['products'];geo=report['geography'];kpis=report['kpis'];previous=report['previous_kpis']
    prefix=f'{start:%d %b %Y}–{end:%d %b %Y}'
    ranked_products=products.loc[products.Quantity.notna()]
    if not ranked_products.empty:
        top=ranked_products.sort_values('Quantity',ascending=False).iloc[0]
        rows.append(f'{prefix}: {top.Product} leads by selling-unit count ({top.Quantity:g}); packaging sizes differ between products.')
    ranked=geo.loc[geo.State.ne('Unknown') & geo.Revenue.gt(0)].sort_values('Revenue',ascending=False)
    if not ranked.empty:rows.append(f'{prefix}: {ranked.iloc[0].State} has the highest recognized sales (RM {ranked.iloc[0].Revenue:,.2f}).')
    current,old=kpis['Recognized Sales Revenue'],previous['Recognized Sales Revenue']
    a,b=report['previous_period']
    if current is not None and old is not None and old>0:
        rows.append(f'Recognized revenue changed {(current/old-1)*100:+.1f}% versus {a:%d %b %Y}–{b:%d %b %Y}.')
    elif current is not None:rows.append('Revenue growth percentage is unavailable because the previous comparable period has no positive recognized revenue.')
    customers=report['customers']
    if not customers.empty:
        spending=total(customers['Recognized Spending']);returning=total(customers.loc[customers.Type.eq('Returning'),'Recognized Spending'])
        if spending and returning is not None:rows.append(f'Returning customers contributed {100*returning/spending:.1f}% of recognized customer spending in this period.')
    if kpis['Cancellation Rate'] is not None and kpis['Cancellation Rate']>=20:
        rows.append(f'Cancellation rate is {kpis["Cancellation Rate"]:.1f}% ({prefix}), above the displayed 20% review threshold.')
    prior=report['previous_products']
    if not products.empty and not prior.empty:
        comparison=products.merge(prior,on=['Product','Category','Unit'],suffixes=('','_previous'))
        declining=comparison.loc[comparison.Quantity.lt(comparison.Quantity_previous),'Product'].tolist()
        if declining:rows.append(f'Lower selling-unit counts versus {a:%d %b %Y}–{b:%d %b %Y}: '+', '.join(declining[:5])+'.')
    return rows or ['No comparable sales data for the selected filters.']


def summary_table(report):
    return pd.DataFrame([{'Metric':k,'Value':v} for k,v in report['kpis'].items()])


def csv_bytes(frame):
    # Neutralize spreadsheet formulas in text fields without changing numbers.
    safe=frame.copy()
    for column in safe.select_dtypes(include=['object','string']).columns:
        safe[column]=safe[column].map(lambda value:"'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value)
    return safe.to_csv(index=False).encode('utf-8-sig')


def excel_report(report,start,end,filters):
    from openpyxl import Workbook
    from openpyxl.utils.dataframe import dataframe_to_rows
    workbook=Workbook();workbook.remove(workbook.active)
    tables={'Summary':summary_table(report),'Monthly':report['monthly'],'Products':report['products'],'Customers':report['customers'],'States':report['geography']}
    for name,frame in tables.items():
        sheet=workbook.create_sheet(name)
        for row in dataframe_to_rows(frame,index=False,header=True):
            sheet.append([None if pd.isna(value) else value for value in row])
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width=24
            for cell in column[1:]:
                if isinstance(cell.value,str) and cell.value.lstrip().startswith(('=','+','-','@')):cell.value="'"+cell.value
                if isinstance(cell.value,(int,float)) and any(word in str(column[0].value).lower() for word in ('revenue','cost','profit','spending','recognized','charges')):cell.number_format='"RM "#,##0.00'
    meta=workbook.create_sheet('Definitions')
    for row in [('Generated MYT',datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).isoformat()),('Period',f'{start} – {end}'),('Filters',str(filters)),*DEFINITIONS.items()]:meta.append(row)
    output=BytesIO();workbook.save(output);return output.getvalue()
