import io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from gang_edition.core import GateError
from gang_edition.telegram import Bot,Store,OfflineAPI,TelegramAPI,TelegramError,build_inputs,transcribe_voice,redact

CHAT={'id':-100,'type':'supergroup','title':'T'}
class T(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.api=OfflineAPI(admins={1},files={'v1':b'OggS-fake'});self.store=Store(self.tmp.name);self.bot=Bot(self.api,self.store,'gangbot');self.n=0
    def say(self,uid,text='',when=1791200000,chat=CHAT,**extra):
        self.n+=1
        if 'reply' in extra:extra['reply_to_message']={'message_id':extra.pop('reply')}
        self.bot.handle({'update_id':self.n,'message':{'message_id':self.n,'date':when,'chat':chat,'from':{'id':uid,'first_name':f'U{uid}','is_bot':False},'text':text,**extra}});return self.n
    def st(self):return self.store.state(-100)
    def optin(self,*ids):
        for u in ids:self.say(u,'/consent')
    def test_join_announces_and_help(self):
        self.bot.handle({'update_id':1,'my_chat_member':{'chat':CHAT,'new_chat_member':{'status':'member'}}})
        self.assertIn('/consent',self.api.texts()[0])
    def test_non_opted_in_not_stored(self):
        self.optin(1);self.say(1,'I am in');self.say(9,'secret stranger text')
        self.assertEqual([m['text'] for m in self.st()['messages']],['I am in'])
        self.assertNotIn('secret stranger',json.dumps(self.st()))
    def test_message_before_consent_not_stored(self):
        self.say(1,'before');self.optin(1);self.say(1,'after')
        self.assertEqual([m['text'] for m in self.st()['messages']],['after'])
    def test_revoke_deletes_and_clears_pending(self):
        self.optin(1,2);self.say(1,'Plot twist! haha!!');self.say(2,'Finally won!');self.say(1,'/comic 2026-10-05' if False else '/comic')
        self.assertIsNotNone(self.st()['pending'])
        self.say(2,'/revoke')
        s=self.st();self.assertIsNone(s['pending']);self.assertNotIn('2',s['members']);self.assertFalse([m for m in s['messages'] if m['user_id']=='2'])
    def test_needs_two_members(self):
        self.optin(1);self.say(1,'hello there friends')
        with self.assertRaises(GateError):build_inputs(self.st())
    def test_comic_admin_only(self):
        self.optin(1,2);self.say(1,'Finally won!!');self.say(2,'/comic')
        self.assertIn('Only group admins',self.api.texts()[-1]);self.assertIsNone(self.st()['pending'])
    def test_full_flow_and_consent_change_blocks(self):
        self.optin(1,2);self.say(1,'Plot twist! wrong restaurant!!');self.say(2,'Finally won the quiz haha!')
        self.say(1,'/comic');self.assertIn('Draft for the week',self.api.texts()[-1])
        self.say(3,'/consent')  # any opt-in change discards the draft
        self.say(1,'/approve');self.assertIn('Nothing to approve',self.api.texts()[-1]);self.assertFalse([s for s in self.api.sent if s[0]=='photo'])
    def test_tampered_consent_state_blocks_stale_draft(self):
        self.optin(1,2);self.say(1,'Plot twist! wrong restaurant!!');self.say(2,'Finally won the quiz haha!');self.say(1,'/comic')
        s=self.st();s['members']['2']['comic_portrayal']=False;self.store.save(s)  # revoked outside the command path
        self.say(1,'/approve');self.assertIn('Blocked',self.api.texts()[-1]);self.assertFalse([x for x in self.api.sent if x[0]=='photo'])
    def test_approve_posts_png_pdf_and_no_network(self):
        self.optin(1,2);self.say(1,'Plot twist! wrong restaurant!!');self.say(2,'Finally won the quiz haha!')
        with patch('gang_edition.core.urllib.request.build_opener') as net:
            self.say(1,'/comic');self.say(1,'/approve 1 2');net.assert_not_called()
        kinds=[s[0] for s in self.api.sent];self.assertIn('photo',kinds);self.assertIn('document',kinds)
        self.assertTrue(Path([s for s in self.api.sent if s[0]=='photo'][0][2]).exists())
    def test_cloud_needs_every_member(self):
        self.optin(1,2);self.say(1,'Finally won!!');self.say(2,'Plot twist haha!');self.say(1,'/cloudok')
        with patch.dict(os.environ,{'GANG_LLM_API_KEY':'k'}),patch('gang_edition.core.urllib.request.build_opener') as net:
            self.say(1,'/comic cloud');net.assert_not_called()
        self.assertIn('Cloud processing not approved',self.api.texts()[-1])
    def test_voice_needs_transcript_sidecar(self):
        self.optin(1,2);vid=self.say(1,'',voice={'file_id':'v1'})
        self.assertEqual(self.st()['messages'][-1]['kind'],'voice')
        parsed,_=build_inputs(self.st()) if self.say(2,'second person text') else (None,None)
        self.assertTrue(parsed['messages'][0]['media_only'])
        self.say(2,'/transcript hacked',reply=vid);self.assertEqual(self.st()['messages'][0]['text'],'')  # only the author may add it
        self.say(1,'/transcript I will check the address twice',reply=vid)
        self.assertEqual(self.st()['messages'][0]['media_note'],'supplied transcript')
    def test_voice_not_downloaded_offline(self):
        self.optin(1,2);self.say(1,'',voice={'file_id':'v1'});self.say(2,'Finally won!!')
        with patch.object(self.api,'download') as d:
            self.say(1,'/comic');d.assert_not_called()
    def test_transcribe_adapter_mocked(self):
        reply={'text':' hello world '}
        with patch.dict(os.environ,{'GANG_LLM_API_KEY':'synthetic','GANG_LLM_BASE_URL':'https://example.invalid/v1'}),patch('gang_edition.telegram.urllib.request.build_opener') as o:
            o.return_value.open.return_value=io.BytesIO(json.dumps(reply).encode())
            self.assertEqual(transcribe_voice(self.api,'v1'),'hello world')
            self.assertEqual(o.return_value.open.call_args.args[0].full_url,'https://example.invalid/v1/audio/transcriptions')
    def test_transcribe_needs_key(self):
        with patch.dict(os.environ,{},clear=True),self.assertRaises(GateError):transcribe_voice(self.api,'v1')
    def test_private_chat_stores_nothing(self):
        self.say(1,'/consent',chat={'id':5,'type':'private'});self.say(1,'hi',chat={'id':5,'type':'private'})
        self.assertEqual(self.store.groups(),[])
    def test_command_for_other_bot_ignored(self):
        self.say(1,'/consent@otherbot');self.assertNotIn('1',self.st()['members'])
    def test_edit_updates_text(self):
        self.optin(1);mid=self.say(1,'orig text here')
        self.bot.handle({'update_id':99,'edited_message':{'message_id':mid,'date':1791200000,'chat':CHAT,'from':{'id':1,'first_name':'U1'},'text':'edited text'}})
        self.assertEqual(self.st()['messages'][0]['text'],'edited text')
    def test_retention_prunes(self):
        self.optin(1);self.say(1,'ancient message',when=1000000000);self.say(1,'fresh message',when=int(__import__('time').time()))
        self.assertEqual([m['text'] for m in self.st()['messages']],['fresh message'])
    def test_privacy_mode_hint(self):
        self.optin(1);self.say(1,'/status')
        self.assertIn('setprivacy',self.api.texts()[-1])
    def test_token_validation_and_redaction(self):
        with self.assertRaises(TelegramError):TelegramAPI('')
        self.assertEqual(redact('x 123:abc y','123:abc'),'x <token> y')
    def test_styles_list_and_admin_set(self):
        self.optin(1,2)
        self.say(1,'/styles');self.assertIn('marvel',self.api.texts()[-1])
        self.say(2,'/style ghibli');self.assertIn('Only group admins',self.api.texts()[-1])
        self.say(1,'/style ghibli');self.assertEqual(self.st()['style'],'ghibli')
        self.say(1,'/style bogus');self.assertIn('Unknown style',self.api.texts()[-1])
        self.assertEqual(self.st()['style'],'ghibli')
    def test_comic_style_arg(self):
        self.optin(1,2);self.say(1,'Plot twist! wrong restaurant!!');self.say(2,'Finally won the quiz haha!')
        self.say(1,'/comic 2026-10-05 ghibli')
        self.assertIn('Ghibli style',self.api.texts()[-1])
        self.assertEqual(self.st()['pending']['plan']['style'],'ghibli')
        self.assertEqual(self.st()['pending']['plan']['art_mode'],'procedural')
    def test_rename_member(self):
        self.optin(1,2);self.say(1,'hello');self.say(2,'world')
        self.say(2,'/rename U1 Dan');self.assertIn('Only group admins',self.api.texts()[-1])
        self.say(1,'/rename U1 Dan')
        self.assertEqual(self.st()['members']['1']['label'],'Dan')
        parsed,consent=build_inputs(self.st())
        self.assertEqual(consent['members']['U1']['label'],'Dan')
        from gang_edition.core import character_sheet
        self.assertEqual(character_sheet(consent['members'],{})['U1']['label'],'Dan')
if __name__=='__main__':unittest.main()
