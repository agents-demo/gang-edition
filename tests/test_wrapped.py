import base64
import datetime as dt
import io
import tempfile
import unittest
from pathlib import Path

from gang_edition.stats import empty_stats, apply_message, apply_parsed
from gang_edition.wrapped import period_range, compute_awards
from gang_edition.core import character_sheet


class TestStats(unittest.TestCase):
    def test_apply_message_aggregates(self):
        s = empty_stats()
        apply_message(s, {'author': 'A', 'timestamp': '2026-10-05T02:30:00', 'text': 'Hello world!! \U0001F600', 'kind': 'text'})
        apply_message(s, {'author': 'A', 'timestamp': '2026-10-05T03:00:00', 'text': 'night owl', 'kind': 'text'})
        apply_message(s, {'author': 'A', 'timestamp': '2026-10-05T10:00:00', 'text': '', 'kind': 'voice'})
        a = s['by_author']['A']['days']['2026-10-05']
        self.assertEqual(a['messages'], 3)
        self.assertEqual(a['words'], 5)
        self.assertEqual(a['night'], 2)
        self.assertEqual(a['exclaim'], 2)
        self.assertEqual(a['emoji'], 1)
        self.assertEqual(a['voice'], 1)
        self.assertEqual(s['by_day']['2026-10-05'], 3)
        self.assertEqual(s['emoji']['\U0001F600'], 1)
        self.assertEqual(s['since'], '2026-10-05T02:30:00')

    def test_apply_parsed_kind(self):
        s = empty_stats()
        parsed = {'messages': [
            {'author': 'A', 'timestamp': '2026-10-05T10:00:00', 'text': 'hi', 'attachment': 'pic.jpg'},
            {'author': 'A', 'timestamp': '2026-10-05T10:01:00', 'text': 'yo', 'attachment': 'note.opus'},
        ]}
        apply_parsed(s, parsed)
        a = s['by_author']['A']['days']['2026-10-05']
        self.assertEqual(a['photo'], 1)
        self.assertEqual(a['voice'], 1)


class TestWrapped(unittest.TestCase):
    def test_period_range(self):
        today = dt.date(2026, 10, 14)
        self.assertEqual(period_range('year', today)[:2], (dt.date(2026, 1, 1), today))
        self.assertIsNone(period_range('all', today)[0])
        self.assertEqual(period_range('2024', today)[:2], (dt.date(2024, 1, 1), dt.date(2024, 12, 31)))
        with self.assertRaises(ValueError):
            period_range('bogus')

    def test_compute_awards(self):
        s = empty_stats()
        for i in range(20):
            apply_message(s, {'author': 'A', 'timestamp': f'2026-06-01T10:{i % 60:02d}:00', 'text': 'great!!', 'kind': 'text'})
        for _ in range(5):
            apply_message(s, {'author': 'B', 'timestamp': '2026-06-01T02:00:00', 'text': '', 'kind': 'voice'})
        r = compute_awards(s, 'all')
        awards = {a['award']: a for a in r['awards']}
        self.assertEqual(r['summary']['messages'], 25)
        self.assertEqual(r['summary']['active_members'], 2)
        self.assertEqual(awards['Most Active']['name'], 'A')
        self.assertEqual(awards['Voice-Note MVP']['name'], 'B')
        self.assertEqual(awards['Hype Machine']['name'], 'A')
        self.assertEqual(awards['Night Owl']['name'], 'B')

    def test_period_filtering(self):
        s = empty_stats()
        apply_message(s, {'author': 'A', 'timestamp': '2024-03-01T10:00:00', 'text': 'old', 'kind': 'text'})
        apply_message(s, {'author': 'A', 'timestamp': '2026-03-01T10:00:00', 'text': 'new', 'kind': 'text'})
        self.assertEqual(compute_awards(s, '2024')['summary']['messages'], 1)
        self.assertEqual(compute_awards(s, '2026')['summary']['messages'], 1)
        self.assertEqual(compute_awards(s, 'all')['summary']['messages'], 2)


class TestAvatar(unittest.TestCase):
    def test_character_sheet_preserves_avatar(self):
        sheet = character_sheet({'Alex': {'avatar': 'avatars/alex.png', 'likeness': True}}, {})
        self.assertEqual(sheet['Alex']['avatar'], 'avatars/alex.png')
        self.assertTrue(sheet['Alex']['likeness'])

    def test_character_sheet_drops_avatar_when_removed(self):
        existing = {'Alex': {'color': '#73a89a', 'hair': 0, 'glasses': False, 'label': 'Alex',
                             'avatar': 'avatars/alex.png', 'likeness': True}}
        sheet = character_sheet({'Alex': {}}, existing)
        self.assertNotIn('avatar', sheet['Alex'])
        self.assertNotIn('likeness', sheet['Alex'])

    def test_render_wrapped(self):
        from gang_edition.render import render_wrapped
        from gang_edition.styles import resolve_style
        s = empty_stats()
        apply_message(s, {'author': 'A', 'timestamp': '2026-10-05T10:00:00', 'text': 'hello there!!', 'kind': 'text'})
        apply_message(s, {'author': 'B', 'timestamp': '2026-10-05T02:00:00', 'text': '', 'kind': 'voice'})
        r = compute_awards(s, 'all')
        sheet = character_sheet({'A': {}, 'B': {}}, {})
        with tempfile.TemporaryDirectory() as d:
            png = render_wrapped(r, sheet, d, resolve_style('cartoon'))
            self.assertTrue(Path(png).exists())
            self.assertTrue((Path(d) / 'wrapped.pdf').exists())

    def test_reference_data_urls_uses_avatar(self):
        from gang_edition.img import _reference_data_urls
        from PIL import Image
        sheet = character_sheet({'A': {}, 'B': {}}, {})
        sheet['A']['avatar'] = 'a.png'
        with tempfile.TemporaryDirectory() as d:
            av = Path(d)
            Image.new('RGB', (20, 20), 'red').save(av / 'a.png')
            refs = _reference_data_urls(sheet, ['A', 'B'], avatars_dir=av)
            self.assertEqual(len(refs), 2)
            a0 = Image.open(io.BytesIO(base64.b64decode(refs[0].split(',', 1)[1])))
            a1 = Image.open(io.BytesIO(base64.b64decode(refs[1].split(',', 1)[1])))
            self.assertEqual(a0.size, (20, 20))      # the avatar file
            self.assertEqual(a1.size, (384, 384))    # the procedural card


if __name__ == '__main__':
    unittest.main()
