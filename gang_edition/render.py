import datetime as dt
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from .core import safe_media, PANELS_PER_PAGE
from .styles import effective_style

FONT_DIR = Path(__file__).resolve().parent / 'fonts'

_BOLDISH = ('bold', 'bangers', 'bebas')


def font(size, name=None):
    name = name or 'DejaVuSans.ttf'
    p = FONT_DIR / name
    if not p.is_file():
        name = 'DejaVuSans-Bold.ttf' if any(b in name.lower() for b in _BOLDISH) else 'DejaVuSans.ttf'
        p = FONT_DIR / name
    if not p.is_file():
        p = FONT_DIR / 'DejaVuSans.ttf'
    return ImageFont.truetype(str(p), size)


def wrap(draw, text, face, width):
    lines = []
    for paragraph in text.splitlines() or ['']:
        line = ''
        for word in paragraph.split():
            if draw.textlength(word, font=face) > width:
                pieces = textwrap.wrap(word, width=max(8, int(width / face.size * 1.5)), break_long_words=True)
            else:
                pieces = [word]
            for piece in pieces:
                attempt = (line + ' ' + piece).strip()
                if draw.textlength(attempt, font=face) <= width:
                    line = attempt
                else:
                    if line: lines.append(line)
                    line = piece
        lines.append(line)
    return lines


def halftone(draw, x0, y0, x1, y1, color, spacing=13, radius=3):
    for yy in range(y0, y1, spacing):
        for xx in range(x0, x1, spacing):
            draw.ellipse((xx, yy, xx + radius, yy + radius), fill=color)


def action_lines(draw, cx, cy, color, count=7, length=70, spread=40):
    from math import cos, sin, pi
    for i in range(count):
        a = -pi / 2 + (i - (count - 1) / 2) * (spread / 180.0 * pi)
        draw.line((cx - cos(a) * length * 0.4, cy - sin(a) * length * 0.4,
                   cx + cos(a) * length, cy + sin(a) * length), fill=color, width=3)


def portrait(draw, cx, cy, r, character, ink):
    skin = character.get('skin', '#eccab0')
    color = character.get('color', '#cccccc')
    draw.rounded_rectangle((cx - r, cy + int(r * 0.35), cx + r, cy + int(r * 1.35)),
                           radius=int(r * 0.7), fill=color, outline=ink, width=3)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=skin, outline=ink, width=3)
    hair = character.get('hair', 0)
    if hair == 0:
        draw.pieslice((cx - r - 2, cy - r - 2, cx + r + 2, cy + 2), 180, 360, fill=ink)
    elif hair == 1:
        draw.arc((cx - r + 4, cy - r + 4, cx + r - 4, cy + 6), 180, 360, fill=ink, width=max(2, int(r * 0.32)))
    elif hair == 2:
        for off in (-int(r * 0.5), 0, int(r * 0.5)):
            draw.ellipse((cx + off - int(r * 0.26), cy - r - 2, cx + off + int(r * 0.26), cy - r + int(r * 0.5)), fill=ink)
    else:
        draw.pieslice((cx - r, cy - r, cx + r, cy + int(r * 0.15)), 180, 360, fill=ink)
    for dx in (-int(r * 0.3), int(r * 0.3)):
        draw.ellipse((cx + dx - int(r * 0.07), cy - int(r * 0.1), cx + dx + int(r * 0.07), cy + 2), fill=ink)
    if character.get('glasses'):
        for dx in (-int(r * 0.34), int(r * 0.34)):
            draw.ellipse((cx + dx - int(r * 0.24), cy - int(r * 0.34), cx + dx + int(r * 0.24), cy + int(r * 0.12)), outline=ink, width=2)
        draw.line((cx - int(r * 0.1), cy - int(r * 0.1), cx + int(r * 0.1), cy - int(r * 0.1)), fill=ink, width=2)
    draw.arc((cx - int(r * 0.3), cy - int(r * 0.05), cx + int(r * 0.3), cy + int(r * 0.4)), 10, 170, fill=ink, width=2)


def name_chip(draw, x, y, character, label, ink):
    face = font(20, 'DejaVuSans-Bold.ttf')
    tw = draw.textlength(label, font=face)
    draw.rounded_rectangle((x, y, x + tw + 28, y + 34), radius=10,
                           fill=character.get('color', '#cccccc'), outline=ink, width=3)
    draw.text((x + 14, y + 6), label, font=face, fill=ink)


def speech_bubble(draw, bx, by, bw, bh, text, face, style, tail_tip):
    draw.polygon([(bx + 26, by + bh - 2), tail_tip, (bx + 74, by + bh - 2)],
                 fill=style.bubble_fill, outline=style.bubble_outline)
    draw.rounded_rectangle((bx, by, bx + bw, by + bh), radius=style.bubble_radius,
                           fill=style.bubble_fill, outline=style.bubble_outline, width=3)
    lines = wrap(draw, text, face, bw - 52)
    shortened = len(lines) > 7
    if shortened:
        lines = lines[:6] + [lines[6].rstrip() + ' ...']
    yy = by + 22
    for line in lines[:7]:
        draw.text((bx + 26, yy), line, font=face, fill=style.ink)
        yy += 31


