"""Check shared CSS cascade and actual local font loading with Google Fonts blocked."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ui_theme import STYLE
from playwright.sync_api import sync_playwright

markup='''<div data-testid="stApp"><div data-testid="stAppViewContainer"><div data-testid="stMainBlockContainer">
<div data-testid="stMarkdownContainer"><h1 id="title">Dashboard</h1><h3 id="section">Revenue over time</h3><p id="body">Business performance</p></div>
<button><div data-testid="stMarkdownContainer"><p id="button">Save changes</p></div></button>
<div data-testid="stLinkButton"><a href="#"><p id="link-button">Open WhatsApp</p></a></div>
<div class="nour-stat-value" id="kpi">12,345.00</div><div data-testid="stText"><pre id="plain">Customer details</pre></div>
<section data-testid="stSidebar"><div class="st-key-nour_nav_PRIMARY_0"><button><p id="navigation">Dashboard</p></button></div></section>
<span data-testid="stIconMaterial" id="icon">notifications</span>
<div class="st-key-nour_orders_kpis"><div data-testid="stColumn"><div data-testid="stMetricValue"><p id="orders-kpi">123</p></div></div></div>
</div></div></div><div data-testid="stPopoverBody"><button><p id="portal-button">Mark as read</p></button></div>
<div role="tooltip"><div data-testid="stTooltipContent"><div data-testid="stMarkdownContainer"><p id="tooltip">Notifications</p></div></div></div>'''
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
    for theme in ('Light','Dark'):
        css=STYLE+(ROOT/'styles/orders.css').read_text()+(ROOT/'styles/products.css').read_text()
        if theme=='Dark':css+=(ROOT/'styles/dark.css').read_text()
        for width in (1440,390):
            page=browser.new_page(viewport={'width':width,'height':1000})
            page.route('https://fonts.googleapis.com/**',lambda route:route.abort())
            page.route('https://fonts.gstatic.com/**',lambda route:route.abort())
            page.route('http://127.0.0.1:8501/__typography_check__',lambda route:route.fulfill(content_type='text/html',body='<html><style>'+css+'</style><body>'+markup+'</body></html>'))
            page.goto('http://127.0.0.1:8501/__typography_check__')
            for family,weights in [('Inter',[400,500,600,700]),('Plus Jakarta Sans',[500,600,700])]:
                for weight in weights:
                    loaded=page.evaluate('async ([family,weight])=>{let faces=await document.fonts.load(`${weight} 15px "${family}"`);return faces.map(f=>[f.family,f.status]);}',[family,weight])
                    assert loaded and all(face[1]=='loaded' for face in loaded),(family,weight,loaded)
            expected={'title':('Plus Jakarta Sans','26px' if width<600 else '28px','700'),'section':('Plus Jakarta Sans','19px','600'),
                      'body':('Inter','15px','400'),'button':('Plus Jakarta Sans','14px','600'),'portal-button':('Plus Jakarta Sans','14px','600'),
                      'plain':('Inter','15px','400'),'link-button':('Plus Jakarta Sans','14px','600'),'kpi':('Inter','28px' if width<600 else '32px','700'),
                      'orders-kpi':('Inter','28px' if width<600 else '32px','700'),'navigation':('Plus Jakarta Sans','15px','500'),'tooltip':('Inter','13px','500')}
            for identity,(family,size,weight) in expected.items():
                actual=page.locator('#'+identity).evaluate('e=>{let s=getComputedStyle(e);return [s.fontFamily,s.fontSize,s.fontWeight]}')
                assert family in actual[0] and actual[1:]==[size,weight],(theme,width,identity,actual)
            assert 'Material Symbols' in page.locator('#icon').evaluate('e=>getComputedStyle(e).fontFamily')
            page.screenshot(path=str(ROOT/f'uat/typography-local-{theme}-{width}.png'),full_page=True)
            print(f'PASS: {theme}, {width}px — all seven local font faces loaded; role fonts/sizes/weights and icon font correct.')
            page.close()
    page=browser.new_page()
    page.route('https://fonts.googleapis.com/**',lambda route:route.abort())
    page.route('https://fonts.gstatic.com/**',lambda route:route.abort())
    page.goto('http://127.0.0.1:8501')
    page.get_by_role('button',name='Log In',exact=False).wait_for(timeout=30000)
    for family in ('Inter','Plus Jakarta Sans'):
        loaded=page.evaluate('async family=>(await document.fonts.load(`600 15px "${family}"`)).map(f=>f.status)',family)
        assert loaded and all(status=='loaded' for status in loaded)
    print('PASS: actual Streamlit document loads both local families with Google Fonts blocked; owner login remains required.')
    page.close();browser.close()
