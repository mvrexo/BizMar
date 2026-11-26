from display_preferences import option_labels
"""Six-section settings view using the existing authenticated owner workspace."""
from io import BytesIO
import importlib.util
import zipfile
import pandas as pd
import streamlit as st
import sqlite_db
from owner_profile import _email, get_profile, save_profile, avatar_url
from settings_store import load, save, business_logo, validate_phone
from display_preferences import tr

CATEGORIES = ['Bakery & Desserts', 'Food & Beverages', 'Retail', 'Services', 'Other']


def _save(values, logo=None):
    save(values, logo)
    st.session_state.bizmar_preferences = values
    st.session_state.settings_notice = 'Settings saved.'
    st.rerun()


def _appearance_changed():
    """Persist only appearance fields through the existing owner settings store."""
    current=load()
    updated={**current,
             'theme':'Dark' if st.session_state['settings_dark_mode'] else 'Light',
             'language':st.session_state['settings_language'],
             'date_format':st.session_state['settings_date_format']}
    try:
        save(updated)
    except (ValueError,OSError) as error:
        st.session_state.settings_appearance_error=str(error)
        st.session_state['settings_dark_mode']=current['theme']=='Dark'
        st.session_state['settings_language']=current['language']
        st.session_state['settings_date_format']=current['date_format']
    else:
        st.session_state.bizmar_preferences=updated
        st.session_state.settings_notice='Settings saved.'


def export_tables():
    """This schema is one owner workspace, not tenant-scoped business records."""
    email = _email()
    configured_owner = str(st.secrets.get('OWNER_EMAIL', '')).strip().lower()
    if not configured_owner or email != configured_owner:
        raise PermissionError('Exports require the configured workspace owner. Business records are shared within this single-owner database.')
    # Explicit allowlist excludes profiles, credentials, settings, tokens and secrets.
    return {table: pd.DataFrame(sqlite_db.all_rows(table)) for table in
            ('products', 'customers', 'orders', 'order_items', 'payments')}


