import copy
import io
import json
import time
import zipfile
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from voice_platform.api import create_app
from voice_platform.audio import sha256, split_text, safe_name
from voice_platform.config import load_config
from voice_platform.schemas import GenerationInput, VoiceInput
from voice_platform.service import Platform
from .fake_engine import FakeEngine

def wait(client, job_id, wanted=None):
    end = time.monotonic()+10
    while time.monotonic()<end:
        j = client.get(f"/api/v1/jobs/{job_id}").json()
        if j["status"] in (wanted or {"succeeded", "failed", "cancelled"}):
            return j
        time.sleep(.02)
    raise AssertionError(j)

def submit(client, **values):
    response = client.post("/api/v1/jobs", json=dict(text="这是第一句话。这是第二句话。", **values))
    assert response.status_code == 202, response.text
    return response.json()

def reference(client, rights=True):
    stream=io.BytesIO()
    sf.write(stream, np.sin(np.arange(24000)*.03)*.1, 24000, format="WAV")
    response=client.post("/api/v1/references",files={"file":("ref.wav",stream.getvalue(),"audio/wav")},
        data={"source":"本测试生成", "authorization":"仅测试用途", "rights_confirmed":str(rights).lower()})
    assert response.status_code==201, response.text
    return response.json()

def test_complete_async_streaming_and_provenance(client):
    j=submit(client, candidates=2, streaming=True, seed=123)
    job=wait(client,j["id"])
    assert job["status"]=="succeeded" and len(job["results"])==2
    result=client.get('/api/v1/results/'+job["results"][0]).json()
    assert result["review"]=="pending" and result["parameters"]["effective_seed"]==123
    assert result["timestamp_kind"]=="segment_boundaries_not_forced_alignment"
    pcm,rate=sf.read(io.BytesIO(client.get('/api/v1/results/'+result["id"]+'/audio').content))
    assert rate==24000 and len(pcm)>100
    events=client.get(f'/api/v1/jobs/{j["id"]}/events').json()
    chunks=[e for e in events if e["event"]=='audio_chunk']
    assert len(chunks)>=8
    assert chunks[0]["created_at"]<job["finished_at"]
    assert client.get('/api/v1/events/'+chunks[0]["id"]+'/audio').status_code==200
    stream=client.get(f'/api/v1/jobs/{j["id"]}/stream').text
    assert 'event: audio_chunk' in stream and 'event: end' in stream

def test_voice_versions_freeze_and_project_isolation(client):
    p=client.post('/api/v1/projects',json={"name":"游戏 A"}).json()
    r=reference(client)
    data=dict(name="角色",engine="test",reference_id=r["id"],reference_confirmed=True,status="active",project_id=p["id"],style="温柔",seed=22)
    voice=client.post('/api/v1/voices',json=data).json()
    denied=client.post('/api/v1/jobs',json={"text":"你好","voice_id":voice["id"]})
    assert denied.status_code==400
    j=submit(client, voice_id=voice["id"],project_id=p["id"])
    data.update(name="新名称",style="激昂",project_id=None)
    updated=client.put('/api/v1/voices/'+voice["id"],json=data).json()
    assert updated["version"]==2
    assert len(client.get('/api/v1/voices/'+voice["id"]+'/versions').json())==2
    job=wait(client,j["id"])
    assert job["voice_snapshot"]["name"]=="角色" and job["style"]=="温柔"
    assert job["voice_snapshot"]["reference"]["sha256"]==r["sha256"]

def test_reference_authorization_and_confirmation(client):
    r=reference(client,rights=False)
    assert client.post('/api/v1/voices',json=dict(name="无权利",engine="test",reference_id=r["id"])).status_code==400
    assert client.post('/api/v1/voices',json=dict(name="错误正式音色",engine="test",status="active")).status_code==400
    bad=client.post('/api/v1/references',files={'file':('wrong.wav',b'not wave')},data=dict(source='self',authorization='test'))
    assert bad.status_code==400

