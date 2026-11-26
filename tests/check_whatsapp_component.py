"""Browser checks with a synthetic number; external WhatsApp requests are intercepted."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from customer_message_templates import whatsapp_url
from playwright.sync_api import sync_playwright,expect

url=whatsapp_url('0123456789','Synthetic review only & <script>not HTML</script>')
args=json.dumps(dict(url=url,message_id=123,version=0,disabled=False))
html='''<html><script>window.events=[];window.addEventListener('message',event=>{
 if(event.data.type==='streamlit:componentReady')event.source.postMessage({type:'streamlit:render',args:ARGS},'*');
 if(event.data.type==='streamlit:setComponentValue')window.events.push(event.data.value);
});</script><iframe title="WhatsApp launch" src="/message-component" style="width:100%;height:80px"></iframe></html>'''.replace('ARGS',args)
component=(ROOT/'components/whatsapp_launch/index.html').read_text(encoding='utf-8')
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
    for width in (1440,390):
        page=browser.new_page(viewport={'width':width,'height':700})
        page.route('http://127.0.0.1:8501/__message_component_test__',lambda route:route.fulfill(content_type='text/html',body=html))
        page.route('http://127.0.0.1:8501/message-component',lambda route:route.fulfill(content_type='text/html',body=component))
        browser.contexts[-1].route('https://wa.me/**',lambda route:route.fulfill(content_type='text/html',body='Synthetic intercepted destination; no message sent.'))
        page.goto('http://127.0.0.1:8501/__message_component_test__')
        button=page.frame_locator('iframe').get_by_role('link',name='Send via WhatsApp')
        expect(button).to_have_attribute('aria-disabled','false')
        fonts=button.evaluate('async e=>{const fonts=await document.fonts.load(\'600 14px "Plus Jakarta Sans"\');return fonts.map(f=>[f.family,f.status]);}')
        assert fonts and all(f[1]=='loaded' for f in fonts)
        assert 'Plus Jakarta Sans' in button.evaluate('e=>getComputedStyle(e).fontFamily')
        with page.expect_popup() as popup:button.click()
        opened=popup.value;opened.wait_for_load_state('domcontentloaded')
        event=page.evaluate('window.events[0]')
        assert event['action']=='opened' and event['message_id']==123 and event['version']==0
        assert not page.locator('script').count()>1
        opened.close();page.close()
        print(f'PASS: {width}px; user click opens review link and emits Opened only; external request intercepted.')
    browser.close()
