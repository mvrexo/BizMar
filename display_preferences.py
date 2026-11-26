"""Presentation preferences; never modify stored dates, money, or route identifiers."""
from datetime import date, datetime
import re
from settings_store import runtime

DATE_FORMATS = {'DD/MM/YYYY': '%d/%m/%Y', 'MM/DD/YYYY': '%m/%d/%Y', 'YYYY-MM-DD': '%Y-%m-%d'}
MALAY = {
    'Dashboard': 'Papan Pemuka', 'Orders': 'Pesanan', 'Products': 'Produk', 'Analytics': 'Analitik',
    'Settings': 'Tetapan', 'Account Settings': 'Tetapan Akaun', 'Business Profile': 'Profil Perniagaan',
    'Order Preferences': 'Keutamaan Pesanan', 'Notifications': 'Notifikasi',
    'Appearance & Preferences': 'Penampilan & Keutamaan', 'Security & Data': 'Keselamatan & Data',
    'Full name': 'Nama penuh', 'Email address': 'Alamat e-mel', 'Phone number': 'Nombor telefon',
    'Save account': 'Simpan akaun', 'Business name': 'Nama perniagaan', 'Business category': 'Kategori perniagaan',
    'Business address': 'Alamat perniagaan', 'Contact number': 'Nombor untuk dihubungi',
    'Business description': 'Penerangan perniagaan', 'Operating hours': 'Waktu operasi',
    'Save business profile': 'Simpan profil perniagaan', 'Default order status': 'Status lalai pesanan',
    'Order ID prefix': 'Awalan ID pesanan', 'Default payment method': 'Kaedah bayaran lalai',
    'Allow order cancellation': 'Benarkan pembatalan pesanan', 'Deadline reminder (days ahead)': 'Peringatan tarikh akhir (hari lebih awal)',
    'Save order preferences': 'Simpan keutamaan pesanan', 'Notification Settings': 'Tetapan Notifikasi',
    'Upcoming order deadlines': 'Tarikh akhir pesanan akan datang', 'Overdue payments': 'Bayaran tertunggak',
    'Pending orders': 'Pesanan belum disahkan', 'Save notification preferences': 'Simpan keutamaan notifikasi',
    'Theme': 'Tema', 'Language': 'Bahasa', 'Currency': 'Mata wang', 'Date format': 'Format tarikh',
    'Save appearance preferences': 'Simpan keutamaan penampilan', 'Light': 'Cerah', 'Dark': 'Gelap',
    'Security & Data Management': 'Keselamatan & Pengurusan Data', 'Current password': 'Kata laluan semasa',
    'New password': 'Kata laluan baharu', 'Confirm new password': 'Sahkan kata laluan baharu',
    'Change password': 'Tukar kata laluan', 'Sign Out': 'Log Keluar', 'Back': 'Kembali',
    'Edit Profile': 'Edit Profil', 'Messages': 'Mesej', 'Notifications & Alerts': 'Notifikasi & Amaran',
    'Total Sales': 'Jumlah Unit Terjual', 'Total Revenue': 'Jumlah Hasil',
    'Total Orders': 'Jumlah Pesanan', 'Total Profits': 'Jumlah Keuntungan',
    'Outstanding Balance': 'Baki Tertunggak', 'Gross Profit': 'Untung Kasar',
    'Sales by State': 'Jualan Mengikut Negeri',
    'Customer Location Analytics': 'Analitik Lokasi Pelanggan',
    'Measure': 'Ukuran', 'By Customers': 'Mengikut Pelanggan', 'By Orders': 'Mengikut Pesanan',
    'Customers': 'Pelanggan', 'Orders': 'Pesanan',
    'Total Customers with Known Location': 'Jumlah Pelanggan dengan Lokasi Diketahui',
    'Top State': 'Negeri Teratas', 'Unknown locations': 'Lokasi tidak diketahui',
    'Top 5 Customer States': '5 Negeri Pelanggan Teratas',
    'Top 5 States by Orders': '5 Negeri Teratas Mengikut Pesanan',
    'No known customer locations in this period.': 'Tiada lokasi pelanggan diketahui dalam tempoh ini.',
    'Key Insights': 'Wawasan Utama', 'Top-Selling Product': 'Produk Paling Laris',
    'Top Sales State': 'Negeri Jualan Tertinggi', 'Average Order Value': 'Nilai Purata Pesanan',
    'Completion Rate': 'Kadar Penyelesaian', 'No sales yet': 'Belum ada jualan',
    'units sold': 'unit terjual', 'per order in selected period': 'bagi setiap pesanan dalam tempoh dipilih',
    'of': 'daripada', 'orders completed': 'pesanan selesai',
    'No orders in selected period': 'Tiada pesanan dalam tempoh dipilih',
    'Upcoming Orders': 'Pesanan akan datang', 'Best Selling Product': 'Produk Terlaris', 'Top Customer': 'Pelanggan Teratas',
    'View all orders': 'Lihat semua pesanan', 'View customers': 'Lihat pelanggan',
    'Quick Order Entry': 'Pesanan Pantas', 'All Orders': 'Semua Pesanan', 'Customers': 'Pelanggan',
    'Deadline Calendar': 'Kalendar Tarikh Akhir', 'Production Tracking': 'Penjejakan Pengeluaran',
    'Payments': 'Bayaran', 'Product catalogue': 'Katalog produk', 'Sales Analytics': 'Analitik Jualan',
    'Profitability Analysis': 'Analisis Keuntungan', 'Customer Insights': 'Wawasan Pelanggan',
    'Long-Term Trends': 'Trend Jangka Panjang', 'Reports': 'Laporan', 'Business overview': 'Gambaran perniagaan',
    'Good Morning': 'Selamat Pagi', 'Good Afternoon': 'Selamat Petang', 'Good Evening': 'Selamat Malam',
    'Prepare business export': 'Sediakan eksport perniagaan', 'Download CSV backup (ZIP)': 'Muat turun sandaran CSV (ZIP)',
    'Download Excel': 'Muat turun Excel', 'Existing data import tools': 'Alat import data sedia ada',
    'Display name': 'Nama paparan', 'Phone': 'Telefon', 'Save Profile': 'Simpan Profil',
    'Remove profile photo': 'Buang foto profil', 'Production alert thresholds': 'Ambang amaran pengeluaran',
    'Manage your account, business information, and application preferences.': 'Urus akaun, maklumat perniagaan dan keutamaan aplikasi anda.',
    'Your owner profile and business details.': 'Profil pemilik dan maklumat perniagaan anda.',
    'Total Customers':'Jumlah Pelanggan', 'Search Customer':'Cari Pelanggan',
    'Search by name or phone number':'Cari mengikut nama atau nombor telefon',
    'Add Customer':'Tambah Pelanggan', 'Edit Customer':'Edit Pelanggan',
    'Customer List':'Senarai Pelanggan', 'Customer Name':'Nama Pelanggan',
    'Phone Number':'Nombor Telefon', 'Address':'Alamat', 'State':'Negeri',
    'Actions':'Tindakan', 'Edit':'Edit', 'Page':'Halaman', 'Cancel':'Batal',
    'Save Customer':'Simpan Pelanggan', 'Select a state':'Pilih negeri',
    'Not Specified':'Tidak Dinyatakan',
    'Customer name is required.':'Nama pelanggan diperlukan.',
    'Enter a valid Malaysian phone number.':'Masukkan nombor telefon Malaysia yang sah.',
    'Address is required.':'Alamat diperlukan.',
    'Select a Malaysian state.':'Pilih negeri di Malaysia.',
    'Customer no longer exists. Refresh and try again.':'Pelanggan tidak lagi wujud. Muat semula dan cuba lagi.',
    'This phone number is already registered to another customer.':'Nombor telefon ini sudah didaftarkan kepada pelanggan lain.',
    'Customer saved successfully.':'Pelanggan berjaya disimpan.',
    'Could not save customer. Please try again.':'Tidak dapat menyimpan pelanggan. Sila cuba lagi.',
    'No customers yet. Add your first customer to get started.':'Belum ada pelanggan. Tambah pelanggan pertama anda.',
    'No customers match your search.':'Tiada pelanggan sepadan dengan carian anda.',
}


