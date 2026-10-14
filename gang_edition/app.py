import argparse
import json
import shutil
import os
from pathlib import Path
from .core import load,save,parse_export,enrich,prepare,validate_plan,character_sheet,fingerprint,content_fingerprint,check_consent
from .render import render_pages
from .styles import effective_style

ROOT=Path(__file__).resolve().parent.parent

def read_source(chat, order, media_manifest=None, media_dir=None):
    parsed=parse_export(Path(chat).read_text(encoding='utf-8-sig'),order)
    if media_manifest:
        enrich(parsed,load(media_manifest),media_dir or Path(chat).parent)
    return parsed

def finish(parsed,consent,plan,workspace,media_dir):
    chosen=validate_plan(parsed,consent,plan)
    workspace=Path(workspace)
    sheet=character_sheet(consent['members'],load(workspace/'characters.json') if (workspace/'characters.json').exists() else {})
    out=workspace/'editions'/plan['week']
    style=effective_style(plan.get('style'))
    chosen_ids=[m['id'] for m in chosen]
    if plan.get('mode')=='cloud' and sorted(chosen_ids)!=sorted(plan.get('title_source_ids',[])):
        from .core import summarize
        meta=summarize(chosen)
        plan['title']=meta['title'];plan['summary']=meta['summary'];plan['title_source_ids']=list(chosen_ids)
    if plan.get('art_mode')=='image':
        from .img import render_image_page
        render_image_page(chosen,sheet,plan,style,out,avatars_dir=workspace/'avatars')
    else:
        render_pages(chosen,sheet,plan['week'],out,media_dir,style,title=plan.get('title','The Gang Edition'),summary=plan.get('summary','A week worth keeping'),avatars_dir=workspace/'avatars')
    save(out/'sources.json',chosen)
    save(out/'reviewed-plan.json',plan)
    (out/'transcript.txt').write_text('\n\n'.join(f"{m['timestamp']} | {m['author']}\n{m['text']}" for m in chosen),encoding='utf-8')
    save(workspace/'characters.json',sheet)
    memory=load(workspace/'memory.json') if (workspace/'memory.json').exists() else {}
    memory['used_message_fingerprints']=sorted(set(memory.get('used_message_fingerprints',[]))|{fingerprint(m) for m in chosen})
    memory['used_content_hashes']=sorted(set(memory.get('used_content_hashes',[]))|{content_fingerprint(m) for m in chosen})
    memory['last_week']=plan['week']
    save(workspace/'memory.json',memory)
    return out

def load_env():
    # Small .env reader: literal KEY=VALUE, no shell evaluation or interpolation.
    path=Path('.env')
    if path.is_file():
        for raw in path.read_text(encoding='utf-8').splitlines():
            line=raw.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            key,value=line.split('=',1)
            if key.strip() in ('GANG_LLM_API_KEY','GANG_LLM_BASE_URL','GANG_LLM_MODEL','TELEGRAM_BOT_TOKEN','GANG_TRANSCRIBE_MODEL','GANG_TRANSCRIBE_API_KEY','GANG_TRANSCRIBE_BASE_URL','GANG_RETENTION_DAYS',
                               'GANG_IMG_API_KEY','GANG_IMG_BASE_URL','GANG_IMG_MODEL','GANG_IMG_MODE','GANG_IMG_RESOLUTION','GANG_IMG_ASPECT_RATIO',
                               'GANG_IMG_READER_API_KEY','GANG_IMG_READER_BASE_URL','GANG_IMG_READER_MODEL',
                               'GANG_DEFAULT_STYLE'):
                os.environ.setdefault(key.strip(),value.strip().strip("'\""))

