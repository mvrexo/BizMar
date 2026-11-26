"""Check the real header in the isolated synthetic dashboard preview."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', headless=True)
    for theme in ('Light', 'Dark'):
        for width in (1440, 900, 390):
            page = browser.new_page(viewport={'width': width, 'height': 1000})
            page.goto(f'http://127.0.0.1:8769/?theme={theme}&avatar=1')
            page.wait_for_selector('.nour-stat')
            buttons = page.locator('.st-key-nour_shell_actions button:visible')
            expect(buttons).to_have_count(3)
            boxes = [button.bounding_box() for button in buttons.all()]
            assert len(boxes) == 3
            for index, box in enumerate(boxes):
                assert box['width'] == box['height'] == 52, boxes
                assert abs(box['y'] - boxes[0]['y']) < 1, boxes
                if index:
                    assert abs(box['x'] - boxes[index - 1]['x'] - 64) < 1, boxes
            avatar = buttons.nth(2)
            image = avatar.locator('img')
            assert image.evaluate('(e) => e.complete && e.naturalWidth === 240')
            styles = image.evaluate('(e) => {const s=getComputedStyle(e);return [s.objectFit,s.objectPosition,s.margin,s.transform]}')
            assert styles == ['cover', '50% 50%', '0px', 'none'], styles
            assert avatar.evaluate('(e) => getComputedStyle(e).overflow') == 'hidden'
            assert avatar.evaluate('(e) => getComputedStyle(e).borderRadius') == '50%'
            ib = image.bounding_box()
            ab = avatar.bounding_box()
            assert ib['x'] >= ab['x'] and ib['y'] >= ab['y']
            assert ib['x'] + ib['width'] <= ab['x'] + 52
            assert ib['y'] + ib['height'] <= ab['y'] + 52
            assert abs(ib['x'] + ib['width']/2 - ab['x'] - 26) < 1
            assert abs(ib['y'] + ib['height']/2 - ab['y'] - 26) < 1
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            buttons.nth(1).click()
            page.get_by_text('Messaging is not connected yet.', exact=True).wait_for()
            page.keyboard.press('Escape')
            output = ROOT / 'uat/soft-forest'
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output / f'avatar-{theme}-{width}.png'))
            avatar.click()
            page.get_by_text('Opened: Edit Profile', exact=True).wait_for()
            buttons.nth(0).click()
            page.get_by_text('Opened: Notifications', exact=True).wait_for()
            page.close()
    page = browser.new_page()
    page.goto('http://127.0.0.1:8769/?theme=Light')
    page.wait_for_selector('.nour-stat')
    expect(page.locator('.st-key-nour_header_nav_profile button:visible [data-testid="stIconMaterial"]')).to_have_text('account_circle')
    browser.close()
print('Avatar alignment, clipping, actions and fallback passed in both themes at desktop, tablet and mobile sizes.')
