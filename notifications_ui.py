from display_preferences import option_labels
"""Reference-inspired notification inbox using only existing persisted notices."""
from display_preferences import tr
from collections import OrderedDict
from datetime import datetime,timedelta
from html import escape
from zoneinfo import ZoneInfo
import streamlit as st
import orders_store

MYT=ZoneInfo('Asia/Kuala_Lumpur')


def timestamp(value):
    try:
        parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return (parsed.replace(tzinfo=MYT) if parsed.tzinfo is None else parsed.astimezone(MYT))
    except (ValueError,TypeError):return None


def group_notifications(records,current=None):
    current=current or datetime.now(MYT)
    today=current.astimezone(MYT).date();week=today-timedelta(days=today.weekday())
    groups=OrderedDict((name,[]) for name in ('Today','Yesterday','This Week','Earlier'))
    for record in sorted(records,key=lambda r:(timestamp(r['created_at']) or datetime.min.replace(tzinfo=MYT),r['id']),reverse=True):
        created=timestamp(record['created_at'])
        day=created.date() if created else None
        name='Today' if day==today else 'Yesterday' if day==today-timedelta(days=1) else 'This Week' if day and week<=day<today else 'Earlier'
        groups[name].append(record)
    return {name:rows for name,rows in groups.items() if rows}


def relative_time(value,current=None):
    created=timestamp(value)
    if created is None:return 'Time unavailable'
    seconds=max(0,int(((current or datetime.now(MYT))-created).total_seconds()))
    if seconds<60:return 'Just now'
    if seconds<3600:return f'{seconds//60}m ago'
    if seconds<86400:return f'{seconds//3600}h ago'
    return created.strftime('%d %b %Y · %H:%M MYT')


def styles():
    st.markdown(tr('''<style>
    [class*="st-key-notification_card_"]{background:var(--forest-card,var(--nour-surface,#fffcf8));border:1px solid var(--forest-border,var(--nour-line,#dfd5df));border-radius:28px;padding:22px;box-shadow:var(--nour-shadow,0 10px 28px rgba(0,0,0,.08));}
    .st-key-notification_card_full{max-width:860px;margin:0 auto;}
    [class*="st-key-notification_card_"] h3{font-size:26px;font-weight:700;letter-spacing:normal;}
    [class*="st-key-notice_row_"]{border-bottom:1px solid var(--forest-border,var(--nour-line,#dfd5df));padding:15px 0;}
    [class*="st-key-notice_row_"]:hover{background:var(--forest-hover,rgba(220,233,203,.18));border-radius:14px;}
    [class*="st-key-notice_row_"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;align-items:center;gap:10px;}
    [class*="st-key-notice_row_"] [data-testid="stColumn"]:nth-child(1){flex:0 0 58px!important;width:58px!important;min-width:58px!important;}
    [class*="st-key-notice_row_"] [data-testid="stColumn"]:nth-child(2){flex:1 1 0!important;min-width:0!important;}
    [class*="st-key-notice_row_"] [data-testid="stColumn"]:nth-child(3){flex:0 0 38px!important;width:38px!important;min-width:38px!important;}
    [class*="st-key-notice_row_"] [data-testid="stButton"] button{border:0!important;box-shadow:none!important;background:transparent!important;min-height:32px;padding:0 2px;justify-content:flex-start;text-align:left;color:var(--forest-primary,var(--nour-matcha-strong,#426536))!important;}
    [class*="st-key-notice_row_"] [data-testid="stButton"] button p{font-weight:600;white-space:normal;overflow-wrap:anywhere;}
    [class*="st-key-notice_row_"] [data-testid="stColumn"]:nth-child(3) button{border-radius:12px;background:var(--forest-hover,var(--nour-strawberry,#f8dce2))!important;width:36px;height:36px;justify-content:center;}
    .bizmar-notice-avatar{position:relative;display:flex;align-items:center;justify-content:center;margin-left:8px;width:44px;height:44px;border-radius:50%;background:var(--forest-hover,var(--nour-matcha,#dce9cb));color:var(--forest-text,var(--nour-matcha-strong,#426536));font:600 15px 'Plus Jakarta Sans',Arial,sans-serif;}
    .bizmar-notice-dot{position:absolute;left:-9px;top:19px;width:7px;height:7px;border-radius:50%;background:var(--forest-pink,var(--nour-strawberry-strong,#98415a));}
    .bizmar-notice-type{position:absolute;right:-1px;bottom:-2px;background:var(--forest-card,var(--nour-surface,#fffcf8));border-radius:50%;font-size:12px;padding:2px;}
    @media(max-width:640px){[class*="st-key-notification_card_"]{padding:14px;}[class*="st-key-notice_row_"] [data-testid="stHorizontalBlock"]{gap:7px;}}
    </style>'''),unsafe_allow_html=True)


