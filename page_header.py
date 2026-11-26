"""One shared, theme-aware page header for every authenticated dashboard route."""
from contextlib import contextmanager
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo
import streamlit as st

MYT=ZoneInfo('Asia/Kuala_Lumpur')


def header_title(page,labels):
    return 'Order List' if page=='Order Management' else labels.get(page,page)


@contextmanager
def page_header(title,*,when=None,date_text=None,greeting=None,with_actions=False):
    current=when or datetime.now(MYT)
    current=current.replace(tzinfo=MYT) if current.tzinfo is None else current.astimezone(MYT)
    if greeting:
        st.markdown(f'<div class="bizmar-page-greeting">{escape(greeting)}</div>',unsafe_allow_html=True)
    with st.container(key='nour_shell_header'):
        columns=st.columns([3,2,1] if with_actions else [3,2],gap='medium',vertical_alignment='center')
        with columns[0]:
            st.markdown(f'<h1 class="nour-header-title">{escape(str(title))}</h1>',unsafe_allow_html=True)
        with columns[1]:
            label=(date_text if date_text is not None else current.strftime('%d/%m/%Y'))+' | Malaysia (MYT)'
            st.markdown(f'<time class="bizmar-page-date" datetime="{current.isoformat()}">{escape(label)}</time>',unsafe_allow_html=True)
        yield columns[2] if with_actions else None
