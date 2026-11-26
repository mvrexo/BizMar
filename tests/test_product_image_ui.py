from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch
from PIL import Image
from streamlit.testing.v1 import AppTest


SCRIPT = '''
import streamlit as st
from product_image_ui import render_product_image, clear_image_drafts
photo, removed, valid = render_product_image('test', st.session_state.get('saved_image'))
st.session_state['image_result'] = (removed, valid)
if st.button('Cancel'):
    clear_image_drafts()
    st.rerun()
st.button('Save', disabled=not valid)
'''


class ProductImageUITests(unittest.TestCase):
    def test_placeholder_and_confirmation_cancel(self):
        app = AppTest.from_string(SCRIPT).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('No product image' in m.value for m in app.markdown))
        app.session_state['saved_image'] = 'assets/bizmar_logo.png'
        app.run()
        self.assertFalse(app.exception)
        self.assertFalse(app.session_state['image_result'][0])
        confirm = next(b for b in app.button if b.label == 'Confirm removal')
        confirm.click().run()
        self.assertTrue(app.session_state['image_result'][0])
        self.assertTrue(any('No product image' in m.value for m in app.markdown))
        next(b for b in app.button if b.label == 'Cancel').click().run()
        self.assertFalse(app.session_state['image_result'][0])
        self.assertFalse(app.exception)

    def test_upload_preview_and_invalid_save_disabled(self):
        image = BytesIO()
        Image.new('RGB', (40, 20), 'pink').save(image, 'PNG')
        with patch('product_image_ui.st.file_uploader', return_value=image):
            app = AppTest.from_string(SCRIPT).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('data:image/png;base64,' in m.value for m in app.markdown))
            self.assertEqual(app.session_state['image_result'], (False, True))
        with patch('product_image_ui.st.file_uploader', return_value=BytesIO(b'invalid')):
            app = AppTest.from_string(SCRIPT).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.assertTrue(next(b for b in app.button if b.label == 'Save').disabled)
