from pathlib import Path
from urllib.parse import urlparse,quote
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
output=ROOT/'uat/customer-directory-screenshots';output.mkdir(exist_ok=True)
def assets(route):
    target=ROOT/'static/fonts'/Path(urlparse(route.request.url).path).name
    if target.is_file():route.fulfill(body=target.read_bytes(),content_type='text/css' if target.suffix=='.css' else 'font/ttf')
    else:route.abort()

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
    for language in ('English','Bahasa Melayu'):
        for theme in ('Light','Dark'):
            for width in (1440,390):
                page=browser.new_page(viewport={'width':width,'height':1000})
                page.route('**/app/static/fonts/**',assets)
                base=f'http://127.0.0.1:8797/?theme={theme}&language={quote(language)}'
                page.goto(base)
                expect(page.locator('[data-testid=stMetricValue]')).to_have_text('17',timeout=30000)
                expect(page.get_by_role('button',name='Edit',exact=True)).to_have_count(15)
                assert page.locator('[data-testid=stException]').count()==0
                assert page.locator('[data-testid=stMetric]').count()==1
                assert page.locator('[data-testid=stPlotlyChart]').count()==0
                search=page.get_by_role('textbox',name='Search Customer' if language=='English' else 'Cari Pelanggan',exact=True)
                search.fill('Customer 00');search.press('Enter')
                expect(page.get_by_role('button',name='Edit',exact=True)).to_have_count(1)
                page.get_by_role('button',name='Edit',exact=True).click()
                form=page.locator('.st-key-bizmar_customer_editor')
                expect(form).to_be_visible()
                expect(form.get_by_role('textbox',name='Customer Name' if language=='English' else 'Nama Pelanggan',exact=True)).to_have_value('Example Customer 00')
                form.get_by_role('button',name='Cancel' if language=='English' else 'Batal',exact=True).click()
                expect(form).to_have_count(0)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(output/f'{language}-{theme}-{width}.png'),full_page=True)
                page.goto(base+'&empty=1')
                expect(page.locator('[data-testid=stMetricValue]')).to_have_text('0')
                assert page.locator('[data-testid=stException]').count()==0
                print('PASS',language,theme,width,'list/search/edit/cancel/empty',flush=True)
                page.close()
    browser.close()
