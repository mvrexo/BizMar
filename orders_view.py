"""Pure order filtering and business-only export helpers."""
from io import BytesIO
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
import pandas as pd
from sales_period import filter_period
from malaysian_states import destination, UNSPECIFIED

EXPORT_FIELDS = {
    'order_code':'Order ID','customer_name':'Customer','phone_number':'Phone',
    'products':'Products / Items','state':'State', 'customer_state_snapshot':'Customer Residence State', 'delivery_state':'Delivery Destination State', 'ordered_at':'Order Date (MYT)',
    'fulfilment_date':'Pickup / Delivery Date','fulfilment_time':'Fulfillment Time',
    'fulfilment_method':'Fulfillment Method','delivery_address':'Delivery Address',
    'total_amount':'Order Total (RM)','discount':'Discount (RM)','delivery_fee':'Delivery Fee (RM)',
    'amount_paid':'Amount Paid (RM)','balance':'Outstanding Balance (RM)',
    'payment_status':'Payment Status','status':'Order Status','source':'Source','notes':'Notes',
    'completed_at':'Completed At','cancelled_at':'Cancelled At','cancellation_reason':'Cancellation Reason',
}


def order_summary(frame, today=None):
    """Order-date scoped KPIs; only active debts contribute to outstanding."""
    today = today or datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date()
    pending = frame.loc[frame.status.eq('Pending')]
    dates = pd.to_datetime(pending.fulfilment_date, errors='coerce', format='mixed').dt.date
    outstanding = sum((max(Decimal(str(row.balance)), Decimal(0)) for row in frame.itertuples()
                       if row.status != 'Cancelled'), Decimal(0))
    return dict(total=len(frame), pending=len(pending), completed=int(frame.status.eq('Completed').sum()),
                cancelled=int(frame.status.eq('Cancelled').sum()),
                outstanding=outstanding, today=int(dates.eq(today).sum()),
                tomorrow=int(dates.eq(today + timedelta(days=1)).sum()), overdue=int(dates.lt(today).sum()))


def whatsapp_message(order, items):
    products = ', '.join(f"{item['quantity']} x {item['product_name']}" for item in items)
    return (f"Hi {order['customer_name']}, your BizMar order {order['order_code']}: {products}. "
            f"Total: RM {Decimal(str(order['total_amount'])):.2f}. "
            f"{order['fulfilment_method']}: {order['fulfilment_date']} {order.get('fulfilment_time') or ''}. "
            f"Outstanding balance: RM {Decimal(str(order['balance'])):.2f}.")


def order_frame(records):
    frame = pd.DataFrame(records)
    for column in ['id', *EXPORT_FIELDS, 'version']:
        if column not in frame:
            frame[column] = pd.Series(index=frame.index, dtype='object')
    frame['state'] = [destination(row) for row in frame.to_dict('records')]
    return frame


def date_scope(frame, start=None, end=None):
    result = frame.copy()
    if start and end:
        return filter_period(result, start, end) if start <= end else result.iloc[0:0].copy()
    dates = pd.to_datetime(result['ordered_at'], errors='coerce', format='mixed', utc=True).dt.tz_convert('Asia/Kuala_Lumpur').dt.date
    if start:
        result = result.loc[dates.ge(start)]
    if end:
        result = result.loc[dates.le(end)]
    return result


def filter_orders(frame, *, search='', status='All', payment='All', fulfillment='All', source='All', state='All States', sort='Newest date'):
    result = frame.copy()
    if result.empty:
        return result
    if state != 'All States':
        result = result.loc[result['state'].fillna(UNSPECIFIED).eq(state)]
    for field, value in (('status',status),('payment_status',payment),('fulfilment_method',fulfillment),('source',source)):
        if value != 'All': result = result.loc[result[field].eq(value)]
    if search.strip():
        text = result[['order_code','customer_name','phone_number','products']].fillna('').astype(str).agg(' '.join,axis=1).str.casefold()
        result = result.loc[text.str.contains(search.strip().casefold(),regex=False)]
    field, ascending = {'Newest date':('ordered_at',False),'Oldest date':('ordered_at',True),
                        'Fulfillment deadline':('fulfilment_date',True),'Highest amount':('total_amount',False),
                        'Lowest amount':('total_amount',True)}[sort]
    if field == 'ordered_at':
        result = result.assign(_sort_date=pd.to_datetime(result[field],utc=True,errors='coerce',format='mixed'))
        return result.sort_values('_sort_date',ascending=ascending,kind='stable',na_position='last').drop(columns='_sort_date')
    return result.sort_values(field,ascending=ascending,kind='stable',na_position='last')


def export_frame(frame):
    exported = frame[list(EXPORT_FIELDS)].rename(columns=EXPORT_FIELDS).copy()
    exported['Order Date (MYT)'] = pd.to_datetime(exported['Order Date (MYT)'],utc=True,errors='coerce',format='mixed').dt.tz_convert('Asia/Kuala_Lumpur').dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')
    # Untrusted spreadsheet cells must never execute formulas when exported.
    return exported.map(lambda value: "'" + value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value)


def excel_bytes(frame):
    output = BytesIO()
    with pd.ExcelWriter(output,engine='openpyxl') as writer:
        export_frame(frame).to_excel(writer,index=False,sheet_name='Orders')
    return output.getvalue()
