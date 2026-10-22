import io
import time
from pathlib import Path
import numpy as np
import soundfile as sf
from voice_platform.audio import sha256
from voice_platform.processing_engines import overlap_add,restore_source_scale
from voice_platform.reference_worker import write_progress
from voice_platform.references import ReferenceLibrary
from voice_platform.restoration import AudioRestoration
from .test_platform import wait


def analysis(self,request,folder,kind,identity):
    y,sr=sf.read(request['recording']['analysis_path'],dtype='float32');duration=len(y)/sr
    spans=[(0,min(6,duration))]+([(8.,min(14,duration))] if duration>14 else [])
    clips=[]
    for i,(start,end) in enumerate(spans):
        path=folder/f'clip-{i}.wav';sf.write(path,y[round(start*sr):round(end*sr)],sr)
        clips.append(dict(file=str(path),start=start,end=end,duration=end-start,sample_rate=sr,sha256=sha256(path),embedding=[1.,0.,0.],speaker_labels=['S1'],
            quality=dict(score=.9,speech_score=.9,warnings=[]),transcript=dict(text='用于验证的转写',confirmed=False,version=1,source='test')))
    return dict(clips=clips,summary=dict(duration=duration,models={'test':True},estimated_speakers=1,music_suspected=True,noise_suspected=True))


def process(self,request,folder,kind,identity):
    y,sr=sf.read(request['input_path'],dtype='float32',always_2d=True);outputs=[]
    for index,role in enumerate(('speech','speech','background')):
        path=folder/f'output-{index}.wav';sf.write(path,y*(1-index*.2),sr,subtype='PCM_24')
        outputs.append(dict(file=str(path),sha256=sha256(path),sample_rate=sr,duration=len(y)/sr,channels=y.shape[1],label=f'output {index}',role=role,stage='separate',final=True))
    return dict(outputs=outputs,model_sources={'test':'controlled fake worker'},device='test',note='test only')


def until(client,route,ready):
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        response=client.get('/api/v1/'+route);assert response.status_code==200,response.text
        item=response.json()
        if ready(item):return item
        time.sleep(.03)
    raise AssertionError(item)


def upload(client,smart=False):
    stream=io.BytesIO();sf.write(stream,.15*np.sin(np.arange(18*16000,dtype=np.float32)*.05),16000,format='WAV')
    response=client.post('/api/v1/recordings',files={'file':('source.wav',stream.getvalue())},data=dict(source='self synthetic',authorization='controlled tests',rights_confirmed='true',smart_reference=str(smart).lower()))
    assert response.status_code==202,response.text
    return response.json(),stream.getvalue()


def test_overlap_add_preserves_tail_channels_and_aligns_swaps():
    t=np.arange(1357,dtype=np.float32);signal=np.stack([np.sin(t*.11),np.cos(t*.07)])
    calls=[0]
    def predict(chunk):
        calls[0]+=1;return chunk[::-1] if calls[0]%2==0 else chunk
    progress=[];result=overlap_add(signal,100,4,predict,progress.append,True)
    assert result.shape==signal.shape and np.max(np.abs(result-signal))<1e-5
    assert progress[-1]==1 and np.isfinite(result).all()
    short=overlap_add(signal[:,:57],100,4,lambda x:x,lambda _:None)
    assert short.shape==(2,57) and np.allclose(short,signal[:,:57])


def test_source_scale_restores_ambiguous_neural_gain():
    t=np.arange(1200,dtype=np.float32);sources=np.stack([.08*np.sin(t*.11),.03*np.cos(t*.23)])
    restored,gains=restore_source_scale(sources*np.array([[35.],[.01]]),sources.sum(axis=0))
    assert np.max(np.abs(restored-sources))<1e-5 and np.allclose(gains,[1/35,100],rtol=1e-4)


def test_windows_progress_lock_is_advisory(tmp_path,monkeypatch):
    target=tmp_path/'progress.json';original=Path.replace;calls=[]
    def busy(path,destination):
        calls.append(True)
        if len(calls)<3:raise PermissionError('controlled Windows share violation')
        return original(path,destination)
    monkeypatch.setattr(Path,'replace',busy)
    assert write_progress(target,100,'done') and len(calls)==3 and target.exists()
    def locked(*args):raise PermissionError('controlled long share violation')
    monkeypatch.setattr(Path,'replace',locked)
    assert write_progress(target,100,'done') is False


