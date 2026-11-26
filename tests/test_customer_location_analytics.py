import unittest
from datetime import date
import json
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest

from customer_location_analytics import (
    build_location_metrics,
    load_state_geojson,
    normalize_state,
    render_location_map,
)
from malaysian_states import STATES


class CustomerLocationAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.customers = pd.DataFrame([
            {'id': 1, 'state': ''},
            {'id': 2, 'state': 'Johor'},
            {'id': 3, 'state': 'invalid value'},
            {'id': 4, 'state': 'Sabah'},
        ])
        self.orders = pd.DataFrame([
            {'id': 11, 'customer_id': 1, 'ordered_at': '2026-10-27T02:00:00+08:00',
             'status': 'Pending', 'customer_state_snapshot': 'Perak'},
            {'id': 12, 'customer_id': 1, 'ordered_at': '2026-10-27T03:00:00+08:00',
             'status': 'Completed', 'customer_state_snapshot': 'Sabah'},
            {'id': 13, 'customer_id': 1, 'ordered_at': '2026-10-27T04:00:00+08:00',
             'status': 'Pending', 'customer_state_snapshot': 'Perak'},
            {'id': 21, 'customer_id': 2, 'ordered_at': '2026-10-27T05:00:00+08:00',
             'status': 'Pending', 'customer_state_snapshot': 'Sarawak'},
            {'id': 22, 'customer_id': 2, 'ordered_at': '2026-10-27T06:00:00+08:00',
             'status': 'Completed', 'customer_state_snapshot': 'Sarawak'},
            {'id': 31, 'customer_id': 3, 'ordered_at': '2026-10-27T07:00:00+08:00',
             'status': 'Pending', 'customer_state_snapshot': ''},
            {'id': 41, 'customer_id': 4, 'ordered_at': '2026-10-27T08:00:00+08:00',
             'status': 'Cancelled', 'customer_state_snapshot': 'Sabah'},
        ])

    def test_normalizes_common_state_names_and_rejects_unknown(self):
        self.assertEqual(normalize_state('  PENANG '), 'Pulau Pinang')
        self.assertEqual(normalize_state('Malacca'), 'Melaka')
        self.assertEqual(normalize_state('W.P. Kuala Lumpur'), 'Wilayah Persekutuan Kuala Lumpur')
        self.assertEqual(normalize_state('Federal Territory of Labuan'), 'Wilayah Persekutuan Labuan')
        self.assertIsNone(normalize_state('Somewhere'))
        self.assertIsNone(normalize_state(None))

    def test_unique_customer_assignment_unknowns_and_percentages(self):
        result = build_location_metrics(self.customers, self.orders)
        states = result['states'].set_index('state')
        self.assertEqual(result['known_customers'], 2)
        self.assertEqual(result['known_orders'], 5)
        self.assertEqual(result['unknown_customers'], 1)
        self.assertEqual(result['unknown_orders'], 1)
        self.assertEqual(result['total_customers'], 3)
        self.assertEqual(result['total_orders'], 6)
        self.assertEqual(states.loc['Perak', 'customer_count'], 1)
        self.assertEqual(states.loc['Johor', 'customer_count'], 1)
        self.assertEqual(states.loc['Perak', 'order_count'], 3)
        self.assertEqual(states.loc['Johor', 'order_count'], 2)
        self.assertEqual(states.loc['Perak', 'customer_percent'], 50.)
        self.assertEqual(states.loc['Johor', 'customer_percent'], 50.)
        self.assertEqual(states.loc['Perak', 'order_percent'], 60.)
        self.assertEqual(states.loc['Johor', 'order_percent'], 40.)
        self.assertEqual(len(result['states']), 16)

    def test_legacy_aliases_share_the_canonical_analytics_category(self):
        customers=pd.DataFrame([{'id':1,'state':'Penang'},{'id':2,'state':'Pulau Pinang'}])
        orders=pd.DataFrame([
            {'id':1,'customer_id':1,'ordered_at':'2026-10-27','status':'Pending','customer_state_snapshot':'Penang'},
            {'id':2,'customer_id':2,'ordered_at':'2026-10-27','status':'Pending','customer_state_snapshot':'Pulau Pinang'},
        ])
        states=build_location_metrics(customers,orders)['states']
        penang=states.loc[states.state.eq('Pulau Pinang')]
        self.assertEqual(len(states),16)
        self.assertEqual(len(penang),1)
        self.assertEqual(penang.iloc[0].customer_count,2)
        self.assertEqual(penang.iloc[0].order_count,2)

    def test_customer_state_profile_precedes_snapshot_and_snapshot_ties_are_stable(self):
        customers = pd.DataFrame([{'id': 1, 'state': 'Kuala Lumpur'},
                                  {'id': 5, 'state': ''}])
        orders = pd.DataFrame([
            {'id': 1, 'customer_id': 1, 'ordered_at': '2026-10-27',
             'status': 'Pending', 'customer_state_snapshot': 'Perak'},
            {'id': 2, 'customer_id': 5, 'ordered_at': '2026-10-27',
             'status': 'Pending', 'customer_state_snapshot': 'Sabah'},
            {'id': 3, 'customer_id': 5, 'ordered_at': '2026-10-27',
             'status': 'Pending', 'customer_state_snapshot': 'Perak'},
        ])
        states = build_location_metrics(customers, orders)['states'].set_index('state')
        self.assertEqual(states.loc['Wilayah Persekutuan Kuala Lumpur', 'customer_count'], 1)
        self.assertEqual(states.loc['Wilayah Persekutuan Kuala Lumpur', 'order_count'], 1)
        self.assertEqual(states.loc['Perak', 'customer_count'], 1)
        self.assertEqual(states.loc['Perak', 'order_count'], 2)

    def test_date_range_filters_customer_and_order_counts(self):
        orders = self.orders.copy()
        orders.loc[orders['id'].eq(13), 'ordered_at'] = '2026-10-28T04:00:00+08:00'
        result = build_location_metrics(
            self.customers, orders, date(2026, 10, 27), date(2026, 10, 27),
        )
        states = result['states'].set_index('state')
        self.assertEqual(result['known_customers'], 2)
        self.assertEqual(result['known_orders'], 4)
        self.assertEqual(states.loc['Perak', 'order_count'], 2)
        self.assertEqual(states.loc['Johor', 'order_count'], 2)
        self.assertEqual(result['unknown_orders'], 1)

    def test_geojson_contains_verified_polygons_for_all_states_and_territories(self):
        geojson = load_state_geojson()
        self.assertEqual(len(geojson['features']), 16)
        states = {feature['properties']['bizmarState'] for feature in geojson['features']}
        self.assertEqual(states, set(STATES))
        for state in ('Sabah', 'Sarawak', 'Wilayah Persekutuan Kuala Lumpur',
                      'Wilayah Persekutuan Putrajaya', 'Wilayah Persekutuan Labuan'):
            feature = next(item for item in geojson['features']
                           if item['properties']['bizmarState'] == state)
            self.assertIn(feature['geometry']['type'], ('Polygon', 'MultiPolygon'))
        for feature in geojson['features']:
            geometry=feature['geometry']
            polygons=[geometry['coordinates']] if geometry['type']=='Polygon' else geometry['coordinates']
            for polygon in polygons:
                for index,ring in enumerate(polygon):
                    area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]))
                    self.assertLess(area,0) if index==0 else self.assertGreater(area,0)

    def test_choropleth_is_rendered_for_all_regions_with_state_tooltips(self):
        metrics = build_location_metrics(self.customers, self.orders)
        source = (
            'from customer_location_analytics import render_location_map\n'
            f'metrics = {metrics!r}\n'
            "render_location_map(metrics, 'customer_count')\n"
        )
        # Build a JSON-safe frame instead of embedding Python's DataFrame repr.
        metrics_json = metrics['states'].to_json(orient='records')
        app = AppTest.from_string(
            'import json, pandas as pd\n'
            'from customer_location_analytics import render_location_map\n'
            f"metrics = {{'states': pd.DataFrame(json.loads({metrics_json!r}))}}\n"
            "render_location_map(metrics, 'customer_count')\n"
        ).run(timeout=30)
        self.assertFalse(app.exception, source)
        chart = json.loads(app.get('plotly_chart')[0].proto.spec)
        self.assertEqual(len(chart['data'][0]['locations']), 16)
        self.assertEqual(chart['data'][0]['type'], 'choropleth')
        self.assertIn('Customers:', chart['data'][0]['hovertemplate'])
        self.assertIn('Share of known locations', chart['data'][0]['hovertemplate'])
        self.assertEqual(chart['layout']['geo']['projection']['type'], 'mercator')
        self.assertFalse(chart['layout']['geo']['fitbounds'])
        self.assertEqual(chart['layout']['geo']['center'],dict(lon=109.5,lat=4.0))
        self.assertEqual(chart['layout']['geo']['lonaxis']['range'],[99.0,120.0])
        self.assertEqual(chart['layout']['height'], 470)
        self.assertIn('app/static/maps/', app.get('plotly_chart')[0].proto.config)

    def test_empty_and_unknown_only_maps_show_message_without_chart(self):
        for customers, orders in (([], []), ([{'id':1,'state':'Unknown'}],[{'id':1,'customer_id':1}])):
            for metric in ('customer_count','order_count'):
                with self.subTest(metric=metric,empty=not orders), patch('customer_location_analytics.st.info') as message, patch('customer_location_analytics.st.plotly_chart') as chart:
                    render_location_map(build_location_metrics(customers,orders),metric)
                    message.assert_called_once_with('No geographical data available')
                    chart.assert_not_called()

    def test_map_uses_normalized_locations_and_distinct_customer_order_counts(self):
        metrics=build_location_metrics(self.customers,self.orders)
        metrics['states'].loc[metrics['states']['state'].eq('Pulau Pinang'),'state']='Penang'
        for metric in ('customer_count','order_count'):
            with patch('customer_location_analytics.st.plotly_chart') as chart:
                render_location_map(metrics,metric)
                figure=chart.call_args.args[0]
                trace=figure.data[0]
                self.assertIn('Pulau Pinang',trace.locations)
                self.assertNotIn('Penang',trace.locations)
                self.assertEqual(sum(trace.z),metrics['known_customers' if metric=='customer_count' else 'known_orders'])
                self.assertEqual(chart.call_args.kwargs['config']['topojsonURL'],'./app/static/maps/')

    def test_invalid_geojson_geometry_is_rejected(self):
        import copy
        import customer_location_analytics as module
        valid=load_state_geojson()
        for coordinates in ([],[[[100,3],[101,4],[102,3]]],[[[100,3],[101,4],[999,3],[100,3]]]):
            broken=copy.deepcopy(valid)
            broken['features'][0]['geometry']={'type':'Polygon','coordinates':coordinates}
            with patch.object(module.json,'load',return_value=broken):
                with self.assertRaises(ValueError):
                    module.load_state_geojson.__wrapped__()

    def test_bundled_plotly_topology_contains_all_regions_and_valid_arcs(self):
        path=Path(__file__).resolve().parents[1]/'static/maps/world_110m.json'
        topology=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(topology['type'],'Topology')
        features=topology['objects']['countries']['geometries']
        self.assertEqual(len(features),16)
        self.assertEqual({normalize_state(f['properties']['shapeName']) for f in features},set(STATES))
        for feature in features:
            for polygon in feature['arcs']:
                for ring in polygon:
                    arc=topology['arcs'][ring[0]]
                    self.assertGreaterEqual(len(arc),4)
                    self.assertEqual(arc[0],arc[-1])


if __name__ == '__main__':
    unittest.main()
