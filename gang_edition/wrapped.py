"""Gang Wrapped: turn aggregate stats into a shareable awards recap."""
import datetime as dt
import re

_COUNTERS = ('messages', 'chars', 'words', 'voice', 'photo', 'video',
             'night', 'exclaim', 'question', 'emoji')


def period_range(arg='year', today=None):
    """Resolve a period string to (start, end, label). 'year' means the current
    calendar year, 'all' means the whole ledger, and 'YYYY' a specific year."""
    today = today or dt.date.today()
    arg = (arg or 'year').strip().lower()
    if arg in ('year', ''):
        return dt.date(today.year, 1, 1), today, str(today.year)
    if arg == 'all':
        return None, today, 'all time'
    if re.fullmatch(r'\d{4}', arg):
        year = int(arg)
        return dt.date(year, 1, 1), min(today, dt.date(year, 12, 31)), arg
    raise ValueError('Period must be "year", "all", or a year such as 2026.')


def _zero():
    return dict.fromkeys(_COUNTERS, 0)


def aggregate_author(entry, start, end):
    out = _zero()
    for day, c in entry.get('days', {}).items():
        date = dt.date.fromisoformat(day)
        if (start is None or date >= start) and date <= end:
            for k in out:
                out[k] += c.get(k, 0)
    return out


def compute_awards(stats, period='year'):
    """Return {'summary', 'awards', 'label', 'start', 'end'} for a period."""
    start, end, label = period_range(period)
    rows = []
    totals = _zero()
    for name, entry in stats.get('by_author', {}).items():
        agg = aggregate_author(entry, start, end)
        if agg['messages'] == 0:
            continue
        rows.append((name, agg))
        for k in totals:
            totals[k] += agg[k]

    awards = []
    if rows:
        def pick(metric, award, fmt):
            best = max(rows, key=lambda r: r[1][metric])
            if best[1][metric] > 0:
                awards.append({'award': award, 'name': best[0], 'detail': fmt(best[1][metric])})

        pick('messages', 'Most Active', lambda n: f'{n} messages')
        pick('night', 'Night Owl', lambda n: f'{n} messages after midnight')
        pick('exclaim', 'Hype Machine', lambda n: f'{n} exclamation marks')
        pick('question', 'The Questioner', lambda n: f'{n} questions asked')
        pick('voice', 'Voice-Note MVP', lambda n: f'{n} voice notes')
        pick('photo', 'Photo MVP', lambda n: f'{n} photos')
        essay = max(rows, key=lambda r: (r[1]['chars'] / r[1]['messages']) if r[1]['messages'] else 0)
        if essay[1]['messages'] >= 3:
            awards.append({'award': 'The Essayist', 'name': essay[0],
                           'detail': f"{essay[1]['chars'] // essay[1]['messages']} chars per message"})
        quiet = min(rows, key=lambda r: r[1]['messages'])
        if quiet[1]['messages'] < totals['messages'] / max(1, len(rows)):
            awards.append({'award': 'The Quiet Legend', 'name': quiet[0],
                           'detail': f'{quiet[1]["messages"]} messages'})
        emoji_best = max(rows, key=lambda r: r[1]['emoji'])
        if emoji_best[1]['emoji'] > 0:
            awards.append({'award': 'Emoji Poet', 'name': emoji_best[0],
                           'detail': f'{emoji_best[1]["emoji"]} emoji'})

    by_day = {d: n for d, n in stats.get('by_day', {}).items()
              if (start is None or dt.date.fromisoformat(d) >= start) and dt.date.fromisoformat(d) <= end}
    busiest = max(by_day, key=lambda d: by_day[d], default=None)
    top_emoji = max(stats.get('emoji', {}), key=lambda c: stats['emoji'][c], default=None)
    summary = {
        'messages': totals['messages'],
        'words': totals['words'],
        'photos': totals['photo'],
        'voice': totals['voice'],
        'video': totals['video'],
        'active_members': len(rows),
        'busiest_day': busiest,
        'busiest_count': by_day.get(busiest) if busiest else 0,
        'top_emoji': top_emoji,
        'top_emoji_count': stats.get('emoji', {}).get(top_emoji) if top_emoji else 0,
    }
    return {'summary': summary, 'awards': awards, 'label': label, 'start': start, 'end': end}
