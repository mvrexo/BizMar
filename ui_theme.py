"""BizMar shared Matcha Strawberry Liquid Glass presentation.

Only CSS is injected: widgets, routing, state and business operations stay native.
Use the public CSS variables and nour-* classes for future page work. Solid
surfaces are the baseline; supported browsers progressively add backdrop blur.
"""
import streamlit as st
from pathlib import Path

STYLE = r"""
@import url('./app/static/fonts/bizmar-fonts.css');

:root {
  color-scheme: light;
  --nour-cream: #fffaf3;
  --nour-matcha: #dce9cb;
  --nour-matcha-strong: #426536;
  --nour-strawberry: #f8dce2;
  --nour-strawberry-strong: #98415a;
  --nour-lavender: #e4d9f2;
  --nour-lavender-strong: #654880;
  --nour-ink: #302f35;
  --nour-muted: #655e6c;
  --nour-line: #dfd5df;
  --nour-surface: #fffcf8;
  --nour-glass: rgba(255, 252, 248, .88);
  --nour-shadow: 0 10px 28px rgba(80, 62, 75, .09);
  --nour-reflection: inset 0 1px 0 rgba(255,255,255,.95);
  --nour-radius-sm: 12px;
  --nour-radius: 20px;
  --nour-radius-lg: 28px;
  --nour-space-1: .25rem;
  --nour-space-2: .5rem;
  --nour-space-3: .75rem;
  --nour-space-4: 1rem;
  --nour-space-6: 1.5rem;
  --nour-space-8: 2rem;
  --nour-body-font: 'Inter', 'Segoe UI', Arial, sans-serif;
  --nour-heading-font: 'Plus Jakarta Sans', 'Segoe UI', Arial, sans-serif;
  /* Compatibility aliases used by the previous theme. */
  --ink: var(--nour-ink); --muted: var(--nour-muted);
  --lav: var(--nour-lavender); --pink: var(--nour-strawberry);
  --mint: var(--nour-matcha); --peach: #fff0df;
}
html, body, [data-testid="stApp"] {
  font-family: var(--nour-body-font);
  color: var(--nour-ink);
}
[data-testid="stApp"] { background: var(--nour-cream); color-scheme: light; }
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(ellipse at 92% 8%, #f7dfe7 0, transparent 40%),
    radial-gradient(ellipse at 15% 85%, #e4edda 0, transparent 42%),
    var(--nour-cream);
}
[data-testid="stMainBlockContainer"] { padding-top: 1.75rem; max-width: 1350px; }
[data-testid="stMarkdownContainer"], input, textarea, button, select,
[data-baseweb="select"] { font-family: var(--nour-body-font); }
h1, h2, h3, h4, .nour-welcome, .nour-section-title {
  font-family: var(--nour-heading-font) !important;
  color: var(--nour-ink) !important;
  font-weight: 600 !important;
  letter-spacing: -.025em;
}
[data-testid="stCaptionContainer"] { color: var(--nour-muted); }
[data-testid="stWidgetLabel"] { color: var(--nour-ink); font-weight: 700; }
[data-testid="stMarkdownContainer"] a { color: var(--nour-matcha-strong); text-underline-offset: 3px; }

/* Preserve native sidebar positioning and collapse behavior. */
section[data-testid="stSidebar"] {
  background: linear-gradient(155deg, #eee5f7, #d9c9ec 65%, #e6d7eb) !important;
  border: 1px solid #f7f1fc !important;
  border-radius: 0 var(--nour-radius-lg) var(--nour-radius-lg) 0;
  box-shadow: 8px 0 30px rgba(87,64,108,.10), var(--nour-reflection);
}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding: 20px 12px; }
section[data-testid="stSidebar"] .nour-menu-caption {
  color: var(--nour-lavender-strong); font-weight: 800;
  letter-spacing: .14em; font-size: .75rem; margin: 20px 10px 10px;
}
section[data-testid="stSidebar"] [class*="st-key-nour_nav_"] button {
  border: 1px solid transparent !important;
  background: transparent !important;
  color: #513c66 !important;
  border-radius: 16px !important;
  min-height: 44px !important;
  padding: 10px 14px !important;
  font-size: .875rem !important;
  font-weight: 800 !important;
  justify-content: flex-start !important;
  text-align: left !important;
  box-shadow: none !important;
}
section[data-testid="stSidebar"] [class*="st-key-nour_nav_"] button:hover {
  background: #eee4f7 !important;
}
section[data-testid="stSidebar"] [class*="st-key-nour_nav_"] button[kind="primary"] {
  background: linear-gradient(160deg, #fffdf9, #f5edf8) !important;
  color: #513c66 !important;
  border-color: #fffcff !important;
  box-shadow: 0 5px 12px #73569322, var(--nour-reflection) !important;
}
section[data-testid="stSidebar"] .st-key-sidebar_signout button {
  background: #174C35 !important;
  color: #FFFFFF !important;
  border-color: #174C35 !important;
}
section[data-testid="stSidebar"] .st-key-sidebar_signout button p { color: inherit !important; }
section[data-testid="stSidebar"] .st-key-sidebar_signout button:hover { background: #103D2C !important; color: #FFFFFF !important; }
section[data-testid="stSidebar"] .nour-sidebar-tagline { color: #513c66 !important; }

/* Shared surfaces: these also work as classes for later page composition. */
.nour-glass, .nour-card, .nour-stat, .nour-hero,
[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stVerticalBlock"][data-border="true"],
[data-testid="stMetric"], [data-testid="stForm"] {
  background: var(--nour-surface);
  border: 1px solid var(--nour-line);
  border-radius: var(--nour-radius);
  box-shadow: var(--nour-shadow), var(--nour-reflection);
}
.nour-card { padding: var(--nour-space-6); }
[data-testid="stMetric"] { padding: 1.125rem; }
[data-testid="stMetricLabel"] { color: var(--nour-muted); }
[data-testid="stMetricValue"] { color: var(--nour-ink); font-weight: 800; }
.nour-stack { display: flex; flex-direction: column; gap: var(--nour-space-4); }
.nour-muted { color: var(--nour-muted); }

/* Gloss stays inside the surface; no overlays intercept widget clicks. */
.stButton > button, .stDownloadButton > button,
[data-testid="stFormSubmitButton"] > button {
  background: linear-gradient(175deg, #fffefb 0%, #f6edea 100%);
  color: var(--nour-ink);
  border: 1px solid #d9ced7;
  border-radius: 16px !important;
  min-height: 44px;
  font-weight: 800 !important;
  box-shadow: inset 0 2px 1px #ffffff, inset 0 -2px 2px #a68b9b12,
              0 4px 9px #60485814;
  transition: transform .16s ease, box-shadow .16s ease;
}
button[kind="primary"], button[data-testid="stBaseButton-primary"],
button[data-testid="stBaseButton-primaryFormSubmit"] {
  background: linear-gradient(175deg, #edf5e2, #d1e2bd) !important;
  color: #304d28 !important;
  border-color: #a8bf96 !important;
}
.stButton > button p, .stDownloadButton > button p,
[data-testid="stFormSubmitButton"] > button p { color: inherit; }
@media (hover: hover) {
  .stButton > button:not(:disabled):hover,
  .stDownloadButton > button:not(:disabled):hover,
  [data-testid="stFormSubmitButton"] > button:not(:disabled):hover {
    transform: translateY(-1px);
    box-shadow: var(--nour-reflection), 0 7px 16px #60485822;
    border-color: var(--nour-matcha-strong);
  }
}
.stButton > button:not(:disabled):active,
[data-testid="stFormSubmitButton"] > button:not(:disabled):active { transform: translateY(1px); }
button:disabled { opacity: .6; cursor: not-allowed; }
[data-testid="stApp"] :is(button, a, input, textarea, select, [role="tab"], [role="checkbox"], [role="radio"], [role="switch"]):focus-visible {
  outline: 3px solid var(--nour-matcha-strong) !important;
  outline-offset: 3px;
}

/* Opaque field backgrounds keep entered text legible over glass. */
[data-testid="stTextInput"] [data-baseweb="input"],
[data-testid="stNumberInput"] [data-baseweb="input"],
[data-testid="stTextArea"] [data-baseweb="textarea"],
[data-baseweb="select"] > div,
[data-testid="stDateInput"] [data-baseweb="input"],
[data-testid="stTimeInput"] [data-baseweb="input"] {
  background: #fffdf9 !important;
  color: var(--nour-ink);
  border-radius: var(--nour-radius-sm) !important;
  border-color: #bbaeBC !important;
  box-shadow: inset 0 2px 4px #60485808;
}
[data-testid="stApp"] input, [data-testid="stApp"] textarea {
  color: var(--nour-ink); caret-color: var(--nour-matcha-strong);
}
[data-testid="stApp"] input::placeholder,
[data-testid="stApp"] textarea::placeholder { color: #746b76; opacity: 1; }
[data-testid="stFileUploaderDropzone"] {
  background: #f6f4ec; border: 1px dashed #8c9c80; border-radius: 16px;
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
  gap: .5rem; background: #f3ecef; border-radius: 16px; padding: .375rem;
}
[data-testid="stTabs"] [role="tab"] {
  min-height: 44px; padding: .5rem 1rem; color: #594d61; border-radius: 12px;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
  background: #fffdf9; color: #38572d; box-shadow: 0 3px 8px #60485812;
}
[data-testid="stExpander"] { border-radius: 16px; border-color: var(--nour-line); }
[data-testid="stExpander"] summary { min-height: 44px; }
[data-testid="stAlert"] { border-radius: 16px; }
[data-testid="stDataFrame"], [data-testid="stTable"] {
  border: 1px solid var(--nour-line); border-radius: 16px;
  background: #fffdf9; overflow: hidden;
}
[data-testid="stTable"] table { width: 100%; border-collapse: collapse; }
[data-testid="stTable"] th { background: #edf2e5; color: #354b2f; }
[data-testid="stTable"] td, [data-testid="stTable"] th { padding: .75rem; border-color: #e6dfe5; }
[data-testid="stPlotlyChart"], .nour-chart {
  border-radius: 16px; background: #fffdf9; padding: .5rem;
  border: 1px solid #eee5e8;
}

/* Existing app.py class contract, retained for visual compatibility. */
.nour-welcome { font-size: 1.5rem; }
.nour-section-title { font-size: 1.2rem; margin: 24px 0 12px; }
.nour-section-title span { font-family: var(--nour-body-font); font-size: .8rem; color: var(--nour-muted); font-weight: 600; margin-left: 9px; }
.nour-hero {
  min-height: 196px; display: flex; align-items: center; justify-content: space-between;
  gap: 16px; padding: 26px 34px; margin: 14px 0 22px; overflow: hidden;
  border-radius: var(--nour-radius-lg);
  background: linear-gradient(120deg, #fbe7e8, #f5eceb 55%, #e7eedc);
}
.nour-hero-copy { max-width: 75%; position: relative; z-index: 1; }
.nour-hero-kicker { font-size: .75rem; font-weight: 900; letter-spacing: .12em; color: #874052; }
.nour-hero h2 { font-size: clamp(22px, 2.8vw, 35px); margin: 8px 0; }
.nour-hero p { color: #65505b; margin: 0 0 14px; font-size: .9375rem; }
.nour-hero-pill, .nour-badge {
  display: inline-block; border-radius: 99px; padding: 6px 13px;
  background: #fffaf5; color: #704252; font-size: .75rem; font-weight: 800;
  border: 1px solid #e5d4d9;
}
.nour-stat { padding: 20px; min-height: 133px; border-radius: 22px; }
.nour-stat-lavender { background: linear-gradient(145deg, #f8f3fc, #e9dff3); }
.nour-stat-pink { background: linear-gradient(145deg, #fff3f3, #f7dce3); }
.nour-stat-mint { background: linear-gradient(145deg, #f3f7ec, #dde9cf); }
.nour-stat-peach { background: linear-gradient(145deg, #fff8ec, #f9e9d4); }
.nour-stat-label { font-size: .8125rem; font-weight: 800; color: #5c5260; }
.nour-stat-value { font-size: clamp(20px, 2vw, 30px); font-weight: 900; color: var(--nour-ink); margin: 12px 0 5px; overflow-wrap: anywhere; }
.nour-stat-foot { font-size: .75rem; font-weight: 700; color: #6b5364; }
.nour-task, .nour-customer { display: flex; justify-content: space-between; align-items: center; gap: 10px; border-bottom: 1px solid #e8dfe5; padding: 12px 0; }
.nour-task strong { display: block; font-size: .875rem; color: var(--nour-ink); }
.nour-task small { display: block; color: var(--nour-muted); font-size: .75rem; margin-top: 3px; }
.nour-task span { background: #f8e4e9; color: #853d53; border-radius: 99px; font-size: .75rem; padding: 5px 9px; }
.nour-customer { font-size: .875rem; }
.nour-customer strong { color: #654880; }
.nour-product-placeholder { background: linear-gradient(135deg, #f6e7ec, #e9efdf); border-radius: 16px; }
.nour-cupcake { width: 115px; height: 140px; position: relative; flex: none; filter: drop-shadow(0 12px 10px #b985a333); }
.nour-cherry { position: absolute; width: 25px; height: 25px; border-radius: 50%; background: #da829b; left: 45px; top: 3px; z-index: 3; box-shadow: inset -5px -4px 0 #bd5877; }
.nour-frosting { position: absolute; width: 105px; height: 83px; top: 26px; left: 5px; background: #fff9f0; border-radius: 60% 60% 35% 35%; text-align: center; font-size: 54px; line-height: 88px; color: #cb819e; box-shadow: inset -12px -6px 0 #e9dfe8; }
.nour-cupcake-base { position: absolute; bottom: 0; left: 17px; width: 82px; height: 59px; background: repeating-linear-gradient(90deg, #b7cca2 0, #b7cca2 10px, #9eb78a 10px, #9eb78a 18px); clip-path: polygon(0 0,100% 0,86% 100%,14% 100%); border-radius: 6px; }

/* Keep Streamlit's icon glyphs outside our typography overrides. */
[data-testid="stIconMaterial"], [data-testid="stIconMaterial"] *,
span[class*="material-symbols"], .material-symbols-rounded, .material-symbols-outlined {
  font-family: 'Material Symbols Rounded', 'Material Symbols Outlined' !important;
  font-feature-settings: 'liga' !important; font-weight: normal !important;
  letter-spacing: normal !important; line-height: 1 !important;
}
@supports ((backdrop-filter: blur(16px)) or (-webkit-backdrop-filter: blur(16px))) {
  .nour-glass, .nour-card,
  [data-testid="stVerticalBlockBorderWrapper"],
  [data-testid="stVerticalBlock"][data-border="true"],
  [data-testid="stMetric"], [data-testid="stForm"] {
    background: var(--nour-glass);
    -webkit-backdrop-filter: blur(16px) saturate(115%);
    backdrop-filter: blur(16px) saturate(115%);
  }
}
@media (min-width: 1000px) {
  section[data-testid="stSidebar"] { margin: 12px 0 12px 12px; border-radius: 26px; }
}
@media (max-width: 900px) {
  [data-testid="stMainBlockContainer"] { padding-left: 1rem; padding-right: 1rem; }
  .nour-hero { padding: 20px; }
  .nour-stat { min-height: 110px; padding: 16px; }
}
@media (max-width: 600px) {
  .nour-hero { padding: 18px; min-height: auto; }
  .nour-cupcake { display: none; }
  .nour-hero-copy { max-width: 100%; }
  .nour-section-title span { display: block; margin: 6px 0 0; }
  .nour-task, .nour-customer { flex-wrap: wrap; }
  .nour-card { padding: 16px; }
}
@media (prefers-reduced-motion: reduce) {
  [data-testid="stApp"] *, [data-testid="stApp"] *::before, [data-testid="stApp"] *::after {
    animation: none !important; transition: none !important; scroll-behavior: auto !important;
  }
  .stButton > button:hover, .stButton > button:active,
  .stDownloadButton > button:hover,
  [data-testid="stFormSubmitButton"] > button:hover,
  [data-testid="stFormSubmitButton"] > button:active { transform: none !important; }
}
@media (prefers-reduced-transparency: reduce) {
  .nour-glass, .nour-card, [data-testid="stVerticalBlockBorderWrapper"],
  [data-testid="stVerticalBlock"][data-border="true"],
  [data-testid="stMetric"], [data-testid="stForm"] {
    background: var(--nour-surface) !important;
    -webkit-backdrop-filter: none !important; backdrop-filter: none !important;
  }
}
@media (forced-colors: active) {
  .nour-glass, .nour-card, .nour-stat, .nour-hero,
  [data-testid="stMetric"], [data-testid="stForm"] {
    background: Canvas !important; color: CanvasText !important;
    border: 1px solid CanvasText; box-shadow: none;
  }
}
/* Phase 3: application shell only. Native widgets own every interaction. */
[data-testid="stMainBlockContainer"] {
  max-width: 1400px;
  /* Leave room for Streamlit's fixed header and Deploy toolbar. */
  padding: 4.5rem clamp(1rem, 2vw, 2rem) 2rem;
}
section[data-testid="stSidebar"] {
  width: 238px !important;
  min-width: 0 !important;
}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
  padding: 12px 10px !important;
}
section[data-testid="stSidebar"] [data-testid="stImage"] img {
  max-height: 68px; object-fit: contain;
}
.nour-sidebar-brand {
  font-family: var(--nour-heading-font);
  text-align: center; font-size: 1.2rem; font-weight: 600; color: #513c66;
}
section[data-testid="stSidebar"] .nour-sidebar-tagline {
  text-align: center; font-size: .75rem; line-height: 1.4; margin: 3px 0 8px;
}
section[data-testid="stSidebar"] .nour-menu-caption {
  margin: 10px 12px 4px; font-size: .6875rem; letter-spacing: .16em;
}
section[data-testid="stSidebar"] [class*="st-key-nour_nav_"] button {
  width: 100%; gap: .65rem; line-height: 1.35 !important;
  white-space: normal !important;
}
section[data-testid="stSidebar"] [class*="st-key-nour_nav_"] button[kind="primary"] {
  border-left: 4px solid #806294 !important;
  background: linear-gradient(155deg, #fffdf9, #f5eaf4 65%, #e8eddf) !important;
}
.nour-workspace-label {
  text-align: center; color: #655271; font-size: .75rem; padding-top: 8px;
}
.st-key-nour_shell_owner {
  background: #f5eef9; border: 1px solid #fffafa;
  border-radius: 16px; padding: 10px; margin-top: 8px;
  box-shadow: var(--nour-reflection), 0 5px 16px #6048580d;
}
.nour-owner-name { font-weight: 900; color: #513c66; overflow-wrap: anywhere; }
.nour-owner-role { font-size: .75rem; color: #655271; }

.nour-header-eyebrow {
  color: var(--nour-matcha-strong); font-size: .6875rem;
  font-weight: 900; letter-spacing: .15em; margin-bottom: 6px;
}


.st-key-bizmar_settings [data-testid="stForm"] {
  border: 1px solid #e4e9df; border-radius: 20px; padding: 24px;
  background: #ffffffd9; box-shadow: 0 5px 20px #174c3508;
}
.st-key-bizmar_settings [role="tablist"] { gap: .4rem; overflow-x: auto; }
.st-key-bizmar_settings [role="tab"] { white-space: nowrap; padding: .7rem; }
.st-key-bizmar_settings [role="tab"][aria-selected="true"] { color: #174c35; background: #edf3e9; border-radius: 12px 12px 0 0; }
.st-key-nour_shell_actions {
  --header-action-size: 52px;
  display: flex; flex-direction: row; flex-wrap: wrap; gap: .5rem;
}
.st-key-nour_shell_actions > [data-testid="stElementContainer"] { width: auto; flex: 0 1 auto; }
[class*="st-key-nour_header_nav_"] button {
  background: linear-gradient(165deg, #fffdfa, #efe7f4);
  border-color: #d9cde2; color: #513c66;
}
.st-key-nour_header_nav_notifications button {
  background: linear-gradient(165deg, #fff9f8, #f8e1e7);
}
.st-key-nour_header_nav_profile button {
  background: linear-gradient(165deg, #fbfff6, #e4edd9);
}
@supports ((backdrop-filter: blur(16px)) or (-webkit-backdrop-filter: blur(16px))) {
  section[data-testid="stSidebar"] {
    background: linear-gradient(155deg, #eee5f7ee, #d9c9ecee 65%, #e6d7ebee) !important;
    -webkit-backdrop-filter: blur(18px); backdrop-filter: blur(18px);
  }

}
@media (max-width: 600px) {
  [data-testid="stMainBlockContainer"] { padding: 4.5rem .875rem 2rem; }
  section[data-testid="stSidebar"] { max-width: calc(100vw - 48px); }

  .st-key-nour_shell_actions > [data-testid="stElementContainer"] { flex: 1 1 120px; }
  [class*="st-key-nour_header_nav_"] button { width: 100%; }
}
@media (prefers-reduced-transparency: reduce) {
  section[data-testid="stSidebar"] {
    background: #e4d9f2 !important;
    -webkit-backdrop-filter: none !important; backdrop-filter: none !important;
  }

}
@media (forced-colors: active) {
  section[data-testid="stSidebar"], .st-key-nour_shell_owner {
    background: Canvas !important; color: CanvasText !important;
    border: 1px solid CanvasText; box-shadow: none;
  }
}

/* Phase 4: Overview only; other page compositions retain their styles. */
.st-key-nour_overview {
  --overview-matcha: #9BB89A;
  --overview-deep-matcha: #526F5A;
  --overview-strawberry: #F4B6C2;
  --overview-lavender: #D9C7F0;
  --overview-cream: #FFF9F3;
}
.st-key-nour_overview .nourish-overview-hero {
  min-height: 160px; padding: 18px 24px;
  margin: 0 0 8px; border: 1px solid #f5d5dd;
  background: linear-gradient(130deg, #fff3f2f5, #f8dce5ee 65%, #e8e3f1ed);
  box-shadow: inset 0 2px 0 #ffffff, inset 0 -2px 10px #e8adc222,
              0 15px 32px #a06c7e15;
}
.st-key-nour_overview .nour-hero-copy { max-width: 78%; }
.st-key-nour_overview .nour-hero h2 {
  max-width: 650px; font-size: clamp(1.3rem, 2.3vw, 1.8rem);
  line-height: 1.25; margin: 7px 0;
}
.st-key-nour_overview .nour-hero p { max-width: 560px; line-height: 1.5; font-size: .875rem; margin-bottom: 8px; }
.st-key-nour_overview .nour-hero-kicker { font-size: .6875rem; line-height: 1.7; }
.st-key-nour_overview .nour-cupcake { margin: 0 8px; transform: rotate(7deg); }
.st-key-nour_overview .nour-frosting {
  background: radial-gradient(ellipse at 32% 20%, #ffffff 0, #fff3f3 40%, #f2c7d5 90%);
  box-shadow: inset -9px -7px 12px #c97f9a33, inset 3px 3px 4px #ffffff;
}
.st-key-nour_overview .nour-section-title { margin: 6px 0 10px; }
.st-key-nour_overview_kpis .nour-stat {
  min-height: 138px; padding: 16px; border: 1px solid #ffffff;
  box-shadow: inset 0 2px 1px #ffffffdd, inset 0 -3px 6px #a4899c0b,
              0 8px 24px #70546812;
}
.st-key-nour_overview_kpis .nour-stat-value {
  font-size: clamp(1.35rem, 2vw, 1.8rem); margin: 9px 0 5px; line-height: 1.25;
  font-variant-numeric: tabular-nums;
}
.nour-stat-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.nour-stat-icon {
  display: inline-flex; align-items: center; justify-content: center;
  width: 40px; height: 40px; flex-shrink: 0; font-size: 24px;
  border-radius: 14px; background: #fffaf6aa; border: 1px solid #fffdf4;
  box-shadow: inset 0 2px 0 #ffffff, 0 5px 9px #75556916;
}
.st-key-nour_overview [class*="st-key-nour_overview_"] h4 {
  font-size: 1rem; line-height: 1.5; margin-bottom: 14px;
}
.st-key-nour_overview_activity, .st-key-nour_overview_insights { margin-bottom: 12px; }
.st-key-nour_overview_sales, .st-key-nour_overview_orders,
.st-key-nour_overview_products, .st-key-nour_overview_customers {
  padding: clamp(14px, 1.5vw, 20px) !important;
  border-radius: 24px !important; border-color: #e8dde3 !important;
}
.st-key-nour_overview_orders, .st-key-nour_overview_sales { min-height: 390px; }
.st-key-nour_overview_products, .st-key-nour_overview_customers { min-height: 340px; }
.st-key-nour_overview .nour-task {
  padding: 14px; margin-bottom: 10px; border: 1px solid #eee4e9;
  border-radius: 16px; background: #fffbf7; align-items: flex-start;
}
.st-key-nour_overview .nour-task > div { min-width: 0; flex: 1 1 150px; overflow-wrap: anywhere; }
.st-key-nour_overview .nour-task small { margin-top: 6px; line-height: 1.6; }
.st-key-nour_overview .nour-task > span { flex: 0 0 auto; }
.st-key-nour_overview .nour-task-overdue {
  background: #fff0f2; border-color: #db9cad; border-left: 4px solid #a44760;
}
.st-key-nour_overview .nour-task-overdue small { color: #923b53; font-weight: 800; }
.st-key-nour_overview .nour-status-pending { background: #f5e9d5; color: #73542d; }
.st-key-nour_overview .nour-status-confirmed { background: #eaddf6; color: #62467c; }
.st-key-nour_overview .nour-status-preparing { background: #f8dce5; color: #873c53; }
.st-key-nour_overview .nour-status-ready { background: #e0ecd8; color: #3e5f34; }
.st-key-nour_overview .nour-customer {
  padding: 15px 0; gap: 12px; align-items: baseline; overflow-wrap: anywhere;
}
.st-key-nour_overview .nour-customer > span { min-width: 0; }
.st-key-nour_overview .nour-customer strong { color: #526F5A; font-variant-numeric: tabular-nums; }
.nour-customer-rank { color: #755684; font-weight: 900; margin-right: 8px; }
@supports ((backdrop-filter: blur(16px)) or (-webkit-backdrop-filter: blur(16px))) {
  .st-key-nour_overview .nourish-overview-hero {
    -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px);
  }
}
/* Only the Overview's three layout rows change at these breakpoints. */
@media (max-width: 1100px) {
  .st-key-nour_overview_kpis [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  .st-key-nour_overview_kpis [data-testid="stColumn"] {
    width: calc(50% - .5rem) !important; flex: 1 1 calc(50% - .5rem) !important;
    min-width: 0 !important;
  }
  .st-key-nour_overview_activity [data-testid="stHorizontalBlock"],
  .st-key-nour_overview_insights [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  .st-key-nour_overview_activity [data-testid="stColumn"],
  .st-key-nour_overview_insights [data-testid="stColumn"] {
    width: 100% !important; flex: 1 1 100% !important; min-width: 0 !important;
  }
}
@media (max-width: 600px) {
  .st-key-nour_overview_kpis [data-testid="stColumn"] {
    width: 100% !important; flex: 1 1 100% !important;
  }
  .st-key-nour_overview_kpis .nour-stat { min-height: 130px; }
  .st-key-nour_overview .nour-hero-copy { max-width: 100%; }
  .st-key-nour_overview .nour-cupcake { display: none; }
  .st-key-nour_overview .nour-task { flex-wrap: wrap; }
  .st-key-nour_overview_sales, .st-key-nour_overview_orders,
  .st-key-nour_overview_products, .st-key-nour_overview_customers { min-height: 0; }
}
@media (prefers-reduced-transparency: reduce) {
  .st-key-nour_overview .nourish-overview-hero {
    background: #f9e3e9 !important;
    -webkit-backdrop-filter: none !important; backdrop-filter: none !important;
  }
}
@media (forced-colors: active) {
  .st-key-nour_overview .nour-task, .st-key-nour_overview .nourish-overview-hero {
    background: Canvas !important; color: CanvasText !important; border: 1px solid CanvasText;
  }
}

/* Phase 4.1: compact shell and layered, non-interactive glass highlights. */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > [data-testid="stVerticalBlock"] {
  gap: .35rem;
}
section[data-testid="stSidebar"] [class*="st-key-nour_nav_"] button {
  padding: 7px 10px !important; font-size: .8125rem !important;
}


.st-key-nour_shell_actions { display: block; width: 100%; }
.st-key-nour_shell_actions > [data-testid="stHorizontalBlock"] {
  justify-content: flex-end; flex-wrap: nowrap !important; gap: 12px;
}
.st-key-nour_shell_actions > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  flex: 0 0 var(--header-action-size) !important; width: var(--header-action-size) !important; min-width: var(--header-action-size) !important;
}
.st-key-nour_shell_actions button {
  width: var(--header-action-size) !important; height: var(--header-action-size); min-height: var(--header-action-size);
  padding: 0 !important; border-radius: 50% !important;
  background: #fffaf6 !important; border: 1px solid #eee4e0 !important;
  color: #655e6c !important; box-shadow: 0 3px 9px #70546812;
}
.st-key-nour_shell_actions button:hover { border-color: #b9a2cd !important; background: #f4edf9 !important; }
.st-key-nour_header_nav_profile button { background: #eee1f4 !important; color: #654880 !important; }
[class*="st-key-nour_header_nav_"] button {
  min-height: 44px; padding: 6px 10px; font-size: .8125rem;
}
.st-key-nour_overview { gap: .65rem; }
.st-key-nour_overview .nour-hero-pill { padding: 4px 10px; font-size: .6875rem; }
.st-key-nour_overview .nourish-overview-hero,
.st-key-nour_overview_kpis .nour-stat {
  position: relative; isolation: isolate;
}
.st-key-nour_overview .nourish-overview-hero::before,
.st-key-nour_overview_kpis .nour-stat::before {
  content: ""; position: absolute; inset: 0; border-radius: inherit;
  pointer-events: none; z-index: -1;
  background: radial-gradient(ellipse at 12% 0%, #ffffffb8, transparent 55%),
              linear-gradient(165deg, #ffffff55, transparent 45%, #ffffff24);
  box-shadow: inset 0 1px 0 #ffffff, inset 0 -1px 0 #ffffff80;
}
.st-key-nour_overview_kpis .nour-stat {
  box-shadow: inset 0 2px 2px #ffffffef, inset 0 -2px 6px #947e8a10,
              0 3px 5px #70546808, 0 10px 24px #70546816;
}
@supports ((backdrop-filter: blur(16px)) or (-webkit-backdrop-filter: blur(16px))) {
  .st-key-nour_overview_kpis .nour-stat {
    -webkit-backdrop-filter: blur(14px) saturate(120%);
    backdrop-filter: blur(14px) saturate(120%);
  }
  .st-key-nour_overview_kpis .nour-stat-lavender { background: linear-gradient(145deg, #f8f3fcd9, #d9c7f0b8); }
  .st-key-nour_overview_kpis .nour-stat-pink { background: linear-gradient(145deg, #fff3f3df, #f4b6c2a3); }
  .st-key-nour_overview_kpis .nour-stat-mint { background: linear-gradient(145deg, #f3f7ece6, #9bb89a75); }
  .st-key-nour_overview_kpis .nour-stat-peach { background: linear-gradient(145deg, #fff8ece6, #f9e9d4b8); }
}
/* Existing CSS illustration: sculpted frosting, glazed cherry and pleated cup. */
.st-key-nour_overview .nour-cupcake {
  width: 115px; height: 140px; margin: -6px 6px;
  transform: rotate(5deg) scale(.9);
  filter: drop-shadow(5px 12px 8px #8b526b2b);
}
.st-key-nour_overview .nour-cupcake::before {
  content: ""; position: absolute; bottom: -6px; left: 13px;
  width: 92px; height: 17px; border-radius: 50%;
  background: radial-gradient(ellipse, #81647538, transparent 70%);
}
.st-key-nour_overview .nour-cherry {
  background: radial-gradient(circle at 30% 24%, #ffe6ed 0, #f4b6c2 18%, #cf6c8b 60%, #a63e62);
  box-shadow: inset -3px -3px 5px #92395566, inset 2px 2px 3px #fff2f6b3, 0 3px 4px #8c436b30;
}
.st-key-nour_overview .nour-cherry::after {
  content: ""; position: absolute; width: 13px; height: 7px; top: -5px; left: 13px;
  border-radius: 100% 0 100% 0; transform: rotate(-25deg);
  background: linear-gradient(145deg, #c6ddaf, #526f5a);
}
.st-key-nour_overview .nour-frosting {
  z-index: 2; color: #b55e82; font-size: 36px;
  background: radial-gradient(ellipse at 32% 12%, #fffefa 0, #fff0f5 35%, #efb7cb 78%, #c87899);
  box-shadow: inset -9px -8px 12px #b8698d45, inset 4px 4px 5px #ffffff,
              0 4px 4px #9b5b7b25;
}
.st-key-nour_overview .nour-frosting::before {
  content: ""; position: absolute; top: 16px; left: 12px; width: 76px; height: 20px;
  border-top: 5px solid #fffaf3aa; border-radius: 50%; transform: rotate(-12deg);
}
.st-key-nour_overview .nour-cupcake-base {
  background: linear-gradient(100deg, #ffffff55, transparent 40%, #3d614d44),
              repeating-linear-gradient(90deg, #bcd2ac 0 5px, #9bb89a 5px 12px, #829e7a 12px 16px);
  box-shadow: inset 0 -6px 8px #49634535, inset 4px 0 5px #ffffff80;
}
@media (min-width: 701px) {


}
@media (max-width: 700px) {


  .st-key-nour_shell_actions { justify-content: flex-start; }
}
@media (max-width: 600px) {

  .st-key-nour_overview .nourish-overview-hero { padding: 16px; min-height: 0; }
}
@media (prefers-reduced-transparency: reduce) {
  .st-key-nour_overview_kpis .nour-stat {
    -webkit-backdrop-filter: none !important; backdrop-filter: none !important;
    background: var(--nour-surface) !important;
  }
  .st-key-nour_overview .nourish-overview-hero::before,
  .st-key-nour_overview_kpis .nour-stat::before { display: none; }
}

/* Final visual fixes: local SVG KPI icons and single-line sidebar labels. */
.nour-stat-icon img { display: block; width: 24px; height: 24px; }
section[data-testid="stSidebar"] [class*="st-key-nour_nav_"] button {
  gap: .375rem; padding: 7px 8px !important; font-size: .75rem !important;
  white-space: nowrap !important;
}
section[data-testid="stSidebar"] [class*="st-key-nour_nav_"] button p {
  font-size: inherit !important; white-space: nowrap !important;
  overflow-wrap: normal !important; word-break: normal !important;
}

/* Phase 5A: order workspaces, scoped away from Overview and other pages. */
.st-key-nour_order_form, .st-key-nour_orders_page { gap: 1rem; }
.st-key-nour_order_form [class*="_customer_card"],
.st-key-nour_order_form [class*="_details_card"],
.st-key-nour_order_form [class*="_products_card"],
.st-key-nour_order_form [class*="_summary_card"],
.st-key-nour_orders_filters, .st-key-nour_orders_table,
.st-key-nour_orders_actions, .st-key-nour_orders_deadlines {
  padding: clamp(16px, 2vw, 24px) !important;
  border-radius: 22px !important; border: 1px solid #e7dce3 !important;
  background: #fffcf8;
  box-shadow: inset 0 2px 0 #ffffff, 0 8px 24px #7054680f;
}
.nour-order-section-title {
  display: flex; align-items: center; gap: 12px; margin-bottom: 16px;
}
.nour-order-step {
  display: inline-flex; align-items: center; justify-content: center;
  flex: 0 0 38px; height: 38px; border-radius: 13px;
  background: linear-gradient(150deg, #fffdf9, #e4d9f2);
  border: 1px solid #ffffff; color: #654880; font-size: .8rem; font-weight: 900;
  box-shadow: inset 0 2px 0 #ffffff, 0 4px 8px #70546816;
}
.nour-order-section-title h3 {
  font-size: 1rem !important; margin: 0 !important; padding: 0 !important;
  line-height: 1.4 !important;
}
.nour-order-section-title p { color: #655e6c; font-size: .8125rem; margin: 3px 0 0; }
.st-key-nour_order_form [class*="_details_card"] { background: #f7f2fb; }
.st-key-nour_order_form [class*="_customer_card"] { background: #fff9f6; }
.st-key-nour_order_form [class*="_summary_card"] {
  background: linear-gradient(135deg, #f7faf2, #e8efdf);
  border-color: #c5d4ba !important;
}
.st-key-nour_order_form [class*="_summary_card"] h3 { color: #426536 !important; }
.st-key-nour_order_form [class*="_product_row_"] {
  background: #fffdf9; border: 1px solid #e5dde4;
  padding: 12px; border-radius: 16px; margin-bottom: 8px;
}
.st-key-nour_order_form [class*="_product_row_"] [data-testid="stMetric"] {
  background: #f1f5e9; padding: 10px; box-shadow: none; border-color: #d8e2cc;
}
.st-key-nour_order_form [class*="_save_actions"] button[kind="primary"] {
  background: linear-gradient(170deg, #fff2f4, #f4b6c2) !important;
  color: #713449 !important; border-color: #cf94a4 !important;
}
.st-key-nour_order_form [class*="_save_actions"] { padding: 4px 0 8px; }
.st-key-nour_orders_kpis [data-testid="stColumn"]:nth-child(1) [data-testid="stMetric"] { background: #eee5f6; }
.st-key-nour_orders_kpis [data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"] { background: #fbe5eb; }
.st-key-nour_orders_kpis [data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"] { background: #e6efdc; }
.st-key-nour_orders_kpis [data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"] { background: #fff0dc; }
.st-key-nour_orders_kpis [data-testid="stMetricValue"] { font-size: clamp(1.25rem, 2vw, 1.8rem); }
.st-key-nour_orders_filters { background: #f7f4fa; }
.st-key-nour_orders_deadlines [data-testid="stMetric"] { box-shadow: none; }
.st-key-nour_orders_table [data-testid="stDataFrame"],
.st-key-nour_orders_actions [data-testid="stDataFrame"] { background: #fffdf9; }
.st-key-nour_orders_actions [class*="st-key-om_delete_"] button {
  background: #fff0f2; border-color: #d9a7b3; color: #8c3d52;
}
@supports ((backdrop-filter: blur(16px)) or (-webkit-backdrop-filter: blur(16px))) {
  .st-key-nour_order_form [class*="_customer_card"],
  .st-key-nour_orders_actions, .st-key-nour_orders_deadlines {
    background: #fffcf8eb;
    -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px);
  }
}
@media (max-width: 1000px) {
  .st-key-nour_orders_kpis > [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  .st-key-nour_orders_kpis [data-testid="stColumn"] {
    flex: 1 1 calc(50% - .5rem) !important; min-width: 0 !important; width: auto !important;
  }
  .st-key-nour_orders_filters [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  .st-key-nour_orders_filters [data-testid="stColumn"] {
    flex: 1 1 45% !important; min-width: 0 !important; width: auto !important;
  }
}
@media (max-width: 700px) {
  .st-key-nour_order_form [data-testid="stHorizontalBlock"],
  .st-key-nour_orders_actions [data-testid="stHorizontalBlock"],
  .st-key-nour_orders_deadlines [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  .st-key-nour_order_form [data-testid="stColumn"],
  .st-key-nour_orders_actions [data-testid="stColumn"],
  .st-key-nour_orders_deadlines [data-testid="stColumn"],
  .st-key-nour_orders_kpis [data-testid="stColumn"],
  .st-key-nour_orders_filters [data-testid="stColumn"] {
    flex: 1 1 100% !important; min-width: 0 !important; width: 100% !important;
  }
}
@media (prefers-reduced-transparency: reduce) {
  .st-key-nour_order_form [class*="_customer_card"],
  .st-key-nour_orders_actions, .st-key-nour_orders_deadlines {
    background: #fffcf8 !important;
    -webkit-backdrop-filter: none !important; backdrop-filter: none !important;
  }
}
@media (forced-colors: active) {
  .st-key-nour_order_form [class*="_card"],
  .st-key-nour_orders_filters, .st-key-nour_orders_table,
  .st-key-nour_orders_actions, .st-key-nour_orders_deadlines {
    background: Canvas !important; border-color: CanvasText !important; box-shadow: none;
  }
}

/* Phase 5B: customer directory/profile and payment workspaces. */
.st-key-nour_customer_page, .st-key-nour_payment_page { gap: 1rem; }
.st-key-nour_customer_page h1 { font-size: 1.2rem !important; padding: 0 !important; }
.st-key-nour_customer_page h3, .st-key-nour_payment_page h3 {
  font-size: 1rem !important; line-height: 1.5;
}
.st-key-nour_customer_directory, .st-key-nour_customer_profile,
.st-key-nour_customer_filters, .st-key-nour_payment_record,
.st-key-nour_payment_selected, .st-key-nour_payment_history {
  padding: clamp(14px, 1.7vw, 22px) !important;
  border: 1px solid #e5dbe1 !important; border-radius: 22px !important;
  background: #fffcf8; box-shadow: inset 0 2px 0 #ffffff, 0 8px 24px #7054680e;
}
.st-key-nour_customer_profile { background: #f8f4fb; }
.st-key-nour_customer_filters { background: #f5f2f8; }
.st-key-nour_payment_selected {
  background: linear-gradient(140deg, #f9fbf4, #e8efdf); border-color: #ccd8c2 !important;
}
.st-key-nour_customer_kpis [data-testid="stMetric"],
.st-key-nour_customer_profile_metrics [data-testid="stMetric"],
.st-key-nour_payment_kpis [data-testid="stMetric"] { padding: 14px; }
.st-key-nour_customer_kpis [data-testid="stColumn"]:nth-child(1) [data-testid="stMetric"] { background: #eee5f6; }
.st-key-nour_customer_kpis [data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"] { background: #fbe5eb; }
.st-key-nour_customer_kpis [data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"] { background: #e6efdc; }
.st-key-nour_customer_kpis [data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"] { background: #fff0dc; }
.st-key-nour_payment_kpis [data-testid="stColumn"]:nth-child(1) [data-testid="stMetric"] { background: #eee5f6; }
.st-key-nour_payment_kpis [data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"] { background: #e6efdc; }
.st-key-nour_payment_kpis [data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"] { background: #fbe5eb; }
.st-key-nour_customer_page [data-testid="stMetricValue"],
.st-key-nour_payment_page [data-testid="stMetricValue"] {
  font-size: clamp(1.15rem, 1.8vw, 1.6rem); line-height: 1.4;
}
.st-key-nour_customer_page [data-testid="stMetricValue"] *,
.st-key-nour_customer_page [data-testid="stMetricLabel"] *,
.st-key-nour_payment_page [data-testid="stMetricValue"] *,
.st-key-nour_payment_page [data-testid="stMetricLabel"] * {
  white-space: normal !important; text-overflow: clip !important;
  overflow: visible !important; overflow-wrap: anywhere;
}
.st-key-nour_customer_primary_actions button { min-height: 44px; }
.st-key-nour_customer_danger {
  margin-top: 12px; padding-top: 14px; border-top: 1px solid #e4cbd3;
}
.st-key-nour_customer_danger button {
  background: #fff0f2; color: #873c53; border-color: #d8a8b6;
}
.st-key-nour_customer_profile_metrics [data-testid="stMetric"] {
  background: #fffcf8; min-height: 116px; margin-bottom: 8px;
}
.st-key-nour_payment_record [data-testid="stForm"] { border: 0; box-shadow: none; background: transparent; }
.st-key-nour_payment_selected [data-testid="stMetric"] { background: #fffdf8; box-shadow: none; }
.st-key-nour_customer_directory [data-testid="stDataFrame"],
.st-key-nour_payment_history [data-testid="stDataFrame"] { background: #fffdf9; }
@supports ((backdrop-filter: blur(16px)) or (-webkit-backdrop-filter: blur(16px))) {
  .st-key-nour_customer_directory, .st-key-nour_payment_record,
  .st-key-nour_payment_history {
    background: #fffcf8eb;
    -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px);
  }
}
@media (max-width: 1100px) {
  .st-key-nour_customer_split > [data-testid="stHorizontalBlock"],
  .st-key-nour_payment_split > [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  .st-key-nour_customer_split > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
  .st-key-nour_payment_split > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    flex: 1 1 100% !important; width: 100% !important; min-width: 0 !important;
  }
  .st-key-nour_customer_kpis > [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  .st-key-nour_customer_kpis [data-testid="stColumn"] {
    flex: 1 1 calc(50% - .5rem) !important; width: auto !important; min-width: 0 !important;
  }
}
@media (max-width: 700px) {
  .st-key-nour_customer_filters [data-testid="stHorizontalBlock"],
  .st-key-nour_customer_profile_metrics [data-testid="stHorizontalBlock"],
  .st-key-nour_payment_kpis [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  .st-key-nour_customer_filters [data-testid="stColumn"],
  .st-key-nour_customer_profile_metrics [data-testid="stColumn"],
  .st-key-nour_payment_kpis [data-testid="stColumn"],
  .st-key-nour_customer_kpis [data-testid="stColumn"] {
    flex: 1 1 100% !important; width: 100% !important; min-width: 0 !important;
  }
}
@media (prefers-reduced-transparency: reduce) {
  .st-key-nour_customer_directory, .st-key-nour_payment_record, .st-key-nour_payment_history {
    background: #fffcf8 !important;
    -webkit-backdrop-filter: none !important; backdrop-filter: none !important;
  }
}
@media (forced-colors: active) {
  .st-key-nour_customer_directory, .st-key-nour_customer_profile,
  .st-key-nour_customer_filters, .st-key-nour_payment_record,
  .st-key-nour_payment_selected, .st-key-nour_payment_history {
    background: Canvas !important; border-color: CanvasText !important; box-shadow: none;
  }
}

/* BizMar R1: text-only application identity; business assets remain intact. */
.bizmar-mark {
  display: inline-flex; align-items: center; justify-content: center;
  width: 54px; height: 54px; border-radius: 18px;
  font-family: var(--nour-heading-font); font-size: 1.1rem; font-weight: 700;
  letter-spacing: -.06em; color: #426536;
  background: linear-gradient(145deg, #fffdf8, #dce9cb 60%, #f4dce4);
  border: 1px solid #fffdf8;
  box-shadow: inset 0 2px 0 #ffffff, 0 6px 14px #70546820;
}
.bizmar-sidebar-mark, .bizmar-login-brand { text-align: center; }
.bizmar-login-brand { padding: 12px 0 16px; }
.bizmar-login-name {
  font-family: var(--nour-heading-font); font-size: 2rem;
  color: var(--nour-ink); font-weight: 600; margin-top: 10px;
}
.bizmar-login-brand p, .bizmar-description, .bizmar-malay {
  color: var(--nour-muted); font-size: .75rem; line-height: 1.5; text-align: center;
}
section[data-testid="stSidebar"] .bizmar-description { margin: 4px 0 6px; color: #513c66; }
section[data-testid="stSidebar"] .bizmar-malay { margin: 0 0 8px; color: #655271; }
@media (forced-colors: active) {
  .bizmar-mark { background: Canvas; color: CanvasText; border: 1px solid CanvasText; box-shadow: none; }
}

.st-key-bizmar_daily_volume, .st-key-bizmar_product_profitability {
  padding: clamp(14px, 1.8vw, 24px) !important;
  border-radius: 22px !important; margin-top: 14px;
}

/* Phase 6C: native seven-column deadline calendar. */
.st-key-bizmar_deadline_calendar {
  padding: clamp(12px, 1.8vw, 24px) !important; border-radius: 24px !important;
}
.bizmar-calendar-month { text-align: center; font-family: var(--nour-heading-font); font-weight: 600; font-size: 1.2rem; }
.bizmar-calendar-weekday { text-align: center; font-size: .75rem; color: #655e6c; font-weight: 800; }
.st-key-bizmar_calendar_grid [data-testid="stHorizontalBlock"] { gap: .35rem; flex-wrap: nowrap !important; }
.st-key-bizmar_calendar_grid [data-testid="stColumn"] { min-width: 0 !important; flex: 1 1 0 !important; width: 0 !important; }
.st-key-bizmar_calendar_grid button { min-height: 52px; width: 100%; padding: 6px 2px !important; font-size: .8125rem; border-radius: 12px !important; }
.st-key-bizmar_calendar_grid [class*="st-key-bizmar_calendar_scheduled_"] button { background: linear-gradient(155deg, #f7fbed, #dce9cb); border-color: #a4b894; color: #36532c; }
.st-key-bizmar_calendar_grid [class*="st-key-bizmar_calendar_scheduled_overdue_"] button { background: #f8dce5; border-color: #ca8da1; color: #873c53; }
.st-key-bizmar_calendar_grid [class*="st-key-bizmar_calendar_scheduled_today_"] button { background: #eee2f7; border-color: #b89dcb; color: #62467c; }
.st-key-bizmar_calendar_grid [class*="st-key-bizmar_calendar_scheduled_completed_"] button { background: #edf2e8; color: #4b6242; }
.st-key-bizmar_calendar_grid [class*="st-key-bizmar_calendar_scheduled_cancelled_"] button { background: #eee9ec; border-color: #d2c8ce; color: #655e6c; }
.st-key-bizmar_calendar_grid button[kind="primary"] { outline: 2px solid #654880; outline-offset: -3px; background: linear-gradient(155deg, #fff3f6, #f4d3e0) !important; color: #70405c !important; }
.bizmar-calendar-blank { min-height: 52px; }
@media (max-width: 600px) {
  .st-key-bizmar_calendar_grid button { font-size: .6875rem; min-height: 48px; }
  .bizmar-calendar-weekday { font-size: .625rem; }
}
@media (forced-colors: active) {
  .st-key-bizmar_calendar_grid button { background: ButtonFace !important; color: ButtonText !important; border: 1px solid ButtonText !important; }
  .st-key-bizmar_calendar_grid button[kind="primary"] { outline: 2px solid Highlight; }
}

/* Approved BizMar Matcha Strawberry refresh. Native Streamlit controls stay interactive. */
:root {
  --nour-lavender: #f8dce2;
  --nour-lavender-strong: #98415a;
  --nour-strawberry: #f8dce2;
  --nour-strawberry-strong: #98415a;
  --nour-cream: #fff9f3;
  --nour-glass: rgba(255, 250, 246, .84);
  --nour-line: #f0dfe1;
  --nour-shadow: 0 12px 28px rgba(106, 71, 77, .09);
}
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(ellipse at 88% 8%, #fbe2e8 0, transparent 38%),
    radial-gradient(ellipse at 12% 82%, #e4eddc 0, transparent 36%),
    #fff9f3 !important;
}
[data-testid="stMainBlockContainer"] { max-width: 1500px; }

section[data-testid="stSidebar"] {
  width: 226px !important;
  background: linear-gradient(155deg, #fffaf3 0%, #f9e8e8 56%, #e6eedf 100%) !important;
  border-color: #fffdf8 !important;
  box-shadow: 8px 0 28px rgba(99, 74, 76, .09), var(--nour-reflection);
}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
  padding: 16px 12px !important;
}
section[data-testid="stSidebar"] [data-testid="stImage"] img {
  display: block; width: 100%; max-height: none; height: auto;
  object-fit: contain; border-radius: 0;
}
.st-key-bizmar_sidebar_logo {
  padding: 4px 8px 12px; margin-bottom: 10px;
  border-bottom: 1px solid #e8d8d9;
}
section[data-testid="stSidebar"] [class*="st-key-nour_nav_"] button {
  min-height: 46px !important; padding: 10px 12px !important;
  border-radius: 15px !important; color: #3c4638 !important;
  font-size: .86rem !important; font-weight: 800 !important;
}
section[data-testid="stSidebar"] [class*="st-key-nour_nav_"] button:hover {
  background: #f9e7e9 !important; border-color: #f2d3da !important;
}
section[data-testid="stSidebar"] [class*="st-key-nour_nav_"] button[kind="primary"] {
  background: linear-gradient(120deg, #ffd9e0, #f6a8b8) !important;
  color: #612e3b !important; border-color: #f5cad2 !important;
  box-shadow: 0 5px 15px #bc68761c, var(--nour-reflection) !important;
}
section[data-testid="stSidebar"] .nour-sidebar-brand { color: #315c3c; }
section[data-testid="stSidebar"] .nour-sidebar-tagline,
section[data-testid="stSidebar"] .bizmar-description,
section[data-testid="stSidebar"] .bizmar-malay { color: #5d6456 !important; }
.st-key-nour_shell_owner {
  margin-top: auto; padding: 10px 8px !important;
  border-radius: 17px; border: 1px solid #fffdf9;
  background: linear-gradient(135deg, #fffaf4e8, #f8dfe5c9);
  box-shadow: var(--nour-reflection), 0 6px 16px #70546812;
}
.bizmar-owner-avatar {
  width: 38px; height: 38px; display: flex; align-items: center; justify-content: center;
  border-radius: 50%; color: #fff; font-weight: 900;
  background: linear-gradient(145deg, #81a77b, #416b4c);
  border: 2px solid #fffaf4; box-shadow: 0 4px 9px #536c4c28;
}
.nour-owner-name { color: #273e2c; font-size: .9rem; }
.nour-owner-role { color: #65605c; }

.st-key-bizmar_login_logo {
  display: flex; justify-content: center; padding: 20px 12px 8px;
}
.st-key-bizmar_login_logo [data-testid="stImage"] {
  width: min(100%, 330px); margin: 0 auto;
}
.st-key-bizmar_login_logo img {
  display: block; width: 100%; height: auto; object-fit: contain;
}
.bizmar-login-heading {
  text-align: center; margin: 4px 0 !important;
  font-size: clamp(1.5rem, 3vw, 2rem) !important;
  color: #315c3c !important;
}
.bizmar-login-subtitle {
  margin: 0 0 18px; text-align: center; color: #71676a;
}
.st-key-bizmar_google_login button {
  min-height: 52px !important; border-radius: 999px !important;
  background: linear-gradient(115deg, #ff9caf, #ef7190) !important;
  border: 1px solid #f9b4c1 !important; color: #fff !important;
  font-size: .95rem !important; font-weight: 900 !important;
  box-shadow: inset 0 2px 0 #ffffff9c, 0 7px 18px #cb5d7a35 !important;
}
.st-key-bizmar_google_login button p { color: inherit !important; }


.st-key-nour_overview { gap: .55rem; }
.st-key-nour_overview .nourish-overview-hero {
  min-height: 112px; padding: 16px 22px; margin: 2px 0 6px;
  position: relative; isolation: isolate; overflow: hidden;
  border: 1px solid #fff; border-radius: 22px;
  background: linear-gradient(110deg, #fff6f2 0%, #fde9e9 58%, #eaf0e1 100%);
  box-shadow: inset 0 2px 0 #ffffff, 0 10px 24px #906c7415;
}
.st-key-nour_overview .nourish-overview-hero::before {
  z-index: 0; opacity: .58;
  background: linear-gradient(105deg, #fffaf5 4%, #fff6f0b8 46%, transparent 80%);
}
.bizmar-overview-art {
  position: absolute; z-index: 0; top: 0; right: 0; width: 40%; height: 100%;
  object-fit: cover; object-position: center 48%; opacity: .48;
  mask-image: linear-gradient(90deg, transparent, #000 34%);
  pointer-events: none;
}
.st-key-nour_overview .nour-hero-copy { z-index: 1; max-width: 72%; }
.st-key-nour_overview .nour-hero-copy p {
  margin: 0 0 8px; color: #23392d; font-size: 1.12rem;
  font-weight: 900; letter-spacing: -.025em;
}
.st-key-nour_overview .nour-hero-pill {
  padding: 7px 14px; color: #873b53; background: #fffaf5;
  border-color: #f3d9df; font-size: .82rem;
}
.st-key-nour_overview .nour-stat {
  min-height: 142px; padding: 16px;
  border: 1px solid #fff; border-radius: 20px;
  box-shadow: inset 0 2px 1px #ffffffed, 0 9px 23px #70546816;
}
.st-key-nour_overview_kpis .nour-stat-lavender { background: linear-gradient(145deg, #f4edf9, #e6dcf1); }
.st-key-nour_overview_kpis .nour-stat-pink { background: linear-gradient(145deg, #fff0ed, #f8dce2); }
.st-key-nour_overview_kpis .nour-stat-mint { background: linear-gradient(145deg, #f4f7ed, #dfead8); }
.st-key-nour_overview_kpis .nour-stat-peach { background: linear-gradient(145deg, #fff5df, #f8e7c5); }
.st-key-nour_overview_kpis .nour-stat { min-height: 180px; padding: 22px; }
.st-key-nour_overview_activity > [data-testid="stHorizontalBlock"] { align-items: flex-start; }
.st-key-nour_overview_activity [data-testid="stVerticalBlock"] { gap: 1.2rem; }
.st-key-nour_overview_products, .st-key-nour_overview_customers {
  padding: 20px !important; border-radius: 22px !important;
  border: 1px solid #fff !important; background: rgba(255, 252, 248, .84);
  box-shadow: var(--nour-shadow);
}
.st-key-nour_overview_customers { background: linear-gradient(145deg, #fff6e7, #fbeac9); }
.st-key-nour_overview_kpis .nour-stat-value {
  margin: 8px 0 5px; font-size: clamp(1.2rem, 1.8vw, 1.65rem);
}
.st-key-nour_overview_kpis .nour-stat-icon { border-radius: 50%; }
.st-key-nour_overview_sales, .st-key-nour_overview_orders {
  min-height: 0; padding: 16px !important; border-radius: 22px !important;
  border-color: #fff !important; background: rgba(255, 252, 248, .84);
}
.st-key-nour_overview_sales [data-testid="stPlotlyChart"] {
  padding: 0; border: 0; background: transparent;
}
.st-key-nour_overview_sales h4, .st-key-nour_overview_orders h4 {
  color: #262a28; font-size: 1rem !important;
}
.st-key-nour_overview .nour-task {
  padding: 11px 9px; margin-bottom: 8px; border-radius: 15px;
  background: #fffaf6; border: 1px solid #f1e6e5;
}
.st-key-nour_overview .nour-task span {
  background: #fae4e8; color: #873b53;
}
.st-key-nour_overview .nour-status-confirmed,
.st-key-nour_overview .nour-status-ready {
  background: #e4efdf !important; color: #3e6544 !important;
}
.st-key-nour_overview [class*="st-key-overview_sales_"] button,
.st-key-nour_overview [class*="st-key-overview_sales_"] button[kind="secondary"] {
  min-height: 40px !important; border-radius: 999px !important;
  background: #fffaf7 !important; border-color: #eadfe0 !important;
}
.st-key-nour_overview [class*="st-key-overview_sales_"] button[kind="primary"] {
  background: linear-gradient(120deg, #ffbdca, #f58ca2) !important;
  border-color: #f5a8b8 !important; color: #642e3d !important;
}
.st-key-nour_overview [class*="st-key-overview_sales_"] button p { color: inherit !important; }

@media (max-width: 1100px) {
  section[data-testid="stSidebar"] { width: 216px !important; }
  .st-key-nour_overview_activity [data-testid="stColumn"] {
    width: 100% !important; flex: 1 1 100% !important;
  }
}
@media (max-width: 700px) {
  .st-key-bizmar_login_logo { padding-top: 8px; }
  .st-key-bizmar_login_logo [data-testid="stImage"] { width: min(100%, 260px); }
  .st-key-nour_overview .nourish-overview-hero { min-height: 98px; padding: 14px; }
  .st-key-nour_overview .nour-hero-copy { max-width: 82%; }
  .bizmar-overview-art { width: 48%; opacity: .34; }
  .st-key-nour_overview_sales, .st-key-nour_overview_orders { padding: 13px !important; }
}
@media (prefers-reduced-transparency: reduce) {
  .st-key-nour_shell_owner, .st-key-nour_overview_sales, .st-key-nour_overview_orders {
    background: #fffcf8 !important;
    -webkit-backdrop-filter: none !important; backdrop-filter: none !important;
  }
  .bizmar-overview-art { opacity: .22; }
}
@media (forced-colors: active) {
  .st-key-bizmar_google_login button, .st-key-nour_overview .nourish-overview-hero,
  .st-key-bizmar_sidebar_logo, .st-key-nour_shell_owner {
    background: Canvas !important; color: CanvasText !important;
    border: 1px solid CanvasText; box-shadow: none;
  }
  .bizmar-overview-art { display: none; }
}

/* Shared date filter presentation, loaded before the optional dark theme. */

    [class*="st-key-overview_sales_"] button,
    [class*="st-key-analytics_sales_"] button {
        border-radius: 999px !important;
        min-height: 42px !important;
        padding: 0 18px !important;
        white-space: nowrap !important;
        color: #463a4d !important;
        font-weight: 800 !important;
    }
    [class*="st-key-overview_sales_"] button[kind="secondary"],
    [class*="st-key-analytics_sales_"] button[kind="secondary"] {
        background: #f2eaf4 !important;
        border-color: #e5d8e9 !important;
        color: #463a4d !important;
    }
    [class*="st-key-overview_sales_"] button[kind="secondary"]:hover,
    [class*="st-key-analytics_sales_"] button[kind="secondary"]:hover {
        background: #dff0e6 !important;
        border-color: #c4e2cf !important;
        color: #30283a !important;
    }
    [class*="st-key-overview_sales_"] button[kind="primary"],
    [class*="st-key-analytics_sales_"] button[kind="primary"] {
        background: #ddcbed !important;
        border-color: #c7b0df !important;
        color: #382a46 !important;
    }
    [class*="st-key-overview_sales_"] button[kind="primary"]:hover,
    [class*="st-key-analytics_sales_"] button[kind="primary"]:hover {
        background: #f5dce8 !important;
        border-color: #eac1d3 !important;
        color: #382a46 !important;
    }
    [class*="st-key-overview_sales_"] button p,
    [class*="st-key-analytics_sales_"] button p {
        color: inherit !important;
        white-space: nowrap !important;
    }
    
/* Native tooltips are portalled outside the app; style only their actual surface. */
:root {
  --bizmar-tooltip-bg: #344B40;
  --bizmar-tooltip-text: #F5F7F3;
  --bizmar-tooltip-border: #50645A;
}
[role="tooltip"] [data-testid="stTooltipContent"] {
  background: var(--bizmar-tooltip-bg) !important;
  color: var(--bizmar-tooltip-text) !important;
  border: 1px solid var(--bizmar-tooltip-border) !important;
  border-radius: 10px;
  box-shadow: 0 6px 18px rgb(20 35 27 / 24%);
  padding: 9px 12px;
}
[role="tooltip"] [data-testid="stTooltipContent"] [data-testid="stMarkdownContainer"],
[role="tooltip"] [data-testid="stTooltipContent"] p {
  color: var(--bizmar-tooltip-text) !important;
  margin: 0 !important;
  line-height: 1.4;
}
/* Dashboard layout: keep the DOM in normal flow and let wrapping content grow. */

.st-key-nour_overview { gap: 24px !important; }
.st-key-nour_overview_filters { margin: 0; }
.st-key-nour_overview_filters [data-testid="stCaptionContainer"] { margin-top: 8px; }
.st-key-nour_overview_kpis { margin: 0; }
.st-key-nour_overview_kpis [data-testid="stHorizontalBlock"] {
  display: grid !important; grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 18px !important; align-items: stretch;
}
.st-key-nour_overview_kpis [data-testid="stColumn"] {
  width: 100% !important; min-width: 0 !important; height: auto;
  display: flex; flex-direction: column;
}
.st-key-nour_overview_kpis :is([data-testid="stVerticalBlock"], [data-testid="stElementContainer"], [data-testid="stMarkdown"], [data-testid="stMarkdownContainer"]) {
  height: auto !important; display: flex; flex-direction: column; flex: 1 1 auto; min-width: 0;
}
.st-key-nour_overview_kpis [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
.st-key-nour_overview_kpis [data-testid="stMarkdown"] > div { display: flex; flex-direction: column; flex: 1 1 auto; }
.st-key-nour_overview_kpis .nour-stat {
  box-sizing: border-box; height: auto; min-height: 180px; padding: 22px; flex: 1 1 auto;
  display: flex; flex-direction: column; gap: 8px; margin: 0;
  overflow-wrap: anywhere;
}
.st-key-nour_overview_kpis .nour-stat-value { margin: 0; line-height: 1.3; }
.st-key-nour_overview_kpis .nour-stat-foot { margin-top: auto; line-height: 1.5; }
.st-key-nour_overview_activity { margin: 0; }
.st-key-nour_overview_activity [data-testid="stVerticalBlock"] { gap: 24px; }
.st-key-nour_overview_sales, .st-key-nour_overview_orders,
.st-key-nour_overview_products, .st-key-nour_overview_customers { padding: 22px !important; min-height: 0; }
.st-key-nour_shell_actions {
  display: flex !important; align-items: center; justify-content: flex-end;
  width: max-content !important; max-width: 100%; margin-left: auto; gap: 12px !important;
}
.st-key-nour_shell_actions [data-testid="stHorizontalBlock"] {
  display: flex !important; align-items: center; justify-content: flex-end;
  flex-wrap: nowrap !important; gap: 12px !important; width: max-content !important;
}
.st-key-nour_shell_actions [data-testid="stColumn"] {
  flex: 0 0 var(--header-action-size) !important; width: var(--header-action-size) !important; min-width: var(--header-action-size) !important;
}
.st-key-nour_shell_actions :is([data-testid="stElementContainer"],[data-testid="stButton"],[data-testid="stPopover"]) { width: var(--header-action-size) !important; flex: 0 0 var(--header-action-size) !important; }
.st-key-nour_shell_actions button {
  display: flex; align-items: center; justify-content: center;
  width: var(--header-action-size) !important; height: var(--header-action-size) !important; min-height: var(--header-action-size) !important;
  padding: 0 !important; border-radius: 50% !important;
  margin: 0 !important; transform: none !important; box-sizing: border-box;
}
.st-key-nour_shell_actions .st-key-nour_header_nav_profile button { overflow: hidden; }
.st-key-nour_header_nav_profile button:has(img) :is(div,span,p) {
  display: contents !important; margin: 0 !important; padding: 0 !important;
}
.st-key-nour_header_nav_profile button img {
  display: block; width: 100% !important; height: 100% !important;
  max-width: none !important; max-height: none !important;
  object-fit: cover; object-position: center; border-radius: 50%;
  margin: 0 !important; padding: 0 !important; transform: none !important;
}
.st-key-nour_shell_actions [data-testid="stPopoverButton"] > svg:last-child { display: none; }
.st-key-nour_shell_actions [data-testid="stPopoverButton"] > div > div[aria-hidden="true"] { display: none; }
@media (max-width: 1100px) {
  .st-key-nour_overview_kpis [data-testid="stHorizontalBlock"] { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
  .st-key-nour_overview_kpis [data-testid="stHorizontalBlock"] { grid-template-columns: minmax(0, 1fr); }
  .st-key-nour_overview_sales, .st-key-nour_overview_orders,
  .st-key-nour_overview_products, .st-key-nour_overview_customers { padding: 20px !important; }
}
"""


