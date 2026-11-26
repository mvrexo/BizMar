import unittest
import plotly.graph_objects as go
from typography import style_chart_fonts


class ChartTypographyTests(unittest.TestCase):
    def test_cartesian_chart_fonts_do_not_change_data_or_colors(self):
        figure=go.Figure(go.Scatter(x=['Jan','Feb'],y=[10,20],line_color='#C57B8F'))
        style_chart_fonts(figure)
        self.assertEqual(list(figure.data[0].y),[10,20])
        self.assertEqual(figure.data[0].line.color,'#C57B8F')
        self.assertIn('Inter',figure.layout.font.family)
        self.assertIn('Plus Jakarta Sans',figure.layout.title.font.family)
        self.assertEqual(figure.layout.hoverlabel.font.size,13)

    def test_pie_labels_and_annotations_use_body_font(self):
        figure=go.Figure(go.Pie(labels=['A','B'],values=[1,2]))
        figure.add_annotation(text='Total',x=.5,y=.5,font_size=24)
        style_chart_fonts(figure)
        self.assertIn('Inter',figure.data[0].insidetextfont.family)
        self.assertIn('Inter',figure.data[0].outsidetextfont.family)
        self.assertEqual(figure.layout.annotations[0].font.size,24)
        self.assertIn('Inter',figure.layout.annotations[0].font.family)
