"""Controlled end-to-end reference flow. No model quality or listener approval claims."""
import copy
import numpy as np
import pytest
import soundfile as sf
from voice_platform.audio import sha256
from voice_platform.schemas import ProcessingInput
from voice_platform.speaker_tracking import assemble_clips,match_sources
from voice_platform.tracking_quality import coverage,reference_quality,restore_timeline
from voice_platform.references import ReferenceLibrary
from voice_platform.restoration import AudioRestoration
from .test_restoration import analysis,upload,until


def seed(platform,recording):
    folder=platform.data/'audio-processing'/'tracking-test';folder.mkdir(parents=True)
    outputs=[]
    for i in range(3):
        path=folder/f'{i}.wav';sf.write(path,np.sin(np.arange(32000)*(.03+i*.01))*.1,16000)
        spans=[dict(source_start=i*4.,source_end=i*4.+2.,output_start=0.,output_end=2.)]
        outputs.append(dict(id=f'clip-{i}',key=str(i),path=str(path.relative_to(platform.data)),sha256=sha256(path),
            sample_rate=16000,duration=2.,channels=1,kind='clip',speaker_id='A',origin='solo',
            source_spans=spans,speech_spans=[dict(source_start=i*4.,source_end=i*4.+2.)],
            embedding=[1.,0.],transcript=dict(text='test',confirmed=False),revision=1,label='test'))
    item=dict(id='tracking-test',recording_id=recording['id'],root_recording_id=recording['id'],
        source_snapshot=recording,outputs=outputs,status='succeeded',operations=['track_speakers'],
        model_sources={},tracking=dict(speakers=[dict(id='A',name='甲'),dict(id='B',name='乙')],revision=1),
        created_at='2026-10-27T00:00:00+00:00')
    platform.store.save('audio_processing',item)
    return item


def test_coverage_duplicate_source_and_silence_policy(cfg):
    options=cfg['speaker_tracking']
    clips=[dict(speaker_id='A',duration=2.,source_spans=[dict(source_start=0,source_end=2)],speech_spans=[dict(source_start=0,source_end=2)])]
    assert reference_quality(clips,options,True,True)['unique_speech_seconds']==2
    assert reference_quality(clips,options,True,True)['state']=='blocked'
    duplicate=copy.deepcopy(clips[0]);duplicate['duration']=12.
    q=reference_quality(clips+[duplicate],options,True,True)
    assert q['unique_speech_seconds']==2 and any('重复' in x for x in q['issues'])
    assert coverage([dict(source_start=0,source_end=1),dict(source_start=.5,source_end=2)])==2


def test_full_timeline_restores_internal_pause_and_overlap():
    clips=[dict(origin='solo',source_spans=[dict(source_start=0,source_end=1,output_start=0,output_end=1),
        dict(source_start=3,source_end=4,output_start=1.2,output_end=2.2)]),
        dict(origin='overlap',source_spans=[dict(source_start=5,source_end=6,output_start=0,output_end=1)])]
    wave=np.concatenate([np.ones(10),np.zeros(2),np.ones(10)*2])
    out=restore_timeline(clips,70,10,lambda c:wave if c['origin']=='solo' else np.ones(10)*3)
    assert np.all(out[:10]==1) and not out[10:30].any() and np.all(out[30:40]==2)
    assert np.all(out[50:60]==3) and not out[60:].any()


def test_partial_anchor_rejects_competing_sources():
    assert [m['speaker'] for m in match_sources([[1,0],[0,1]],{'A':[1,0]},['A','B'],.65,.08)]==['A',None]
    assert all(m['speaker'] is None for m in match_sources([[1,0],[1,0]],{'A':[1,0]},['A','B'],.65,.08))
    with pytest.raises(ValueError):ProcessingInput(recording_id='x',speaker_count=4)


