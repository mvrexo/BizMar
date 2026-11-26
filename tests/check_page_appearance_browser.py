from pathlib import Path
from urllib.parse import quote,urlparse
from io import BytesIO
import json
from PIL import Image,ImageChops,ImageDraw,ImageStat
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
output=ROOT/'uat/page-appearance-screenshots';output.mkdir(exist_ok=True)
def assets(route):
    suffix=urlparse(route.request.url).path.split('/app/static/',1)[-1]
    path=(ROOT/'static'/suffix).resolve()
    if not path.is_relative_to((ROOT/'static').resolve()) or not path.is_file():route.abort();return
    mime='text/css' if path.suffix=='.css' else 'application/json' if path.suffix=='.json' else 'font/ttf'
    route.fulfill(body=path.read_bytes(),content_type=mime)

def sidebar_style(page):
    return page.locator('[data-testid=stSidebar]').evaluate('''e=>[e,...e.querySelectorAll('button,p,img')].map(n=>{let s=getComputedStyle(n);return [s.backgroundColor,s.backgroundImage,s.color,s.borderColor,s.borderRadius,s.padding,s.fontFamily,s.boxShadow]})''')

def set_mobile_sidebar(page,width,expanded):
    if width==390:
        name='Expand sidebar' if expanded else 'Collapse sidebar'
        button=page.get_by_role('button',name=name)
        if button.is_visible():button.click()

def settle_sidebar_capture(page,width):
    sidebar=page.locator('[data-testid=stSidebar]')
    expect(sidebar.locator('img')).to_have_count(1)
    page.wait_for_function("() => Array.from(document.querySelectorAll('[data-testid=stSidebar] img')).every(img => img.complete && img.naturalWidth > 0)")
    page.evaluate('async() => { await document.fonts.ready; if (document.activeElement instanceof HTMLElement) document.activeElement.blur() }')
    page.mouse.move(width-1,1099)
    page.wait_for_timeout(200)

def sidebar_pixels_equal(light,dark,width):
    if light==dark:return True
    before=Image.open(BytesIO(light)).convert('RGB')
    after=Image.open(BytesIO(dark)).convert('RGB')
    if before.size!=after.size:return False
    difference=ImageChops.difference(before,after)
    if width==390:
        mask=Image.new('L',before.size,255)
        draw=ImageDraw.Draw(mask)
        # Ignore transparent rounded corners and their antialiased edge.
        radius=30
        for x in range(radius+1):
            for y in range(radius+1):
                if (x-radius)**2+(y-radius)**2>(radius-1)**2:
                    for point in ((x,y),(before.width-1-x,y),(x,before.height-1-y),
                                  (before.width-1-x,before.height-1-y)):
                        draw.point(point,fill=0)
        difference=Image.composite(difference,Image.new('RGB',before.size),mask)
        # Mobile screenshot rasterization may vary by one RGB level.
        return max(channel[1] for channel in ImageStat.Stat(difference).extrema)<=1
    return not any(difference.tobytes())

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
    for language in ('English','Bahasa Melayu'):
        for width in (1440,390):
            page=browser.new_page(viewport={'width':width,'height':1100})
            page.route('**/app/static/**',assets)
            page.goto(f'http://127.0.0.1:8798/?theme=Light&language={quote(language)}')
            expect(page.get_by_role('tab')).to_have_count(6,timeout=30000)
            page.evaluate("() => history.replaceState({}, '', location.pathname)")
            set_mobile_sidebar(page,width,True)
            sidebar=page.locator('[data-testid=stSidebar]');expect(sidebar).to_be_visible()
            expect(sidebar.locator('button')).to_have_count(8,timeout=30000)
            page.evaluate('async()=>{await document.fonts.ready}')
            settle_sidebar_capture(page,width)
            original=sidebar_style(page)
            light=sidebar.screenshot()
            set_mobile_sidebar(page,width,False)
            page.get_by_role('tab',name='Appearance & Preferences' if language=='English' else 'Penampilan & Keutamaan',exact=True).click()
            toggle_label='Dark Mode' if language=='English' else 'Mod Gelap'
            switch=page.get_by_role('switch',name=toggle_label,exact=True)
            page.get_by_text('Dark Mode' if language=='English' else 'Mod Gelap',exact=True).click()
            expect(page.locator('[data-testid=stMain]')).to_have_css('background-color','rgb(20, 25, 26)',timeout=20000)
            page.reload()
            expect(page.get_by_role('tab')).to_have_count(6,timeout=30000)
            page.get_by_role('tab',name='Appearance & Preferences' if language=='English' else 'Penampilan & Keutamaan',exact=True).click()
            switch=page.get_by_role('switch',name=toggle_label,exact=True)
            expect(switch).to_be_checked()
            set_mobile_sidebar(page,width,True)
            expect(sidebar.locator('button')).to_have_count(8,timeout=30000)
            settle_sidebar_capture(page,width)
            after=sidebar_style(page)
            if after!=original:
                (output/'sidebar-style-difference.json').write_text(json.dumps({'before':original,'after':after},indent=2),encoding='utf-8')
            assert after==original,'Sidebar computed styles changed with dark mode'
            dark=sidebar.screenshot()
            if not sidebar_pixels_equal(light,dark,width):
                (output/'sidebar-light.png').write_bytes(light)
                (output/'sidebar-dark.png').write_bytes(dark)
                raise AssertionError('Sidebar pixels changed with dark mode')
            set_mobile_sidebar(page,width,False)
            page.screenshot(path=str(output/f'Settings-{language}-{width}-dark.png'),full_page=True)
            page.get_by_text(toggle_label,exact=True).click()
            expect(page.locator('[data-testid=stMain]')).not_to_have_css('background-color','rgb(20, 25, 26)')
            page.reload()
            expect(page.get_by_role('tab')).to_have_count(6,timeout=30000)
            page.get_by_role('tab',name='Appearance & Preferences' if language=='English' else 'Penampilan & Keutamaan',exact=True).click()
            expect(page.get_by_role('switch',name=toggle_label,exact=True)).not_to_be_checked()
            assert page.locator('[data-testid=stException]').count()==0
            print('PASS sidebar invariance, immediate toggle',language,width,flush=True)
            page.close()
    for theme in ('Light','Dark'):
        for route in ('Customers','Order Management','Products','Payments','Deadline Calendar','Sales Analytics'):
            page=browser.new_page(viewport={'width':1440,'height':1000});page.route('**/app/static/**',assets)
            page.goto(f'http://127.0.0.1:8798/?theme={theme}&language=Bahasa%20Melayu&route={quote(route)}')
            expect(page.get_by_text('QA shared controls',exact=True)).to_be_visible(timeout=45000)
            assert page.locator('[data-testid=stException]').count()==0,(theme,route,page.locator('[data-testid=stException]').all_text_contents())
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(theme,route)
            page.locator('.nour-header-title').scroll_into_view_if_needed()
            page.screenshot(path=str(output/f'{route}-{theme}.png'))
            print('PASS actual page',theme,route,flush=True);page.close()
    browser.close()
