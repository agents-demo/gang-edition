import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Style:
    key: str
    name: str
    page_bg: str
    ink: str
    accent: str
    panel_bg: str
    panel_border: str
    bubble_fill: str
    bubble_outline: str
    title_color: str
    subtitle_color: str
    title_font: str
    body_font: str
    body_bold: str
    halftone: bool = False
    action_lines: bool = False
    bubble_radius: int = 18
    panel_radius: int = 18
    title_scale: float = 1.0
    desc: str = ''


STYLES = {
    'cartoon': Style(
        key='cartoon', name='Cartoon',
        page_bg='#f4efec', ink='#251f21', accent='#73a89a',
        panel_bg='#f4efec', panel_border='#251f21',
        bubble_fill='#ffffff', bubble_outline='#251f21',
        title_color='#251f21', subtitle_color='#585254',
        title_font='DejaVuSans-Bold.ttf', body_font='DejaVuSans.ttf', body_bold='DejaVuSans-Bold.ttf',
        desc='clean modern cartoon',
    ),
    'marvel': Style(
        key='marvel', name='Marvel',
        page_bg='#f7e9d9', ink='#191019', accent='#c11e2b',
        panel_bg='#fdf6ec', panel_border='#191019',
        bubble_fill='#ffffff', bubble_outline='#191019',
        title_color='#c11e2b', subtitle_color='#6b2430',
        title_font='Bangers-Regular.ttf', body_font='DejaVuSans.ttf', body_bold='DejaVuSans-Bold.ttf',
        halftone=True, action_lines=True, bubble_radius=12, panel_radius=10, title_scale=1.15,
        desc='vintage superhero comic book, bold halftone dots, dynamic diagonal panels, high-contrast inks, action lines, classic American comic style',
    ),
    'dc': Style(
        key='dc', name='DC',
        page_bg='#14181f', ink='#e8edf3', accent='#2f7bd9',
        panel_bg='#1d232d', panel_border='#2f7bd9',
        bubble_fill='#10141a', bubble_outline='#e8edf3',
        title_color='#7fb2f0', subtitle_color='#9aa7b8',
        title_font='BebasNeue-Regular.ttf', body_font='DejaVuSans.ttf', body_bold='DejaVuSans-Bold.ttf',
        action_lines=True, bubble_radius=6, panel_radius=4, title_scale=1.1,
        desc='dark cinematic DC superhero comic, moody, angular panels, deep shadows, dramatic lighting, gritty, high contrast',
    ),
    'ghibli': Style(
        key='ghibli', name='Ghibli',
        page_bg='#eaf3ee', ink='#2c3a34', accent='#e8a87c',
        panel_bg='#fdfbf6', panel_border='#2c3a34',
        bubble_fill='#ffffff', bubble_outline='#2c3a34',
        title_color='#3a6b57', subtitle_color='#6b7a70',
        title_font='ComicNeue-Bold.ttf', body_font='ComicNeue-Regular.ttf', body_bold='ComicNeue-Bold.ttf',
        bubble_radius=26, panel_radius=24, title_scale=1.0,
        desc='Studio Ghibli style, soft hand-drawn watercolor, warm pastel colors, gentle rounded shapes, whimsical and cozy',
    ),
}

DEFAULT_STYLE = 'marvel'


def resolve_style(key):
    if key is None:
        key = DEFAULT_STYLE
    key = str(key).lower()
    if key not in STYLES:
        raise ValueError(f'Unknown style "{key}". Choose from: {", ".join(sorted(STYLES))}.')
    return STYLES[key]


def effective_style(explicit=None, group_default=None):
    key = explicit or group_default or os.getenv('GANG_DEFAULT_STYLE') or DEFAULT_STYLE
    return resolve_style(key)