from localization_ms import MS_MY
MALAY.update(MS_MY)


def _malay_text(text):
    if text in MALAY:return MALAY[text]
    if ' · ' in text:return ' · '.join(_malay_text(part) for part in text.split(' · '))
    heading=re.match(r'^(\s*#{1,6}\s+)(.*)$',text,re.S)
    if heading:return heading[1]+_malay_text(heading[2])
    if text.startswith('**') and text.endswith('**'):return '**'+_malay_text(text[2:-2])+'**'
    if text.startswith('### Grand total: '):return '### Jumlah keseluruhan: '+_malay_text(text[17:])
    if match:=re.fullmatch(r'Import complete: (\d+) new orders saved; (\d+) duplicate responses skipped\.',text):
        return f'Import selesai: {match[1]} pesanan baharu disimpan; {match[2]} respons pendua dilangkau.'
    for english,malay in [('Good Morning','Selamat pagi'),('Good Afternoon','Selamat petang'),('Good Evening','Selamat malam')]:
        if text.startswith(english+','):return malay+text[len(english):]
    prefix,separator,value=text.partition(': ')
    if separator and prefix in MALAY:
        translated_value_prefixes=('Status','Auto Sync','Connection','Payment status','Result',
                                   'Unable to read the response file',
                                   'Unable to load the catalogue or check imported responses',
                                   'Unable to validate the response file',
                                   'Import failed and no partial order records were saved')
        status_value=_malay_text(value) if prefix in translated_value_prefixes else value
        return MALAY[prefix]+separator+status_value
    if match:=re.fullmatch(r'([\d.,]+%) completed',text):return match[1]+' selesai'
    if match:=re.fullmatch(r'([\d.,]+%) collected',text):return match[1]+' diterima'
    if match:=re.fullmatch(r'(.*) sections',text):return 'Bahagian '+MALAY.get(match[1],match[1])
    templates=[
        (r'You have (\d+) notifications today',lambda m:f'Anda mempunyai {m[1]} pemberitahuan hari ini'),
        (r'(\d+) unread',lambda m:f'{m[1]} belum dibaca'),
        (r'Approximately (\d+)s',lambda m:f'Kira-kira {m[1]} saat'),
        (r'Next active-session tick \(up to (\d+)s\)',lambda m:f'Sesi aktif seterusnya (sehingga {m[1]} saat)'),
        (r'(\d+) (min|h|d) ago',lambda m:f'{m[1]} '+{'min':'minit','h':'jam','d':'hari'}[m[2]]+' lalu'),
        (r'(.+): (.+) leads by selling-unit count \(([^)]+)\); packaging sizes differ between products\.',lambda m:f'{m[1]}: {m[2]} mendahului mengikut bilangan unit jualan ({m[3]}); saiz pembungkusan berbeza antara produk.'),
        (r'(.+): (.+) has the highest recognized sales \(RM ([^)]+)\)\.',lambda m:f'{m[1]}: {m[2]} mencatat jualan diiktiraf tertinggi (RM {m[3]}).'),
        (r'Recognized revenue changed (.+)% versus (.+)\.',lambda m:f'Hasil jualan diiktiraf berubah {m[1]}% berbanding {m[2]}.'),
        (r'Returning customers contributed (.+)% of recognized customer spending in this period\.',lambda m:f'Pelanggan berulang menyumbang {m[1]}% daripada belanja pelanggan diiktiraf dalam tempoh ini.'),
        (r'Cancellation rate is (.+)% \((.+)\), above the displayed 20% review threshold\.',lambda m:f'Kadar pembatalan ialah {m[1]}% ({m[2]}), melebihi had semakan 20% yang dinyatakan.'),
        (r'Lower selling-unit counts versus (.+): (.+)\.',lambda m:f'Bilangan unit jualan menurun berbanding {m[1]}: {m[2]}.'),
        (r'(.+) orders have missing/invalid order dates and cannot be assigned to a period\.',lambda m:f'{m[1]} pesanan mempunyai tarikh tiada atau tidak sah dan tidak dapat dikelaskan mengikut tempoh.'),
        (r'Order-date basis (.+)',lambda m:'Asas tarikh pesanan '+_malay_text(m[1])),
        (r'Comparable period: (.+)',lambda m:'Tempoh perbandingan: '+m[1]),
        (r'Maximum ([\d,]+) response rows per import\.',lambda m:f'Maksimum {m[1]} baris respons bagi setiap import.'),
        (r'(.+) is required',lambda m:_malay_text(m[1])+' diperlukan'),
        (r'(.+) must use an unambiguous date such as YYYY-MM-DD',lambda m:_malay_text(m[1])+' mesti menggunakan tarikh yang jelas seperti YYYY-MM-DD'),
        (r'(.+) is ambiguous; use YYYY-MM-DD',lambda m:_malay_text(m[1])+' tidak jelas; gunakan YYYY-MM-DD'),
        (r'Map a spreadsheet column to (.+)\.',lambda m:'Padankan lajur hamparan dengan '+_malay_text(m[1])+'.'),
        (r'Product mapping references missing column "([^"]+)"\.',lambda m:f'Lajur "{m[1]}" yang dirujuk dalam pemadanan produk tiada.'),
        (r'Invalid catalogue product selected for "([^"]+)"\.',lambda m:f'Produk katalog yang dipilih untuk lajur "{m[1]}" tidak sah.'),
        (r'Column "([^"]+)" must map to an active catalogue product\.',lambda m:f'Lajur "{m[1]}" mesti dipadankan dengan produk katalog yang aktif.'),
        (r'Product quantity column "([^"]+)" has no unique active catalogue match\.',lambda m:f'Lajur kuantiti produk "{m[1]}" tiada padanan unik dalam katalog aktif.'),
        (r'Row (\d+): quantity in "([^"]+)" must be a whole number or blank',lambda m:f'Baris {m[1]}: kuantiti dalam "{m[2]}" mestilah nombor bulat atau dibiarkan kosong'),
        (r'Row (\d+): quantity in "([^"]+)" must be a whole number from 0 to 100,000',lambda m:f'Baris {m[1]}: kuantiti dalam "{m[2]}" mestilah nombor bulat antara 0 hingga 100,000'),
        (r'Row (\d+): conflicting values for (.+) in (.+)',lambda m:f'Baris {m[1]}: nilai bagi {_malay_text(m[2])} bercanggah dalam {m[3]}'),
        (r'Row (\d+): conflicting quantity columns for "([^"]+)": (.+)\. Review or unmap the overlapping column\.',lambda m:f'Baris {m[1]}: lajur kuantiti bagi "{m[2]}" bercanggah: {m[3]}. Semak atau nyahpadankan lajur yang bertindih.'),
        (r'Stable response ID duplicates rows (.+)',lambda m:f'ID respons stabil berulang pada baris {m[1]}'),
        (r'Stable response ID duplicates row (.+)',lambda m:f'ID respons stabil berulang pada baris {m[1]}'),
        (r'Rows ([\d, ]+) have identical response content\. Review that they represent distinct submissions before importing\.',lambda m:f'Baris {m[1]} mempunyai kandungan respons yang sama. Pastikan baris ini ialah penghantaran yang berbeza sebelum mengimport.'),
        (r'Row (\d+): already imported; will be skipped',lambda m:f'Baris {m[1]}: telah diimport dan akan dilangkau'),
        (r'Row (\d+): (.+)',lambda m:f'Baris {m[1]}: {_malay_text(m[2])}'),
    ]
    for pattern,translate in templates:
        if match:=re.fullmatch(pattern,text):return translate(match)
    for english,malay in MALAY.items():
        if len(english)>=60 and english in text:
            return _malay_text(text.replace(english,malay))
    return text


