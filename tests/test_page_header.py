from datetime import datetime,timezone
import unittest
from streamlit.testing.v1 import AppTest
from navigation import ROUTE_LABELS
from page_header import header_title


class PageHeaderTests(unittest.TestCase):
    def test_shared_header_handles_all_routes_and_escapes_titles(self):
        for route,label in ROUTE_LABELS.items():
            with self.subTest(route=route):
                title=header_title(route,ROUTE_LABELS)
                app=AppTest.from_string(f"from page_header import page_header\nwith page_header({title!r}):pass").run()
                self.assertFalse(app.exception)
                self.assertTrue(any('nour-header-title' in m.value for m in app.markdown))
        app=AppTest.from_string("from page_header import page_header\nwith page_header('<script>unsafe</script>'):pass").run()
        self.assertTrue(any('&lt;script&gt;' in m.value for m in app.markdown))

    def test_date_uses_malaysia_day_and_optional_existing_preference(self):
        app=AppTest.from_string("""from datetime import datetime,timezone
from page_header import page_header
with page_header('Orders',when=datetime(2026,12,31,18,tzinfo=timezone.utc)):pass
""").run()
        self.assertFalse(app.exception)
        self.assertTrue(any('01/01/2027 | Malaysia (MYT)' in m.value for m in app.markdown))

    def test_overview_actions_and_greeting_are_supported(self):
        app=AppTest.from_string("""import streamlit as st
from page_header import page_header
with page_header('Dashboard',greeting='Good Morning, Owner!',with_actions=True) as actions:
 with actions:
  st.button('Notifications',key='header_action_test')
""").run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Good Morning' in m.value for m in app.markdown))
        self.assertEqual(app.button(key='header_action_test').label,'Notifications')