STYLE += (Path(__file__).parent / 'styles' / 'typography.css').read_text(encoding='utf-8')
STYLE += (Path(__file__).parent / 'styles' / 'page_header.css').read_text(encoding='utf-8')
STYLE += (Path(__file__).parent / 'styles' / 'kpi_sparklines.css').read_text(encoding='utf-8')

def apply_theme():
    """Apply shared presentation without changing state or widget behavior."""
    from display_preferences import install_table_localization
    install_table_localization()
    st.markdown("<style>" + STYLE + "</style>", unsafe_allow_html=True)



def style_overview_chart(fig, *, product_ranking=False):
    """Style an existing Plotly figure without changing data or aggregations."""
    if product_ranking:
        fig.update_traces(
            marker_color='#9BB89A', marker_line_color='#526F5A',
            marker_line_width=1, textposition='outside', cliponaxis=False,
            hovertemplate='%{y}<br>Units sold: %{x}<extra></extra>',
        )
    else:
        for trace in fig.data:
            color = '#98415a' if trace.name == 'revenue' else '#526F5A'
            trace.update(line_color=color, marker_color=color, line_width=3,
                         marker_size=7,
                         hovertemplate='%{x}<br>RM %{y:,.2f}<extra>%{fullData.name}</extra>')
    fig.update_layout(
        font=dict(family='Inter, Arial, sans-serif', size=13, color='#403b43'),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=8, r=28, t=20, b=20),
        hoverlabel=dict(bgcolor='#FFF9F3', font_color='#302f35',
                        bordercolor='#D9C7F0'),
        legend=dict(title_text='', orientation='h', y=1.15, x=0),
        hovermode='closest' if product_ranking else 'x unified',
    )
    fig.update_xaxes(showgrid=True, gridcolor='#e8e4df', zeroline=False,
                     title_text='Units sold' if product_ranking else 'Period',
                     automargin=True)
    fig.update_yaxes(showgrid=not product_ranking, gridcolor='#e8e4df',
                     zeroline=False, automargin=True)
    return fig