def tr(text):
    if runtime().get('language') != 'Bahasa Melayu' or not isinstance(text, str):
        return text
    if '<style' in text or '<script' in text:return text
    if '<' not in text:return _malay_text(text)
    # Only translate exact HTML text nodes, never code, attributes or user data.
    return re.sub(r'>([^<>]+)<', lambda match: '>' + _malay_text(match[1]) + '<', text)


def localized_dialog(title, **options):
    """Resolve dialog titles when opened, so cached modules follow language changes."""
    from functools import wraps
    import streamlit as st
    def decorate(function):
        @wraps(function)
        def opened(*args,**kwargs):
            return st.dialog(tr(title),**options)(function)(*args,**kwargs)
        return opened
    return decorate


def option_labels(options):
    """Freeze display labels for this render, keeping raw option identities stable."""
    labels={option:tr(str(option)) for option in options}
    return lambda option:labels.get(option,str(option))


def date_input_format():
    return runtime().get('date_format', 'DD/MM/YYYY')


def date_pattern():
    return DATE_FORMATS[date_input_format()]


def format_date(value, include_time=False):
    if value is None:
        return ''
    try:
        parsed = value if isinstance(value, (date, datetime)) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.strftime(date_pattern() + (' %H:%M' if include_time else ''))
    except (ValueError, TypeError):
        return str(value)


