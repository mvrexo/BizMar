from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import pandas as pd
import plotly.graph_objects as go
from streamlit.testing.v1 import AppTest
import display_preferences as display
import settings_store
import owner_profile
import sqlite_db


class PageLocalizationTests(unittest.TestCase):
    def test_standard_malaysian_terminology(self):
        expected={'Overview':'Papan Pemuka','Sales Analytics':'Analisis Jualan','Notifications':'Pemberitahuan','Outstanding Balance':'Baki Belum Bayar','Edit Customer':'Kemas Kini Pelanggan','Settings sections':'Bahagian Tetapan','Settings saved.':'Tetapan berjaya disimpan.','Forgot your password?':'Terlupa kata laluan?','Send recovery code':'Hantar kod pemulihan','Resend confirmation email':'Hantar semula e-mel pengesahan','The recovery code is invalid or expired.':'Kod pemulihan tidak sah atau telah tamat tempoh.','Please verify your email before signing in.':'Sahkan alamat e-mel anda sebelum log masuk.','Too many login attempts. Please wait and try again.':'Terlalu banyak percubaan log masuk. Sila tunggu sebentar dan cuba lagi.','Unable to sign in. Please check the account and try again.':'Log masuk tidak berjaya. Semak akaun anda dan cuba lagi.','The authentication server could not be found. Check the configured Supabase project and your network DNS, then try again.':'Pelayan pengesahan tidak dapat ditemui. Semak projek Supabase yang ditetapkan dan DNS rangkaian, kemudian cuba lagi.','or':'atau'}
        with patch.object(display,'runtime',return_value={'language':'Bahasa Melayu'}):
            for label,value in expected.items():self.assertEqual(display.tr(label),value)
            self.assertEqual(display.tr('BizMar'),'BizMar')
            self.assertEqual(display.tr('ORD012'),'ORD012')
            self.assertEqual(display.tr('<span data-status="Pending">Pending</span>'),'<span data-status="Pending">Belum Diproses</span>')

    def test_google_forms_labels_and_dynamic_messages_translate_without_changing_source_values(self):
        from google_forms_importer import FIELD_LABELS
        with patch.object(display,'runtime',return_value={'language':'Bahasa Melayu'}):
            for label in FIELD_LABELS.values():
                self.assertNotEqual(display.tr(label),label)
            self.assertEqual(display.tr('Import Google Forms Orders'),'Import Pesanan Google Forms')
            self.assertEqual(display.tr('Not mapped'),'Tidak dipadankan')
            self.assertEqual(display.tr('Row 7: quantity in "Delivery" must be a whole number or blank'),
                             'Baris 7: kuantiti dalam "Delivery" mestilah nombor bulat atau dibiarkan kosong')
            self.assertEqual(display.tr('Map a spreadsheet column to Customer name.'),
                             'Padankan lajur hamparan dengan Nama pelanggan.')
            self.assertEqual(display.tr('Product mapping references missing column "Delivery".'),
                             'Lajur "Delivery" yang dirujuk dalam pemadanan produk tiada.')
            self.assertEqual(display.tr('Import complete: 3 new orders saved; 1 duplicate responses skipped.'),
                             'Import selesai: 3 pesanan baharu disimpan; 1 respons pendua dilangkau.')
            self.assertEqual(display.tr('Unable to read the response file: File exceeds 5 MB. Split it into smaller files.'),
                             'Tidak dapat membaca fail respons: Fail melebihi 5 MB. Bahagikan kepada beberapa fail yang lebih kecil.')

    def test_google_forms_import_dialog_uses_bahasa_melayu(self):
        source='''import streamlit as st
from settings_store import DEFAULTS
st.session_state.bizmar_preferences={**DEFAULTS,'language':'Bahasa Melayu'}
from google_forms_importer import render_google_forms_import
render_google_forms_import()
'''
        app=AppTest.from_string(source).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.caption[0].value,'Import fail respons Google Forms. Padankan lajur borang dan semak kuantiti produk serta jumlah sebelum menyimpan.')
        self.assertEqual(app.info[0].value,'Persediaan awal memerlukan pemadanan lajur secara manual kerana tajuk Google Forms berbeza-beza. Eksport helaian respons sebagai Excel (.xlsx) atau CSV; fail diproses secara setempat.')
        self.assertEqual(app.get('file_uploader')[0].label,'Muat naik respons Google Forms (.xlsx atau .csv), maksimum 5 MB')

    def test_option_formatting_keeps_stored_statuses_and_render_language(self):
        choices=['Pending','Completed','Cancelled']
        with patch.object(display,'runtime',return_value={'language':'Bahasa Melayu'}):
            format_label=display.option_labels(choices)
        self.assertEqual(format_label('Pending'),'Belum Diproses')
        self.assertEqual(choices,['Pending','Completed','Cancelled'])

    def test_chart_labels_do_not_change_data(self):
        frame=pd.DataFrame({'Status':['Pending','Completed'],'Revenue':[12.,32.]})
        fig=go.Figure(go.Bar(x=frame.Status,y=frame.Revenue,name='Revenue',customdata=['ORD001','ORD002'],hovertemplate='Revenue: RM %{y}<extra></extra>'))
        fig.update_layout(xaxis_title='Status',yaxis_title='Revenue')
        with patch.object(display,'runtime',return_value={**settings_store.DEFAULTS,'language':'Bahasa Melayu','theme':'Dark'}):
            display.style_figure(fig)
        self.assertEqual(list(fig.data[0].x),['Pending','Completed'])
        self.assertEqual(list(fig.data[0].y),[12.,32.])
        self.assertEqual(list(fig.data[0].customdata),['ORD001','ORD002'])
        self.assertEqual(fig.data[0].name,'Hasil Jualan')
        self.assertEqual(list(fig.layout.xaxis.ticktext),['Belum Diproses','Selesai'])

    def test_dark_css_is_scoped_not_sidebar_or_application_root(self):
        css=(Path(__file__).resolve().parents[1]/'styles/dark.css').read_text(encoding='utf-8')
        self.assertNotIn(':root',css)
        self.assertNotIn('stSidebar',css)
        self.assertNotIn('stAppViewContainer',css)
        self.assertIn('[data-testid="stMain"]',css)
        self.assertIn('[role="dialog"]',css)
        self.assertIn('[role="listbox"]',css)

    def test_immediate_persisted_preferences_preserve_business_records(self):
        with TemporaryDirectory(prefix='bizmar-appearance-unit-') as temporary:
            db=Path(temporary)/'settings.sqlite3'
            identity=SimpleNamespace(session_state={'authenticated':True,'local_owner_email':'owner@example.test'},secrets={'OWNER_EMAIL':'owner@example.test'})
            with patch.object(sqlite_db,'DB_PATH',db),patch.object(owner_profile,'DATABASE',db),patch.object(owner_profile,'st',identity):
                sqlite_db.initialize()
                sqlite_db.add('customers',dict(name='Orders',phone='0123456789',address='Original address',state='Kedah'))
                before=sqlite_db.all_rows('customers')
                code='from settings_ui import render_settings\nrender_settings(lambda:None)'
                app=AppTest.from_string(code).run()
                app.toggle(key='settings_dark_mode').set_value(True).run()
                app.selectbox(key='settings_language').set_value('Bahasa Melayu').run()
                self.assertFalse(app.exception)
                self.assertEqual(settings_store.load()['theme'],'Dark')
                self.assertEqual(settings_store.load()['language'],'Bahasa Melayu')
                self.assertTrue(any(x.value=='Tetapan berjaya disimpan.' for x in app.success))
                identity.session_state['authenticated']=False
                with self.assertRaises(PermissionError):settings_store.load()
                identity.session_state['authenticated']=True
                restarted=AppTest.from_string(code).run()
                self.assertTrue(restarted.toggle(key='settings_dark_mode').value)
                self.assertEqual(restarted.tabs[0].label,'Tetapan Akaun')
                restarted.toggle(key='settings_dark_mode').set_value(False).run()
                restarted.selectbox(key='settings_language').set_value('English').run()
                self.assertEqual(settings_store.load()['theme'],'Light')
                self.assertEqual(settings_store.load()['language'],'English')
                self.assertEqual(sqlite_db.all_rows('customers'),before)

if __name__=='__main__':unittest.main()
