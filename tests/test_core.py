import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from gang_edition.core import *
from gang_edition.app import ROOT,read_source,finish

class TestGang(unittest.TestCase):
    def setUp(self):
        self.parsed=read_source(ROOT/'sample/chat.txt','DMY',ROOT/'sample/media.json',ROOT/'sample')
        self.consent=load(ROOT/'sample/consent.json')
    def test_android_multiline(self):
        p=parse_export('05/10/2026, 18:02 - Alex: one\nsecond line\n05/10/2026, 18:03 - Maya: two')
        self.assertEqual(p['messages'][0]['text'],'one\nsecond line')
    def test_ios_ampm(self):
        p=parse_export('[10/05/26, 6:02:00 PM] Alex: hi\n[10/05/26, 6:03:00 PM] Maya: yes','MDY')
        self.assertEqual(p['messages'][0]['timestamp'],'2026-10-05T18:02:00')
    def test_unicode_export(self):
        p=parse_export('\u200e[05/10/2026, 6:02\u202fPM] \u200fAlex: hi')
        self.assertEqual(p['participants'],['Alex'])
    def test_system_not_member(self):
        self.assertNotIn('Messages and calls',self.parsed['participants'])
        self.assertEqual(len(self.parsed['system_events']),1)
    def test_missing_consent(self):
        del self.consent['members']['Alex']
        with self.assertRaises(GateError):prepare(self.parsed,self.consent,'2026-10-05',{})
    def test_silent_member_denial(self):
        self.consent['members']['Silent']={'local_processing':False}
        with self.assertRaises(GateError):prepare(self.parsed,self.consent,'2026-10-05',{})
    def test_full_roster_required(self):
        self.consent['roster_confirmed_complete']=False
        with self.assertRaises(GateError):prepare(self.parsed,self.consent,'2026-10-05',{})
    def test_cloud_gate_before_network(self):
        with patch('gang_edition.core.urllib.request.build_opener') as network:
            with self.assertRaises(GateError):prepare(self.parsed,self.consent,'2026-10-05',{},True)
            network.assert_not_called()
    def test_sensitive_excluded(self):
        p=parse_export('05/10/2026, 18:02 - Alex: My password is not for sharing!\n05/10/2026, 18:03 - Maya: haha pizza')
        self.assertEqual([m['author'] for m in candidates(p,'2026-10-05',{})],['Maya'])
    def test_content_dedup_echo(self):
        p=parse_export('05/10/2026, 18:02 - Alex: you should PR to the experimental branch\n05/10/2026, 18:03 - Maya: you should PR to the experimental branch')
        self.assertEqual(len(candidates(p,'2026-10-05',{})),2)
        mem={'used_content_hashes':[content_fingerprint(p['messages'][0])]}
        self.assertEqual(candidates(p,'2026-10-05',mem),[])
    def test_review_gate(self):
        plan=prepare(self.parsed,self.consent,'2026-10-05',{})
        with self.assertRaises(GateError):validate_plan(self.parsed,self.consent,plan)
    def test_revocation(self):
        plan=prepare(self.parsed,self.consent,'2026-10-05',{});plan['approved']=True
        self.consent['members']['Jo']['comic_portrayal']=False
        with self.assertRaises(GateError):validate_plan(self.parsed,self.consent,plan)
    def test_changed_source(self):
        plan=prepare(self.parsed,self.consent,'2026-10-05',{});plan['approved']=True
        self.parsed['messages'][0]['text']='changed'
        with self.assertRaises(GateError):validate_plan(self.parsed,self.consent,plan)
    def test_week_filter(self):
        with self.assertRaises(ValueError):prepare(self.parsed,self.consent,'2026-10-12',{})
    def test_stable_character(self):
        a=character_sheet(self.consent['members'],{})
        b=character_sheet(['Extra','Alex'],a)
        self.assertEqual(a['Alex'],b['Alex'])
    def test_character_distinct(self):
        sheet=character_sheet({'Alex':{},'Maya':{},'Sam':{},'Jo':{},'Lee':{},'Kim':{}},{})
        keys=[(v['color'],v['hair'],v['glasses']) for v in sheet.values()]
        self.assertEqual(len(keys),len(set(keys)))
    def test_character_collision_resolved(self):
        existing={'A':{'color':'#73a89a','hair':0,'glasses':False,'label':'A'},
                  'B':{'color':'#73a89a','hair':0,'glasses':False,'label':'B'}}
        sheet=character_sheet(['A','B'],existing)
        self.assertNotEqual((sheet['A']['color'],sheet['A']['hair'],sheet['A']['glasses']),
                            (sheet['B']['color'],sheet['B']['hair'],sheet['B']['glasses']))
    def test_validate_plan_multi_page(self):
        plan=prepare(self.parsed,self.consent,'2026-10-05',{})
        cands=plan['candidates']
        self.assertGreaterEqual(len(cands),7)
        plan['approved']=True
        plan['selected_ids']=[c['message_id'] for c in cands[:7]]
        self.assertEqual(len(validate_plan(self.parsed,self.consent,plan)),7)
    def test_multi_page_render(self):
        from gang_edition.render import render_pages
        from gang_edition.styles import resolve_style
        msgs=[{'author':'A','timestamp':'2026-10-05T00:00:00','text':f'message number {i}','attachment':None} for i in range(7)]
        sheet=character_sheet({'A':{},'B':{}},{})
        with tempfile.TemporaryDirectory() as d:
            pngs=render_pages(msgs,sheet,'2026-10-05',d,None,resolve_style('cartoon'))
            self.assertEqual(len(pngs),2)
            self.assertTrue((Path(d)/'comic-1.png').exists())
            self.assertTrue((Path(d)/'comic-2.png').exists())
            self.assertTrue((Path(d)/'comic.pdf').exists())
    def test_media_path(self):
        with self.assertRaises(ValueError):safe_media(ROOT/'sample','../.env')
    def test_media_enrichment(self):
        self.assertEqual(self.parsed['messages'][-1]['media_note'],'supplied transcript')
    def test_offline_no_network_and_outputs(self):
        with tempfile.TemporaryDirectory() as folder, patch('gang_edition.core.urllib.request.build_opener') as network:
            plan=prepare(self.parsed,self.consent,'2026-10-05',{});plan['approved']=True
            out=finish(self.parsed,self.consent,plan,folder,ROOT/'sample')
            self.assertTrue((out/'comic.png').exists());self.assertTrue((out/'comic.pdf').exists())
            self.assertTrue((out/'sources.json').exists());network.assert_not_called()
            pool=candidates(self.parsed,'2026-10-05',load(Path(folder)/'memory.json'))
            self.assertFalse(set(plan['selected_ids']) & {m['message_id'] for m in pool})
    def test_invalid_selected_ids(self):
        plan=prepare(self.parsed,self.consent,'2026-10-05',{});plan['approved']=True;plan['selected_ids']=['made-up']
        with self.assertRaises(GateError):validate_plan(self.parsed,self.consent,plan)