def test_review_gate_and_non_destructive_export(client):
    job=wait(client,submit(client)["id"])
    rid=job["results"][0]
    result=client.get('/api/v1/results/'+rid).json()
    assert client.post('/api/v1/exports',json={'result_ids':[rid]}).status_code==400
    assert client.put(f'/api/v1/results/{rid}/review',json={'status':'approved'}).status_code==422
    draft=client.post('/api/v1/exports',json={'result_ids':[rid],'draft':True,'adapter':'game_audio'}).json()
    archive=zipfile.ZipFile(io.BytesIO(client.get('/api/v1/exports/'+draft['id']+'/download').content))
    assert any('/DRAFT_' in n for n in archive.namelist())
    assert client.put(f'/api/v1/results/{rid}/review',json={'status':'approved','listened':True}).status_code==200
    output=client.post('/api/v1/exports',json={'result_ids':[rid],'adapter':'media_dubbing','format':'flac','normalize':True,'sample_rate':16000}).json()
    archive=zipfile.ZipFile(io.BytesIO(client.get('/api/v1/exports/'+output['id']+'/download').content))
    wav=next(n for n in archive.namelist() if n.endswith('.flac'))
    info=sf.info(io.BytesIO(archive.read(wav)))
    assert info.samplerate==16000
    assert any(n.endswith('.srt') for n in archive.namelist())
    original=client.get('/api/v1/results/'+rid).json()
    assert original['sha256']==result['sha256']
    assert client.post('/api/v1/exports',json={'result_ids':[rid],'trim_silence':True,'subtitles':True}).status_code==400
    path=client.app.state.platform.data/result['path']
    assert sha256(path)==result['sha256']

def test_failure_retry_and_preservation(client):
    first=wait(client,submit(client)["id"])
    rid=first['results'][0]
    original=client.get('/api/v1/results/'+rid+'/audio').content
    FakeEngine.failures=1
    second=wait(client,submit(client)["id"])
    assert second['status']=='succeeded' and second['attempt']==2
    failed=client.post('/api/v1/jobs',json={'text':'FAIL','max_retries':0,'seed':19}).json()
    job=wait(client,failed['id'])
    assert job['status']=='failed' and job['attempt']==1
    retry=client.post('/api/v1/jobs/'+job['id']+'/retry').json()
    assert retry['id']!=job['id'] and retry['seed']==19 and retry['retry_of']==job['id']
    wait(client,retry['id'])
    assert client.get('/api/v1/results/'+rid+'/audio').content==original

def test_cancel_queued_and_running(client):
    long=submit(client,streaming=True,candidates=5)
    queued=submit(client)
    cancelled=client.post('/api/v1/jobs/'+queued['id']+'/cancel').json()
    assert cancelled['status']=='cancelled'
    wait(client,long['id'],{'running'})
    client.post('/api/v1/jobs/'+long['id']+'/cancel')
    assert wait(client,long['id'])['status']=='cancelled'

def test_atomic_batch_validation_and_model_capabilities(client):
    before=len(client.get('/api/v1/jobs').json())
    body={'items':[{'text':'good'},{'text':'bad','engine':'not-real'}]}
    assert client.post('/api/v1/batches',json=body).status_code==400
    assert len(client.get('/api/v1/jobs').json())==before
    for values in ({'streaming':True},{'style':'young'},{'language':'zh'}):
        assert client.post('/api/v1/jobs',json={'text':'test','engine':'limited',**values}).status_code==400
    batch=client.post('/api/v1/batches',json={'items':[{'text':'one','engine':'limited'},{'text':'two'}]}).json()
    assert len(batch['jobs'])==2 and batch['batch_id']

def test_restart_recovery(cfg):
    platform=Platform(cfg)
    j=platform.prepare_job(GenerationInput(text='queued'))
    platform.store.save('jobs',j)
    interrupted=copy.deepcopy(j)
    interrupted.update(id='interrupted',status='running')
    platform.store.save('jobs',interrupted)
    with TestClient(create_app(cfg)) as client:
        assert client.get('/api/v1/jobs/interrupted').json()['status']=='failed'
        assert wait(client,j['id'])['status']=='succeeded'