def render_notification(notification,key_prefix,open_order):
    with st.container(key=f'notice_row_{key_prefix}_{notification["id"]}'):
        avatar,content,action=st.columns([1,5,1],gap='small',vertical_alignment='center')
        with avatar:
            initials=''.join(part[0] for part in str(notification['customer_name']).split()[:2]).upper() or '?'
            dot='<span class="bizmar-notice-dot" aria-label="Unread"></span>' if notification.get('read_at') is None else ''
            st.markdown(tr(f'<div class="bizmar-notice-avatar" aria-hidden="true">{escape(initials)}{dot}<span class="bizmar-notice-type">↗</span></div>'),unsafe_allow_html=True)
        with content:
            if st.button(str(notification['customer_name']),key=f'{key_prefix}_order_{notification["id"]}',help=f'View order {notification["order_code"]}',use_container_width=True):
                orders_store.mark_order_notification_read(notification['id'])
                open_order(notification['order_id'])
            st.caption(tr(f"New order received · {notification['order_code']} · {relative_time(notification['created_at'])}"))
        with action:
            if notification.get('read_at') is None:
                if st.button(tr(''),key=f'{key_prefix}_read_{notification["id"]}',icon=':material/done:',help=tr('Mark as read')):
                    orders_store.mark_order_notification_read(notification['id']);st.rerun()
            else:
                st.caption(tr('✓ Read'))


def render_notifications(open_order,*,compact=False,key_prefix='notifications_order'):
    try:
        records=orders_store.list_order_notifications()
        counts=orders_store.order_notification_counts()
    except PermissionError:
        st.warning(tr('Sign in as the owner to view notifications.'));return
    except Exception:
        st.error(tr('Notifications could not be loaded. Please retry.'));return
    styles()
    with st.container(key='notification_card_'+('compact' if compact else 'full')):
        heading,filters=st.columns([5,1],vertical_alignment='center')
        with heading:st.markdown(tr('### Notifications'))
        with filters:
            with st.popover(tr(''),icon=':material/tune:',help=tr('Notification filters')):
                selection=st.radio(tr('Show notifications'),['All','Unread'],key=f'{key_prefix}_filter', format_func=option_labels(['All','Unread']))
        current=datetime.now(MYT)
        today_count=sum(timestamp(r['created_at']) is not None and timestamp(r['created_at']).date()==current.date() for r in records)
        st.caption(tr(f"You have {today_count} notifications today · {counts['unread']} unread"))
        if st.button(tr('Mark all as read'),key=f'{key_prefix}_mark_all_read',icon=':material/done_all:',disabled=not counts['unread']):
            orders_store.mark_order_notification_read(mark_all=True);st.rerun()
        shown=[r for r in records if selection=='All' or r.get('read_at') is None]
        if not shown:
            st.info(tr('You’re all caught up.' if selection=='Unread' else 'No order notifications yet.'))
        else:
            with st.container(height=390 if compact else 'content',border=False):
                for label,rows in group_notifications(shown,current).items():
                    st.markdown(tr(f'**{label}**'))
                    for row in rows:render_notification(row,key_prefix,open_order)
