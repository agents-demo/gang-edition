import subprocess,time,urllib.request,json,re,os,tempfile
from pathlib import Path
root=str(Path(__file__).resolve().parent.parent)
with tempfile.TemporaryDirectory() as temp:
    env=dict(os.environ,PYTHONPATH=root)
    process=subprocess.Popen(['python3','-m','gang_edition','serve','--port','8766'],cwd=temp,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for _ in range(30):
            try:
                page=urllib.request.urlopen('http://127.0.0.1:8766').read().decode();break
            except OSError:time.sleep(.1)
        token=re.search("const token='([^']+)'",page).group(1)
        def post(path,data):
            req=urllib.request.Request('http://127.0.0.1:8766'+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Gang-Token':token})
            return json.load(urllib.request.urlopen(req))
        sample=json.load(urllib.request.urlopen('http://127.0.0.1:8766/sample'))
        p=post('/prepare',dict(chat=sample['chat'],consent=sample['consent'],order='DMY',week='2026-10-05'))
        r=post('/render',dict(session=p['session'],ids=p['plan']['selected_ids'],approved=True))
        image=urllib.request.urlopen('http://127.0.0.1:8766'+r['png']).read()
        assert image[:8]==b'\x89PNG\r\n\x1a\n'
        pdf=urllib.request.urlopen('http://127.0.0.1:8766'+r['pdf']).read();assert pdf.startswith(b'%PDF')
        import shutil
        if shutil.which('google-chrome-stable'):
            subprocess.run(['google-chrome-stable','--headless','--no-sandbox','--disable-gpu','--hide-scrollbars','--window-size=390,1700','--screenshot='+root+'/preview/ui-mobile.png','http://127.0.0.1:8766'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=25)
        # Persisted revocation blocks downloads from old session.
        c=sample['consent'];c['members']['Jo']['local_processing']=False
        open(temp+'/web-workspace/consent.json','w').write(json.dumps(c))
        try:urllib.request.urlopen('http://127.0.0.1:8766'+r['png']);raise AssertionError('revocation did not block')
        except urllib.error.HTTPError as e:assert e.code==403
        print('WEB CHECK PASSED: import -> review -> render -> PNG/PDF download; revocation blocks old output.')
    finally:
        process.terminate();process.wait(timeout=5)
