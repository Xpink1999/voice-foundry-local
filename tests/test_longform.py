"""Long-form contracts: import completeness, checkpoints, retry/review/export isolation."""
import hashlib
import io
import json
import time
import zipfile
from pathlib import Path
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from voice_platform.api import create_app
from tests.fake_engine import FakeEngine

BASE='/api/v1/longform'
def wait(client,url,predicate,timeout=15):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        r=client.get(url);assert r.status_code==200,r.text;item=r.json()
        if predicate(item):return item
        time.sleep(.02)
    raise AssertionError(item)
def upload(client,text,encoding='utf-8',selection='auto'):
    content=text.encode(encoding);r=client.post(BASE+'/books',files={'file':('整本.txt',content,'text/plain')},data={'title':'长文验收','encoding':selection});assert r.status_code==202,r.text
    identity=r.json()['id'];book=wait(client,BASE+'/books/'+identity,lambda b:b['phase'] in {'ready','failed'});assert book['phase']=='ready',book
    return identity,content

def complete(client,identity):
    r=client.post(f'{BASE}/books/{identity}/resume',json={});assert r.status_code==200,r.text
    return wait(client,f'{BASE}/books/{identity}',lambda b:b['state'] in {'completed','attention'})

@pytest.mark.parametrize('encoding,selection',[('utf-8','auto'),('utf-16','auto'),('gb2312','auto'),('gbk','gbk'),('gb2312','gb2312')])
def test_encoding_chapters_and_source_offsets(client,encoding,selection):
    text='\n第一章 开始\n夜色渐深。故事从这里开始。\n\n第二章 归来\n回到家里，灯光依旧温暖。\n'
    identity,raw=upload(client,text,encoding,selection);book=client.get(f'{BASE}/books/{identity}').json();chapters=client.get(f'{BASE}/books/{identity}/chapters').json()
    assert chapters['total']==2 and book['source_sha256']==hashlib.sha256(raw).hexdigest()
    assert client.get(f'{BASE}/books/{identity}/source').content==raw
    actual=''
    for chapter in chapters['items']:
        rows=client.get(f'{BASE}/books/{identity}/chapters/{chapter["no"]}/segments').json()['items'];actual+=''.join(r['text'] for r in rows)
        assert all(r['chars']<=160 and r['end_byte']>r['start_byte'] for r in rows)
    assert ''.join(actual.split())==''.join(text.split())
    assert client.get(f'{BASE}/books/{identity}/chapters?limit=101').status_code==422

def test_no_headings_or_paragraphs_are_bounded(client):
    text='只有连续内容也应该完整保留，自动寻找标点进行分段。'*4000
    identity,_=upload(client,text);book=client.get(f'{BASE}/books/{identity}').json();assert book['chars']==len(text) and book['chapters']>=3 and book['segments']>500
    chapter=client.get(f'{BASE}/books/{identity}/chapters?limit=1').json()['items'][0]
    page=client.get(f'{BASE}/books/{identity}/chapters/{chapter["no"]}/segments?limit=2').json();assert len(page['items'])==2 and page['total']>2
    assert client.get('/api/v1/jobs').json()==[]

def test_retry_encoding_reuses_original(client):
    raw='第一章 开始\n这是没有编码标记的文本。'.encode('utf-16-le');r=client.post(BASE+'/books',files={'file':('原件.txt',raw)},data={'encoding':'auto'});identity=r.json()['id']
    bad=wait(client,f'{BASE}/books/{identity}',lambda b:b['phase']=='failed');assert '空字符' in bad['error']
    assert client.post(f'{BASE}/books/{identity}/retry-import',json={'encoding':'utf-16-le'}).status_code==202
    ready=wait(client,f'{BASE}/books/{identity}',lambda b:b['phase']=='ready');assert ready['encoding']=='utf-16-le';assert client.get(f'{BASE}/books/{identity}/source').content==raw

def test_pause_restart_resumes_without_replacing_success(cfg):
    with TestClient(create_app(cfg)) as client:
        identity,_=upload(client,'第一章 长篇\n'+('我们继续前行，故事还没有结束。'*120)+'\n第二章 明天\n等待新的旅程。')
        client.post(f'{BASE}/books/{identity}/resume',json={})
        wait(client,f'{BASE}/books/{identity}',lambda b:b['done']>=1)
        client.post(f'{BASE}/books/{identity}/pause')
        wait(client,f'{BASE}/books/{identity}/chapters/1/segments',lambda p:all(r['status']!='running' for r in p['items']))
        before={r['no']:r['take'] for r in client.get(f'{BASE}/books/{identity}/chapters/1/segments').json()['items'] if r['status']=='succeeded'};assert before
    with TestClient(create_app(cfg)) as client:
        assert client.get(f'{BASE}/books/{identity}').json()['state']=='paused';done=complete(client,identity);assert done['state']=='completed'
        after={r['no']:r['take'] for r in client.get(f'{BASE}/books/{identity}/chapters/1/segments').json()['items']}
        assert all(after[n]['id']==take['id'] and after[n]['sha256']==take['sha256'] for n,take in before.items())