def test_reference_hash_and_model_pin_reject(cfg):
    platform=Platform(cfg)
    j=platform.prepare_job(GenerationInput(text='hello'))
    j['model']['revision']='different'
    platform.store.save('jobs',j)
    platform.start()
    try:
        deadline=time.monotonic()+5
        while platform.store.get('jobs',j['id'])['status'] not in {'failed','succeeded'} and time.monotonic()<deadline:
            time.sleep(.02)
        assert platform.store.get('jobs',j['id'])['status']=='failed'
    finally:
        platform.stop()

def test_boundaries_auth_and_openapi(cfg,monkeypatch):
    monkeypatch.setenv('VOICE_PLATFORM_TOKEN','test-token-not-real')
    with TestClient(create_app(cfg)) as client:
        assert client.get('/api/v1/health').status_code==401
        assert client.get('/api/v1/health',headers={'Authorization':'Bearer test-token-not-real'}).status_code==200
        assert client.post('/api/v1/session',json={'token':'bad'}).status_code==401
        assert client.post('/api/v1/session',json={'token':'test-token-not-real'}).status_code==200
        assert client.get('/openapi.json').json()['info']['version']=='1.0.0'
        assert client.post('/api/v1/projects',json={'name':'x'},headers={'Origin':'https://evil.example'}).status_code==403
        assert client.get('/api/v1/health',headers={'Host':'evil.example'}).status_code==403

def test_queue_capacity_and_backup(cfg):
    cfg['max_pending_jobs']=1
    platform=Platform(cfg)
    platform.submit([GenerationInput(text='first')])
    with pytest.raises(ValueError,match='队列已满'):
        platform.submit([GenerationInput(text='second')])
    backup=platform.backup()
    assert (Path(backup['directory'])/'platform.sqlite3').exists()

def test_settings_freeze_pipeline_and_reference_hash(client):
    platform=client.app.state.platform
    job=platform.prepare_job(GenerationInput(text='new task'))
    before=job['pipeline'].copy()
    response=client.put('/api/v1/settings',json=dict(idle_unload_seconds=60,segment_chars=80,segment_pause_ms=90,max_pending_jobs=10))
    assert response.status_code==200
    assert job['pipeline']==before
    assert platform.prepare_job(GenerationInput(text='later'))['pipeline']['segment_chars']==80
    r=reference(client)
    v=client.post('/api/v1/voices',json=dict(name='frozen',engine='test',reference_id=r['id'])).json()
    frozen=platform.prepare_job(GenerationInput(text='hello',voice_id=v['id'],max_retries=0))
    (platform.data/r['path']).write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='哈希'):
        platform._generate(frozen,0)

def test_engine_specific_voice_parameters(client):
    voice=client.post('/api/v1/voices',json=dict(name='configured',engine='test',engine_options={'test_strength':2.5})).json()
    job=submit(client,voice_id=voice['id'])
    assert job['request']['engine_options']=={'test_strength':2.5}
    for options in ({'unsupported':1},{'test_strength':4},{'test_strength':True},{'test_strength':'x'}):
        assert client.post('/api/v1/jobs',json=dict(text='test',engine_options=options)).status_code==400
    limited=client.post('/api/v1/jobs',json=dict(text='test',engine='limited')).json()
    assert limited['request']['engine_options']=={}

@pytest.mark.parametrize('text', ['你好，世界。第二句话！再见。','x'*700, 'English words, with punctuations. Another sentence!','这是一句话\n第二行内容', ' a b c '])
def test_segment_integrity(text):
    chunks=split_text(text,15)
    assert all(0<len(c)<=15 for c in chunks)
    assert ''.join(''.join(chunks).split())==''.join(text.split())

def test_file_names():
    assert '/' not in safe_name('../../escape')
    assert safe_name('CON')=='_CON'
