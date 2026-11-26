"""Read-only State/filter/menu/layout checks for the reference-style Orders page."""
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'uat/soft-forest'
OUT.mkdir(exist_ok=True)

def choose_state(page,value):
    field=page.locator('.st-key-om_state_filter input')
    field.click()
    field.fill(value)
    page.get_by_role('option',name=value,exact=True).click()

def menu(page,identity,width):
    expect(page.locator('[data-testid=stApp]')).to_have_attribute('data-test-script-state','notRunning')
    if page.locator('[data-testid=stPopoverBody]').filter(visible=True).count():
        page.keyboard.press('Escape')
    prefix=f'.st-key-om_mobile_card_{identity}' if width<=640 else f'.st-key-orders_table_row_{identity}'
    control=page.locator(prefix+' button[data-testid=stPopoverButton]').filter(visible=True)
    expect(control).to_have_count(1)
    control.click()
    return page.locator('[data-testid=stPopoverBody]').filter(visible=True)

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
    for theme in ('Light','Dark'):
        for width in (1440,768,390):
            page=browser.new_page(viewport={'width':width,'height':1100})
            page.goto('http://127.0.0.1:8771/?theme='+theme,wait_until='domcontentloaded')
            expect(page.get_by_role('heading',name='Order List',exact=True)).to_be_visible()
            expect(page.locator('[data-testid=stApp]')).to_have_attribute('data-test-script-state','notRunning')
            metrics=page.locator('.st-key-nour_orders_kpis [data-testid=stMetricValue]')
            expect(metrics).to_have_count(4)
            assert metrics.all_text_contents()==['3','1','1','1']
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            if width<901:
                assert abs(metrics.nth(0).bounding_box()['y']-metrics.nth(1).bounding_box()['y'])<2
                assert metrics.nth(2).bounding_box()['y']>metrics.nth(0).bounding_box()['y']
            page.screenshot(path=str(OUT/f'orders-reference-{theme}-{width}.png'))
            choose_state(page,'Kedah')
            expect(page.get_by_role('button',name='State: Kedah ×',exact=True)).to_be_visible()
            state_customer = (
                '.st-key-om_mobile_card_1' if width<=640 else
                '.st-key-orders_table_row_1 [data-testid="stColumn"]:nth-child(2)'
            )
            page.locator(state_customer).get_by_role('button',name='Synthetic Customer',exact=True).click()
            expect(page.get_by_role('dialog')).to_contain_text('ORD001')
            page.keyboard.press('Escape')
            page.get_by_role('radio',name='Completed',exact=True).click()
            expect(page.get_by_text('No orders found for the selected state.',exact=True)).to_be_visible()
            page.get_by_role('button',name='Clear All',exact=True).click()
            expect(page.get_by_role('radio',name='All',exact=True)).to_be_checked()
            choose_state(page,'Not Specified')
            state_customer = (
                '.st-key-om_mobile_card_3' if width<=640 else
                '.st-key-orders_table_row_3 [data-testid="stColumn"]:nth-child(2)'
            )
            page.locator(state_customer).get_by_role('button',name='Synthetic Cancelled',exact=True).click()
            expect(page.get_by_role('dialog')).to_contain_text('ORD003')
            page.keyboard.press('Escape')
            page.get_by_role('button',name='State: Not Specified ×',exact=True).click()
            choose_state(page,'Labuan')
            expect(page.get_by_text('No orders found for the selected state.',exact=True)).to_be_visible()
            page.get_by_role('button',name='Clear All',exact=True).click()
            customer_prefix = (
                f'.st-key-om_mobile_card_1' if width<=640 else
                f'.st-key-orders_table_row_1 [data-testid="stColumn"]:nth-child(2)'
            )
            page.locator(customer_prefix).get_by_role('button',name='Synthetic Customer',exact=True).click()
            expect(page.get_by_role('dialog').get_by_role('heading',name='Order Details')).to_be_visible()
            expect(page.get_by_role('dialog')).to_contain_text('ORD001')
            expect(page.get_by_role('dialog')).to_contain_text('Edit Order')
            assert page.locator('.st-key-nour_orders_actions').count()==0
            popup=menu(page,2,width)
            expect(popup.get_by_role('button',name='View Details',exact=True)).to_be_visible()
            assert popup.get_by_role('button',name='Edit Order',exact=True).count()==0
            popup.get_by_role('button',name='View Details',exact=True).click()
            expect(page.get_by_role('dialog')).to_contain_text('ORD002')
            popup=menu(page,1,width)
            popup.get_by_role('button',name='View Details',exact=True).click()
            expect(page.get_by_role('dialog')).to_contain_text('ORD001')
            popup=menu(page,1,width)
            popup.get_by_role('button',name='Cancel Order',exact=True).click()
            expect(page.get_by_role('button',name='Keep Order',exact=True)).to_be_visible()
            page.get_by_role('button',name='Keep Order',exact=True).click()
            expect(page.get_by_role('button',name='Yes, Cancel Order',exact=True)).to_have_count(0)
            popup=menu(page,1,width)
            popup.get_by_role('button',name='Edit Order',exact=True).click()
            editor=page.locator('.st-key-nour_order_form')
            expect(editor).to_be_visible()
            expect(page.get_by_label('Customer residence state (optional)',exact=True)).to_be_visible()
            page.screenshot(path=str(OUT/f'orders-reference-editor-{theme}-{width}.png'))
            editor.get_by_role('button',name='Cancel',exact=True).click()
            expect(editor).not_to_be_visible()
            page.get_by_role('button',name='Export',exact=True).click()
            expect(page.get_by_role('button',name='CSV',exact=True)).to_be_visible()
            expect(page.get_by_role('button',name='Excel (.xlsx)',exact=True)).to_be_visible()
            page.keyboard.press('Escape')
            href=page.get_by_role('link',name='WhatsApp Customer',exact=True).get_attribute('href')
            assert urlparse(href).netloc=='wa.me'
            assert 'ORD001' in parse_qs(urlparse(href).query)['text'][0]
            page.get_by_role('button',name='Add Order',exact=True).click()
            expect(page.get_by_role('heading',name='Add New Order',exact=True)).to_be_visible()
            page.get_by_role('button',name='Cancel',exact=True).click()
            assert not page.locator('[data-testid=stException]').count()
            page.close()
    browser.close()
print('Reference Orders layout, State filters/chips, row menus, dialogs and exports passed in both themes at 1440/768/390px.')
