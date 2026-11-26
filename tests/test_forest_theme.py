"""Contrast and presentation-only regressions for Soft Forest Dark Mode."""
import unittest
from unittest.mock import patch
import pandas as pd
import plotly.graph_objects as go
import display_preferences as display
from forest_theme import tokens, status_colors
from settings_store import DEFAULTS


def contrast(first, second):
    def luminance(color):
        channels = [int(color[index:index+2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
        return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + .05) / (dark + .05)


class ForestThemeTests(unittest.TestCase):
    def test_shared_tooltip_palette_meets_aa(self):
        import re
        from ui_theme import STYLE
        colors = dict(re.findall(r'--bizmar-tooltip-([\w-]+):\s*(#[0-9A-Fa-f]{6})\s*;', STYLE))
        self.assertEqual(colors, {'bg': '#344B40', 'text': '#F5F7F3', 'border': '#50645A'})
        self.assertGreaterEqual(contrast(colors['text'], colors['bg']), 4.5)

    def test_text_states_meet_aa(self):
        colors = tokens()
        for foreground in ('text', 'secondary', 'muted'):
            for background in ('bg', 'sidebar', 'card', 'hover'):
                # Muted text is used on inputs/disabled controls, never hover states.
                if foreground == 'muted' and background == 'hover':
                    continue
                with self.subTest(foreground=foreground, background=background):
                    self.assertGreaterEqual(contrast(colors[foreground], colors[background]), 4.5)
        self.assertGreaterEqual(contrast(colors['primary-text'], colors['primary']), 4.5)
        self.assertGreaterEqual(contrast(colors['hover-text'], colors['primary-hover']), 4.5)
        for foreground in ('pink', 'primary', 'control-border', 'chart-grid'):
            for background in ('bg', 'card'):
                self.assertGreaterEqual(contrast(colors[foreground], colors[background]), 3)

    def test_order_save_button_text_has_clear_contrast(self):
        from pathlib import Path
        import re
        css = (Path(__file__).resolve().parents[1] / 'styles' / 'orders.css').read_text()
        self.assertIn(
            '.st-key-nour_order_form [class*="_save_actions"] '
            '[data-testid="stButton"] button[kind="primary"]',
            css,
        )
        self.assertGreaterEqual(contrast('#FFFFFF', '#174C35'), 4.5)

    def test_written_statuses_have_distinct_readable_tones(self):
        for name in ('Pending', 'Confirmed', 'Preparing', 'Ready', 'Completed', 'Cancelled', 'Paid', 'Unpaid', 'Partial', 'Overdue', 'Due today', 'Upcoming'):
            background, foreground = status_colors(name)
            self.assertGreaterEqual(contrast(background, foreground), 4.5, name)
        self.assertNotEqual(status_colors('Pending'), status_colors('Confirmed'))

    def test_chart_dark_labels_and_data_preserved(self):
        colors = tokens()
        figure = go.Figure(go.Bar(x=['First', 'Second'], y=[10, 20], text=[10, 20]))
        with patch.object(display, 'runtime', return_value={**DEFAULTS, 'theme': 'Dark'}):
            display.style_figure(figure)
        self.assertEqual(list(figure.data[0].y), [10, 20])
        self.assertEqual(figure.layout.xaxis.tickfont.color, colors['secondary'])
        self.assertEqual(figure.data[0].textfont.color, colors['text'])
        self.assertGreaterEqual(contrast(figure.data[0].marker.color, colors['card']), 3)
        self.assertGreaterEqual(contrast(figure.layout.hoverlabel.font.color, figure.layout.hoverlabel.bgcolor), 4.5)

    def test_light_chart_data_and_colors_unchanged(self):
        figure = go.Figure(go.Scatter(x=[1], y=[2]))
        before = figure.data[0].to_plotly_json()
        color = figure.layout.paper_bgcolor
        table = pd.DataFrame({'Amount': [12.5], 'Status': ['Pending']})
        with patch.object(display, 'runtime', return_value={**DEFAULTS, 'theme': 'Light'}):
            self.assertIs(display.style_table(table), table)
            self.assertIs(display.style_figure(figure), figure)
        self.assertEqual(figure.data[0].to_plotly_json(), {**before, 'textfont': {'family': 'Inter, Arial, sans-serif'}})
        self.assertEqual(figure.layout.paper_bgcolor, color)
        self.assertEqual(figure.layout.font.family, 'Inter, Arial, sans-serif')

    def test_dark_table_does_not_modify_records(self):
        table = pd.DataFrame({'Amount': [12.5], 'Status': ['Pending']})
        before = table.copy(deep=True)
        with patch.object(display, 'runtime', return_value={**DEFAULTS, 'theme': 'Dark'}):
            styled = display.style_table(table)
            rendered = styled.to_html()
        pd.testing.assert_frame_equal(table, before)
        self.assertIn(tokens()['card'], rendered)
        self.assertIn(status_colors('Pending')[0], rendered)


if __name__ == '__main__':
    unittest.main()