def test_restoration_original_outputs_lineage_and_dedup(client,monkeypatch):
    monkeypatch.setattr(ReferenceLibrary,'_run_worker',analysis);monkeypatch.setattr(AudioRestoration,'_run_worker',process)
    recording,original=upload(client);until(client,'recordings/'+recording['id'],lambda x:x['status']=='succeeded')
    response=client.post('/api/v1/audio-processing',json=dict(recording_id=recording['id'],operations=['separate']))
    assert response.status_code==202,response.text
    task=until(client,'audio-processing/'+response.json()['id'],lambda x:x['status'] in {'succeeded','failed'})
    assert task['status']=='succeeded',task.get('error')
    task=until(client,'audio-processing/'+task['id'],lambda x:len(x['child_recording_ids'])==2)
    assert client.get('/api/v1/recordings/'+recording['id']+'/original').content==original
    assert client.get('/api/v1/audio-processing/'+task['id']+'/before').status_code==200
    for output in task['outputs']:
        response=client.get(f"/api/v1/audio-processing/{task['id']}/outputs/{output['id']}")
        assert response.status_code==200 and len(response.content)>100
    background=task['outputs'][-1]
    assert client.post(f"/api/v1/audio-processing/{task['id']}/analyze-output",json={'output_id':background['id']}).status_code==400
    output=task['outputs'][0]
    again=client.post(f"/api/v1/audio-processing/{task['id']}/analyze-output",json={'output_id':output['id']}).json()
    assert again['id']==output['recording_id'] and again['root_recording_id']==recording['id']
    child=until(client,'recordings/'+again['id'],lambda x:x['status']=='succeeded')
    ref=child['candidates'][0];assert ref['source_lineage']['original_sha256']==recording['original_sha256'] and ref['processing_id']==task['id']
    voice=client.post('/api/v1/reference-voices',json={'reference_id':ref['id'],'name':'test person'}).json()
    assert voice['status']=='draft' and voice['reference_id']==ref['id'] and not voice['reference_confirmed']
    assert client.get('/api/v1/recordings/'+recording['id']+'/original').content==original


def test_smart_reference_one_upload_ready_and_single_reference_voice(client,monkeypatch):
    monkeypatch.setattr(ReferenceLibrary,'_run_worker',analysis);monkeypatch.setattr(AudioRestoration,'_run_worker',process)
    item,original=upload(client,True)
    result=until(client,'recordings/'+item['id'],lambda x:x.get('smart_reference',{}).get('status') in {'ready','partial','failed'})
    assert result['smart_reference']['status']=='ready',result['smart_reference']
    assert result['recommendations'] and len(result['candidates'])==6
    task=client.get('/api/v1/audio-processing/'+result['smart_reference']['processing_id']).json()
    assert task['operations']==['remove_music','separate','denoise']
    ref=next(r for r in result['candidates'] if r.get('processing_id')==task['id'])
    assert client.post('/api/v1/recordings/'+item['id']+'/save',json={'reference_ids':[ref['id']]}).status_code==200
    voice=client.post('/api/v1/reference-voices',json={'reference_id':ref['id'],'name':'quick person'}).json()
    assert voice['reference_ids']==[ref['id']] and voice['reference_confirmed'] is False
    second=next(r for r in result['candidates'] if r['id']!=ref['id'])
    attached=client.post('/api/v1/reference-voices',json={'reference_id':second['id'],'voice_id':voice['id'],'scenario':'平静对白'}).json()
    assert attached['version']==voice['version']+1 and attached['reference_id']==ref['id']
    assert set(attached['reference_ids'])=={ref['id'],second['id']} and attached['reference_scenarios'][second['id']]=='平静对白'
    assert client.get('/api/v1/recordings/'+item['id']+'/original').content==original


def test_processing_failure_preserves_original_and_smart_fallback(client,monkeypatch):
    monkeypatch.setattr(ReferenceLibrary,'_run_worker',analysis)
    def fail(*args):raise ValueError('controlled model failure')
    monkeypatch.setattr(AudioRestoration,'_run_worker',fail)
    recording,original=upload(client,True)
    result=until(client,'recordings/'+recording['id'],lambda x:x.get('smart_reference',{}).get('status')=='partial')
    assert result['recommendations'] and len(result['candidates'])==2
    task=client.get('/api/v1/audio-processing/'+result['smart_reference']['processing_id']).json();assert task['status']=='failed'
    assert client.get('/api/v1/recordings/'+recording['id']+'/original').content==original