def test_failure_retry_and_versioned_review(client):
    identity,_=upload(client,'第一章 开始\n'+('一路向前，光就在前方。'*30))
    FakeEngine.failures=1
    try:bad=complete(client,identity)
    finally:FakeEngine.failures=0
    assert bad['state']=='attention' and bad['failed']==1
    assert client.post(f'{BASE}/books/{identity}/chapters/1/review',json={'status':'approved','listened':True}).status_code==400
    retry=client.post(f'{BASE}/books/{identity}/retry-failed',json={}).json();assert retry['retried']==1
    done=complete(client,identity);assert done['state']=='completed' and done['failed']==0
    assert client.post(f'{BASE}/books/{identity}/chapters/1/review',json={'status':'approved'}).status_code==422
    assert client.post(f'{BASE}/books/{identity}/exports',json={}).status_code==400
    assert client.post(f'{BASE}/books/{identity}/chapters/1/review',json={'status':'approved','listened':True,'reviewer':'test fixture'}).status_code==200
    segment=client.get(f'{BASE}/books/{identity}/chapters/1/segments').json()['items'][0];old=segment['take'];platform=client.app.state.platform
    assert client.post(f'{BASE}/books/{identity}/segments/{segment["no"]}/regenerate').status_code==200
    assert client.get(f'{BASE}/books/{identity}/chapters').json()['items'][0]['review']=='pending'
    complete(client,identity);new=client.get(f'{BASE}/books/{identity}/chapters/1/segments').json()['items'][0]['take'];assert new['seed']!=old['seed'];assert (platform.data/old['path']).exists()
    assert client.post(f'{BASE}/books/{identity}/exports',json={}).status_code==400
    history=client.get(f'{BASE}/books/{identity}/segments/1/attempts').json();assert history['total']>=3

def test_chapter_book_exports_draft_and_formal(client):
    identity,_=upload(client,'第一章 出发\n启程吧，朋友。\n第二章 归来\n我们终于回到了家。');assert complete(client,identity)['state']=='completed'
    for mode in ['chapters','book']:
        r=client.post(f'{BASE}/books/{identity}/exports',json={'mode':mode,'draft':True});assert r.status_code==202,r.text;eid=r.json()['id']
        output=wait(client,f'{BASE}/exports/{eid}',lambda x:x['state'] in {'succeeded','failed'});assert output['state']=='succeeded',output
        raw=client.get(f'{BASE}/exports/{eid}/download').content
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            manifest=json.loads(z.read('manifest.json'));assert manifest['draft'] is True
            waves=[n for n in z.namelist() if n.endswith('.wav')];assert len(waves)==(2 if mode=='chapters' else 1)
            assert all(n.startswith('DRAFT_') for n in waves)
            assert all(sf.info(io.BytesIO(z.read(n))).duration>0 for n in waves)
            records=[json.loads(line) for line in z.read('segments.jsonl').decode().splitlines()];assert len(records)==4 and all(r['take']['sha256'] for r in records)
    for chapter in [1,2]:client.post(f'{BASE}/books/{identity}/chapters/{chapter}/review',json={'status':'approved','listened':True,'reviewer':'test fixture'})
    r=client.post(f'{BASE}/books/{identity}/exports',json={'chapter_no':2});assert r.status_code==202
    output=wait(client,f'{BASE}/exports/{r.json()["id"]}',lambda x:x['state'] in {'succeeded','failed'});assert output['state']=='succeeded' and output['chapters']==1

def test_audio_corruption_is_detected_and_export_not_approved(client):
    identity,_=upload(client,'第一章 测试\n保留原件并校验音频。');complete(client,identity)
    platform=client.app.state.platform;segment=platform.longform.db.segment(identity,1);(platform.data/segment['take']['path']).write_bytes(b'corrupt fixture')
    assert client.get(f'{BASE}/books/{identity}/segments/1/audio').status_code==400
    export=client.post(f'{BASE}/books/{identity}/exports',json={'draft':True}).json();out=wait(client,f'{BASE}/exports/{export["id"]}',lambda x:x['state']=='failed');assert '哈希' in out['error']


def test_rf64_container_and_idle_worker_stay_alive(client,monkeypatch):
    import voice_platform.longform_export as module
    assert module.wav_container(1600000000)=='RF64'
    assert module.wav_container(1000)=='WAV'
    monkeypatch.setattr(module,'wav_container',lambda frames:'RF64')
    identity,_=upload(client,'第一章 测试\n验证真实 RF64 文件。');complete(client,identity)
    request=client.post(f'{BASE}/books/{identity}/exports',json={'draft':True,'mode':'book'}).json()
    exported=wait(client,f'{BASE}/exports/{request["id"]}',lambda x:x['state'] in {'succeeded','failed'});assert exported['state']=='succeeded',exported
    with zipfile.ZipFile(io.BytesIO(client.get(f'{BASE}/exports/{request["id"]}/download').content)) as z:
        wave=next(n for n in z.namelist() if n.endswith('.wav'));raw=z.read(wave);assert raw[:4]==b'RF64';assert sf.info(io.BytesIO(raw)).frames>0
    platform=client.app.state.platform
    with platform.engine_lock:
        platform.last_use=time.monotonic()-1000
        time.sleep(1.2)
        assert platform.worker.is_alive()
