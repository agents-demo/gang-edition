"""Telegram group-bot adapter for The Gang Edition.

The bot reads group messages through the official Bot API (long polling), keeps
ONLY messages from members who opted in with /consent, and feeds them to the
same moment-picking, consent-gate and renderer used by the WhatsApp-export path.
Nothing here talks to Telegram unless you run `telegram-run` with a real token.
"""
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from .core import GateError, load, save, prepare, check_consent, digest
from .styles import STYLES, DEFAULT_STYLE, effective_style

HELP = (
    "The Gang Edition: a weekly comic page from this group's best moments.\n\n"
    "Nothing is stored about you until you opt in. Members who do not opt in are left out: "
    "their messages are not kept and they are not drawn.\n\n"
    "/consent - opt in (store my text messages here, draw me in the comic)\n"
    "/cloudok - also allow my text/voice to be sent to the group's AI provider (optional)\n"
    "/cloudno - withdraw cloud permission\n"
    "/revoke - opt out and delete everything stored about me\n"
    "/roster - who has opted in\n"
    "/status - what the bot has stored\n"
    "/transcript <text> - reply to your own voice message with its transcript\n"
    "/describe <text> - reply to your own photo with a description\n"
    "/styles - list available comic styles\n"
    "Admins: /comic [YYYY-MM-DD] [cloud] [style] picks moments for review, /approve [numbers] draws and posts, "
    "/style <name> sets the default style, /rename <name> <label> gives a member a display name."
)

PRIVACY_WARNING = (
    "I have not seen any normal (non-command) messages yet. In BotFather, run /setprivacy -> Disable "
    "for this bot, then remove and re-add it to the group, or make it a group admin. Otherwise Telegram only "
    "shows me commands."
)


class TelegramError(RuntimeError):
    pass


def redact(text, token):
    return str(text).replace(token, '<token>') if token else str(text)


