"""SMIL playback and responsive layout checks for the original login SVG."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'uat/soft-forest'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
 for name,width,height in [('desktop',1440,1000),('tablet',900,900),('mobile',390,844)]:
  page=browser.new_page(viewport={'width':width,'height':height})
  page.goto('http://127.0.0.1:8770',wait_until='domcontentloaded')
  image=page.locator('.bizmar-login-animation img');image.wait_for()
  page.wait_for_function('document.querySelector(".bizmar-login-animation img").complete')
  assert image.evaluate('e=>Math.abs(e.naturalWidth/e.naturalHeight-4/3)<0.01')
  assert image.evaluate('e=>getComputedStyle(e).objectFit')=='contain'
  first=image.screenshot();page.wait_for_timeout(650);second=image.screenshot()
  assert first!=second, name+': animation did not advance'
  area=page.locator('.bizmar-login-animation').bounding_box()
  description=page.locator('.bizmar-brand-description').bounding_box()
  form=page.locator('.st-key-bizmar_login_card').bounding_box()
  assert area['y']>=description['y']+description['height']-1,(name,area,description)
  if form['x'] < area['x']+area['width']:
   assert form['y']>=area['y']+area['height']-1,(name,area,form)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),name+' horizontal overflow'
  assert not page.locator('[data-testid=stException]').count()
  page.screenshot(path=str(OUTPUT/f'login-animation-{name}.png'),full_page=True)
  print(name+': SMIL playback, aspect ratio, branding/form separation, and responsive width passed',flush=True)
  page.close()
 browser.close()
