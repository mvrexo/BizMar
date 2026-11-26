from display_preferences import option_labels
"""Owner product catalogue and native dialogs backed by local persistence."""
from display_preferences import tr
from display_preferences import localized_dialog
import base64
from html import escape
from io import BytesIO
from pathlib import Path
from decimal import Decimal
from PIL import Image
import streamlit as st
import products_store as store
from product_image_ui import render_product_image, clear_image_drafts
from storage import validated_image_bytes
from uat_hardening import local_image

ROOT = Path(__file__).resolve().parent


def money(value):
    return f'RM {Decimal(str(value)):.2f}'


def profit(product):
    return Decimal(str(product['price'])) - Decimal(str(product['unit_cost']))


def packaging(product):
    quantity = float(product.get('quantity_per_unit', 1))
    return f"{quantity:g} {product.get('measurement_unit', 'pieces')} / {product.get('packaging_type', 'Unit').lower()}"


def filter_products(products, search='', category='All categories', availability='All products'):
    query = search.strip().casefold()
    return [p for p in products if
        (not query or query in f"{p['name']} {p['category']} {packaging(p)}".casefold()) and
        (category == 'All categories' or p['category'] == category) and
        (availability == 'All products' or bool(p['active']) == (availability == 'Active'))]


def image_markup(product):
    path = Path(local_image(product.get('image_url')))
    if path.name != 'uat-placeholder.svg':
        try:
            image = validated_image_bytes(BytesIO(path.read_bytes()))
            with Image.open(BytesIO(image)) as source:
                source.thumbnail((640, 480))
                output = BytesIO()
                source.save(output, 'PNG')
            encoded = base64.b64encode(output.getvalue()).decode('ascii')
            return f'<img src="data:image/png;base64,{encoded}" alt="{escape(product["name"], quote=True)}">'
        except (OSError, ValueError):
            pass
    return '<span class="product-no-image">No product image</span>'


def _close_editor():
    st.session_state.pop('catalogue_dialog', None)
    clear_image_drafts()
    for key in list(st.session_state):
        if key.startswith('catalogue_editor_'):
            del st.session_state[key]


def _changed(callback, message):
    _close_editor()
    st.session_state['catalogue_flash'] = message
    if callback:
        callback()
    st.rerun()


