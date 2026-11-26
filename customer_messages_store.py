"""Owner-only communications; writes are confined to the three Messages tables."""
from contextlib import closing
from datetime import datetime, timedelta
import hashlib
import json
import re
from uuid import uuid4
from zoneinfo import ZoneInfo
import sqlite_db
import orders_store
from customer_message_templates import DEFAULTS, FIELDS, render, validate_template, whatsapp_url, display_date

MYT=ZoneInfo('Asia/Kuala_Lumpur')


def _guard():
    orders_store._authorize()


def now():return datetime.now(MYT).isoformat(timespec='microseconds')


def _text(value,limit=4000):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:
        raise ValueError(f'Enter text of up to {limit:,} characters.')
    return value.strip()


def _token(value):
    if not isinstance(value,str) or not 16<=len(value)<=128:
        raise ValueError('Reload this form before saving.')
    return value


def _context(con,customer_id,order_id):
    customer=con.execute('SELECT * FROM customers WHERE id=?',(int(customer_id),)).fetchone()
    if customer is None:raise ValueError('The selected customer is unavailable.')
    if order_id is not None:
        order=con.execute('SELECT customer_id FROM orders WHERE id=?',(int(order_id),)).fetchone()
        if order is None or order['customer_id']!=int(customer_id):raise ValueError('Choose an order belonging to this customer.')
    return dict(customer)


def _payment_guard(con,template,order_id):
    if template not in DEFAULTS:raise ValueError('Choose a supported message template.')
    if template=='Payment Received':
        paid=con.execute('SELECT COALESCE(SUM(amount),0) FROM payments WHERE order_id=?',(order_id,)).fetchone()[0] if order_id else 0
        if paid<=0:raise ValueError('Payment Received requires a verified payment recorded in SQLite. A submitted payment claim is not verification.')


def templates():
    _guard()
    with closing(sqlite_db._connect()) as con:
        return {**DEFAULTS,**{r['template_type']:r['content'] for r in con.execute('SELECT * FROM customer_message_templates')}}


def save_template(template,content):
    _guard()
    if template not in DEFAULTS:raise ValueError('Choose a supported template.')
    validate_template(content)
    with sqlite_db.transaction() as con:
        con.execute('''INSERT INTO customer_message_templates VALUES(?,?,?) ON CONFLICT(template_type) DO UPDATE SET content=excluded.content,updated_at=excluded.updated_at''',(template,content,now()))


def template_message(customer_id,order_id,template,content=None):
    _guard()
    with closing(sqlite_db._connect()) as con:
        customer=_context(con,customer_id,order_id)
        _payment_guard(con,template,order_id)
    details=orders_store.details(order_id) if order_id else None
    order=details['order'] if details else {}
    awaiting=order.get('quote_pending',False)
    money=lambda value:f'RM {float(value or 0):,.2f}'
    values=dict(customer_name=customer.get('full_name') or customer['name'],order_id=order.get('order_code'),order_date=display_date(order.get('ordered_at')),
                order_total='Awaiting rider quote' if awaiting else money(order['total_amount']) if order else 'Not provided',
                payment_status=order.get('payment_status'),order_status=order.get('status'),delivery_date=display_date(order.get('fulfilment_date')),
                delivery_time=order.get('fulfilment_time') or 'Not provided',delivery_fee='Awaiting rider quote' if awaiting else money(order.get('delivery_fee')) if order else 'Not provided')
    return render(content if content is not None else templates()[template],values)


def customer_orders(customer_id):
    _guard()
    return sorted((order for order in orders_store.list_orders() if order['customer_id']==int(customer_id)),key=_order_key,reverse=True)


def _order_key(order):
    try:
        parsed=datetime.fromisoformat(str(order.get('ordered_at') or '').replace('Z','+00:00'))
        if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=MYT)
        return parsed.timestamp(),order['id']
    except ValueError:return float('-inf'),order['id']


def messages(customer_id=None):
    _guard()
    with closing(sqlite_db._connect()) as con:
        return [dict(r) for r in con.execute('SELECT * FROM customer_messages'+(' WHERE customer_id=?' if customer_id is not None else '')+' ORDER BY id DESC', (int(customer_id),) if customer_id is not None else ())]


def get_message(message_id):
    _guard()
    with closing(sqlite_db._connect()) as con:
        row=con.execute('SELECT * FROM customer_messages WHERE id=?',(int(message_id),)).fetchone()
        if row is None:raise ValueError('This message is unavailable.')
        return dict(row)