def test_retry_failed_child_refreshes_recommendation_without_rerunning_models(client,monkeypatch):
    failed=[]
    def once(self,request,*args):
        if request.get('recording',{}).get('processing_id') and not failed:
            failed.append(True);raise ValueError('controlled child failure')
        return analysis(self,request,*args)
    monkeypatch.setattr(ReferenceLibrary,'_run_worker',once);monkeypatch.setattr(AudioRestoration,'_run_worker',process)
    recording,_=upload(client,True)
    partial=until(client,'recordings/'+recording['id'],lambda x:x.get('smart_reference',{}).get('status')=='partial')
    child=next(c for c in partial['analysis_children'] if c['status']=='failed')
    assert client.post('/api/v1/recordings/'+child['id']+'/retry').status_code==202
    ready=until(client,'recordings/'+recording['id'],lambda x:x.get('smart_reference',{}).get('status')=='ready')
    assert ready['smart_reference']['processing_id']==partial['smart_reference']['processing_id']
    assert len(client.get('/api/v1/audio-processing').json())==1 and len(ready['candidates'])==6


def test_processing_validates_operations_hash_and_rights(client,monkeypatch):
    monkeypatch.setattr(ReferenceLibrary,'_run_worker',analysis);monkeypatch.setattr(AudioRestoration,'_run_worker',process)
    recording,_=upload(client);result=until(client,'recordings/'+recording['id'],lambda x:x['status']=='succeeded')
    assert client.post('/api/v1/audio-processing',json={'recording_id':recording['id'],'operations':['denoise','denoise']}).status_code==422
    assert client.post('/api/v1/audio-processing',json={'recording_id':recording['id'],'operations':['unknown']}).status_code==422
    platform=client.app.state.platform;ref=result['candidates'][0];platform.store.update('references',ref['id'],rights_confirmed=False)
    assert client.post('/api/v1/reference-voices',json={'reference_id':ref['id'],'name':'blocked'}).status_code==400
    source=Path(platform.data/recording['original_path']);source.write_bytes(b'changed')
    task=client.post('/api/v1/audio-processing',json={'recording_id':recording['id'],'operations':['denoise']}).json()
    failed=until(client,'audio-processing/'+task['id'],lambda x:x['status']=='failed');assert '哈希' in failed['error']


def test_processing_gpu_lock_wait_and_cancellation(client,monkeypatch):
    monkeypatch.setattr(ReferenceLibrary,'_run_worker',analysis);called=[]
    def tracked(self,*args):called.append(True);return process(self,*args)
    monkeypatch.setattr(AudioRestoration,'_run_worker',tracked)
    recording,_=upload(client);until(client,'recordings/'+recording['id'],lambda x:x['status']=='succeeded')
    platform=client.app.state.platform
    with platform.engine_lock:
        task=client.post('/api/v1/audio-processing',json={'recording_id':recording['id'],'operations':['separate']}).json()
        until(client,'audio-processing/'+task['id'],lambda x:x['status']=='running')
        assert not called
        client.post('/api/v1/audio-processing/'+task['id']+'/cancel')
    item=until(client,'audio-processing/'+task['id'],lambda x:x['status'] in {'cancelled','succeeded'})
    assert item['status']=='cancelled' and not called


def test_design_result_becomes_reference_recording_without_file_download(client,monkeypatch):
    monkeypatch.setattr(ReferenceLibrary,'_run_worker',analysis)
    job=client.post('/api/v1/jobs',json={'text':'这是第一句内容。接下来，继续第二句内容。'}).json();job=wait(client,job['id'])
    result=client.get('/api/v1/results/'+job['results'][0]).json()
    response=client.post('/api/v1/recordings/from-result',json={'result_id':result['id']});assert response.status_code==202,response.text
    recording=response.json();assert recording['generated_result_id']==result['id']
    assert client.get('/api/v1/recordings/'+recording['id']+'/original').content==client.get('/api/v1/results/'+result['id']+'/audio').content
    assert client.get('/api/v1/results/'+result['id']).json()['review']=='pending'
