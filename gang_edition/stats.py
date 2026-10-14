"""Rolling aggregate statistics for The Gang Edition.

Stats are kept in a separate ``stats.json`` per group so they survive the raw
message retention window: ``state.json`` is pruned after ``GANG_RETENTION_DAYS``
but ``stats.json`` is never pruned. It stores only aggregate counts (and top
emoji), never raw message text.
"""
import datetime as dt
import re

# Common emoji blocks (a light heuristic, stdlib-only).
EMOJI = re.compile(
    '[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF'
    '\U00002190-\U000021FF\U0000FE00-\U0000FE0F\U0001F1E6-\U0001F1FF]'
)

COUNTERS = ('messages', 'chars', 'words', 'voice', 'photo', 'video',
            'night', 'exclaim', 'question', 'emoji')


def empty_stats():
    return {'since': None, 'updated': None, 'by_author': {}, 'by_day': {}, 'emoji': {}}


def _zero():
    return dict.fromkeys(COUNTERS, 0)


def _hour(ts):
    if len(ts) >= 13 and ts[10] == 'T':
        try:
            return int(ts[11:13])
        except ValueError:
            return 0
    return 0


def apply_message(stats, m):
    """Accumulate one message into ``stats``. ``m`` needs author, timestamp,
    text and kind (text/voice/photo/video)."""
    ts = str(m['timestamp'])
    if stats['since'] is None or ts < stats['since']:
        stats['since'] = ts
    if stats['updated'] is None or ts > stats['updated']:
        stats['updated'] = ts
    author = m['author']
    text = str(m.get('text') or '')
    kind = m.get('kind', 'text')
    entry = stats['by_author'].setdefault(author, {'first_seen': ts, 'last_seen': ts, 'days': {}})
    if ts < entry['first_seen']:
        entry['first_seen'] = ts
    if ts > entry['last_seen']:
        entry['last_seen'] = ts
    day = ts[:10]
    d = entry['days'].setdefault(day, _zero())
    d['messages'] += 1
    d['chars'] += len(text)
    d['words'] += len(text.split())
    if kind == 'voice':
        d['voice'] += 1
    elif kind == 'photo':
        d['photo'] += 1
    elif kind == 'video':
        d['video'] += 1
    d['exclaim'] += text.count('!')
    d['question'] += text.count('?')
    d['emoji'] += len(EMOJI.findall(text))
    if 0 <= _hour(ts) < 5:
        d['night'] += 1
    stats['by_day'][day] = stats['by_day'].get(day, 0) + 1
    for ch in EMOJI.findall(text):
        stats['emoji'][ch] = stats['emoji'].get(ch, 0) + 1
    return stats


def _kind_for(m):
    if m.get('kind') in ('voice', 'photo', 'video'):
        return m['kind']
    att = (m.get('attachment') or '').lower()
    if att.endswith(('.opus', '.ogg', '.m4a', '.mp3')):
        return 'voice'
    if att.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
        return 'photo'
    if att.endswith(('.mp4', '.mov')):
        return 'video'
    return 'text'


def apply_parsed(stats, parsed):
    """Accumulate a whole parsed export (WhatsApp path)."""
    for m in parsed['messages']:
        apply_message(stats, {'author': m['author'], 'timestamp': m['timestamp'],
                              'text': m['text'], 'kind': _kind_for(m)})
    return stats