def csv_archive(tables):
    output = BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, frame in tables.items():
            safe = frame.copy()
            # Prevent user-entered cells being interpreted as spreadsheet formulas.
            for column in safe.select_dtypes(include=['object', 'string']).columns:
                safe[column] = safe[column].map(lambda value: "'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value)
            archive.writestr(name + '.csv', safe.to_csv(index=False).encode('utf-8-sig'))
    return output.getvalue()


def render_settings(sign_out, local_auth=False, alert_renderer=None, import_renderer=None):
    _email()  # Guard before reading any settings or records.
    values, profile = load(), get_profile()
    st.session_state.bizmar_preferences = values
    if st.session_state.pop('settings_notice', None):
        st.success(tr('Settings saved.'))
    tabs = st.tabs([tr(label) for label in ['Account Settings', 'Business Profile', 'Order Preferences',
                    'Notifications', 'Appearance & Preferences', 'Security & Data']])
    with tabs[0]:
        st.subheader(tr('Account Settings'))
        photo = avatar_url(profile)
        if photo:
            st.image(photo, width=80)
        with st.form('settings_account'):
            name = st.text_input(tr('Full name'), value=profile['display_name'], max_chars=100)
            st.text_input(tr('Email address'), value=profile['email'], disabled=True)
            st.caption(tr('Email is your authentication identity. Email changes require a verified provider flow and are unavailable here.'))
            phone = st.text_input(tr('Phone number'), value=profile['phone'], max_chars=50)
            upload = st.file_uploader(tr('Profile photo (JPG, PNG or WEBP, up to 3 MB)'), type=['jpg', 'jpeg', 'png', 'webp'])
            if st.form_submit_button(tr('Save account'), type='primary'):
                try:
                    validate_phone(phone)
                    save_profile(name, profile['business_name'] or 'My Business', phone, photo=upload)
                    st.session_state.settings_notice = 'Settings saved.'
                    st.rerun()
                except (ValueError, OSError) as error:
                    st.error(tr(str(error)))
        st.caption(tr('Password controls are in Security & Data.'))
    with tabs[1]:
        st.subheader(tr('Business Profile'))
        logo = business_logo()
        if logo:
            st.image(logo, width=120)
        with st.form('settings_business'):
            business = st.text_input(tr('Business name'), value=profile['business_name'], max_chars=200)
            category = st.selectbox(tr('Business category'), CATEGORIES, index=CATEGORIES.index(values['category']),format_func=option_labels(CATEGORIES))
            address = st.text_area(tr('Business address'), value=values['address'], max_chars=2000)
            contact = st.text_input(tr('Contact number'), value=values['contact'])
            description = st.text_area(tr('Business description'), value=values['description'], max_chars=2000)
            hours = st.text_input(tr('Operating hours'), value=values['hours'], placeholder=tr('Mon–Fri, 9:00 AM–6:00 PM'))
            upload = st.file_uploader(tr('Business logo (JPG, PNG or WEBP, up to 3 MB)'), type=['jpg', 'jpeg', 'png', 'webp'])
            if st.form_submit_button(tr('Save business profile'), type='primary'):
                try:
                    validate_phone(contact)
                    if not business.strip():
                        raise ValueError('Business name is required.')
                    if upload is not None:
                        from owner_profile import _image_bytes
                        _image_bytes(upload)
                    updated = {**values, **dict(category=category, address=address, contact=contact, description=description, hours=hours)}
                    if any(len(updated[key]) > 2000 for key in ('address', 'contact', 'description', 'hours')):
                        raise ValueError('Business fields must be at most 2000 characters.')
                    save_profile(profile['display_name'], business, profile['phone'])
                    _save(updated, upload)
                except (ValueError, OSError) as error:
                    st.error(tr(str(error)))
    with tabs[2]:
        st.subheader(tr('Order Preferences'))
        st.caption(tr('Defaults apply to new orders and payments. Existing order IDs and records stay unchanged.'))
        with st.form('settings_orders'):
            status = 'Pending'
            st.caption(tr('New orders start as Pending. Complete or cancel them from Order Details.'))
            prefix = st.text_input(tr('Order ID prefix'), value=values['prefix'], max_chars=10)
            methods = ['Transfer', 'Cash', 'E-wallet', 'Other']
            payment = st.selectbox(tr('Default payment method'), methods, index=methods.index(values['payment']),format_func=option_labels(methods))
            cancellation = st.toggle(tr('Allow order cancellation'), value=values['cancellation'])
            reminder = st.number_input(tr('Deadline reminder (days ahead)'), min_value=0, max_value=30, value=values['reminder_days'])
            if st.form_submit_button(tr('Save order preferences'), type='primary'):
                try:
                    _save({**values, **dict(status=status, prefix=prefix.strip().upper(), payment=payment, cancellation=cancellation, reminder_days=int(reminder))})
                except ValueError as error:
                    st.error(tr(str(error)))
        st.caption(tr('Inventory tracking is unavailable; no low-stock settings are offered.'))
    with tabs[3]:
        st.subheader(tr('Notification Settings'))
        st.caption(tr('These controls affect in-app Notifications & Alerts only.'))
        with st.form('settings_notifications'):
            deadlines = st.toggle(tr('Upcoming order deadlines'), value=values['deadlines'])
            payments = st.toggle(tr('Overdue payments'), value=values['overdue_payments'])
            pending = st.toggle(tr('Pending orders'), value=values['pending_orders'])
            if st.form_submit_button(tr('Save notification preferences'), type='primary'):
                _save({**values, **dict(deadlines=deadlines, overdue_payments=payments, pending_orders=pending)})
        st.caption(tr('Low-stock alerts, daily sales summaries and email/SMS/push delivery are unavailable.'))
        if alert_renderer:
            with st.expander(tr('Production alert thresholds')):
                alert_renderer()
    with tabs[4]:
        st.subheader(tr('Appearance & Preferences'))
        for key,value in [('settings_dark_mode',values['theme']=='Dark'),('settings_language',values['language']),('settings_date_format',values['date_format'])]:
            if key not in st.session_state:st.session_state[key]=value
        st.toggle(tr('Dark Mode'),key='settings_dark_mode',on_change=_appearance_changed)
        st.selectbox(tr('Language'),['English','Bahasa Melayu'],key='settings_language',on_change=_appearance_changed, format_func=option_labels(['English','Bahasa Melayu']))
        st.selectbox(tr('Currency'),['MYR (RM)'],disabled=True, format_func=option_labels(['MYR (RM)']))
        st.selectbox(tr('Date format'),['DD/MM/YYYY','MM/DD/YYYY','YYYY-MM-DD'],key='settings_date_format',on_change=_appearance_changed, format_func=option_labels(['DD/MM/YYYY','MM/DD/YYYY','YYYY-MM-DD']))
        st.caption(tr('Changes are saved automatically. Dark mode applies to page content only.'))
        if error:=st.session_state.pop('settings_appearance_error',None):st.error(tr(error))
    with tabs[5]:
        st.subheader(tr('Security & Data Management'))
        if local_auth:
            with st.form('settings_password'):
                current = st.text_input(tr('Current password'), type='password')
                replacement = st.text_input(tr('New password'), type='password')
                confirm = st.text_input(tr('Confirm new password'), type='password')
                if st.form_submit_button(tr('Change password')):
                    try:
                        if replacement != confirm:
                            raise ValueError('Passwords do not match.')
                        from local_auth import change_password
                        change_password(profile['email'], current, replacement)
                        st.success(tr('Password changed. Sign in again.'))
                        sign_out()
                        st.rerun()
                    except (ValueError, RuntimeError, OSError) as error:
                        st.error(tr(str(error)))
        else:
            st.info(tr('Password and email changes are managed by your authentication provider. A verified current-password change flow is not connected in this UAT build.'))
        if st.button(tr('Sign Out'), key='settings_secure_logout', icon=':material/logout:'):
            sign_out()
            if st.user.is_logged_in:
                st.logout()
            else:
                st.rerun()
        st.divider()
        st.caption(tr('The database represents one configured business owner. Exports omit authentication, profile and settings tables. No database reset or deletion is offered.'))
        if st.button(tr('Prepare business export'), key='settings_prepare_export'):
            try:
                tables = export_tables()
                st.download_button(tr('Download CSV backup (ZIP)'), csv_archive(tables), 'bizmar_business_backup.zip', 'application/zip')
                st.caption(tr('This is a logical business-record backup, not a raw database or automatic restore file.'))
                if importlib.util.find_spec('xlsxwriter'):
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter', engine_kwargs={'options': {'strings_to_formulas': False, 'strings_to_urls': False}}) as writer:
                        for name, frame in tables.items():
                            frame.to_excel(writer, sheet_name=name, index=False)
                    st.download_button(tr('Download Excel'), output.getvalue(), 'bizmar_business.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                else:
                    st.caption(tr('Excel export unavailable: optional xlsxwriter dependency is not installed.'))
            except (PermissionError, OSError, ValueError) as error:
                st.error(tr(str(error)))
        if import_renderer:
            with st.expander(tr('Existing data import tools')):
                if importlib.util.find_spec('openpyxl'):
                    import_renderer()
                else:
                    st.info(tr('Excel import tools require openpyxl. Install the project requirements to enable them.'))
