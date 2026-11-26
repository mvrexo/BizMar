"""All-route native Streamlit header QA on isolated data, in both themes."""
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def font_asset(route):
    name=Path(urlparse(route.request.url).path).name
    path=ROOT/'static/fonts'/name
    if not path.is_file():route.abort();return
    route.fulfill(body=path.read_bytes(),content_type='text/css' if name.endswith('.css') else 'font/ttf')


def contrast(a,b):
    def lum(rgb):
        values=[v/255 for v in rgb];values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
        return sum(v*w for v,w in zip(values,[.2126,.7152,.0722]))
    high,low=sorted([lum(a),lum(b)],reverse=True)
    return (high+.05)/(low+.05)


out=ROOT/'uat/page-header-screenshots';out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
    checks=0
    for theme in ('Light','Dark'):
        for width in (1440,390):
            page=browser.new_page(viewport={'width':width,'height':900})
            page.route('**/app/static/fonts/**',font_asset)
            page.goto('http://127.0.0.1:8794/?theme='+theme)
            expect(page.locator('.nour-header-title')).to_be_visible(timeout=30000)
            page.evaluate('async()=>{await document.fonts.load(\'600 28px Poppins\');await document.fonts.load(\'400 13px Poppins\');}')
            field=page.locator('.st-key-header_test_route input')
            field.click();routes=page.get_by_role('option').all_text_contents();page.keyboard.press('Escape')
            for route in routes:
                field.click();field.fill(route);page.get_by_role('option',name=route,exact=True).click()
                page.wait_for_timeout(100)
                expect(page.locator('[data-testid=stApp]')).to_have_attribute('data-test-script-state','notRunning',timeout=30000)
                title=page.locator('.nour-header-title');date=page.locator('.bizmar-page-date');header=page.locator('.st-key-nour_shell_header')
                expect(title).to_be_visible()
                assert page.get_by_role('heading',level=1).count()==1
                assert page.locator('[data-testid=stException]').count()==0
                h,t,d=header.bounding_box(),title.bounding_box(),date.bounding_box()
                assert h['height']>=79,(theme,width,route,h)
                for rect in (t,d):
                    assert rect['y']>=h['y']+14 and rect['y']+rect['height']<=h['y']+h['height']-14,(theme,width,route,h,rect)
                    assert rect['x']>=h['x']+14 and rect['x']+rect['width']<=h['x']+h['width']-14,(theme,width,route,h,rect)
                if width>700:assert abs(t['y']+t['height']/2-d['y']-d['height']/2)<2,(route,t,d)
                else:assert d['y']>=t['y']+t['height']+8,(route,t,d)
                fonts=title.evaluate('e=>{const s=getComputedStyle(e);return [s.fontFamily,s.fontSize,s.fontWeight,s.marginTop,s.marginBottom]}')
                assert 'Poppins' in fonts[0] and fonts[1:]==['26px' if width<700 else '28px','600','0px','0px'],fonts
                date_style=date.evaluate('e=>{const s=getComputedStyle(e);return [s.fontFamily,s.fontSize,s.fontWeight,s.color]}')
                assert 'Poppins' in date_style[0] and date_style[1:3]==['13px','400'],date_style
                rgb=tuple(map(int,re.findall(r'\d+',date_style[3])[:3]));background=(59,81,71) if theme=='Dark' else (255,240,241)
                assert contrast(rgb,background)>=4.5,(theme,date_style,contrast(rgb,background))
                assert 'Malaysia (MYT)' in date.inner_text() and '+08:00' in date.get_attribute('datetime')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(theme,width,route)
                if route=='Overview':
                    for button in page.locator('.st-key-nour_shell_actions button').all():
                        box=button.bounding_box();assert abs(box['width']-52)<1 and abs(box['height']-52)<1
                header.screenshot(path=str(out/f'{theme}-{width}-{re.sub(r"[^a-zA-Z0-9]+","-",route)}.png'))
                checks+=1
            print(f'PASS: {theme}, {width}px — {len(routes)} page/long-title headers centered, unclipped and readable.',flush=True)
            page.close()
    browser.close()
print('Total header checks:',checks)
