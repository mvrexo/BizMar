# Local Malaysia geography for Plotly

`world_110m.json` is a Malaysia-only TopoJSON background generated from the
existing `assets/malaysia_adm1.geojson` by `uat/build_map_topology.py`.
The filename is required by Plotly's geographic renderer; it does not contain
worldwide geometry. Plotly's hidden base layers still request this resource.

Source: geoBoundaries gbOpen Malaysia ADM1 (2017), OpenStreetMap/Wambacher,
ODbL 1.0, as documented with the original GeoJSON asset. No customer data.
Regenerate after changing that source; do not edit the generated arcs manually.