def test_compose_direct_library_voice_and_stale_revision(client,monkeypatch,ffmpeg_available):
    platform=client.app.state.platform
    monkeypatch.setattr(ReferenceLibrary,'_run_worker',analysis)
    original,raw=upload(client);original=until(client,'recordings/'+original['id'],lambda r:r['status']=='succeeded')
    task=seed(platform,original);base='/api/v1/audio-processing/'+task['id']
    before=[sha256(platform.data/o['path']) for o in task['outputs']]
    # Real bounded-memory assembly; ASR/embedding are controlled to test HTTP lifecycle.
    from voice_platform.speaker_tracking import Analyzer
    monkeypatch.setattr(Analyzer,'transcribe',lambda self,y:dict(text='controlled transcript',confirmed=False))
    monkeypatch.setattr(Analyzer,'embedding',lambda self,y:[1.,0.])
    def worker(self,request,folder,kind,identity):return assemble_clips(request,folder,lambda *_:None)
    monkeypatch.setattr(AudioRestoration,'_run_worker',worker)
    monkeypatch.setattr(AudioRestoration,'_decode',lambda *_:pytest.fail('assembly must not decode the original'))
    body=dict(output_ids=[o['id'] for o in task['outputs']],name='同人参考',gap_ms=120,purpose='reference',speaker_confirmed=True,expected_revision=1)
    denied=client.post(base+'/assemble',json=dict(body,speaker_confirmed=False));assert denied.status_code==400
    accepted=client.post(base+'/assemble',json=body);assert accepted.status_code==202,accepted.text
    composite=until(client,'audio-processing/'+accepted.json()['id'],lambda r:r['status'] in {'succeeded','failed'})
    assert composite['status']=='succeeded',composite
    assert composite['outputs'][0]['duration']==pytest.approx(6.24)
    endpoint='/api/v1/audio-processing/'+composite['id']+'/save-reference'
    assert client.post(endpoint,json=dict(name='voice',listened=False)).status_code==400
    ref=client.post(endpoint,json=dict(name='voice',listened=True)).json()
    assert ref['reference_kind']=='composite' and ref['review']=='pending' and not ref['transcript']['confirmed']
    assert len(ref['component_refs'])==3 and ref['qc']['unique_speech_seconds']==6
    assert client.post(endpoint,json=dict(name='voice',listened=True)).json()['id']==ref['id']
    voice=client.post('/api/v1/reference-voices',json=dict(reference_id=ref['id'],name='人物甲')).json()
    assert voice['reference_id']==ref['id'] and voice['status']=='draft'
    job=client.post('/api/v1/jobs',json=dict(text='同一份参考直接用于生成。',voice_id=voice['id']));assert job.status_code==202,job.text
    correction=dict(speaker_id='B',confirmed=True,expected_revision=1)
    updated=client.put(base+'/clips/clip-0/assignment',json=correction);assert updated.status_code==200,updated.text
    assert updated.json()['tracking']['revision']==2
    assert client.put(base+'/clips/clip-1/assignment',json=correction).status_code==400
    assert client.post(endpoint,json=dict(name='voice',listened=True)).status_code==400
    assert platform.store.get('references',ref['id'])['source_changed']
    assert platform.store.get('voices',voice['id'])['reference_id']==ref['id']
    assert [sha256(platform.data/o['path']) for o in task['outputs']]==before
    assert (platform.data/original['original_path']).read_bytes()==raw
    assert client.post(base+'/assemble',json=dict(body,expected_revision=2)).status_code==400


def test_event_cursor_is_task_scoped_and_incremental(cfg):
    from voice_platform.store import Store
    store=Store(cfg['data_dir'])
    # 100k unrelated historical events, inserted in one transaction rather than
    # spending the test on filesystem commits. Reads must stay task-indexed.
    with store.connect() as db:
        db.execute("WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<100000) INSERT INTO entities SELECT 'events','history-'||x,json_object('id','history-'||x,'job_id','other','event','progress') FROM n")
        db.execute("INSERT INTO event_sequence(event_id,job_id) SELECT id,'other' FROM entities WHERE kind='events'")
    first=store.event('target','progress',value=1);last=store.event('target','succeeded')
    assert [e['id'] for e in store.events('target',first['seq'])]==[last['id']]
    assert store.event_cursor('target',first['id'])==first['seq']
    with pytest.raises(ValueError):store.event_cursor('other',first['id'])
    store2=Store(cfg['data_dir']);assert len(store2.events('target'))==2


def test_separator_weights_load_once_for_multiple_overlap_windows(cfg,monkeypatch):
    pytest.importorskip('torch')
    import types
    import voice_platform.processing_engines as module
    cfg['audio_processing']['device']='cpu';engine=module.ProcessingEngines(cfg);loads=[]
    real_import=module.importlib.import_module
    class Model:
        def __call__(self,value):return [value*.6,value*.4]
    monkeypatch.setattr(module.importlib,'import_module',lambda name:types.SimpleNamespace(MossFormer2_SS_16K=lambda args:types.SimpleNamespace(model=None)) if name.endswith('mossformer2_ss.mossformer2') else real_import(name))
    monkeypatch.setattr(engine,'load_weights',lambda *args:loads.append(1) or Model())
    y=np.sin(np.arange(1600)*.05).astype(np.float32)[None,:]*.1
    for _ in range(10):engine.separate(y,16000,lambda _:None,retain=True)
    assert len(loads)==1
    engine.close();assert not hasattr(engine,'separator')


def test_background_export_idempotency_and_recovery(client,monkeypatch):
    import threading
    platform=client.app.state.platform
    entered=threading.Event();release=threading.Event()
    monkeypatch.setattr(platform,'validate_export',lambda request:None)
    def export(request,stop_event=None,progress=None):
        entered.set();release.wait(3)
        if stop_event.is_set():raise InterruptedError('cancelled')
        return dict(id='package')
    monkeypatch.setattr(platform,'export',export)
    body=dict(result_ids=['result'])
    first=client.post('/api/v1/export-tasks',json=body,headers={'Idempotency-Key':'request-one'})
    assert first.status_code==202
    identity=first.json()['id'];assert entered.wait(3)
    assert client.post('/api/v1/export-tasks',json=body,headers={'Idempotency-Key':'request-one'}).json()['id']==identity
    assert client.post('/api/v1/export-tasks',json=dict(result_ids=['other']),headers={'Idempotency-Key':'request-one'}).status_code==400
    assert client.post('/api/v1/export-tasks/'+identity+'/cancel').status_code==200
    release.set();item=until(client,'export-tasks/'+identity,lambda i:i['status']=='cancelled')
    assert item['status']=='cancelled' and 'export_id' not in item
    assert client.get('/api/v1/export-tasks').json()[0]['id']==identity