def save_draft(customer_id,order_id,template,content,*,token,message_id=None,version=None):
    _guard();content=_text(content);_token(token)
    digest=hashlib.sha256(json.dumps([customer_id,order_id,template,content],separators=(',',':')).encode()).hexdigest()
    with sqlite_db.transaction() as con:
        _context(con,customer_id,order_id);_payment_guard(con,template,order_id)
        stamp=now()
        if message_id is None:
            previous=con.execute('SELECT * FROM customer_messages WHERE request_token=?',(token,)).fetchone()
            if previous:
                if previous['creation_hash']!=digest:raise ValueError('This form was already saved with different content. Start a new draft.')
                return dict(previous)
            identity=con.execute('''INSERT INTO customer_messages(customer_id,order_id,template_type,content,created_at,updated_at,request_token,creation_hash) VALUES(?,?,?,?,?,?,?,?)''',
                                 (int(customer_id),int(order_id) if order_id else None,template,content,stamp,stamp,token,digest)).lastrowid
        else:
            previous=con.execute('SELECT * FROM customer_messages WHERE id=?',(int(message_id),)).fetchone()
            if previous is None or previous['customer_id']!=int(customer_id) or previous['order_id']!=order_id:raise ValueError('This draft does not belong to the selected context.')
            if previous['status']!='Draft':raise ValueError('Only drafts can be edited. Start a new draft for another message.')
            if version!=previous['version']:raise ValueError('This draft changed in another session. Reload it before saving.')
            if previous['content']==content and previous['template_type']==template:return dict(previous)
            identity=previous['id']
            con.execute('UPDATE customer_messages SET content=?,template_type=?,updated_at=?,version=version+1 WHERE id=?',(content,template,stamp,identity))
        con.execute('INSERT INTO customer_message_activity(message_id,event_key,action,occurred_at,content) VALUES(?,?,?,?,?)',(identity,uuid4().hex,'Draft Saved',stamp,content))
        return dict(con.execute('SELECT * FROM customer_messages WHERE id=?',(identity,)).fetchone())


def launch_url(message_id):
    _guard()
    with closing(sqlite_db._connect()) as con:
        message=con.execute('SELECT * FROM customer_messages WHERE id=?',(int(message_id),)).fetchone()
        if message is None:raise ValueError('This message is unavailable.')
        customer=_context(con,message['customer_id'],message['order_id'])
        _payment_guard(con,message['template_type'],message['order_id'])
        return whatsapp_url(customer.get('phone_number') or customer['phone'],message['content'])


def record_opened(message_id,event_id,version):
    _guard();_token(event_id)
    with sqlite_db.transaction() as con:
        message=con.execute('SELECT * FROM customer_messages WHERE id=?',(int(message_id),)).fetchone()
        if message is None:raise ValueError('This message is unavailable.')
        key='opened:'+event_id
        previous=con.execute('SELECT message_id FROM customer_message_activity WHERE event_key=?',(key,)).fetchone()
        if previous:
            if previous['message_id']!=message['id']:raise ValueError('Invalid message event.')
            return dict(message)
        if version!=message['version']:raise ValueError('The message changed. Review its latest content before opening WhatsApp.')
        if message['status']=='Sent':return dict(message)
        customer=_context(con,message['customer_id'],message['order_id']);_payment_guard(con,message['template_type'],message['order_id'])
        whatsapp_url(customer.get('phone_number') or customer['phone'],message['content'])
        stamp=now()
        con.execute("UPDATE customer_messages SET status='WhatsApp Opened',whatsapp_opened_at=COALESCE(whatsapp_opened_at,?),updated_at=?,version=version+1 WHERE id=?",(stamp,stamp,message['id']))
        con.execute('INSERT INTO customer_message_activity(message_id,event_key,action,occurred_at,content) VALUES(?,?,?,?,?)',(message['id'],key,'WhatsApp Opened',stamp,message['content']))
        return dict(con.execute('SELECT * FROM customer_messages WHERE id=?',(message['id'],)).fetchone())


def mark_sent(message_id,*,confirmed=False):
    _guard()
    if not confirmed:raise ValueError('Confirm that you manually sent this message.')
    with sqlite_db.transaction() as con:
        message=con.execute('SELECT * FROM customer_messages WHERE id=?',(int(message_id),)).fetchone()
        if message is None:raise ValueError('This message is unavailable.')
        if message['sent_at']:return dict(message)
        if not message['whatsapp_opened_at']:raise ValueError('Open WhatsApp and manually send the message before marking it sent.')
        stamp=now()
        con.execute("UPDATE customer_messages SET status='Sent',sent_at=?,updated_at=?,version=version+1 WHERE id=?",(stamp,stamp,message['id']))
        con.execute('INSERT INTO customer_message_activity(message_id,event_key,action,occurred_at,content) VALUES(?,?,?,?,?)',(message['id'],'sent:'+str(message['id']),'Marked as Sent by Owner',stamp,message['content']))
        return dict(con.execute('SELECT * FROM customer_messages WHERE id=?',(message['id'],)).fetchone())


def schedule_followup(message_id,when,notes=''):
    _guard()
    if not isinstance(when,datetime):raise ValueError('Choose a valid follow-up date and time.')
    if len(notes)>2000:raise ValueError('Follow-up notes must be at most 2,000 characters.')
    due=(when.replace(tzinfo=MYT) if when.tzinfo is None else when.astimezone(MYT)).isoformat()
    with sqlite_db.transaction() as con:
        message=con.execute('SELECT * FROM customer_messages WHERE id=?',(int(message_id),)).fetchone()
        if message is None:raise ValueError('This message is unavailable.')
        if message['followup_at']==due and message['notes']==notes and not message['followup_completed_at']:return
        stamp=now()
        con.execute('UPDATE customer_messages SET followup_at=?,notes=?,followup_completed_at=NULL,updated_at=?,version=version+1 WHERE id=?',(due,notes,stamp,message['id']))
        con.execute('INSERT INTO customer_message_activity(message_id,event_key,action,occurred_at,content) VALUES(?,?,?,?,?)',(message['id'],uuid4().hex,'Follow-up Scheduled / Rescheduled',stamp,due+'\n'+notes))