@localized_dialog('Product', width='large', on_dismiss=_close_editor)
def _editor(identity=None, on_change=None):
    store.current_owner()
    try:
        product = store.get_product(identity) if identity is not None else dict(name='', category='Dessert', price=0., unit_cost=0., active=1,
            quantity_per_unit=1., measurement_unit='pieces', packaging_type='Unit', weight_grams=None, image_url=None)
    except (ValueError, PermissionError) as error:
        st.error(tr(str(error)))
        return
    with st.container(key='bizmar_product_editor'):
        st.subheader(tr('Edit Product' if identity is not None else 'Add Product'))
        st.caption(tr('Price and cost apply to one complete selling unit, such as one box or jar.'))
        name = st.text_input(tr('Product name'), value=product['name'], max_chars=150, key='catalogue_editor_name')
        categories = sorted({'Kuih Raya', 'Kuih Tradisional', 'Dessert', product['category']} | {p['category'] for p in store.list_products()})
        category = st.selectbox(tr('Category'), categories, index=categories.index(product['category']), accept_new_options=True, key='catalogue_editor_category')
        prices = st.columns(2)
        price = prices[0].number_input(tr('Selling price (RM)'), min_value=0., value=float(product['price']), step=.5, format='%.2f', key='catalogue_editor_price')
        cost = prices[1].number_input(tr('Cost per selling unit (RM)'), min_value=0., value=float(product['unit_cost']), step=.1, format='%.2f', key='catalogue_editor_cost')
        st.markdown(tr(f'<div class="product-profit">Estimated unit profit <strong>{money(Decimal(str(price)) - Decimal(str(cost)))}</strong></div>'), unsafe_allow_html=True)
        st.caption(tr('Selling price minus cost, before overheads. Orders count complete selling units.'))
        pack = st.columns(2)
        quantity = pack[0].number_input(tr('Quantity per selling unit'), min_value=.001, max_value=1_000_000., value=float(product['quantity_per_unit']), step=1., format='%g', key='catalogue_editor_quantity')
        unit = pack[1].selectbox(tr('Measurement unit'), store.UNITS, index=store.UNITS.index(product['measurement_unit']) if product['measurement_unit'] in store.UNITS else 0, key='catalogue_editor_unit')
        pack = st.columns(2)
        packaging_type = pack[0].selectbox(tr('Packaging type'), store.PACKAGING, index=store.PACKAGING.index(product['packaging_type']) if product['packaging_type'] in store.PACKAGING else 0, key='catalogue_editor_packaging')
        weight = pack[1].number_input(tr('Weight in grams (optional)'), min_value=.001, max_value=1_000_000., value=float(product['weight_grams']) if product['weight_grams'] else None, step=1., placeholder=tr('Not specified'), key='catalogue_editor_weight')
        photo, removed, valid = render_product_image(f'catalogue_{identity or "new"}', product.get('image_url'))
        active = st.checkbox(tr('Available for new orders'), value=bool(product['active']), key='catalogue_editor_active')
        controls = st.columns(2)
        if controls[0].button(tr('Save Changes' if identity is not None else 'Add Product'), type='primary', icon=':material/check:', disabled=not valid, key='catalogue_editor_save'):
            try:
                store.save_product(dict(name=name, category=category, price=price, unit_cost=cost,
                    quantity_per_unit=quantity, measurement_unit=unit, packaging_type=packaging_type,
                    weight_grams=weight, image_url=None if removed else product.get('image_url'), active=active), photo=photo, product_id=identity)
            except Exception as error:
                st.error(tr(f'Could not save product: {error}'))
            else:
                _changed(on_change, 'Product saved.')
        if controls[1].button(tr('Cancel'), icon=':material/close:', key='catalogue_editor_cancel'):
            _close_editor()
            st.rerun()


@localized_dialog('Product Details', width='large', on_dismiss=_close_editor)
def _details(identity, on_change=None):
    try:
        product = store.get_product(identity)
    except (ValueError, PermissionError) as error:
        st.error(tr(str(error)))
        return
    with st.container(key='bizmar_product_details'):
        st.markdown(tr(f'<div class="product-detail-image product-image">{image_markup(product)}</div>'), unsafe_allow_html=True)
        st.subheader(tr(product['name']))
        st.caption(tr(product['category']))
        st.write('Active · Available for new orders' if product['active'] else 'Archived · Unavailable for new orders')
        columns = st.columns(3)
        columns[0].metric(tr('Selling price'), money(product['price']))
        columns[1].metric(tr('Unit cost'), money(product['unit_cost']))
        columns[2].metric(tr('Estimated unit profit'), money(profit(product)))
        st.write(f'**Packaging:** {packaging(product)}')
        st.write(f'**Weight:** {product["weight_grams"]:g} g' if product.get('weight_grams') else '**Weight:** Not specified')
        st.caption(tr('Product price changes apply to new selections. Saved order prices and costs remain unchanged.'))
        label = 'Archive Product' if product['active'] else 'Reactivate Product'
        with st.popover(tr(label), icon=':material/inventory_2:'):
            st.write('Hide this product from new orders? Historical orders remain unchanged.' if product['active'] else 'Make this product available for new orders?')
            if st.button(tr('Confirm archive' if product['active'] else 'Confirm reactivation'), key='catalogue_status_confirm'):
                try:
                    store.set_active(identity, not product['active'])
                except Exception as error:
                    st.error(tr(str(error)))
                else:
                    _changed(on_change, 'Product archived.' if product['active'] else 'Product reactivated.')