def style_figure(fig):
    from typography import style_chart_fonts
    style_chart_fonts(fig)
    if runtime().get('theme') == 'Dark':
        from forest_theme import tokens
        colors = tokens()
        fig.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                          font_color=colors['text'], title_font_color=colors['text'],
                          legend=dict(font_color=colors['secondary'], title_font_color=colors['text']),
                          hoverlabel=dict(bgcolor=colors['card'], font_color=colors['text'], bordercolor=colors['control-border']),
                          colorway=[colors['primary'], colors['pink'], colors['confirmed-text'], colors['pending-text']])
        series_colors = [colors['primary'], colors['pink'], colors['confirmed-text'], colors['pending-text']]
        for index, trace in enumerate(fig.data):
            # Presentation only: trace labels, values, ordering and aggregations stay intact.
            if trace.type in ('bar', 'scatter', 'scattergl'):
                color = colors['pink'] if str(trace.name).lower() in ('revenue', 'sales') else series_colors[index % len(series_colors)]
                marker_color = trace.marker.color
                if marker_color is None or isinstance(marker_color, str):
                    trace.update(marker_color=color)
                elif all(isinstance(value, str) for value in marker_color):
                    trace.update(marker_color=[series_colors[item % len(series_colors)] for item in range(len(marker_color))])
                if trace.type != 'bar':
                    trace.update(line_color=color)
            if 'textfont' in trace._valid_props:
                trace.update(textfont_color=colors['text'])
            if 'cliponaxis' in trace._valid_props:
                trace.update(cliponaxis=False)
            if trace.type == 'pie':
                trace.update(marker_colors=series_colors, insidetextfont_color=colors['primary-text'], outsidetextfont_color=colors['text'])
        for annotation in fig.layout.annotations or ():
            annotation.font.color = colors['text']
        fig.update_xaxes(gridcolor=colors['chart-grid'], linecolor=colors['control-border'], zerolinecolor=colors['chart-grid'],
                         tickfont_color=colors['secondary'], title_font_color=colors['text'])
        fig.update_yaxes(gridcolor=colors['chart-grid'], linecolor=colors['control-border'], zerolinecolor=colors['chart-grid'],
                         tickfont_color=colors['secondary'], title_font_color=colors['text'])
    if runtime().get('language')=='Bahasa Melayu':
        for trace in fig.data:
            if trace.name:trace.name=tr(trace.name)
        if fig.layout.title.text:fig.layout.title.text=tr(fig.layout.title.text)
        if fig.layout.legend.title.text:fig.layout.legend.title.text=tr(fig.layout.legend.title.text)
        for axis in ('xaxis','yaxis','xaxis2','yaxis2'):
            if axis not in fig.layout:continue
            obj=fig.layout[axis]
            if obj.title.text:obj.title.text=tr(obj.title.text)
        for annotation in fig.layout.annotations or ():
            if annotation.text:annotation.text=tr(annotation.text)
    return fig


