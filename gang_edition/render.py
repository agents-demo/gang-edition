import datetime as dt
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from .core import safe_media

INK = '#251f21'
FONT_DIR = Path(__file__).resolve().parent / 'fonts'

def font(size, bold=False):
    name = 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'
    return ImageFont.truetype(str(FONT_DIR / name), size)

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

def avatar(draw, x, y, character, scale=1):
    # Stable stylized avatars, not inferred physical likenesses.
    s = scale
    box = lambda a,b,c,d: (x+a*s,y+b*s,x+c*s,y+d*s)
    draw.rounded_rectangle(box(-68,35,68,144), radius=int(28*s), fill=character['color'], outline=INK, width=max(1,int(3*s)))
    draw.line([x-42*s,y+136*s,x-48*s,y+187*s], fill=INK,width=int(10*s))
    draw.line([x+42*s,y+136*s,x+48*s,y+187*s], fill=INK,width=int(10*s))
    draw.ellipse(box(-47,-72,47,30),fill='#eccab0',outline=INK,width=max(1,int(3*s)))
    hair = character['hair']
    if hair == 0:
        draw.pieslice(box(-48,-84,48,3),180,350,fill=INK)
    elif hair == 1:
        draw.arc(box(-44,-74,42,2),180,350,fill=INK,width=int(18*s))
    elif hair == 2:
        for offset in (-30,-10,10,30): draw.ellipse(box(offset-15,-82,offset+15,-47),fill=INK)
    else:
        draw.rounded_rectangle(box(-47,-82,47,-48),radius=int(12*s),fill=INK)
    for dx in (-17,17):
        draw.ellipse(box(dx-3,-23,dx+3,-17),fill=INK)
    if character['glasses']:
        for dx in (-18,18): draw.ellipse(box(dx-14,-35,dx+14,-9),outline=INK,width=max(1,int(2*s)))
        draw.line(box(-4,-22,4,-22),fill=INK,width=max(1,int(2*s)))
    draw.arc(box(-17,-12,17,12),10,165,fill=INK,width=max(1,int(3*s)))

def render_page(messages, sheet, week, out, media_dir):
    height = 415 + 495 * ((len(messages)+1)//2)
    image = Image.new('RGB',(1400,height),'#f4efec')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((28,28,1372,height-28),radius=24,fill='white')
    draw.text((70,63),'THE GANG EDITION',font=font(58,True),fill=INK)
    end = (dt.date.fromisoformat(week)+dt.timedelta(days=6)).isoformat()
    draw.text((74,141),f'{week} to {end}  |  A week worth keeping',font=font(24),fill='#585254')
    draw.text((74,182),'Illustrated recap. Reviewed source text. Private by default.',font=font(22),fill='#585254')
    draw.line((70,226,1330,226),fill=INK,width=3)
    for i,msg in enumerate(messages):
        col, row = i%2,i//2
        x,y = 70+col*643,256+row*495
        w,h = 617,468
        draw.rounded_rectangle((x,y,x+w,y+h),radius=18,fill='#f4efec',outline=INK,width=3)
        draw.text((x+22,y+19),f'{i+1:02} / '+msg['timestamp'][:10],font=font(20,True),fill='#585254')
        draw.rounded_rectangle((x+20,y+60,x+w-20,y+249),radius=16,fill='white',outline=INK,width=2)
        lines = wrap(draw,msg['text'],font(25),w-76)
        shortened = len(lines)>5
        if shortened: lines = lines[:4]+[lines[4].rstrip()+' ...']
        for j,line in enumerate(lines[:5]):
            draw.text((x+38,y+74+j*31),line,font=font(25),fill=INK)
        draw.polygon([(x+105,y+249),(x+115,y+272),(x+140,y+249)],fill='white',outline=INK)
        avatar(draw,x+146,y+336,sheet[msg['author']],.69)
        name_lines=wrap(draw,sheet[msg['author']].get('label',msg['author']),font(23,True),265)
        for j,line in enumerate(name_lines[:2]): draw.text((x+255,y+303+j*28),line,font=font(23,True),fill=INK)
        note = msg.get('media_note') or 'From the group chat'
        draw.text((x+255,y+371),note,font=font(17),fill='#585254')
        draw.text((x+255,y+402),'Text abridged; see transcript' if shortened else 'Reviewed sidecar text' if msg.get('media_note') else 'Verbatim quote',font=font(17),fill='#585254')
        attachment=msg.get('attachment')
        if attachment and Path(attachment).suffix.lower() in ('.jpg','.jpeg','.png','.webp'):
            p=safe_media(media_dir,attachment)
            if p.is_file():
                with Image.open(p) as photo:
                    photo=ImageOps.fit(photo.convert('RGB'),(96,72))
                image.paste(photo,(x+w-120,y+386))
    draw.line((70,height-120,1330,height-120),fill='#eae9ea',width=2)
    draw.text((74,height-96),'Recurring cast, not inferred likenesses. No invented events. Share only with permission.',font=font(21),fill='#585254')
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    image.save(out/'comic.png')
    image.save(out/'comic.pdf','PDF',resolution=150)
    return out/'comic.png'