class TelegramAPI:
    """Minimal official Bot API client (stdlib only). Needs a real token."""

    def __init__(self, token, base='https://api.telegram.org'):
        if not token or not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}', token):
            raise TelegramError('TELEGRAM_BOT_TOKEN is missing or malformed. Create a bot with @BotFather and put the token in .env.')
        self.token = token
        self.base = base.rstrip('/')

    def call(self, method, params=None, timeout=40, files=None):
        url = f'{self.base}/bot{self.token}/{method}'
        if files:
            boundary = uuid.uuid4().hex
            body = b''
            for k, v in (params or {}).items():
                body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
            for k, path in files.items():
                name = Path(path).name
                body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\n'
                         'Content-Type: application/octet-stream\r\n\r\n').encode() + Path(path).read_bytes() + b'\r\n'
            body += f'--{boundary}--\r\n'.encode()
            req = urllib.request.Request(url, data=body, headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
        else:
            req = urllib.request.Request(url, data=json.dumps(params or {}).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise TelegramError(redact(f'{method} failed: {e}', self.token)) from None
        if not data.get('ok'):
            raise TelegramError(redact(f"{method} refused: {data.get('description')}", self.token))
        return data['result']

    def get_me(self): return self.call('getMe')
    def get_updates(self, offset, timeout=30):
        return self.call('getUpdates', {'offset': offset, 'timeout': timeout, 'allowed_updates': ['message', 'edited_message', 'my_chat_member']}, timeout=timeout + 15)
    def send_message(self, chat_id, text, reply_to=None):
        p = {'chat_id': chat_id, 'text': text[:4000]}
        if reply_to: p['reply_to_message_id'] = reply_to
        return self.call('sendMessage', p)
    def send_photo(self, chat_id, path, caption=''):
        return self.call('sendPhoto', {'chat_id': chat_id, 'caption': caption}, files={'photo': path})
    def send_document(self, chat_id, path, caption=''):
        return self.call('sendDocument', {'chat_id': chat_id, 'caption': caption}, files={'document': path})
    def is_admin(self, chat_id, user_id):
        try:
            return self.call('getChatMember', {'chat_id': chat_id, 'user_id': user_id})['status'] in ('creator', 'administrator')
        except TelegramError:
            return False
    def download(self, file_id):
        info = self.call('getFile', {'file_id': file_id})
        if info.get('file_size', 0) > 20_000_000:
            raise TelegramError('File too large.')
        with urllib.request.urlopen(f"{self.base}/file/bot{self.token}/{info['file_path']}", timeout=60) as r:
            return r.read()


class OfflineAPI:
    """Fake API for tests and the offline demo: records everything, touches no network."""

    def __init__(self, admins=(), files=None):
        self.sent, self.admins, self.files = [], set(admins), files or {}

    def send_message(self, chat_id, text, reply_to=None): self.sent.append(('text', chat_id, text))
    def send_photo(self, chat_id, path, caption=''): self.sent.append(('photo', chat_id, str(path)))
    def send_document(self, chat_id, path, caption=''): self.sent.append(('document', chat_id, str(path)))
    def is_admin(self, chat_id, user_id): return user_id in self.admins
    def download(self, file_id): return self.files[file_id]
    def texts(self): return [s[2] for s in self.sent if s[0] == 'text']


def display_name(user):
    name = ' '.join(x for x in (user.get('first_name'), user.get('last_name')) if x).strip()
    return name or ('@' + user['username'] if user.get('username') else f"user{user['id']}")


def iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).replace(tzinfo=None).isoformat()


class Store:
    def __init__(self, workspace='workspace', retention_days=None):
        self.root = Path(workspace) / 'telegram'
        self.retention_days = int(retention_days or os.getenv('GANG_RETENTION_DAYS', 35))

    def dir(self, chat_id): return self.root / str(chat_id)

    def state(self, chat_id, title=''):
        p = self.dir(chat_id) / 'state.json'
        if p.exists():
            s = load(p)
            if title: s['title'] = title
            return s
        return {'chat_id': chat_id, 'title': title, 'members': {}, 'messages': [], 'pending': None, 'seen_plain': False}

    def save(self, state):
        cutoff = (dt.datetime.utcnow() - dt.timedelta(days=self.retention_days)).isoformat()
        state['messages'] = [m for m in state['messages'] if m['timestamp'] >= cutoff]
        save(self.dir(state['chat_id']) / 'state.json', state)

    def groups(self):
        out = []
        if self.root.is_dir():
            for p in sorted(self.root.glob('*/state.json')):
                s = load(p)
                out.append({'chat_id': s['chat_id'], 'title': s.get('title', ''), 'members': len(s['members']), 'messages': len(s['messages'])})
        return out


def unique_names(members):
    names, count = {}, {}
    for uid, m in members.items():
        count[m['name']] = count.get(m['name'], 0) + 1
    for uid, m in members.items():
        names[uid] = m['name'] if count[m['name']] == 1 else f"{m['name']} (#{str(uid)[-4:]})"
    return names


def build_inputs(state):
    """Turn stored Telegram state into the (parsed, consent) pair the core pipeline expects.
    The roster is the set of opted-in members: Telegram bots cannot list a group's members, so people
    who never opted in are excluded rather than asked."""
    members = {u: m for u, m in state['members'].items() if m.get('local_processing') and m.get('comic_portrayal')}
    names = unique_names(members)
    if len(members) < 2:
        raise GateError('At least two members must opt in with /consent first.')
    consent = {'roster_confirmed_complete': True, 'roster_basis': 'Telegram opt-in: only members who sent /consent are included.', 'members': {}}
    for uid, m in members.items():
        entry = {'local_processing': True, 'comic_portrayal': True, 'cloud_processing': bool(m.get('cloud_processing')),
                 'evidence': f"Telegram /consent by user id {uid} at {m['granted_at']}"}
        if m.get('label'):
            entry['label'] = m['label']
        consent['members'][names[uid]] = entry
    msgs = []
    for m in sorted((x for x in state['messages'] if str(x['user_id']) in members), key=lambda x: (x['timestamp'], x['tg_id'])):
        msgs.append({'id': f'm{len(msgs)+1:04}', 'timestamp': m['timestamp'], 'author': names[str(m['user_id'])], 'text': m['text'],
                     'attachment': None, 'media_only': not m['text'].strip(), 'line': m['tg_id'], '_tg': m['tg_id'], '_kind': m['kind'],
                     **({'media_note': m['media_note']} if m.get('media_note') else {})})
    if not msgs:
        raise ValueError('No stored messages from opted-in members yet.')
    parsed = {'messages': msgs, 'system_events': [], 'warnings': [], 'participants': sorted({m['author'] for m in msgs}), 'date_order': 'ISO'}
    return parsed, consent


def transcribe_voice(api, file_id, filename='voice.ogg'):
    """Optional: send a voice file to an OpenAI-compatible /audio/transcriptions endpoint. Caller must have
    verified every member's cloud consent first."""
    key = os.getenv('GANG_LLM_API_KEY')
    if not key:
        raise GateError('GANG_LLM_API_KEY is not set; voice transcription is unavailable.')
    base = os.getenv('GANG_LLM_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
    u = urllib.parse.urlparse(base)
    if u.scheme != 'https' and not (u.scheme == 'http' and u.hostname in ('localhost', '127.0.0.1', '::1')):
        raise GateError('Use HTTPS for a cloud provider, or HTTP for a loopback-only local model.')
    audio = api.download(file_id)
    b = uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{os.getenv("GANG_TRANSCRIBE_MODEL", "whisper-1")}\r\n'
            f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: audio/ogg\r\n\r\n').encode() + audio + f'\r\n--{b}--\r\n'.encode()
    req = urllib.request.Request(base + '/audio/transcriptions', data=body, headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'multipart/form-data; boundary=' + b})

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k): raise GateError('Provider redirect blocked.')
    with urllib.request.build_opener(NoRedirect).open(req, timeout=90) as r:
        return json.load(r).get('text', '').strip()


