"""Browser regression checks against the isolated Streamlit dashboard preview."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'uat/soft-forest'
OUTPUT.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
    for theme in ['Dark','Light']:
        for label,width in [('desktop',1440),('tablet',900),('mobile',390)]:
            page=browser.new_page(viewport={'width':width,'height':1000})
            page.goto('http://127.0.0.1:8769/?theme='+theme)
            page.wait_for_selector('.nour-stat')
            assert not page.locator('[data-testid=stException]').count()
            cards=[e.bounding_box() for e in page.locator('.nour-stat').all()]
            charts=page.locator('.st-key-nour_overview_activity').bounding_box()
            assert charts['y']-max(c['y']+c['height'] for c in cards)>=23, (theme,width,cards,charts)
            assert max(c['height'] for c in cards)-min(c['height'] for c in cards)<1
            group=page.locator('.st-key-nour_shell_actions')
            buttons=group.locator('button:visible')
            boxes=[b.bounding_box() for b in buttons.all()]
            assert len(boxes)==3, boxes
            assert group.bounding_box()['width']<=184
            for index,box in enumerate(boxes):
                assert abs(box['width']-52)<1 and abs(box['height']-52)<1, box
                if index: assert 10<=box['x']-boxes[index-1]['x']-boxes[index-1]['width']<=14
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (theme,width,'overflow')
            if theme=='Dark':
                assert page.get_by_role('button',name='Today',exact=True).is_visible()
                assert page.get_by_role('button',name='Yesterday',exact=True).is_visible()
                assert page.get_by_role('button',name='7D',exact=True).is_visible()
                buttons.nth(1).click()
                page.get_by_text('Messaging is not connected yet.',exact=True).wait_for(state='visible')
                page.keyboard.press('Escape')
            if width==1440:
                page.locator('.nour-stat-label').nth(1).evaluate("e=>e.textContent='Booked Order Value with a much longer translated label that wraps over multiple lines'")
                heights=[e.bounding_box()['height'] for e in page.locator('.nour-stat').all()]
                assert max(heights)-min(heights)<1, heights
                assert page.locator('.st-key-nour_overview_activity').bounding_box()['y']-max(e.bounding_box()['y']+e.bounding_box()['height'] for e in page.locator('.nour-stat').all())>=23
            page.screenshot(path=str(OUTPUT/f'dashboard-{theme.lower()}-{label}.png'),full_page=True)
            print(theme,label,': no overlap; equal cards; compact actions; interactions passed')
            page.close()
    browser.close()
