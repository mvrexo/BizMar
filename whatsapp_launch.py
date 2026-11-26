"""Native user-initiated external link with a recorded launch-intent callback."""
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

_launch=components.declare_component('bizmar_whatsapp_launch',path=str(Path(__file__).resolve().parent/'components/whatsapp_launch'))


def launch_button(url,message,disabled=False):
    base=str(st.get_option('server.baseUrlPath') or '').strip('/')
    font_css_url=('/'+base if base else '')+'/app/static/fonts/bizmar-fonts.css'
    return _launch(url=url,message_id=message['id'],version=message['version'],disabled=disabled,
                   font_css_url=font_css_url,
                   key=f'whatsapp_message_{message["id"]}',default=None)