if __name__=='__main__':unittest.main()

class TestAdapter(unittest.TestCase):
    def test_custom_base_url_and_validated_ids(self):
        import io
        pool=[{'message_id':'m0001','author':'Alex','quote':'pizza'}]
        reply={'choices':[{'message':{'content':'{"ids":["m0001"]}'}}]}
        with patch.dict(os.environ,{'GANG_LLM_API_KEY':'synthetic-test-key','GANG_LLM_BASE_URL':'https://example.invalid/v1','GANG_LLM_MODEL':'test-model'}), patch('gang_edition.core.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=io.BytesIO(json.dumps(reply).encode())
            self.assertEqual(cloud_select(pool),['m0001'])
            request=opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,'https://example.invalid/v1/chat/completions')
            payload=json.loads(request.data)
            self.assertEqual(payload['model'],'test-model')
    def test_remote_http_rejected(self):
        with patch.dict(os.environ,{'GANG_LLM_API_KEY':'synthetic-test-key','GANG_LLM_BASE_URL':'http://example.invalid/v1'}):
            with self.assertRaises(GateError):cloud_select([])
    def test_hallucinated_id_rejected(self):
        import io
        reply={'choices':[{'message':{'content':'{"ids":["invented"]}'}}]}
        with patch.dict(os.environ,{'GANG_LLM_API_KEY':'synthetic-test-key','GANG_LLM_BASE_URL':'https://example.invalid/v1'}),patch('gang_edition.core.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=io.BytesIO(json.dumps(reply).encode())
            with self.assertRaises(ValueError):cloud_select([{'message_id':'m0001'}])


class TestStyles(unittest.TestCase):
    def test_resolve_known(self):
        from gang_edition.styles import resolve_style,STYLES
        self.assertEqual(resolve_style('marvel').key,'marvel')
        self.assertIn('ghibli',STYLES)
        self.assertIn('dc',STYLES)
    def test_resolve_unknown(self):
        from gang_edition.styles import resolve_style
        with self.assertRaises(ValueError):resolve_style('anime')
    def test_default_is_marvel(self):
        from gang_edition.styles import effective_style
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(effective_style().key,'marvel')
    def test_env_default_override(self):
        from gang_edition.styles import effective_style
        with patch.dict(os.environ,{'GANG_DEFAULT_STYLE':'ghibli'}):
            self.assertEqual(effective_style().key,'ghibli')


class TestImage(unittest.TestCase):
    def test_generate_image_mocked(self):
        import io, base64
        from gang_edition.img import generate_image
        png = b'\x89PNG-fake'
        reply = {'data': [{'b64_json': base64.b64encode(png).decode(), 'media_type': 'image/png'}]}
        with patch.dict(os.environ, {'GANG_IMG_API_KEY': 'k', 'GANG_IMG_BASE_URL': 'https://example.invalid/api/v1', 'GANG_IMG_MODEL': 'm'}), \
                patch('gang_edition.img.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(json.dumps(reply).encode())
            self.assertEqual(generate_image('hello'), png)
            req = opener.return_value.open.call_args.args[0]
            self.assertEqual(req.full_url, 'https://example.invalid/api/v1/images')
            payload = json.loads(req.data)
            self.assertEqual(payload['model'], 'm')
            self.assertEqual(payload['prompt'], 'hello')
            self.assertEqual(req.get_header('Authorization'), 'Bearer k')
    def test_generate_image_needs_key(self):
        from gang_edition.img import generate_image
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(GateError):
                generate_image('x')
    def test_generate_image_no_data_rejected(self):
        import io
        from gang_edition.img import generate_image
        with patch.dict(os.environ, {'GANG_IMG_API_KEY': 'k', 'GANG_IMG_BASE_URL': 'https://example.invalid/api/v1'}), \
                patch('gang_edition.img.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(json.dumps({'data': []}).encode())
            with self.assertRaises(ValueError):
                generate_image('x')
