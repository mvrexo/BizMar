# Overview KPI sparklines

The existing four cards retain their order, icons, values, descriptions, typography
and theme backgrounds. A 48px smooth line with transparent area fill now occupies
the bottom of each card. Desktop cards stretch equally; mobile cards stack using
the existing responsive grid.

## Data and safety

`kpi_sparklines.daily_kpi_trends` consumes the already-filtered order dataframe
and saved order-item snapshots loaded from the existing SQLite database. It makes
no database queries or writes. Streamlit's bounded content-keyed cache includes
the dataframe, raw item costs and selected boundaries, so changed records and
date ranges invalidate the calculation. Existing fetch/refresh behavior remains.

- Orders: daily counts of non-cancelled orders, by Malaysia order date.
- Revenue: the existing `load()` revenue values grouped by Malaysia order date.
  This includes Pending/Unpaid orders under the existing dashboard definition;
  it is not a payment-verification or cash-receipts metric.
- Profit: the existing revenue-minus-recorded-cost values, using saved item cost
  snapshots rather than current product prices. Missing saved costs produce
  `Trend unavailable` instead of silently assuming zero cost.
- Outstanding balance: `Trend unavailable`. Current totals and audit summaries
  do not provide complete immutable historical order-total, cancellation and
  payment-reversal events. Subtracting today's payments from old order dates
  would invent historical balances. The current KPI value remains unchanged.

Empty periods and single-day selections use a neutral `Not enough data` state.
Missing dates cannot be fabricated. Days without orders inside a valid multi-day
period are zero-filled. Curves pass through daily values with monotone cubic
interpolation, avoiding artificial peaks. Negative profit remains supported.

Inline SVG is used inside the existing HTML cards. Embedding separate Plotly
components would split the cards and introduce additional layout containers;
these tiny noninteractive charts need no Plotly toolbar, axes or chart runtime.
SVG has a transparent background and a descriptive accessible label. There are
no new dependencies or business formula changes.

## Modified files

- `app.py`: calculate one shared trend set and add it to existing card markup.
- `kpi_sparklines.py`: cached daily calculations and compact SVG rendering.
- `styles/kpi_sparklines.css`: scoped 48px layout and palette tokens.
- `ui_theme.py`: load the scoped stylesheet.
- `styles/dark.css`: four readable dark-theme sparkline color tokens.
- `uat/dashboard_layout_preview.py`: keep the isolated dashboard preview aligned.
- `tests/test_kpi_sparklines.py`: calculation and SQLite snapshot regressions.
- `tests/kpi_sparkline_fixture.py`, `tests/check_kpi_sparklines_browser.py`:
  visual validation using the actual dashboard card renderer and sample data.

## Validation

- Seven focused tests passed: daily totals, timezone/date boundaries, leap day,
  year rollover, empty/single-day data, missing costs, cache invalidation,
  SQLite snapshots, rendering and unavailable states.
- Existing dashboard analytics tests: 15 passed.
- Existing navigation/business-renderer baseline tests: 22 passed.
- Browser checks: all 16 passed (light/dark × desktop/mobile × historical,
  empty, single-day and shorter-range data). Checked original KPI values, equal
  card heights, 48px charts and no horizontal overflow. Screenshots are in
  `uat/kpi-sparklines/`.

No production test orders, database changes, schema migrations, authentication
changes or Google Sheets synchronization changes were made.
