"""Five-menu routing regressions; no authentication or database imports."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import unittest

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from navigation import (PRIMARY_SECTIONS, ROUTE_LABELS, navigate, navigate_primary,
                        go_back, initialize_navigation, retain_widget_context, primary_for)


class NavigationStateTests(unittest.TestCase):
    def test_exactly_five_primary_entries(self):
        self.assertEqual(list(PRIMARY_SECTIONS), ['Dashboard','Orders','Products','Analytics','Settings'])

    def test_all_requested_sections(self):
        self.assertEqual([label for label,_ in PRIMARY_SECTIONS['Orders']],
                         ['All Orders','Customers','Deadline Calendar','Production Tracking','Payments','Messages'])
        self.assertEqual([label for label,_ in PRIMARY_SECTIONS['Analytics']],
                         ['Sales Analytics','Profitability Analysis','Customer Insights','Long-Term Trends','Reports'])
        self.assertEqual(PRIMARY_SECTIONS['Settings'], [('Settings', 'Settings'), ('Data Import', 'Data Import')])
        self.assertIsNone(primary_for('Edit Profile'))

    def test_legacy_route_targets_are_preserved(self):
        for target in ('Overview','New Order','Order Management','Products','Customers','Payments',
                       'Production Board','Sales Analytics','Reports','Data Import','Settings','Notifications','Profile'):
            state={}
            navigate(state,target)
            self.assertEqual(state['nour_current_page'],'Order Management' if target=='New Order' else target)

    def test_remembers_child_per_primary(self):
        state={}
        navigate(state,'Payments')
        navigate_primary(state,'Analytics')
        navigate_primary(state,'Orders')
        self.assertEqual(state['nour_current_page'],'Payments')

    def test_settings_shortcut_opens_integrated_settings(self):
        state={}
        navigate(state,'Settings')
        self.assertEqual(state['nour_current_page'],'Settings')
        state={}
        navigate_primary(state,'Settings')
        self.assertEqual(state['nour_current_page'],'Settings')

    def test_notifications_and_back_preserve_context(self):
        state={}
        navigate(state,'Deadline Calendar')
        navigate(state,'Notifications')
        self.assertEqual(state['bizmar_last_primary'],'Orders')
        go_back(state)
        self.assertEqual(state['nour_current_page'],'Deadline Calendar')

    def test_back_without_history_defaults_dashboard(self):
        state={}
        go_back(state)
        self.assertEqual(state['nour_current_page'],'Overview')

    def test_same_target_does_not_duplicate_history(self):
        state={}
        navigate(state,'Customers');navigate(state,'Customers')
        self.assertEqual(state['nour_page_history'],['Overview'])

    def test_invalid_route_rejected(self):
        with self.assertRaises(ValueError):navigate({},'Not a page')

    def test_invalid_saved_state_recovered(self):
        state={'nour_current_page':'Missing','nour_page_history':None}
        initialize_navigation(state)
        self.assertEqual(state['nour_current_page'],'Overview')
        self.assertEqual(state['nour_page_history'],[])

    def test_route_primary_is_unambiguous(self):
        routes=[target for entries in PRIMARY_SECTIONS.values() for _,target in entries]
        self.assertEqual(len(routes),len(set(routes)))
        self.assertEqual(primary_for('Customers'),'Orders')
        self.assertEqual(primary_for('Long-Term Trends'),'Analytics')

    def test_retention_does_not_touch_auth_or_buttons(self):
        class RecordingState(dict):
            touched=[]
            def __setitem__(self,key,value):
                self.touched.append(key)
                super().__setitem__(key,value)
        state=RecordingState({'om_add_deadbeef_customer_name':'Synthetic', 'om_add_new':False,
                              'supabase_access_token':'synthetic-not-a-token', 'bizmar_calendar_date':'2026-01-01'})
        retain_widget_context(state)
        self.assertEqual(set(state.touched),{'om_add_deadbeef_customer_name','bizmar_calendar_date'})


UI = """
import streamlit as st
from navigation import render_primary_navigation,render_section_navigation,navigate,go_back
render_primary_navigation()
render_section_navigation()
page=st.session_state['nour_current_page']
st.text(page)
if page=='Order Management':
    st.text_input('Draft customer',key='om_add_deadbeef_customer_name')
if st.button('Bell',key='test_bell'):
    navigate(st.session_state,'Notifications');st.rerun()
if st.button('Back',key='test_back'):
    go_back(st.session_state);st.rerun()
