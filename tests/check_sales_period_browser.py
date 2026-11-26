"""Real native calendars in the synthetic dashboard; no credentials or DB access."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'uat/soft-forest'
OUTPUT.mkdir(parents=True, exist_ok=True)
GREEN, WHITE = 'rgb(36, 84, 61)', 'rgb(245, 247, 243)'
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', headless=True)
    for theme in ('Light', 'Dark'):
        for width in (1440, 900, 390):
            page = browser.new_page(viewport={'width': width, 'height': 900})
            page.goto(f'http://127.0.0.1:8769/?theme={theme}', wait_until='domcontentloaded')
            page.wait_for_selector('.nour-stat')
            trigger = page.locator('.st-key-overview_sales_custom button:visible').first
            trigger.click()
            modes = page.locator('.st-key-bizmar_period_modes')
            expect(modes.locator('button:visible')).to_have_count(4)
            page.get_by_role('button', name='Choose date', exact=True).click()
            native = page.locator('[data-testid=stDateInputCalendar]')
            expect(native).to_be_visible()
            selected = native.locator('[data-selected=true]')
            expect(selected).to_have_css('background-color', GREEN)
            expect(selected).to_have_css('color', WHITE)
            # Selecting a date must update the real filter without losing the single-day mode.
            native.get_by_role('button', name='Previous month', exact=True).click()
            native.locator('[role=button]').filter(has_text='15').first.click()
            expect(page.locator('.st-key-nour_overview_filters [data-testid=stCaptionContainer]')).to_contain_text('Day:')
            page.keyboard.press('Escape')
            for mode in ('Week', 'Month', 'Custom'):
                trigger.click()
                modes.get_by_role('button', name=mode, exact=True).click()
                expect(modes.locator('button[kind=primary]:visible')).to_have_text(mode)
                cal = page.locator('.st-key-bizmar_period_calendar')
                if mode == 'Month':
                    expect(cal.locator('.st-key-bizmar_period_month_grid button:visible')).to_have_count(12)
                    assert not cal.locator('[role=grid]').count()
                    previous = cal.get_by_role('button', name='‹', exact=True)
                    previous.click()
                    cal.get_by_role('button', name='Feb', exact=True).click()
                    expect(page.locator('.st-key-nour_overview_filters [data-testid=stCaptionContainer]')).to_contain_text('28 Feb')
                    expect(cal.get_by_role('button', name='Feb', exact=True)).to_have_css('background-color', GREEN)
                else:
                    grid = cal.locator('.st-key-bizmar_period_day_grid')
                    expect(grid.locator('button:visible').first).to_be_visible()
                    if mode == 'Week':
                        grid.get_by_role('button', name='15', exact=True).click()
                        expect(grid.locator('button[kind=primary]:visible')).to_have_count(7)
                    else:
                        grid.get_by_role('button', name='5', exact=True).click()
                        expect(cal.get_by_role('button', name='Apply', exact=True)).to_be_disabled()
                        grid.get_by_role('button', name='12', exact=True).click()
                        expect(grid.locator('button[kind=primary]:visible')).to_have_count(8)
                        cal.get_by_role('button', name='Cancel', exact=True).click()
                        expect(grid.locator('button[kind=primary]:visible')).to_have_count(1)
                        grid.get_by_role('button', name='5', exact=True).click()
                        expect(cal.get_by_role('button', name='Apply', exact=True)).to_be_disabled()
                        grid.get_by_role('button', name='12', exact=True).click()
                        expect(grid.locator('button[kind=primary]:visible')).to_have_count(8)
                        expect(cal.get_by_role('button', name='Apply', exact=True)).to_be_enabled()
                        cal.get_by_role('button', name='Apply', exact=True).click()
                        expect(page.locator('.st-key-nour_overview_filters [data-testid=stCaptionContainer]')).to_contain_text('Custom: 05')
                    expect(grid.locator('button[kind=primary]:visible').first).to_have_css('background-color', GREEN)
                    expect(grid.locator('button[kind=primary]:visible').first.locator('p')).to_have_css('color', WHITE)
                body = page.locator('[data-testid=stPopoverBody]:visible')
                box = body.bounding_box()
                assert box['x'] >= 0 and box['x'] + box['width'] <= width + 1, (theme, width, mode, box)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert body.evaluate('(e)=>parseInt(getComputedStyle(e).zIndex)') >= 10001
                # A point in a date/month button must hit the popover rather than a KPI card.
                cal.locator('button:visible').first.scroll_into_view_if_needed()
                cal.locator('button:visible').first.click(trial=True)
                page.screenshot(path=str(OUTPUT / f'period-{theme}-{width}-{mode}.png'))
                page.keyboard.press('Escape')
            assert not page.locator('[data-testid=stException]').count()
            page.close()
    browser.close()
print('Day, Week, Month and Custom passed in Light/Dark at desktop, tablet and mobile sizes.')
