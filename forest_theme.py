"""Shared presentation tokens from the dark stylesheet; no business or state changes."""
from functools import lru_cache
from pathlib import Path
import re


@lru_cache(maxsize=1)
def tokens():
    css = (Path(__file__).parent / 'styles' / 'dark.css').read_text(encoding='utf-8')
    return dict(re.findall(r'--forest-([\w-]+):\s*(#[0-9A-Fa-f]{6})\s*;', css))


def status_colors(label):
    palette = tokens()
    tone = {
        'Pending': 'pending', 'Partial': 'confirmed', 'Confirmed': 'confirmed',
        'Preparing': 'preparing', 'Unpaid': 'preparing', 'Ready': 'ready',
        'Completed': 'ready', 'Paid': 'ready', 'Cancelled': 'cancelled',
        'Overdue': 'preparing', 'Due today': 'confirmed', 'Upcoming': 'ready',
        'No deadline': 'pending',
    }.get(str(label).lstrip('\u25cf ').strip())
    return (palette[tone + '-bg'], palette[tone + '-text']) if tone else (palette['card'], palette['text'])
