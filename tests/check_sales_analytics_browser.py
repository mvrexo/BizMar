from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
output=ROOT/'uat/sales-analytics-screenshots';output.mkdir(exist_ok=True)

def assets(route):
    suffix=urlparse(route.request.url).path.split('/app/static/',1)[-1]
    target=(ROOT/'static'/suffix).resolve()
    if not target.is_relative_to((ROOT/'static').resolve()) or not target.is_file():route.abort();return
    mime='application/json' if target.suffix=='.json' else 'text/css' if target.suffix=='.css' else 'font/ttf'
    route.fulfill(body=target.read_bytes(),content_type=mime)

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
    for theme in ('Light','Dark'):
        for width in (1440,390):
            for empty in (False,True):
                page=browser.new_page(viewport={'width':width,'height':950})
                page.route('**/app/static/**',assets)
                page.goto(f'http://127.0.0.1:8796/?theme={theme}&empty={int(empty)}')
                expect(page.locator('[data-testid=stMetric]')).to_have_count(13,timeout=45000)
                expect(page.locator('[data-testid=stApp]')).to_have_attribute('data-test-script-state','notRunning',timeout=45000)
                assert page.locator('[data-testid=stException]').count()==0
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(theme,width,empty)
                expect(page.get_by_role('button',name='Monthly Excel',exact=True)).to_be_visible(timeout=30000)
                if not empty:
                    values=page.locator('[data-testid=stMetricValue]').all_text_contents()
                    assert values[0]=='RM 145.00',values
                    assert values[3]=='RM 85.00',values
                    expect(page.locator('[data-testid=stPlotlyChart]')).to_have_count(16)
                    for plot in page.locator('[data-testid=stPlotlyChart]').all():
                        plot.scroll_into_view_if_needed()
                        expect(plot.locator('.js-plotly-plot')).to_be_visible(timeout=20000)
                    page.screenshot(path=str(output/f'{theme}-{width}-historical.png'),full_page=True)
                    field=page.get_by_role('combobox',name='Order status',exact=True)
                    field.scroll_into_view_if_needed()
                    field.click()
                    field.fill('Pending')
                    page.get_by_role('option',name='Pending',exact=True).click()
                    expect(page.locator('[data-testid=stMetricValue]').first).to_have_text('RM 0.00')
                page.screenshot(path=str(output/f'{theme}-{width}-empty-{empty}.png'),full_page=True)
                print('PASS',theme,width,'empty' if empty else 'historical/filter change',flush=True)
                page.close()
    browser.close()
