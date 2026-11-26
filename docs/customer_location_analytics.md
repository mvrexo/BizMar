# Customer Location Analytics

The Overview location section reads the existing SQLite customer `state` and
order `customer_state_snapshot` fields. It never writes to the database or
infers a state from a street address, phone number, or delivery destination.

The Dashboard date selector applies to qualifying orders; cancelled orders are
excluded. **By Customers** counts each customer once. **By Orders** counts
non-cancelled orders associated with each assigned customer state. Percentages
exclude records whose state is unknown: unique known-location customers in
customer mode, and known-location orders in order mode. Unknown customers and
orders are shown separately.

For customers with multiple state values, the current customer profile state
takes precedence. If it is blank or invalid, the most frequent valid
`customer_state_snapshot` among that customer's qualifying orders is used;
ties are resolved alphabetically. The same assigned state is used for all
orders in **By Orders** mode. Delivery-state snapshots are intentionally not
used as customer residence.

The choropleth uses the simplified Malaysia ADM1 GeoJSON from
[geoBoundaries gbOpen](https://www.geoboundaries.org/), boundary year 2017,
derived from OpenStreetMap/Wambacher under the Open Data Commons Open Database
License 1.0. The bundled boundary file contains all 16 Malaysian states and
federal territories, including Sabah and Sarawak. It is geometry data only;
all displayed counts come from the business database.
