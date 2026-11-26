"""Shared chart typography; no data, theme-color or financial changes."""
BODY_FONT='Inter, Arial, sans-serif'
HEADING_FONT='Plus Jakarta Sans, Arial, sans-serif'


def style_chart_fonts(figure):
    from display_preferences import tr, runtime
    figure.update_layout(font_family=BODY_FONT,font_size=14,title_font_family=HEADING_FONT,title_font_size=19,
                         legend_font_family=BODY_FONT,legend_font_size=14,legend_title_font_family=BODY_FONT,
                         hoverlabel_font_family=BODY_FONT,hoverlabel_font_size=13)
    figure.update_xaxes(tickfont_family=BODY_FONT,tickfont_size=14,title_font_family=BODY_FONT)
    figure.update_yaxes(tickfont_family=BODY_FONT,tickfont_size=14,title_font_family=BODY_FONT)
    for trace in figure.data:
        if 'textfont' in trace._valid_props:trace.update(textfont_family=BODY_FONT)
        if 'insidetextfont' in trace._valid_props:trace.update(insidetextfont_family=BODY_FONT)
        if 'outsidetextfont' in trace._valid_props:trace.update(outsidetextfont_family=BODY_FONT)
        if 'colorbar' in trace._valid_props:trace.update(colorbar_tickfont_family=BODY_FONT,colorbar_tickfont_size=14,colorbar_title_font_family=BODY_FONT)
    if figure.layout.to_plotly_json().get('coloraxis'):
        figure.update_coloraxes(colorbar_tickfont_family=BODY_FONT,colorbar_tickfont_size=14,colorbar_title_font_family=BODY_FONT)
    for annotation in figure.layout.annotations or ():
        annotation.font.family=BODY_FONT
    if runtime().get('language')=='Bahasa Melayu':
        import re
        for trace in figure.data:
            if trace.name:trace.name=tr(trace.name)
            if 'hovertemplate' in trace._valid_props and isinstance(trace.hovertemplate,str):
                trace.hovertemplate=re.sub(r'(^|>)([A-Za-z][A-Za-z /()%-]+):',lambda m:m[1]+tr(m[2])+':',trace.hovertemplate)
        for key in ('xaxis','yaxis','xaxis2','yaxis2'):
            if key not in figure.layout:continue
            axis=figure.layout[key];title=axis.title.text or ''
            if any(term in title.lower() for term in ('status','payment','fulfilment','fulfillment')):
                values=[]
                for trace in figure.data:
                    series=getattr(trace,'x' if key.startswith('x') else 'y',None)
                    for value in (series if series is not None else ()):
                        if isinstance(value,str) and value not in values:values.append(value)
                if values:axis.update(tickmode='array',tickvals=values,ticktext=[tr(value) for value in values])
            if title:axis.title.text=tr(title)
        if figure.layout.title.text:figure.layout.title.text=tr(figure.layout.title.text)
        if figure.layout.legend.title.text:figure.layout.legend.title.text=tr(figure.layout.legend.title.text)
        for key in ('coloraxis','coloraxis2'):
            if key in figure.layout and figure.layout[key].colorbar.title.text:
                figure.layout[key].colorbar.title.text=tr(figure.layout[key].colorbar.title.text)
        for annotation in figure.layout.annotations or ():
            if annotation.text:annotation.text=tr(annotation.text)
    return figure