def order_section_title(step, title, subtitle):
    """Render an escaped, decorative heading above native order controls."""
    from html import escape
    st.markdown(
        '<div class="nour-order-section-title"><span class="nour-order-step" aria-hidden="true">'
        + escape(step) + '</span><div><h3>' + escape(title)
        + '</h3><p>' + escape(subtitle) + '</p></div></div>',
        unsafe_allow_html=True,
    )


def order_status_style(value):
    """Pastel table-cell styling; labels and underlying values stay intact."""
    label = str(value).lstrip('\u25cf ').strip()
    from settings_store import runtime
    if runtime()['theme'] == 'Dark':
        from forest_theme import status_colors
        background, color = status_colors(label)
        return f'background-color: {background}; color: {color}; font-weight: 500'
    tones = {
        'Pending': ('#f6e9d3', '#70512b'),
        'Confirmed': ('#eaddf6', '#62467c'),
        'Preparing': ('#f8dce5', '#873c53'),
        'Ready': ('#e0ecd8', '#3e5f34'),
        'Completed': ('#e0ecd8', '#3e5f34'),
        'Cancelled': ('#eee9ec', '#655e6c'),
        'Unpaid': ('#f8dce5', '#873c53'),
        'Partial': ('#f6e9d3', '#70512b'),
        'Paid': ('#e0ecd8', '#3e5f34'),
    }
    background, color = tones.get(label, ('#fffdf9', '#302f35'))
    return f'background-color: {background}; color: {color}; font-weight: 500'



