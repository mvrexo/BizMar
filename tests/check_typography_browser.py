"""Verify actual typography sizes, roles and responsive wrapping in both themes."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
 for theme in ('Light','Dark'):
  for width in (1440,390):
   page=browser.new_page(viewport={'width':width,'height':1000})
   page.goto('http://127.0.0.1:8769/?theme='+theme)
   page.wait_for_selector('.nour-stat')
   for selector,family,size,weight in [('.nour-header-title','Plus Jakarta Sans',28 if width>600 else 26,700),('.st-key-nour_overview_sales h4','Plus Jakarta Sans',19,600),('.nour-stat-value','Inter',32 if width>600 else 28,700),('.st-key-nour_overview_filters button p','Plus Jakarta Sans',14,600)]:
    data=page.locator(selector).first.evaluate('e=>{let s=getComputedStyle(e);return {family:s.fontFamily,size:s.fontSize,weight:s.fontWeight}}')
    assert family in data['family'] and data['size']==str(size)+'px' and data['weight']==str(weight), (selector,data)
   assert 'tabular-nums' in page.locator('.nour-stat-value').first.evaluate('e=>getComputedStyle(e).fontVariantNumeric')
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   cards=[e.bounding_box() for e in page.locator('.nour-stat').all()]
   if width>600:
    assert max(c['height'] for c in cards)-min(c['height'] for c in cards)<1,cards
   assert page.locator('.st-key-nour_overview_activity').bounding_box()['y']-max(c['y']+c['height'] for c in cards)>=23
   assert page.locator('[data-testid=stIconMaterial]').first.evaluate('e=>getComputedStyle(e).fontFamily').find('Material Symbols')>=0
   if width==1440:
    page.locator('.st-key-nour_header_nav_notifications button:visible').hover()
    tip=page.locator('[role=tooltip] [data-testid=stTooltipContent]:visible');tip.wait_for()
    values=tip.locator('p').evaluate('e=>{let s=getComputedStyle(e);return [s.fontFamily,s.fontSize,s.fontWeight]}')
    assert 'Inter' in values[0] and values[1:] == ['13px','500'],values
    page.mouse.move(0,0)
   if width==1440:
    nav=page.locator('.st-key-nour_nav_PRIMARY_0 button p')
    assert nav.evaluate('e=>getComputedStyle(e).fontSize')=='15px'
    assert nav.evaluate('e=>getComputedStyle(e).fontWeight')=='500'
   page.screenshot(path=str(ROOT/f'uat/soft-forest/typography-{theme.lower()}-{width}.png'),full_page=True)
   print(theme,width,': responsive title/section/KPI/button fonts, icon preservation and overflow checks passed',flush=True)
   page.close()
 browser.close()
