# BizMar local typography

Inter (400, 500, 600, 700): body, labels, KPI values, tables, chart labels and tooltips.
Plus Jakarta Sans (500, 600, 700): headings, navigation and buttons.
Poppins (400, 600): shared dashboard page-header titles and dates.

Files were obtained from the existing official Google Fonts CSS endpoint using
`uat/bundle_typography_fonts.py`. Original sources and SHA256 checksums are in
`manifest.json`. All three families' SIL Open Font License texts are included.

`bizmar-fonts.css` is served by the existing Streamlit static server. The main
document and WhatsApp component load this same local stylesheet; no runtime
Google Fonts request is required. Font files are presentation assets, not secrets.