def _hex_rgb(hex_color):
    h = str(hex_color).lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _panels(messages):
    for i, msg in enumerate(messages):
        col, row = i % 2, i // 2
        yield msg, 70 + col * 643, 256 + row * 495, 617, 468


def build_page(messages, sheet, week, media_dir, style=None, background=None):
    style = style or effective_style()
    height = 415 + 495 * ((len(messages) + 1) // 2)
    image = Image.new('RGB', (1400, height), style.page_bg)
    if background is not None:
        image.paste(ImageOps.fit(background.convert('RGB'), (1400, height)), (0, 0))
        overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        for _, x, y, w, h in _panels(messages):
            odraw.rounded_rectangle((x, y, x + w, y + h), radius=style.panel_radius,
                                    fill=(*_hex_rgb(style.panel_bg), 215))
        image = Image.alpha_composite(image.convert('RGBA'), overlay).convert('RGB')
    draw = ImageDraw.Draw(image)

    if style.halftone:
        halftone(draw, 0, 20, 1400, 48, style.accent, spacing=13, radius=3)
    title_face = font(int(58 * style.title_scale), style.title_font)
    draw.text((70, 63), 'THE GANG EDITION', font=title_face, fill=style.title_color)
    if style.action_lines:
        action_lines(draw, 1290, 110, style.accent)
    end = (dt.date.fromisoformat(week) + dt.timedelta(days=6)).isoformat()
    draw.text((74, 141), f'{week} to {end}  |  A week worth keeping', font=font(24, style.body_font), fill=style.subtitle_color)
    draw.text((74, 182), 'Illustrated recap. Reviewed source text. Private by default.', font=font(22, style.body_font), fill=style.subtitle_color)
    draw.line((70, 226, 1330, 226), fill=style.ink, width=3)

    body = font(24, style.body_font)
    for i, (msg, x, y, w, h) in enumerate(_panels(messages), 1):
        character = sheet.get(msg['author'], {'label': msg['author']})
        draw.rounded_rectangle((x, y, x + w, y + h), radius=style.panel_radius,
                               outline=style.panel_border, width=3)
        draw.text((x + 20, y + 16), f'{i:02} / ' + msg['timestamp'][:10],
                  font=font(20, style.body_bold), fill=style.subtitle_color)
        name_chip(draw, x + 20, y + 44, character, character.get('label', msg['author']), style.ink)
        speech_bubble(draw, x + 20, y + 88, w - 40, 250, msg['text'], body, style, (x + 42, y + 372))
        portrait(draw, x + 80, y + 410, 40, character, style.ink)
        attachment = msg.get('attachment')
        if media_dir and attachment and Path(attachment).suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp'):
            p = safe_media(media_dir, attachment)
            if p.is_file():
                with Image.open(p) as photo:
                    photo = ImageOps.fit(photo.convert('RGB'), (96, 72))
                image.paste(photo, (x + w - 120, y + 386))
    draw.line((70, height - 120, 1330, height - 120), fill=style.accent, width=2)
    draw.text((74, height - 96), 'Recurring cast, not inferred likenesses. No invented events. Share only with permission.',
              font=font(21, style.body_font), fill=style.subtitle_color)
    return image


def render_page(messages, sheet, week, out, media_dir, style=None):
    style = style or effective_style()
    image = build_page(messages, sheet, week, media_dir, style)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    image.save(out / 'comic.png')
    image.save(out / 'comic.pdf', 'PDF', resolution=150)
    return out / 'comic.png'


def _chunks(messages):
    return [messages[i:i + PANELS_PER_PAGE] for i in range(0, len(messages), PANELS_PER_PAGE)]


def save_pages(pages, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if len(pages) == 1:
        pages[0].save(out / 'comic.png')
        pages[0].save(out / 'comic.pdf', 'PDF', resolution=150)
        return [out / 'comic.png']
    pngs = []
    for i, page in enumerate(pages, 1):
        p = out / f'comic-{i}.png'
        page.save(p)
        pngs.append(p)
    pages[0].save(out / 'comic.pdf', 'PDF', resolution=150, save_all=True, append_images=pages[1:])
    return pngs


def render_pages(messages, sheet, week, out, media_dir, style=None):
    style = style or effective_style()
    pages = [build_page(chunk, sheet, week, media_dir, style) for chunk in _chunks(messages)]
    return save_pages(pages, out)


def overlay_page(art, messages, sheet, week, style=None):
    style = style or effective_style()
    return build_page(messages, sheet, week, None, style, background=art)