def install_table_localization():
    """Translate read-only grid labels/formatters, keeping source data and keys intact."""
    import streamlit as st
    from functools import wraps
    from streamlit.delta_generator import DeltaGenerator
    if getattr(DeltaGenerator.dataframe,'_bizmar_localized',False):return
    original=DeltaGenerator.dataframe
    @wraps(original)
    def dataframe(self,data=None,*args,**kwargs):
        if runtime().get('language')=='Bahasa Melayu':
            import pandas as pd
            from pandas.io.formats.style import Styler
            frame=data.data if isinstance(data,Styler) else data
            if isinstance(frame,pd.DataFrame):
                configs=dict(kwargs.get('column_config') or {})
                enum_columns=[]
                for column in frame.columns:
                    config=configs.get(column)
                    if config is None:config={}
                    elif isinstance(config,str):config={'label':config}
                    elif not isinstance(config,dict):continue
                    label=config.get('label') or str(column)
                    configs[column]={**config,'label':tr(label)}
                    if any(term in str(column).lower() for term in ('status','payment_group','deadline_state')) or str(column) in ('Type','Result','Trigger','Payment','Fulfilment','Method'):
                        enum_columns.append(column)
                kwargs['column_config']=configs
                if enum_columns:
                    data=(data if isinstance(data,Styler) else frame.style).format({column:lambda value:tr(value) for column in enum_columns})
        return original(self,data,*args,**kwargs)
    dataframe._bizmar_localized=True
    DeltaGenerator.dataframe=dataframe
    st.dataframe=st._main.dataframe


def style_table(data):
    """Style display cells only; preserve source values and existing status styling."""
    if runtime().get('theme') != 'Dark':
        return data
    import pandas as pd
    from pandas.io.formats.style import Styler
    from forest_theme import tokens, status_colors
    if not isinstance(data, (pd.DataFrame, Styler)):
        return data
    colors = tokens()
    styled = data.style if isinstance(data, pd.DataFrame) else data
    statuses = [column for column in styled.data.columns if 'status' in str(column).lower() or str(column).lower() == 'deadline state']
    normal = [column for column in styled.data.columns if column not in statuses]
    if normal:
        styled = styled.set_properties(subset=normal, **{'background-color': colors['card'], 'color': colors['text']})
    if statuses:
        def badge(value):
            background, foreground = status_colors(value)
            return f'background-color: {background}; color: {foreground}; font-weight: 500'
        styled = styled.map(badge, subset=statuses)
    return styled