def main():
    load_env()
    p=argparse.ArgumentParser(description='The Gang Edition local MVP')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('prepare','render'):
        c=sub.add_parser(name)
        c.add_argument('--chat',required=True);c.add_argument('--consent',required=True)
        c.add_argument('--date-order',choices=['DMY','MDY'],required=True)
        c.add_argument('--workspace',default='workspace')
        c.add_argument('--media-manifest');c.add_argument('--media-dir')
        c.add_argument('--plan',required=True)
        if name=='prepare':
            c.add_argument('--week',required=True,help='ISO date in the desired Monday-Sunday week')
            c.add_argument('--cloud',action='store_true',help='Explicit external API call; all members must consent')
    demo=sub.add_parser('demo');demo.add_argument('--workspace',default='demo-workspace')
    serve=sub.add_parser('serve');serve.add_argument('--port',type=int,default=8765)
    tr=sub.add_parser('telegram-run',help='Run the Telegram group bot (long polling; needs TELEGRAM_BOT_TOKEN in .env)');tr.add_argument('--workspace',default='workspace')
    td=sub.add_parser('telegram-demo',help='Replay a synthetic group through the Telegram handler with a fake API (no network)');td.add_argument('--workspace',default='telegram-demo-workspace')
    tg=sub.add_parser('telegram-groups',help='List groups the bot has collected');tg.add_argument('--workspace',default='workspace')
    wr=sub.add_parser('wrapped',help='Render a Gang Wrapped stats/awards recap for a collected Telegram group')
    wr.add_argument('--chat-id',required=True);wr.add_argument('--workspace',default='workspace');wr.add_argument('--period',default='year')
    for name in ('telegram-prepare','telegram-render'):
        c=sub.add_parser(name);c.add_argument('--chat-id',required=True);c.add_argument('--workspace',default='workspace');c.add_argument('--plan',required=True)
        if name=='telegram-prepare':
            c.add_argument('--week',required=True);c.add_argument('--cloud',action='store_true')
    args=p.parse_args()
    try:
        if args.command=='serve':
            from .web import run
            run(args.port);return
        if args.command=='telegram-run':
            from .telegram import run as tg_run, TelegramError
            try: tg_run(args.workspace)
            except TelegramError as e: p.exit(2,f'Blocked: {e}\n')
            return
        if args.command=='telegram-demo':
            from .telegram import demo as tg_demo
            if Path(args.workspace).exists(): raise ValueError('Demo workspace already exists. Choose a fresh directory or delete it deliberately.')
            tg_demo(args.workspace);return
        if args.command=='telegram-groups':
            from .telegram import Store
            for g in Store(args.workspace).groups(): print(g)
            return
        if args.command=='wrapped':
            from .telegram import Store,build_inputs
            from .wrapped import compute_awards
            from .render import render_wrapped
            from .styles import effective_style
            store=Store(args.workspace)
            chat_id=args.chat_id if not args.chat_id.lstrip('-').isdigit() else int(args.chat_id)
            state=store.state(chat_id)
            parsed,consent=build_inputs(state)
            stats=store.load_stats(state['chat_id'])
            result=compute_awards(stats,args.period)
            cpath=store.dir(state['chat_id'])/'characters.json'
            existing=load(cpath) if cpath.exists() else {}
            sheet=character_sheet(consent['members'],existing)
            style=effective_style(state.get('style'))
            out=store.dir(state['chat_id'])/'wrapped'
            render_wrapped(result,sheet,out,style,avatars_dir=store.dir(state['chat_id'])/'avatars')
            awards=', '.join(f'{a["award"]}: {a["name"]}' for a in result['awards']) or 'no awards yet'
            print(f"Gang Wrapped ({result['label']}): {awards}")
            print(f'Saved under {out}')
            return
        if args.command in ('telegram-prepare','telegram-render'):
            from .telegram import Store,build_inputs
            store=Store(args.workspace);state=store.state(args.chat_id if not args.chat_id.lstrip('-').isdigit() else int(args.chat_id))
            parsed,consent=build_inputs(state);wdir=store.dir(state['chat_id'])
            if args.command=='telegram-prepare':
                memory=load(wdir/'memory.json') if (wdir/'memory.json').exists() else {}
                save(args.plan,prepare(parsed,consent,args.week,memory,args.cloud))
                print(f'Review {args.plan}; select IDs and set approved=true. No comic rendered yet. Cloud mode never transcribes voice from the CLI.');return
            out=finish(parsed,consent,load(args.plan),wdir,wdir)
            print(f'Rendered {out} ({", ".join(p.name for p in sorted(out.glob("comic*.png")))} and comic.pdf)');return
        if args.command=='demo':
            workspace=Path(args.workspace)
            if workspace.exists():
                raise ValueError('Demo workspace already exists. Choose a fresh directory or delete it deliberately.')
            parsed=read_source(ROOT/'sample/chat.txt','DMY',ROOT/'sample/media.json',ROOT/'sample')
            consent=load(ROOT/'sample/consent.json')
            plan=prepare(parsed,consent,'2026-10-05',{})
            plan['approved']=True # Only bundled synthetic demo data.
            out=finish(parsed,consent,plan,workspace,ROOT/'sample')
            print(f'Synthetic demo complete: {out} ({", ".join(p.name for p in sorted(out.glob("comic*.png")))} and comic.pdf)');return
        parsed=read_source(args.chat,args.date_order,args.media_manifest,args.media_dir)
        consent=load(args.consent)
        workspace=Path(args.workspace)
        if args.command=='prepare':
            memory=load(workspace/'memory.json') if (workspace/'memory.json').exists() else {}
            plan=prepare(parsed,consent,args.week,memory,args.cloud)
            save(args.plan,plan)
            print(f'Review {args.plan}; select IDs and set approved=true. No comic rendered yet.')
        else:
            out=finish(parsed,consent,load(args.plan),workspace,args.media_dir or Path(args.chat).parent)
            print(f'Rendered {out} ({", ".join(p.name for p in sorted(out.glob("comic*.png")))} and comic.pdf)')
    except (ValueError,OSError,KeyError,TypeError) as e:
        p.exit(2,f'Blocked: {e}\n')
