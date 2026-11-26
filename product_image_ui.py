"""Draft-only product image controls. Persistence happens in the product save."""
from display_preferences import tr
import base64
from io import BytesIO
from pathlib import Path
import streamlit as st
from storage import validated_image_bytes
from uat_hardening import local_image


def clear_image_drafts():
    for key in list(st.session_state):
        if key.startswith('product_media_'):
            del st.session_state[key]


def render_product_image(scope, saved_image=None):
    prefix = f'product_media_{scope}'
    removed = st.session_state.get(prefix + '_removed', False)
    generation = st.session_state.get(prefix + '_generation', 0)
    st.markdown(tr('##### Product Image'))
    with st.container(key='product_image_editor'):
        st.markdown(tr('''<style>
        .st-key-product_image_editor .product-image-preview {
            width:160px;height:160px;border-radius:14px;overflow:hidden;
            border:1px solid var(--border-color,#88968b);margin-bottom:12px;
            display:flex;align-items:center;justify-content:center;
            background:var(--secondary-background-color,rgba(128,128,128,.08));}
        .st-key-product_image_editor .product-image-preview img {
            width:100%;height:100%;object-fit:cover;object-position:center;display:block;}
        .st-key-product_image_editor .product-image-preview span {
            font-size:14px;color:inherit;text-align:center;}
        </style>'''), unsafe_allow_html=True)
        actions = st.container(horizontal=True, gap='small')
        replacing = bool(saved_image and not removed)
        with actions, st.popover(tr('Replace' if replacing else 'Upload'), icon=':material/swap_horiz:' if replacing else ':material/upload:', use_container_width=False):
            photo = st.file_uploader(tr('Choose product image'), type=['png','jpg','jpeg','webp'],
                max_upload_size=5, key=prefix + f'_upload_{generation}',
                help=tr('PNG, JPG, JPEG or WEBP. Maximum 5 MB.'))
        valid = True
        preview = None
        if photo is not None:
            try:
                preview = validated_image_bytes(photo)
            except ValueError as error:
                st.error(tr(str(error)))
                valid = False
        elif saved_image and not removed:
            path = Path(local_image(saved_image))
            if path.name != 'uat-placeholder.svg':
                try:
                    preview = validated_image_bytes(BytesIO(path.read_bytes()))
                except (ValueError, OSError):
                    pass
        if preview:
            encoded = base64.b64encode(preview).decode('ascii')
            st.markdown(tr(f'<div class="product-image-preview"><img alt="Product image preview" src="data:image/png;base64,{encoded}"></div>'), unsafe_allow_html=True)
        else:
            st.markdown(tr('<div class="product-image-preview"><span>No product image</span></div>'), unsafe_allow_html=True)
        if (saved_image and not removed) or photo is not None:
            with actions, st.popover(tr('Remove'), icon=':material/delete:', use_container_width=False):
                st.write(tr('Remove this image? The change takes effect only when you save the product.'))
                if st.button(tr('Confirm removal'), key=prefix + '_confirm', icon=':material/check:'):
                    st.session_state[prefix + '_removed'] = True
                    st.session_state[prefix + '_generation'] = generation + 1
                    st.rerun()
        if removed and photo is None:
            st.caption(tr('Image removal pending. Save Changes to confirm, or Cancel to keep the saved image.'))
        return photo, removed and photo is None, valid