class Bot:
    def __init__(self, api, store, bot_username=''):
        self.api, self.store, self.username = api, store, bot_username.lower().lstrip('@')

    # ---- update routing -------------------------------------------------
    def handle(self, update):
        if 'my_chat_member' in update:
            return self.on_membership(update['my_chat_member'])
        msg = update.get('message') or update.get('edited_message')
        if not msg or not msg.get('from') or msg['from'].get('is_bot'):
            return
        edited = 'edited_message' in update
        chat = msg['chat']
        text = msg.get('text') or ''
        if text.startswith('/') and not edited:
            return self.command(msg, chat, text)
        if chat['type'] not in ('group', 'supergroup'):
            return
        state = self.store.state(chat['id'], chat.get('title', ''))
        user = str(msg['from']['id'])
        state['seen_plain'] = True
        member = state['members'].get(user)
        if not member or not (member.get('local_processing') and member.get('comic_portrayal')):
            self.store.save(state)
            return  # not opted in: nothing is stored
        if edited:
            for m in state['messages']:
                if m['tg_id'] == msg['message_id'] and str(m['user_id']) == user and 'text' in msg:
                    m['text'] = text
        elif 'voice' in msg or 'audio' in msg:
            v = msg.get('voice') or msg['audio']
            state['messages'].append(self.record(msg, user, '', 'voice', file_id=v['file_id']))
        elif 'photo' in msg or 'video' in msg or 'video_note' in msg:
            state['messages'].append(self.record(msg, user, msg.get('caption', ''), 'photo' if 'photo' in msg else 'video'))
        elif text:
            state['messages'].append(self.record(msg, user, text, 'text'))
        self.store.save(state)

    @staticmethod
    def record(msg, user, text, kind, file_id=None):
        r = {'tg_id': msg['message_id'], 'user_id': user, 'timestamp': iso(msg['date']), 'text': text, 'kind': kind}
        if file_id: r['file_id'] = file_id
        return r

    def on_membership(self, ev):
        chat = ev['chat']
        if chat['type'] in ('group', 'supergroup') and ev['new_chat_member']['status'] in ('member', 'administrator'):
            self.store.save(self.store.state(chat['id'], chat.get('title', '')))
            self.api.send_message(chat['id'], 'Hi, I am The Gang Edition bot. I turn a week of this group into one comic page.\n\n' + HELP)
        elif ev['new_chat_member']['status'] in ('left', 'kicked') and chat['type'] in ('group', 'supergroup'):
            p = self.store.dir(chat['id']) / 'state.json'
            if p.exists():
                s = load(p); s['messages'] = []; s['pending'] = None; self.store.save(s)  # bot removed: drop stored text

    # ---- commands -------------------------------------------------------
    def command(self, msg, chat, text):
        head, _, arg = text.partition(' ')
        cmd, _, target = head[1:].partition('@')
        if target and self.username and target.lower() != self.username:
            return
        cmd, arg = cmd.lower(), arg.strip()
        reply = lambda t: self.api.send_message(chat['id'], t, msg['message_id'])
        if chat['type'] == 'private':
            return reply('Add me to your friends\' group. Members opt in there with /consent.\n\n' + HELP) if cmd in ('start', 'help') else None
        state = self.store.state(chat['id'], chat.get('title', ''))
        user = msg['from']
        uid = str(user['id'])
        member = state['members'].get(uid)
        if cmd in ('start', 'help'):
            return reply(HELP)
        if cmd == 'consent':
            state['members'][uid] = {'name': display_name(user), 'local_processing': True, 'comic_portrayal': True,
                                     'cloud_processing': bool(member and member.get('cloud_processing')), 'granted_at': iso(msg['date'])}
            state['pending'] = None
            self.store.save(state)
            return reply(f"{display_name(user)} is in. I will keep your text messages in this group on this computer and draw you in the comic. /revoke deletes it all.")
        if cmd == 'revoke':
            state['members'].pop(uid, None)
            state['messages'] = [m for m in state['messages'] if str(m['user_id']) != uid]
            state['pending'] = None
            self.store.save(state)
            return reply('Done. Your opt-in and stored messages are deleted. Characters already drawn in past comics are not recalled.')
        if cmd in ('cloudok', 'cloudno'):
            if not member:
                return reply('Send /consent first.')
            member['cloud_processing'] = cmd == 'cloudok'
            state['pending'] = None
            self.store.save(state)
            return reply('Cloud permission ' + ('granted' if cmd == 'cloudok' else 'withdrawn') + '. Cloud mode only runs if every opted-in member allows it.')
        if cmd == 'roster':
            names = unique_names(state['members'])
            return reply('Opted in: ' + (', '.join(sorted(names.values())) or 'nobody yet') + '\nEveryone else is excluded.')
        if cmd == 'styles':
            cur = state.get('style') or os.getenv('GANG_DEFAULT_STYLE') or DEFAULT_STYLE
            return reply('Available styles: ' + ', '.join(sorted(STYLES)) + '.\nDefault: ' + cur + '. Admins set it with /style <name>.')
        if cmd in ('style', 'rename'):
            if not self.api.is_admin(chat['id'], user['id']):
                return reply('Only group admins can run /style and /rename.')
            return self.style(state, arg, reply) if cmd == 'style' else self.rename(state, arg, reply)
        if cmd == 'status':
            mine = sum(1 for m in state['messages'] if str(m['user_id']) == uid)
            out = f"Opted-in members: {len(state['members'])}. Stored messages: {len(state['messages'])} (yours: {mine}). Retention: {self.store.retention_days} days."
            if not state['seen_plain']:
                out += '\n' + PRIVACY_WARNING
            return reply(out)
        if cmd in ('transcript', 'describe'):
            src = (msg.get('reply_to_message') or {}).get('message_id')
            target_msg = next((m for m in state['messages'] if m['tg_id'] == src and str(m['user_id']) == uid), None)
            if not target_msg or not arg:
                return reply(f'Reply to YOUR OWN {"voice message" if cmd == "transcript" else "photo"} with /{cmd} followed by the text.')
            target_msg['text'] = arg[:500]
            target_msg['media_note'] = 'supplied transcript' if cmd == 'transcript' else 'supplied image description'
            self.store.save(state)
            return reply('Saved. It will only be used if you stay opted in.')
        if cmd in ('comic', 'approve'):
            if not self.api.is_admin(chat['id'], user['id']):
                return reply('Only group admins can run /comic and /approve.')
            return self.comic(state, msg, arg, reply) if cmd == 'comic' else self.approve(state, msg, arg, reply)

    def comic(self, state, msg, arg, reply):
        from .core import week_start
        words = arg.split()
        lower = [w.lower() for w in words]
        cloud = 'cloud' in lower
        style_key = next((w for w in lower if w in STYLES), None)
        try:
            style = effective_style(style_key, state.get('style'))
        except ValueError as e:
            return reply(f'Blocked: {e}')
        date = next((w for w in words if re.fullmatch(r'\d{4}-\d{2}-\d{2}', w)), iso(msg['date'])[:10])
        art_mode = 'image' if (cloud and os.getenv('GANG_IMG_API_KEY')) else 'procedural'
        try:
            parsed, consent = build_inputs(state)
            if cloud:
                check_consent(parsed, consent, True)
                by_tg = {m['tg_id']: m for m in state['messages']}
                for m in parsed['messages']:
                    if m['_kind'] == 'voice' and not m['text'].strip():
                        src = by_tg[m['_tg']]
                        m['text'] = transcribe_voice(self.api, src['file_id'])
                        m['media_only'] = not m['text']
                        m['media_note'] = 'provider transcript'
            plan = prepare(parsed, consent, date, self.memory(state), cloud)
            plan['style'] = style.key
            plan['art_mode'] = art_mode
            plan['img_mode'] = os.getenv('GANG_IMG_MODE', 'full')
        except (GateError, ValueError, OSError, urllib.error.URLError, KeyError) as e:
            return reply(f'Blocked: {e}')
        state['pending'] = {'parsed': parsed, 'consent': consent, 'plan': plan}
        self.store.save(state)
        art = 'AI image' if art_mode == 'image' else 'local drawing'
        lines = [f"Draft for the week of {plan['week']} ({plan['mode']} picking, {style.name} style, {art}). * = proposed."]
        for i, c in enumerate(plan['candidates'][:12], 1):
            lines.append(f"{'*' if c['message_id'] in plan['selected_ids'] else ' '} {i}. {c['author']}: {c['quote'][:110]}")
        lines.append('\nAdmin: /approve to use the starred moments, or /approve 2 4 5 (1-6 numbers). Everyone can /revoke before then.')
        reply('\n'.join(lines))

    def style(self, state, arg, reply):
        if not arg:
            cur = state.get('style') or os.getenv('GANG_DEFAULT_STYLE') or DEFAULT_STYLE
            return reply(f'Current comic style: {cur}. Set with /style <name>. Available: ' + ', '.join(sorted(STYLES)) + '.')
        key = arg.strip().split()[0].lower()
        if key not in STYLES:
            return reply(f'Unknown style "{key}". Choose from: ' + ', '.join(sorted(STYLES)) + '.')
        state['style'] = key
        state['pending'] = None
        self.store.save(state)
        return reply(f'Comic style set to {key}. The next /comic will use it unless a style is passed.')

    def rename(self, state, arg, reply):
        tokens = arg.strip().split()
        if len(tokens) < 2:
            return reply('Usage: /rename <member-name> <new-label>. The label is one word.')
        label = tokens[-1]
        name = ' '.join(tokens[:-1])
        matches = [uid for uid, m in state['members'].items() if m.get('name', '').lower() == name.lower() or uid == name]
        if not matches:
            return reply(f'No opted-in member named "{name}". Use /roster to see names.')
        if len(matches) > 1:
            return reply(f'Multiple members are named "{name}". Rename by Telegram id instead: /rename <id> <label>.')
        uid = matches[0]
        state['members'][uid]['label'] = label
        state['pending'] = None
        self.store.save(state)
        return reply(f'{state["members"][uid].get("name", name)} will be shown as "{label}" in future comics.')

    def memory(self, state):
        p = self.store.dir(state['chat_id']) / 'memory.json'
        return load(p) if p.exists() else {}

    def approve(self, state, msg, arg, reply):
        from .app import finish
        pend = state.get('pending')
        if not pend:
            return reply('Nothing to approve. Run /comic first.')
        plan = pend['plan']
        try:
            if arg:
                nums = [int(x) for x in re.findall(r'\d+', arg)]
                plan['selected_ids'] = [plan['candidates'][n - 1]['message_id'] for n in nums]
            plan['approved'] = True
            _, consent_now = build_inputs(state)  # latest opt-ins: any change blocks the old draft
            out = finish(pend['parsed'], consent_now, plan, self.store.dir(state['chat_id']), self.store.dir(state['chat_id']))
        except (GateError, ValueError, IndexError, OSError) as e:
            return reply(f'Blocked: {e}')
        state['pending'] = None
        self.store.save(state)
        self.api.send_photo(state['chat_id'], out / 'comic.png', 'The Gang Edition. Draft approved by an admin.')
        self.api.send_document(state['chat_id'], out / 'comic.pdf', 'Printable page')


