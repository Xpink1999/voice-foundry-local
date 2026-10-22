import copy
import io
import json
import time
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from voice_platform.audio import sha256
from voice_platform.reference_analysis import intervals,silence_metrics,cluster,char_error
from voice_platform.references import ReferenceLibrary
from voice_platform.schemas import GenerationInput,VoiceInput,CompareReferencesInput

def fake_analysis(self,request,folder,kind,identity):
    if request['mode']=='compare':
        ids=[r['reference_id'] for r in request['items']]
        return dict(ranking=[dict(reference_id=i,score=.8,speaker_similarity=.8,seed_consistency=.9,asr_character_error=0,result_ids=[]) for i in ids],recommended_reference_id=ids[0],note='test only')
    path=Path(request['recording']['analysis_path']);y,sr=sf.read(path,dtype='float32')
    clips=[]
    for i,(start,end) in enumerate([(1.,7.),(9.,15.)]):
        target=folder/f'clip-{i}.wav';sf.write(target,y[int(start*sr):int(end*sr)],sr)
        clips.append(dict(file=str(target),start=start,end=end,duration=end-start,sample_rate=sr,sha256=sha256(target),
            embedding=[1.,0.,0.],speaker_labels=['S1'],quality=dict(score=.9,warnings=[]),
            transcript=dict(text='自动识别的文本',confirmed=False,version=1,source='test')))
    return dict(clips=clips,summary=dict(duration=len(y)/sr,models={'test':True},estimated_speakers=1))

def upload(client):
    stream=io.BytesIO();sf.write(stream,.1*np.sin(np.arange(18*16000)*.1),16000,format='WAV')
    original=stream.getvalue()
    response=client.post('/api/v1/recordings',files={'file':('long.wav',original)},data={'source':'test synthetic','authorization':'test only','rights_confirmed':'true'})
    assert response.status_code==202,response.text
    identity=response.json()['id']
    for _ in range(200):
        item=client.get('/api/v1/recordings/'+identity).json()
        if item['status'] in {'succeeded','failed'}:break
        time.sleep(.03)
    assert item['status']=='succeeded',item
    return item,original

def test_original_clips_transcript_and_multi_reference(client,monkeypatch):
    monkeypatch.setattr(ReferenceLibrary,'_run_worker',fake_analysis)
    item,original=upload(client)
    assert client.get('/api/v1/recordings/'+item['id']+'/original').content==original
    refs=item['candidates'];assert len(refs)==2 and not refs[0]['saved']
    assert not any(r['id']==refs[0]['id'] for r in client.get('/api/v1/references').json())
    assert client.post('/api/v1/voices',json=dict(name='draft',engine='test',reference_id=refs[0]['id'])).status_code==400
    saved=client.post('/api/v1/recordings/'+item['id']+'/save',json={'reference_ids':[r['id'] for r in refs]}).json()
    assert all(r['saved'] for r in saved)
    assert saved[0]['sha256']!=saved[1]['sha256'] or saved[0]['start']!=saved[1]['start']
    transcript=client.put('/api/v1/references/'+refs[0]['id']+'/transcript',json={'text':'校对后的原话','confirmed':True}).json()
    assert transcript['transcript']['version']==2 and len(transcript['transcript_history'])==1
    voice=client.post('/api/v1/voices',json=dict(name='person',engine='test',reference_id=refs[0]['id'],reference_ids=[r['id'] for r in refs],reference_scenarios={refs[1]['id']:'平静'})).json()
    assert len(voice['references'])==2 and voice['reference_id']==refs[0]['id']
    job=client.post('/api/v1/jobs',json=dict(text='new text',voice_id=voice['id'],reference_id=refs[1]['id'])).json()
    assert job['reference_snapshot']['id']==refs[1]['id'] and job['voice_snapshot']['reference_id']==refs[0]['id']
    assert job['reference_snapshot']['start']==9
    client.put('/api/v1/references/'+refs[1]['id']+'/transcript',json={'text':'later','confirmed':False})
    assert client.get('/api/v1/jobs/'+job['id']).json()['reference_snapshot']['transcript']['text']=='自动识别的文本'