"""


class NavigationUITests(unittest.TestCase):
    def test_sidebar_has_five_entries_and_correct_labels(self):
        app=AppTest.from_string(UI).run()
        self.assertFalse(app.exception)
        self.assertEqual([button.label for button in app.sidebar.button],list(PRIMARY_SECTIONS))

    def test_every_internal_section_can_be_selected(self):
        app=AppTest.from_string(UI).run()
        for index,primary in enumerate(PRIMARY_SECTIONS):
            app.button(key=f'nour_nav_PRIMARY_{index}').click().run()
            self.assertFalse(app.exception)
            if len(PRIMARY_SECTIONS[primary])>1:
                for label,route in PRIMARY_SECTIONS[primary]:
                    app.radio(key=f'bizmar_section_widget_{primary}').set_value(route).run()
                    self.assertFalse(app.exception)
                    self.assertEqual(app.session_state['nour_current_page'],route)

    def test_order_draft_survives_section_switch(self):
        app=AppTest.from_string(UI).run()
        app.button(key='nour_nav_PRIMARY_1').click().run()
        app.text_input(key='om_add_deadbeef_customer_name').set_value('Synthetic draft').run()
        app.button(key='nour_nav_PRIMARY_3').click().run()
        app.button(key='nour_nav_PRIMARY_1').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_input(key='om_add_deadbeef_customer_name').value,'Synthetic draft')

    def test_bell_and_back_return_to_section(self):
        app=AppTest.from_string(UI).run()
        app.button(key='nour_nav_PRIMARY_1').click().run()
        app.radio(key='bizmar_section_widget_Orders').set_value('Payments').run()
        app.button(key='test_bell').click().run()
        self.assertEqual(app.session_state['nour_current_page'],'Notifications')
        self.assertEqual(len(app.radio),0)
        app.button(key='test_back').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key='bizmar_section_widget_Orders').value,'Payments')


class SourceSafetyTests(unittest.TestCase):
    def setUp(self):
        self.source=(ROOT/'app.py').read_text(encoding='utf-8-sig')
        self.tree=ast.parse(self.source)

    def test_financial_and_business_renderers_unchanged(self):
        baseline=json.loads((ROOT/'tests/navigation_baseline.json').read_text())
        current={n.name:hashlib.sha256(ast.dump(n).encode()).hexdigest() for n in self.tree.body
                 if isinstance(n,ast.FunctionDef) and n.name in baseline}
        self.assertEqual(current,baseline)

    def test_every_route_has_a_dispatch_branch(self):
        routes=set()
        for node in ast.walk(self.tree):
            if isinstance(node,ast.Compare) and isinstance(node.left,ast.Name) and node.left.id=='page':
                for operator,value in zip(node.ops,node.comparators):
                    if isinstance(operator,ast.Eq) and isinstance(value,ast.Constant):routes.add(value.value)
                    elif isinstance(operator,ast.In) and isinstance(value,ast.Tuple):routes.update(v.value for v in value.elts if isinstance(v,ast.Constant))
        self.assertFalse(set(ROUTE_LABELS)-routes)

    def test_no_duplicate_notifications_or_logout_controls(self):
        self.assertEqual(self.source.count("key='nour_header_nav_notifications'"),1)
        self.assertEqual(self.source.count('key="sidebar_signout"'),1)
        self.assertNotIn('SIDEBAR_GROUPS',self.source)
        self.assertEqual(self.source.count("key='nour_header_nav_profile'"), 1)
        self.assertNotIn('nour_header_nav_settings',self.source)

    def test_approved_dashboard_kpis(self):
        calls=[node for node in ast.walk(self.tree) if isinstance(node,ast.Call)
               and isinstance(node.func,ast.Name) and node.func.id=='overview_stat']
        self.assertEqual([node.args[1].value for node in calls],
                         ['Total Orders','Total Revenue','Total Profits','Outstanding Balance'])
        first=ast.get_source_segment(self.source,calls[0])
        self.assertIn('total_orders',first)
        fourth=ast.get_source_segment(self.source,calls[3])
        self.assertIn("valid['balance'].sum()",fourth)
        self.assertIn("st.metric(tr('Total Customers'), len(customers))",self.source)

    def test_auth_gate_still_precedes_navigation(self):
        self.assertLess(self.source.index('if not authorized:'),self.source.index('render_primary_navigation()'))
        self.assertIn('(google_authorized or supabase_authorized)',self.source)
        self.assertIn('if not authorized:', self.source)

    def test_fr01_to_fr13_sources_still_reachable(self):
        required=['render_order_management()','render_customer_management()',
                  'render_payment_tracking()','render_deadline_calendar(orders)',"st.title(tr('Production Tracking'))",
                  'render_sales_analytics(d, owner_authorized=authorized)',"view='profitability'",'render_long_term_profitability(orders, items',
                  'render_repeat_customer_insights(orders, items, customers',
                  'render_production_alerts(orders, items, products, navigate_to)',
                  'alert_renderer=render_alert_settings','render_data_import()','render_import_cleanup()']
        for call in required:self.assertIn(call,self.source)
        self.assertEqual(self.source.count('migrated = import_supabase_records()'),1)


if __name__=='__main__':unittest.main()