def complete_followup(message_id):
    _guard()
    with sqlite_db.transaction() as con:
        message=con.execute('SELECT * FROM customer_messages WHERE id=?',(int(message_id),)).fetchone()
        if message is None or not message['followup_at']:raise ValueError('Schedule a follow-up first.')
        if message['followup_completed_at']:return
        stamp=now()
        con.execute('UPDATE customer_messages SET followup_completed_at=?,updated_at=?,version=version+1 WHERE id=?',(stamp,stamp,message['id']))
        con.execute('INSERT INTO customer_message_activity(message_id,event_key,action,occurred_at) VALUES(?,?,?,?)',(message['id'],uuid4().hex,'Follow-up Completed',stamp))


def reminder_counts(current=None):
    current=current or datetime.now(MYT)
    today=current.astimezone(MYT).date()
    records=messages()
    pending=[datetime.fromisoformat(m['followup_at']).astimezone(MYT) for m in records if m['followup_at'] and not m['followup_completed_at']]
    return dict(due_today=sum(d.date()==today and d>=current for d in pending),overdue=sum(d<current for d in pending),upcoming=sum(d>=current for d in pending),drafts=sum(m['status']=='Draft' for m in records))


def inbox(search='',filter_name='All'):
    _guard()
    orders=sorted(orders_store.list_orders(),key=_order_key,reverse=True);activity=messages();current=datetime.now(MYT)
    with closing(sqlite_db._connect()) as con:customers=[dict(r) for r in con.execute('SELECT * FROM customers ORDER BY name,id')]
    result=[];needle=search.strip().casefold()
    for customer in customers:
        related=[o for o in orders if o['customer_id']==customer['id']]
        records=[m for m in activity if m['customer_id']==customer['id']]
        overdue=any(m['followup_at'] and not m['followup_completed_at'] and datetime.fromisoformat(m['followup_at'])<=current for m in records)
        if filter_name=='Follow-up Needed' and not overdue:continue
        if filter_name=='Drafts' and not any(m['status']=='Draft' for m in records):continue
        if filter_name=='WhatsApp Opened' and not any(m['status']=='WhatsApp Opened' for m in records):continue
        if filter_name=='Completed' and not any(m['sent_at'] or m['followup_completed_at'] for m in records):continue
        phone=customer.get('phone_number') or customer.get('phone') or ''
        haystack=' '.join([customer.get('full_name') or customer['name'],phone,str(customer.get('normalized_phone') or '')]+[str(o.get('order_code') or o['id']) for o in related]).casefold()
        phone_match=False
        if re.fullmatch(r'[+\d\s().-]+',search.strip()):
            digits=re.sub(r'\D','',search).lstrip('0')
            phone_match=len(digits)>=3 and digits in re.sub(r'\D','',phone)
        if needle and needle not in haystack and not phone_match:continue
        latest=related[0] if related else {}
        last=max((m['updated_at'] for m in records),default=None)
        result.append(dict(customer,display_name=customer.get('full_name') or customer['name'],whatsapp=phone,latest_order=latest,last_activity=last,followup_status='Overdue' if overdue else 'Scheduled' if any(m['followup_at'] and not m['followup_completed_at'] for m in records) else 'None'))
    return result


def activity_history(customer_id):
    _guard()
    with closing(sqlite_db._connect()) as con:
        return [dict(r) for r in con.execute('''SELECT a.*,m.template_type,m.status,m.order_id FROM customer_message_activity a JOIN customer_messages m ON m.id=a.message_id WHERE m.customer_id=? ORDER BY a.id DESC''',(int(customer_id),))]


def followups(view='Upcoming',current=None):
    _guard()
    if view not in ('Upcoming','Overdue','Completed'):raise ValueError('Choose a valid reminder view.')
    current=current or datetime.now(MYT)
    with closing(sqlite_db._connect()) as con:
        rows=[dict(r) for r in con.execute('''SELECT m.id,m.customer_id,m.order_id,m.followup_at,m.followup_completed_at,m.notes,
            COALESCE(NULLIF(c.full_name,''),c.name) AS customer_name,o.order_code
            FROM customer_messages m JOIN customers c ON c.id=m.customer_id LEFT JOIN orders o ON o.id=m.order_id
            WHERE m.followup_at IS NOT NULL ORDER BY datetime(m.followup_at),m.id''')]
    return [r for r in rows if (bool(r['followup_completed_at']) if view=='Completed' else not r['followup_completed_at'] and
                               ((datetime.fromisoformat(r['followup_at'])<current) if view=='Overdue' else (datetime.fromisoformat(r['followup_at'])>=current)))]
