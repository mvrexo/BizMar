"""Pure safe template interpolation and WhatsApp launch URL construction."""
from datetime import datetime
import re
from string import Formatter
from urllib.parse import quote
from zoneinfo import ZoneInfo

DEFAULTS={
 'Order Received':'Hi {customer_name}, we have received order {order_id} dated {order_date}. Order total: {order_total}. We will contact you to confirm the details.',
 'Order Confirmation':'Hi {customer_name}, here are the details for order {order_id}: {order_total}. Current order status: {order_status}. Pickup/delivery: {delivery_date}, {delivery_time}. Please confirm these details.',
 'Payment Reminder':'Hi {customer_name}, a friendly payment reminder for order {order_id}. Order total: {order_total}. Current payment status: {payment_status}. Please contact us if you have any questions.',
 'Payment Received':'Hi {customer_name}, thank you. Your payment for order {order_id} has been recorded in our payment ledger. Current payment status: {payment_status}.',
 'Delivery Fee Confirmation':'Hi {customer_name}, delivery details for order {order_id}: delivery fee {delivery_fee}; order total {order_total}. Please review and confirm.',
 'Order Ready':'Hi {customer_name}, your order {order_id} is ready. Pickup/delivery is arranged for {delivery_date}, {delivery_time}. Please contact us to coordinate.',
 'Out for Delivery':'Hi {customer_name}, your order {order_id} is out for delivery. Scheduled delivery: {delivery_date}, {delivery_time}. Thank you.',
 'Order Completed':'Hi {customer_name}, we are following up on order {order_id}. Current order status: {order_status}. Please let us know if you need any help.',
 'Thank You Message':'Hi {customer_name}, thank you for supporting our business! We hope you enjoy order {order_id}.',
 'Custom Message':'Hi {customer_name}, ',
}
FIELDS={'customer_name','order_id','order_date','order_total','payment_status','order_status','delivery_date','delivery_time','delivery_fee'}


def validate_template(content):
    if not isinstance(content,str) or not content.strip() or len(content)>4000:
        raise ValueError('Enter a message or template of up to 4,000 characters.')
    try:
        for _,field,spec,conversion in Formatter().parse(content):
            if field is not None and (field not in FIELDS or spec or conversion):
                raise ValueError('Use only the supported placeholders, without formatting or attribute access.')
    except ValueError as error:
        raise ValueError('Check the template placeholders and matching braces.') from error
    return content


def render(content,values):
    validate_template(content)
    return content.format_map({key:str(values.get(key) or 'Not provided') for key in FIELDS})


def normalize_phone(value):
    text=str(value or '').strip()
    if not text or not re.fullmatch(r'[+()\d\s.\-]+',text):
        raise ValueError('A valid Malaysian WhatsApp number is required. Update the customer phone first.')
    digits=re.sub(r'\D','',text)
    if text.startswith('+') and not digits.startswith('60'):
        raise ValueError('Use a Malaysian number beginning with +60 or 0.')
    if digits.startswith('0060'):digits=digits[2:]
    if digits.startswith('60'):national=digits[2:]
    elif digits.startswith('0'):national=digits[1:]
    else:national=digits
    if not (re.fullmatch(r'1\d{8,9}',national) or re.fullmatch(r'[3-9]\d{7,8}',national)):
        raise ValueError('A valid Malaysian WhatsApp number is required. Update the customer phone first.')
    return '60'+national


def whatsapp_url(phone,content):
    if not isinstance(content,str) or not content.strip() or len(content)>4000:
        raise ValueError('Enter a message of up to 4,000 characters.')
    return 'https://wa.me/'+normalize_phone(phone)+'?text='+quote(content,safe='')


def display_date(value):
    if not value:return 'Not provided'
    try:
        parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if parsed.tzinfo:parsed=parsed.astimezone(ZoneInfo('Asia/Kuala_Lumpur'))
        return parsed.strftime('%d %b %Y')
    except ValueError:return 'Not provided'
