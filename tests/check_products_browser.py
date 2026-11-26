"""Read-only responsive theme and image controls checks using synthetic preview."""
from io import BytesIO
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright, expect
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'uat/soft-forest'
OUT.mkdir(exist_ok=True)
image = BytesIO()
Image.new('RGB', (300, 160), 'pink').save(image, 'PNG')
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', headless=True)
    for theme in ('Light', 'Dark'):
        for width in (1440, 768, 390):
            page = browser.new_page(viewport={'width':width, 'height':1000})
            page.goto(f'http://127.0.0.1:8772/?theme={theme}', wait_until='domcontentloaded')
            expect(page.get_by_role('heading', name='Product', exact=True)).to_be_visible()
            expect(page.get_by_text('Your bakes, beautifully organised.', exact=True)).to_have_count(0)
            expect(page.locator('.st-key-catalogue_kpis [data-testid=stMetricValue]')).to_have_count(3)
            expect(page.locator('[data-testid=stApp]')).to_have_attribute('data-test-script-state', 'notRunning')
            assert not page.locator('[data-testid=stException]').count()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            metrics = page.locator('.st-key-catalogue_kpis [data-testid=stMetric]')
            if width == 390:
                assert abs(metrics.nth(0).bounding_box()['y'] - metrics.nth(2).bounding_box()['y']) < 2
            expect(page.locator('.product-copy h3').first).to_have_css('color', 'rgb(245, 247, 243)' if theme == 'Dark' else 'rgb(36, 51, 46)')
            page.screenshot(path=str(OUT / f'products-{theme}-{width}.png'), full_page=True)
            page.get_by_text('List', exact=True).click()
            expect(page.locator('.st-key-catalogue_list')).to_be_visible()
            page.get_by_label('Search products', exact=True).fill('brownie')
            page.get_by_label('Search products', exact=True).press('Enter')
            expect(page.locator('.product-copy h3')).to_have_count(1)
            page.get_by_role('button', name='Edit', exact=True).click()
            editor = page.locator('.st-key-bizmar_product_editor')
            expect(editor).to_be_visible()
            page.get_by_role('button', name='Upload', exact=True).click()
            page.locator('input[type=file]').set_input_files({'name':'synthetic.png', 'mimeType':'image/png', 'buffer':image.getvalue()})
            expect(editor.locator('.product-image-preview img')).to_be_visible()
            page.keyboard.press('Escape')
            page.get_by_role('button', name='Remove', exact=True).click()
            page.get_by_role('button', name='Confirm removal', exact=True).click()
            expect(editor.get_by_text('No product image', exact=True)).to_be_visible()
            page.get_by_role('button', name='Cancel', exact=True).click()
            expect(editor).not_to_be_visible()
            page.get_by_role('button', name='Details', exact=True).click()
            expect(page.get_by_role('button', name='Archive Product', exact=True)).to_be_visible()
            page.get_by_role('button', name='Close', exact=True).click()
            page.get_by_role('button', name='Add Product', exact=True).click()
            expect(page.get_by_role('heading', name='Add Product', exact=True)).to_be_visible()
            expect(page.get_by_label('Quantity per selling unit', exact=True)).to_be_visible()
            expect(page.locator('[data-testid=stApp]')).to_have_attribute('data-test-script-state', 'notRunning')
            expect(page.get_by_label('Product name', exact=True)).to_have_css('background-color', 'rgb(36, 51, 46)' if theme == 'Dark' else 'rgb(255, 255, 255)')
            expect(page.get_by_label('Product name', exact=True)).to_have_css('color', 'rgb(245, 247, 243)' if theme == 'Dark' else 'rgb(36, 51, 46)')
            expect(page.get_by_role('button', name='Upload', exact=True)).to_have_css('background-color', 'rgb(59, 81, 71)' if theme == 'Dark' else 'rgb(255, 255, 255)')
            page.screenshot(path=str(OUT / f'product-editor-{theme}-{width}.png'), full_page=True)
            page.get_by_role('button', name='Cancel', exact=True).click()
            assert not page.locator('[data-testid=stException]').count()
            page.close()
    browser.close()
print('Catalogue Grid/List, images, dialogs and responsive light/dark layouts passed at 1440, 768 and 390px.')