def _card(product, on_change, list_view=False):
    identity = product['id']
    with st.container(key=f'product_card_{identity}', border=True):
        if list_view:
            image_column, text_column = st.columns([1, 3], vertical_alignment='center')
        else:
            image_column = text_column = st.container()
        with image_column:
            st.markdown(tr(f'<div class="product-image">{image_markup(product)}</div>'), unsafe_allow_html=True)
        with text_column:
            status = 'Active' if product['active'] else 'Archived'
            st.markdown(tr(f'''<div class="product-copy"><div class="product-card-top"><span class="product-category">{escape(product['category'])}</span><span class="product-status {'is-active' if product['active'] else 'is-archived'}">{status}</span></div>
                <h3>{escape(product['name'])}</h3><p class="product-packaging">{escape(packaging(product))}</p>
                <div class="product-price">{money(product['price'])}</div>
                <div class="product-cost">Cost {money(product['unit_cost'])}<span>Unit profit {money(profit(product))}</span></div></div>'''), unsafe_allow_html=True)
            actions = st.columns([2, 1])
            if actions[0].button(tr('Details'), key=f'catalogue_details_{identity}', icon=':material/info:', use_container_width=True):
                st.session_state['catalogue_dialog'] = ('details', identity)
            if actions[1].button(tr('Edit'), key=f'catalogue_edit_{identity}', icon=':material/edit:', use_container_width=True):
                _close_editor()
                st.session_state['catalogue_dialog'] = ('editor', identity)


def render_products(on_change=None):
    st.markdown(tr('<style>' + (ROOT / 'styles/products.css').read_text(encoding='utf-8') + '</style>'), unsafe_allow_html=True)
    try:
        products = store.list_products()
    except (PermissionError, ValueError) as error:
        st.error(tr(str(error)))
        return
    with st.container(key='bizmar_products'):
        heading, action = st.columns([4, 1.5], vertical_alignment='bottom')
        heading.title(tr('Product'))
        if action.button(tr('Add Product'), icon=':material/add:', type='primary', use_container_width=True, key='catalogue_add'):
            _close_editor()
            st.session_state['catalogue_dialog'] = ('editor', None)
        if st.session_state.get('catalogue_flash'):
            st.success(tr(st.session_state.pop('catalogue_flash')))
        with st.container(key='catalogue_kpis'):
            total, active, categories = st.columns(3)
            total.metric(tr('Total Products'), len(products))
            active.metric(tr('Active Products'), sum(bool(p['active']) for p in products))
            categories.metric(tr('Categories'), len({p['category'] for p in products}))
        with st.container(key='catalogue_filters'):
            search, category_column, status_column = st.columns([2, 1.3, 1.2])
            query = search.text_input(tr('Search products'), placeholder=tr('Search cakes, cookies, jars…'), icon=':material/search:', key='catalogue_search')
            category = category_column.selectbox(tr('Category'), ['All categories'] + sorted({p['category'] for p in products}), key='catalogue_category_filter')
            availability = status_column.selectbox(tr('Availability'), ['All products', 'Active', 'Archived'], key='catalogue_availability_filter', format_func=option_labels(['All products', 'Active', 'Archived']))
            view = st.segmented_control(tr('View'), ['Grid', 'List'], default='Grid', selection_mode='single', key='catalogue_view', format_func=option_labels(['Grid', 'List'])) or 'Grid'
        filtered = filter_products(products, query, category, availability)
        st.caption(tr(f'{len(filtered)} product{"s" if len(filtered) != 1 else ""}'))
        if not filtered:
            st.info(tr('No matching products. Try another search or add your first product.'))
        with st.container(key='catalogue_grid' if view == 'Grid' else 'catalogue_list'):
            for offset in range(0, len(filtered), 3 if view == 'Grid' else 1):
                columns = st.columns(3) if view == 'Grid' else [st.container()]
                for column, product in zip(columns, filtered[offset:offset + (3 if view == 'Grid' else 1)]):
                    with column:
                        _card(product, on_change, view == 'List')
        dialog = st.session_state.get('catalogue_dialog')
        if dialog:
            if dialog[0] == 'editor':
                _editor(dialog[1], on_change)
            else:
                _details(dialog[1], on_change)
