"""Offline desktop/mobile CSS preview; no app server, secrets or business records."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
import plotly.graph_objects as go
from ui_theme import STYLE
from settings_store import DEFAULTS
from unittest.mock import patch
from display_preferences import style_figure

ROOT = Path(__file__).resolve().parents[1]
DARK = (ROOT / 'styles/dark.css').read_text(encoding='utf-8')
OUTPUT = ROOT / 'uat' / 'soft-forest'
OUTPUT.mkdir(parents=True, exist_ok=True)
with patch('display_preferences.runtime', return_value={**DEFAULTS, 'theme': 'Dark'}):
    figure = style_figure(go.Figure(go.Scatter(x=['Mon','Tue','Wed'], y=[30,65,48], name='Revenue', mode='lines+markers+text', text=[30,65,48], textposition='top center')))
figure.update_layout(height=250, margin=dict(l=35,r=20,t=25,b=35))
chart = figure.to_html(full_html=False, include_plotlyjs=True, div_id='forest-chart', config={'displayModeBar':False,'responsive':True})
fixture = '''
<div data-testid="stAppViewContainer"><div class="preview-shell">
<section data-testid="stSidebar"><h2>BizMar</h2><button kind="primary"><p>Dashboard</p></button><button><p>Orders</p></button><button><p>Settings</p></button></section>
<main data-testid="stMain"><header class="st-key-nour_shell_header"><h1>Soft Forest dashboard</h1><div data-testid="stCaptionContainer">Readable across desktop and mobile</div></header>
<div class="preview-grid">
<div data-testid="stForm"><h3>Order preferences</h3><label data-testid="stWidgetLabel"><p>Email address</p></label><div data-baseweb="input"><input placeholder="you@example.com"></div>
<label data-testid="stWidgetLabel"><p>Business description</p></label><textarea placeholder="Your business details"></textarea>
<div data-baseweb="select"><div role="combobox" tabindex="0">Pending ?</div></div>
<div class="preview-buttons"><button id="primary" kind="primaryFormSubmit"><p>Save changes</p></button><button id="secondary"><p>Cancel</p></button><button id="disabled" disabled><p>Unavailable</p></button></div>
<div data-testid="stTabs"><div data-baseweb="tab-list" role="tablist"><button role="tab" aria-selected="true">Account</button><button role="tab" aria-selected="false">Business</button></div></div>
</div>
<div data-testid="stForm"><h3>Sales overview</h3><div data-testid="stPlotlyChart">CHART</div><div class="st-key-nour_payment_kpis"><div data-testid="stColumn"><div data-testid="stMetric"><span data-testid="stMetricValue">RM 65.00</span></div></div></div></div>
</div>
<div data-testid="stForm"><h3>Order status</h3><div class="badges">BADGES</div>
<table><thead><tr><th>Order</th><th>Customer</th><th>Balance</th></tr></thead><tbody><tr><td>DEMO001</td><td>Example customer</td><td>RM 25.00</td></tr></tbody></table>
<div data-testid="stAlert"><div role="alert"><span>?</span><div data-testid="stMarkdownContainer"><p>Upcoming deadline: check your order schedule.</p></div></div></div></div>
<div role="listbox"><div role="option">Pending</div><div role="option" aria-selected="true">Confirmed</div></div>
</main></div></div>'''.replace('CHART', chart).replace('BADGES', ''.join(f'<span class="nour-status-{name.lower()}">{name}</span>' for name in ['Pending','Confirmed','Preparing','Ready','Completed','Cancelled']))
preview_css = '''body{margin:0;font:16px Arial,sans-serif}.preview-shell{display:grid;grid-template-columns:240px minmax(0,1fr);min-height:100vh}main{padding:24px;min-width:0}section{padding:20px;box-sizing:border-box}section button{display:block;margin:12px 0;width:100%}.preview-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}[data-testid=stForm]{margin-bottom:20px;padding:20px;min-width:0}button{padding:10px 16px;border:1px solid;border-radius:10px;font:inherit}button p{margin:0}input,textarea,[role=combobox]{width:100%;box-sizing:border-box;padding:12px;border:1px solid;border-radius:8px;font:inherit}textarea{min-height:70px}label p{margin-bottom:6px}.preview-buttons{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.badges{display:flex;gap:8px;flex-wrap:wrap}.badges span{padding:6px 10px;border-radius:8px}table{width:100%;text-align:left;margin:18px 0}td,th{padding:10px}h1{font-size:28px}[role=option]{padding:8px}a{color:inherit}@media(max-width:600px){.preview-shell{display:block}section[data-testid=stSidebar]{display:none}main{padding:12px}.preview-grid{grid-template-columns:1fr}h1{font-size:24px}}'''
html = '<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+STYLE+preview_css+DARK+'</style></head><body>'+fixture+'</body></html>'
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', headless=True)
    for name,width,height in [('desktop',1440,1000),('mobile',390,844)]:
        page = browser.new_page(viewport={'width':width,'height':height}, device_scale_factor=1)
        page.route('http**/*', lambda route: route.abort())
        page.set_content(html, wait_until='load')
        page.wait_for_selector('#forest-chart .main-svg')
        assert page.locator('[data-testid=stMetric]').evaluate('(e)=>getComputedStyle(e).backgroundColor') == 'rgb(48, 66, 59)'
        assert page.locator('[data-testid=stPlotlyChart]').evaluate('(e)=>getComputedStyle(e).backgroundColor') == 'rgb(48, 66, 59)'
        assert page.locator('[role=tablist]').evaluate('(e)=>getComputedStyle(e).backgroundColor') == 'rgb(48, 66, 59)'
        assert page.locator('#primary').evaluate('(e)=>getComputedStyle(e).backgroundColor') == 'rgb(168, 213, 181)'
        assert page.locator('#primary').evaluate('(e)=>getComputedStyle(e).color') == 'rgb(23, 59, 43)'
        page.locator('#primary').hover()
        page.wait_for_timeout(240)
        assert page.locator('#primary').evaluate('(e)=>getComputedStyle(e).color') == 'rgb(255, 255, 255)'
        page.locator('#secondary').focus()
        assert page.locator('#secondary').evaluate('(e)=>getComputedStyle(e).outlineStyle') == 'solid'
        assert page.locator('#disabled').evaluate('(e)=>getComputedStyle(e).color') == 'rgb(174, 191, 179)'
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), name+' horizontal overflow'
        page.screenshot(path=str(OUTPUT / (name+'.png')), full_page=True)
        page.close()
        print(name+': primary/hover/focus/disabled states, chart render and no horizontal overflow passed')
    browser.close()
