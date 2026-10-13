import html
import json
import re
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from .app import ROOT,finish
from .core import parse_export,prepare,load,save,check_consent

HTML='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>The Gang Edition</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f4efec;color:#251f21;font:16px/1.6 system-ui}main{max-width:880px;margin:24px auto;padding:28px;background:white;border-radius:24px}h1{font:700 36px/1.2 Georgia;margin:0 0 12px}h2{font:24px Georgia}label{display:block;margin-top:14px}input,textarea,button,select{font:inherit;max-width:100%}input,textarea,select{padding:10px;border:1px solid #ccc;border-radius:5px}textarea{width:100%;height:190px}button{padding:12px 18px;border:0;border-radius:6px;background:#73a89a;color:#251f21;font-weight:600;cursor:pointer;margin-top:16px}aside{background:#f4efec;padding:16px;border-radius:12px}.moment{border-top:1px solid #eae9ea;padding:12px 0}.moment input{margin-right:12px}img{max-width:100%;height:auto}.error{color:#b22130}a{color:#285f51}details{margin-top:12px}#status{white-space:pre-wrap}small{color:#585254}@media(max-width:500px){main{margin:0;border-radius:0;padding:20px}h1{font-size:30px}}</style>
<main><h1>The Gang Edition</h1><p>Your group. Your week. One page worth keeping.</p><aside>Local-only demo. Nothing is uploaded to a server or AI provider. Import only after everyone agrees. Consent records are your attestations, not identity checks. Comics are drafts until you review them.</aside>
<section id="import"><h2>1. Import and consent</h2><label>WhatsApp .txt export <input id="file" type="file" accept=".txt"></label><label>Chat text<textarea id="chat" placeholder="Paste your WhatsApp export, or load the bundled synthetic sample."></textarea></label>
<label>Date order <select id="order"><option>DMY</option><option>MDY</option></select></label><label>A date in the desired week <input id="week" type="date" value="2026-10-05"></label>
<label>Consent JSON (include silent members)<textarea id="consent" placeholder='{"roster_confirmed_complete":true,"members":{"Alex":{"local_processing":true,"comic_portrayal":true,"cloud_processing":false,"evidence":"Agreed in person on YYYY-MM-DD"}}}'></textarea></label>
<details><summary>Consent format and privacy</summary><p>Every roster member needs local_processing=true, comic_portrayal=true and a dated evidence note. A denied or revoked member blocks the whole run. Check the full roster in WhatsApp, including people who never spoke. This prototype does not authenticate consent or infer membership changes.</p><p>UI supports text exports only. Image descriptions and voice transcripts are supported by the CLI with local sidecars. Never publish automatically.</p></details>
<details><summary>Or load a group collected by the Telegram bot</summary><label>Group <select id="tgchat"></select></label> <button id="tgload">Use this Telegram group</button></details>
<button id="sample">Load synthetic sample</button> <button id="prepare">Pick the moments</button></section>
<section id="review" hidden><h2>2. Review the moments</h2><p>Select up to twelve. Read the quotes and remove anything sensitive. The safety filter is limited and English-focused.</p><div id="moments"></div><label><input id="approve" type="checkbox"> I reviewed these moments and approve a local draft comic.</label><button id="render">Create the comic</button></section>
<section id="result" hidden><h2>3. Your edition</h2><p>Saved locally. This page never sends it to your group.</p><a id="png">Download PNG</a> · <a id="pdf">Download PDF</a><p><img id="comic" alt="Your reviewed illustrated weekly recap"></p></section><p id="status" role="status"></p><small>Persistent characters and used-moment memory live in web-workspace. Stop with Ctrl+C. Delete the folder when finished with private data.</small></main>
<script>
const $=id=>document.getElementById(id);let session;const token='TOKEN_PLACEHOLDER';
async function api(path,data){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Gang-Token':token},body:JSON.stringify(data)});const out=await response.json();if(!response.ok)throw Error(out.error);return out}
function status(text,error=false){$('status').textContent=text;$('status').className=error?'error':''}
$('file').onchange=async()=>{if($('file').files[0])$('chat').value=await $('file').files[0].text()};
$('sample').onclick=async()=>{const r=await fetch('/sample');const s=await r.json();$('chat').value=s.chat;$('consent').value=JSON.stringify(s.consent,null,2);status('Synthetic names and messages loaded. No real group data.')};
fetch('/tg/groups').then(r=>r.json()).then(g=>{for(const x of g){const o=document.createElement('option');o.value=x.chat_id;o.textContent=(x.title||x.chat_id)+' ('+x.members+' opted in, '+x.messages+' msgs)';$('tgchat').append(o)}});
let tgMode=false;$('tgload').onclick=()=>{tgMode=true;$('chat').value='(Telegram group '+$('tgchat').value+': stored opt-in messages will be used)';$('consent').value='(consent comes from members\' /consent commands)';status('Telegram group selected. Pick a date in the week, then Pick the moments.')};
$('prepare').onclick=async()=>{try{status('Selecting local moments...');const p=await api('/prepare',tgMode?{telegram_chat:$('tgchat').value,week:$('week').value}:{chat:$('chat').value,consent:JSON.parse($('consent').value),order:$('order').value,week:$('week').value});session=p.session;$('moments').replaceChildren();for(const m of p.plan.candidates){let div=document.createElement('div');div.className='moment';let label=document.createElement('label');let c=document.createElement('input');c.type='checkbox';c.value=m.message_id;c.checked=p.plan.selected_ids.includes(m.message_id);label.append(c,document.createTextNode(m.author+' | '+m.timestamp+' | '+m.quote));div.append(label);$('moments').append(div)}$('review').hidden=false;$('result').hidden=true;$('approve').checked=false;status(p.warnings.join('\n')||'Review the selected quotes before rendering.')}catch(e){status(e.message,true)}};
$('render').onclick=async()=>{try{if(!$('approve').checked)throw Error('Review and approve the selected quotes first.');const ids=[...$('moments').querySelectorAll('input:checked')].map(x=>x.value);const r=await api('/render',{session,ids,approved:true});$('png').href=r.png;$('pdf').href=r.pdf;$('comic').src=r.png;$('result').hidden=false;status('Created locally. Review the comic before sharing.')}catch(e){status(e.message,true)}};
</script></html>'''

def run(port=8765):
    token=secrets.token_urlsafe(32)
    sessions={}
    workspace=Path('web-workspace').resolve()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass # Do not log private chat content.
        def reply(self,status,data,mime='application/json'):
            data=(json.dumps(data).encode() if mime=='application/json' else data)
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
        def host_ok(self):
            return self.headers.get('Host') in (f'127.0.0.1:{port}',f'localhost:{port}')
        def do_GET(self):
            if not self.host_ok():self.reply(403,{'error':'Invalid host'});return
            if self.path=='/':
                self.reply(200,HTML.replace('TOKEN_PLACEHOLDER',token).encode(),'text/html; charset=utf-8')
            elif self.path=='/tg/groups':
                from .telegram import Store
                self.reply(200,Store('workspace').groups())
            elif self.path=='/sample':
                self.reply(200,{'chat':(ROOT/'sample/chat.txt').read_text(),'consent':load(ROOT/'sample/consent.json')})
            elif self.path.startswith('/output/'):
                bits=self.path.split('/')
                if len(bits)!=4 or bits[2] not in sessions or (bits[3] not in ('comic.png','comic.pdf') and not re.fullmatch(r'comic-\d+\.png', bits[3])):
                    self.reply(404,{'error':'Not found'});return
                state=sessions[bits[2]]
                # Recheck persisted consent before serving a saved output.
                try:
                    consent=load(workspace/'consent.json')
                    check_consent(state['parsed'],consent)
                    if not state.get('out'):raise ValueError('Not rendered')
                    p=state['out']/bits[3]
                    self.reply(200,p.read_bytes(),'image/png' if bits[3].endswith('png') else 'application/pdf')
                except (ValueError,OSError) as e:self.reply(403,{'error':str(e)})
            else:self.reply(404,{'error':'Not found'})
        def do_POST(self):
            if not self.host_ok() or self.headers.get('X-Gang-Token')!=token:
                self.reply(403,{'error':'Invalid local session token'});return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 1<=length<=4_000_000:raise ValueError('Request must be under 4 MB.')
                data=json.loads(self.rfile.read(length))
                if self.path=='/prepare':
                    if data.get('telegram_chat'):
                        from .telegram import Store,build_inputs
                        tg=Store('workspace');tid=data['telegram_chat']
                        parsed,consent=build_inputs(tg.state(int(tid) if tid.lstrip('-').isdigit() else tid))
                    else:
                        parsed=parse_export(data['chat'],data['order'])
                        consent=data['consent']
                    memory=load(workspace/'memory.json') if (workspace/'memory.json').exists() else {}
                    plan=prepare(parsed,consent,data['week'],memory)
                    session=secrets.token_urlsafe(24)
                    sessions[session]={'parsed':parsed,'consent':consent,'plan':plan}
                    save(workspace/'consent.json',consent)
                    self.reply(200,{'session':session,'plan':plan,'warnings':parsed['warnings']})
                elif self.path=='/render':
                    state=sessions[data['session']]
                    plan=state['plan'];plan['selected_ids']=data['ids'];plan['approved']=data.get('approved') is True
                    # Read latest consent so file edits/revocations block stale sessions.
                    consent=load(workspace/'consent.json')
                    out=finish(state['parsed'],consent,plan,workspace,workspace)
                    state['out']=out
                    png='comic.png' if (out/'comic.png').exists() else sorted(out.glob('comic-*.png'))[0].name
                    self.reply(200,{'png':f"/output/{data['session']}/{png}",'pdf':f"/output/{data['session']}/comic.pdf"})
                else:self.reply(404,{'error':'Not found'})
            except (ValueError,KeyError,TypeError,OSError) as e:
                self.reply(400,{'error':str(e)})
    server=HTTPServer(('127.0.0.1',port),Handler)
    print(f'Open http://127.0.0.1:{port} (local only). Ctrl+C to stop.')
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