def style_bi_chart(fig):
    """Shared Plotly presentation without assumptions about measures or units."""
    fig.update_layout(
        font=dict(family='Inter, Arial, sans-serif', size=13, color='#403b43'),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=8, r=20, t=12, b=20),
        hoverlabel=dict(bgcolor='#FFF9F3', font_color='#302f35', bordercolor='#D9C7F0'),
    )
    fig.update_xaxes(gridcolor='#e8e4df', automargin=True)
    fig.update_yaxes(gridcolor='#e8e4df', automargin=True)
    return fig



def deadline_status_style(value):
    """Readable labelled deadline states; color is supplementary."""
    from settings_store import runtime
    if runtime()['theme'] == 'Dark':
        from forest_theme import status_colors
        background, color = status_colors(value)
        return f'background-color: {background}; color: {color}; font-weight: 500'
    colors = {
        'Overdue': ('#f8dce5', '#873c53'),
        'Due today': ('#eee2f7', '#62467c'),
        'Upcoming': ('#e0ecd8', '#3e5f34'),
        'Completed': ('#edf2e8', '#4b6242'),
        'Cancelled': ('#eee9ec', '#655e6c'),
        'No deadline': ('#fff0dc', '#73542d'),
    }
    background, color = colors.get(str(value), ('#fffdf9', '#302f35'))
    return f'background-color: {background}; color: {color}; font-weight: 500'
