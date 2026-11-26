"""Check real Streamlit tooltip surfaces and header interactions in both themes."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'uat/soft-forest'
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
    for theme in ('Light','Dark'):
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.goto('http://127.0.0.1:8769/?theme='+theme)
        page.wait_for_selector('.nour-stat')
        buttons=page.locator('.st-key-nour_shell_actions button:visible')
        for index,name in enumerate(('Notifications','Messages','Edit Profile')):
            page.mouse.move(0,0)
            buttons.nth(index).hover()
            tip=page.locator('[role=tooltip] [data-testid=stTooltipContent]:visible')
            tip.wait_for()
            assert tip.inner_text()==name, (theme,name,tip.inner_text())
            assert tip.evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(52, 75, 64)'
            assert tip.locator('p').evaluate('(e)=>getComputedStyle(e).color')=='rgb(245, 247, 243)'
            assert tip.evaluate('(e)=>getComputedStyle(e).borderTopColor')=='rgb(80, 100, 90)'
            assert tip.evaluate('(e)=>getComputedStyle(e).borderRadius')=='10px'
            tip.screenshot(path=str(OUTPUT/f'tooltip-{theme.lower()}-{index}.png'))
        buttons.nth(1).click()
        page.get_by_text('Messaging is not connected yet.',exact=True).wait_for(state='visible')
        page.keyboard.press('Escape')
        buttons.nth(0).click()
        page.get_by_text('Opened: Notifications',exact=True).wait_for(state='visible')
        buttons.nth(2).click()
        page.get_by_text('Opened: Edit Profile',exact=True).wait_for(state='visible')
        assert not page.locator('[data-testid=stException]').count()
        print(theme+': all 3 tooltip backgrounds/text/borders/corners and header interactions passed')
        page.close()
    browser.close()