def run(workspace='workspace', token=None):
    """Long-poll loop. Real network use: requires a real BotFather token."""
    token = token or os.getenv('TELEGRAM_BOT_TOKEN', '')
    api = TelegramAPI(token)
    me = api.get_me()
    if not me.get('can_read_all_group_messages'):
        print('WARNING: privacy mode is ON for this bot. It will only see commands in groups. In @BotFather: /setprivacy -> Disable, then re-add the bot (or make it an admin).')
    bot = Bot(api, Store(workspace), me.get('username', ''))
    off_file = Path(workspace) / 'telegram' / 'offset.json'
    offset = load(off_file)['offset'] if off_file.exists() else 0
    print(f"Bot @{me.get('username')} polling. Ctrl+C to stop.")
    backoff = 1
    while True:
        try:
            for upd in api.get_updates(offset):
                offset = upd['update_id'] + 1
                try:
                    bot.handle(upd)
                except Exception as e:  # one bad update must not stop the bot
                    print(redact(f'update {upd.get("update_id")} failed: {type(e).__name__}', token))
                save(off_file, {'offset': offset})
            backoff = 1
        except TelegramError as e:
            print(e); time.sleep(backoff); backoff = min(backoff * 2, 60)
        except KeyboardInterrupt:
            return


def demo(workspace):
    """Replay the synthetic sample as Telegram updates through the real handler with a fake API."""
    from .app import ROOT, read_source
    parsed = read_source(ROOT / 'sample/chat.txt', 'DMY', ROOT / 'sample/media.json', ROOT / 'sample')
    api = OfflineAPI(admins={1})
    bot = Bot(api, Store(workspace), 'gang_edition_bot')
    ids = {'Alex': 1, 'Maya': 2, 'Sam': 3, 'Jo': 4, 'Lurker': 5}
    chat = {'id': -1001, 'type': 'supergroup', 'title': 'Synthetic Gang'}
    n = [0]
    def say(who, text, when, **extra):
        n[0] += 1
        if 'reply' in extra: extra['reply_to_message'] = {'message_id': extra.pop('reply')}
        ts = int(dt.datetime.fromisoformat(when).replace(tzinfo=dt.timezone.utc).timestamp())
        bot.handle({'update_id': n[0], 'message': {'message_id': n[0], 'date': ts, 'chat': chat, 'from': {'id': ids[who], 'first_name': who, 'is_bot': False}, 'text': text, **extra}})
    bot.handle({'update_id': 0, 'my_chat_member': {'chat': chat, 'new_chat_member': {'status': 'member'}}})
    for who in ('Alex', 'Maya', 'Sam', 'Jo'):
        say(who, '/consent', '2026-10-05T17:59:00')
    say('Lurker', 'This never gets stored. Plot twist! haha', '2026-10-06T10:01:00')  # did not opt in
    for m in parsed['messages']:
        text = m['text'] if not m['media_only'] or m.get('media_note') else ''
        if m['attachment']:
            is_voice = m['attachment'].lower().endswith(('.opus', '.ogg', '.m4a', '.mp3'))
            say(m['author'], '', m['timestamp'], **({'voice': {'file_id': 'demo-voice'}} if is_voice else {'photo': [{'file_id': 'demo-photo'}]}))
            say(m['author'], ('/transcript ' if is_voice else '/describe ') + m['text'], m['timestamp'], reply=n[0])
            continue
        say(m['author'], text, m['timestamp'])
    api.sent.clear()
    say('Alex', '/comic 2026-10-05', '2026-10-11T20:00:00')
    print(api.texts()[-1])
    say('Alex', '/approve', '2026-10-11T20:01:00')
    out = [s[2] for s in api.sent if s[0] == 'photo']
    print('Posted to group (fake Telegram, no network):', out[-1] if out else api.texts()[-1])
    return out