def test_hifi_validation_and_forwarding(client,monkeypatch):
    monkeypatch.setattr(ReferenceLibrary,'_run_worker',fake_analysis)
    item,_=upload(client);ids=[r['id'] for r in item['candidates']]
    client.post('/api/v1/recordings/'+item['id']+'/save',json={'reference_ids':ids})
    platform=client.app.state.platform
    engine=platform.engines['test'];caps=engine.capabilities
    monkeypatch.setattr(engine,'capabilities',lambda:dict(caps(),hifi_cloning=True))
    assert client.post('/api/v1/jobs',json={'text':'hello','clone_mode':'hifi'}).status_code==400
    voice=client.post('/api/v1/voices',json={'name':'hifi person','style':'沉稳男性','reference_id':ids[0],'engine':'test'}).json()
    assert client.post('/api/v1/jobs',json={'text':'hello','voice_id':voice['id'],'clone_mode':'hifi','style':'excited'}).status_code==400
    job=client.post('/api/v1/jobs',json={'text':'hello','voice_id':voice['id'],'clone_mode':'hifi','engine':'test'}).json()
    assert job['style']=='' and job['pipeline']['control_note'] and job['voice_snapshot']['style']=='沉稳男性'
    assert job['reference_snapshot']['transcript']['text']
    for _ in range(200):
        current=client.get('/api/v1/jobs/'+job['id']).json()
        if current['status']=='succeeded':break
        time.sleep(.02)
    call=next(c for c in engine.calls if c.get('clone_mode')=='hifi')
    assert call['prompt_text']=='自动识别的文本' and call['reference_path']

def test_comparison_preserves_drafts_and_all_references(client,monkeypatch):
    monkeypatch.setattr(ReferenceLibrary,'_run_worker',fake_analysis)
    item,_=upload(client);ids=[r['id'] for r in item['candidates']]
    client.post('/api/v1/recordings/'+item['id']+'/save',json={'reference_ids':ids})
    voice=client.post('/api/v1/voices',json={'name':'person','engine':'test'}).json()
    response=client.post('/api/v1/reference-comparisons',json={'voice_id':voice['id'],'reference_ids':ids,'text':'这是固定比较文本'});
    assert response.status_code==202,response.text
    comparison=response.json()
    for _ in range(200):
        comparison=client.get('/api/v1/reference-comparisons/'+comparison['id']).json()
        if comparison['status'] in {'succeeded','failed'}:break
        time.sleep(.03)
    assert comparison['status']=='succeeded',comparison
    assert len(comparison['job_mapping'])==2 and all(len(j)==2 for j in comparison['job_mapping'].values())
    applied=client.post('/api/v1/reference-comparisons/'+comparison['id']+'/apply').json()
    assert len(applied['reference_ids'])==2 and not applied['reference_confirmed'] and applied['status']=='draft'
    assert all(r['review']=='pending' for r in client.get('/api/v1/results').json())
    assert client.post('/api/v1/reference-comparisons/'+comparison['id']+'/apply').status_code==400

def test_recording_failure_keeps_original(client,monkeypatch):
    def fail(*args):raise ValueError('analysis unavailable')
    monkeypatch.setattr(ReferenceLibrary,'_run_worker',fail)
    stream=io.BytesIO();sf.write(stream,np.zeros(16000),16000,format='WAV')
    response=client.post('/api/v1/recordings',files={'file':('test.wav',stream.getvalue())},data={'source':'self','authorization':'test'})
    identity=response.json()['id']
    for _ in range(100):
        item=client.get('/api/v1/recordings/'+identity).json()
        if item['status']=='failed':break
        time.sleep(.03)
    assert item['status']=='failed'
    assert client.get('/api/v1/recordings/'+identity+'/original').content==stream.getvalue()
    assert client.post('/api/v1/recordings/'+identity+'/retry').status_code==202

def test_intervals_never_stitch_and_respect_speaker_turns(cfg):
    options=cfg['reference_preprocessing']
    speech=[dict(start=1,end=8,speaker_label='S1'),dict(start=8.2,end=13,speaker_label='S2'),dict(start=18,end=65,speaker_label='S1')]
    cuts,count=intervals(speech,70,options)
    assert all(0<end-start<=30 for start,end in cuts)
    assert all(not (start<8 and end>9) for start,end in cuts)
    assert all(not (start<13 and end>18) for start,end in cuts)
    assert count>=5

def test_metrics_and_speaker_clustering():
    labels,_=cluster([[1,0],[.99,.01],[0,1]],.72);assert labels==[0,0,1]
    assert char_error('你好，世界。','你好世界')==0
    assert char_error('你好','你')==.5
    assert char_error('故事，就从这里开始。','故事就從這裡開始')==0
    assert char_error('ＡＢＣ test','abc TEST!')==0
    silence=silence_metrics(np.concatenate([np.zeros(48000),np.ones(16000)*.1]),16000)
    assert silence['longest_seconds']==3 and silence['ratio']==.75
