from datetime import datetime
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import test_google_sheets_sync as fixtures
import orders_store as store
import sqlite_db
from notifications_ui import group_notifications,relative_time,MYT


class NotificationsDesignTests(unittest.TestCase):
    headers=fixtures.GoogleSheetsSyncTests.headers
    make_snapshot=fixtures.GoogleSheetsSyncTests.make_snapshot
    row=fixtures.GoogleSheetsSyncTests.row
    prepare=fixtures.GoogleSheetsSyncTests.prepare
    tearDown=fixtures.GoogleSheetsSyncTests.tearDown

    def setUp(self):
        fixtures.GoogleSheetsSyncTests.setUp(self)
        prepared=self.prepare(self.make_snapshot([self.row()]))
        store.activate_google_sheets_preview(self.config.spreadsheet_id,prepared.sheet_id,prepared.preview.records)

    def app(self,compact=False):
        return AppTest.from_string("""import streamlit as st
from notifications_ui import render_notifications
def open_order(identity):st.session_state['opened_order']=identity
render_notifications(open_order,compact=COMPACT,key_prefix='test_notifications')
""".replace('COMPACT',repr(compact))).run()

    def test_date_groups_respect_malaysia_time_and_calendar_week(self):
        current=datetime(2026,10,29,12,tzinfo=MYT)
        records=[dict(id=1,created_at='2026-10-28T17:00:00+00:00'),dict(id=2,created_at='2026-10-28T10:00:00+08:00'),dict(id=3,created_at='2026-10-26T10:00:00+08:00'),dict(id=4,created_at='2026-10-25T10:00:00+08:00')]
        groups=group_notifications(records,current)
        self.assertEqual(list(groups),['Today','Yesterday','This Week','Earlier'])
        self.assertEqual(groups['Today'][0]['id'],1)
        self.assertEqual(relative_time('2026-10-29T11:00:00+08:00',current),'1h ago')

    def test_open_order_preserves_business_records_and_marks_notice_read(self):
        before=sqlite_db.all_rows('orders')
        notice=store.list_order_notifications()[0]
        app=self.app(True)
        self.assertFalse(app.exception)
        self.assertTrue(any('Notifications' in item.value for item in app.markdown))
        app.button(key=f'test_notifications_order_{notice["id"]}').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['opened_order'],notice['order_id'])
        self.assertEqual(store.order_notification_counts()['unread'],0)
        self.assertEqual(sqlite_db.all_rows('orders'),before)

    def test_mark_all_read_and_unread_filter_empty_state(self):
        app=self.app()
        app.button(key='test_notifications_mark_all_read').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(store.order_notification_counts()['unread'],0)
        self.assertTrue(app.button(key='test_notifications_mark_all_read').disabled)
        app.radio(key='test_notifications_filter').set_value('Unread').run()
        self.assertTrue(any('caught up' in item.value for item in app.info))

    def test_single_read_action_is_persistent(self):
        notice=store.list_order_notifications()[0]
        app=self.app()
        app.button(key=f'test_notifications_read_{notice["id"]}').click().run()
        self.assertFalse(app.exception)
        self.assertIsNotNone(store.list_order_notifications()[0]['read_at'])

    def test_owner_gate_and_no_fake_notifications(self):
        with patch.object(store,'current_owner',side_effect=PermissionError('Expired')):
            app=self.app()
            self.assertFalse(app.exception);self.assertTrue(app.warning);self.assertEqual(len(app.button),0)
        with patch.object(store,'list_order_notifications',return_value=[]),patch.object(store,'order_notification_counts',return_value={'total':0,'unread':0}):
            app=self.app()
            self.assertTrue(any('No order notifications' in item.value for item in app.info))


if __name__=='__main__':unittest.main()
