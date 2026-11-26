from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'uat/kpi-sparklines';out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
    for theme in ('Light','Dark'):
        for width in (1440,390):
            page=browser.new_page(viewport={'width':width,'height':1100})
            def font_asset(route):
                path=ROOT/'static/fonts'/Path(route.request.url).name
                if path.is_file():route.fulfill(body=path.read_bytes(),content_type='text/css' if path.suffix=='.css' else 'font/ttf')
                else:route.abort()
            page.route('**/app/static/fonts/**',font_asset)
            for scenario in ('history','empty','single','short'):
                page.goto(f'http://127.0.0.1:8795/?theme={theme}&scenario={scenario}')
                expect(page.locator('.nour-stat')).to_have_count(4,timeout=30000)
                assert page.locator('[data-testid=stException]').count()==0
                assert page.locator('.bizmar-spark').count()==(3 if scenario in ('history','short') else 0)
                boxes=page.locator('.nour-stat').evaluate_all('(cards)=>cards.map(c=>({h:c.getBoundingClientRect().height,w:c.getBoundingClientRect().width,scroll:c.scrollWidth,client:c.clientWidth}))')
                assert max(b['h'] for b in boxes)-min(b['h'] for b in boxes)<2,boxes
                assert all(b['scroll']<=b['client']+1 for b in boxes)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),(theme,width,scenario)
                expected=['2','RM 150.00','RM 50.00','RM 100.00'] if scenario=='history' else (['0','RM 0.00','RM 0.00','RM 0.00'] if scenario=='empty' else ['1','RM 100.00','RM 60.00','RM 100.00'] if scenario=='single' else ['1','RM 50.00','RM -10.00','RM 0.00'])
                assert page.locator('.nour-stat-value').all_text_contents()==expected
                for spark in page.locator('.bizmar-spark,.bizmar-spark-empty').all():
                    assert abs(spark.bounding_box()['height']-48)<1
                page.screenshot(path=str(out/f'{theme}-{width}-{scenario}.png'),full_page=True)
                print('PASS',theme,width,scenario)
            page.close()
    browser.close()
