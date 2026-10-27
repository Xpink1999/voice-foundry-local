import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from voice_platform.audio import sha256
from voice_platform.processing_engines import ProcessingEngines
from voice_platform.restoration import AudioRestoration
from voice_platform.schemas import ProcessingInput
from voice_platform.speaker_tracking import activity_regions, compact_pcm, match_sources
from voice_platform.speaker_tracking import assemble_clips,SpeakerTracker
from .test_restoration import analysis, upload, until
from voice_platform.references import ReferenceLibrary


def test_regions_keep_overlap_and_same_speaker_duplicates():
    turns=[dict(start=0,end=4,speaker='A'),dict(start=1,end=2,speaker='A'),dict(start=3,end=5,speaker='B'),dict(start=12,end=14,speaker='A')]
    assert activity_regions(turns,15)==[
        dict(start=0.,end=3.,speakers=['A']),dict(start=3.,end=4.,speakers=['A','B']),
        dict(start=4.,end=5.,speakers=['B']),dict(start=12.,end=14.,speakers=['A'])]


def test_voice_anchors_match_swapped_sources_without_adjacent_waveform():
    anchors={'A':[1,0,0],'B':[0,1,0]}
    result=match_sources([[0,1,0],[1,0,0]],anchors,['A','B'],.65,.08)
    assert [r['speaker'] for r in result]==['B','A']
    result=match_sources([[.7,.7,0],[.7,.7,0]],anchors,['A','B'],.65,.08)
    assert all(r['speaker'] is None for r in result)
    partial=match_sources([[1,0,0],[0,1,0]],{'A':[1,0,0]},['A','B'],.65,.08)
    assert [m['speaker'] for m in partial]==['A',None]


def test_compact_removes_gaps_preserves_source_and_maps_offsets():
    source=np.linspace(-.5,.5,1500,dtype=np.float32);before=source.copy()
    audio,mapping=compact_pcm(source,100,[(1,3),(10,13)],180)
    assert len(audio)==518 and np.array_equal(source,before)
    assert mapping[1]==dict(source_start=10.,source_end=13.,output_start=2.18,output_end=5.18)
    assert np.count_nonzero(audio[200:218])==0
    assert compact_pcm(source,100,[],180)[0].size==0


def test_tracking_is_not_combined_with_whole_file_separation():
    with pytest.raises(ValueError):ProcessingInput(recording_id='x',operations=['separate','track_speakers'])
    with pytest.raises(ValueError):ProcessingInput(recording_id='x',operations=['track_speakers'],speaker_count=0)


def test_manual_assembly_keeps_order_and_refuses_corruption(tmp_path):
    files=[]
    for i,value in enumerate([.1,.3]):
        path=tmp_path/f'{i}.wav';sf.write(path,np.full(1600,value),16000,subtype='PCM_24')
        files.append(dict(id=str(i),file=str(path),sha256=sha256(path),sample_rate=16000,source_spans=[dict(source_start=i*4,source_end=i*4+.1)]))
    request=dict(assembly_inputs=files[::-1],gap_ms=0,assembly_name='test',assembly_models={})
    result=assemble_clips(request,tmp_path,lambda *_:None)
    audio,sr=sf.read(result['outputs'][0]['file'])
    assert len(audio)==3200 and np.allclose(audio[:1600],.3,atol=1e-6)
    assert result['outputs'][0]['source_spans'][0]['source_output_id']=='1'
    assert not result['outputs'][0]['reference_eligible']
    request['assembly_inputs'][0]['sha256']='bad'
    with pytest.raises(ValueError):assemble_clips(request,tmp_path,lambda *_:None)


def test_short_turns_and_brief_overlaps_are_not_discarded(cfg,tmp_path,monkeypatch):
    pytest.importorskip('torch')
    path=tmp_path/'input.wav';sf.write(path,np.sin(np.arange(12*16000)*.05)*.1,16000)
    tracker=SpeakerTracker(cfg)
    turns=[dict(start=0,end=6,speaker='A'),dict(start=5.6,end=10,speaker='B'),dict(start=11,end=11.4,speaker='A')]
    monkeypatch.setattr(tracker,'diarize',lambda *args:(turns,{}))
    monkeypatch.setattr(tracker,'speech_spans',lambda _: [(0,10),(11,11.4)])
    monkeypatch.setattr(tracker.analyzer,'embedding',lambda _: [1.,0.,0.])
    monkeypatch.setattr(tracker.analyzer,'transcribe',lambda _: dict(text='test',low_confidence=False,confirmed=False))
    monkeypatch.setattr(tracker.analyzer,'models',lambda :{'speaker_dir':{}})
    monkeypatch.setattr(ProcessingEngines,'separate',lambda self,y,sr,progress,retain=False:[('A',y[0]*.6,sr),('B',y[0]*.4,sr)])
    result=tracker.run(dict(input_path=str(path)),tmp_path,lambda *_:None)
    clips=[o for o in result['outputs'] if o['kind']=='clip']
    assert any(o['origin']=='overlap' and o['duration']<1 for o in clips)
    assert any(o['source_spans'][0]['source_start']>=11 for o in clips)
    assert not any(o['kind']=='compact' for o in result['outputs'])
    assert result['tracking']['unresolved'] # Similar voices stay reviewable rather than falsely assigned.


def tracked(self,request,folder,kind,identity):
    assert request['mode']=='track'
    audio=np.sin(np.arange(16000*6)*.05).astype(np.float32)*.1
    outputs=[]
    for key,output_kind in [('solo','clip'),('merged','compact')]:
        file=folder/(key+'.wav');sf.write(file,audio,16000)
        outputs.append(dict(key=key,file=str(file),label=key,role='speech',stage='track_speakers',final=True,
            duration=6.,sample_rate=16000,channels=1,sha256=sha256(file),kind=output_kind,speaker_id='S1',
            origin='solo',recommended=True,reference_eligible=output_kind=='clip',
            source_spans=[dict(source_start=2.,source_end=8.)],embedding=[1.,0.,0.],similarity=.9,
            transcript=dict(text='测试人物独白',confirmed=False),warnings=[]))
    return dict(outputs=outputs,model_sources={'test':True},device='test',note='test',tracking=dict(
        speakers=[dict(id='S1',name='',anchor_count=1,solo_seconds=6.)],segments=[],unresolved=[],speaker_similarities=[]))


def test_queue_name_save_idempotency_and_non_destructive_reference(client,monkeypatch,ffmpeg_available):
    platform=client.app.state.platform
    model=Path(platform.config['data_dir'])/'model';model.mkdir();(model/'provenance.json').write_text('{}')
    platform.config['speaker_tracking'].update(model_dir=str(model),python=sys.executable)
    monkeypatch.setattr(ReferenceLibrary,'_run_worker',analysis)
    monkeypatch.setattr(AudioRestoration,'_run_worker',tracked)
    original,raw=upload(client)
    until(client,'recordings/'+original['id'],lambda x:x['status']=='succeeded')
    original_candidates=platform.store.get('recordings',original['id'])['candidate_ids'][:]
    response=client.post('/api/v1/audio-processing',json=dict(recording_id=original['id'],operations=['track_speakers'],analyze_outputs=False))
    assert response.status_code==202,response.text
    task=until(client,'audio-processing/'+response.json()['id'],lambda x:x['status'] in {'succeeded','failed'})
    assert task['status']=='succeeded',task
    assert client.put('/api/v1/audio-processing/'+task['id']+'/speakers/S1',json={'name':'旁白甲'}).status_code==200
    assert client.put('/api/v1/audio-processing/'+task['id']+'/speakers/other',json={'name':'错误'}).status_code==404
    solo,compact=task['outputs']
    base='/api/v1/audio-processing/'+task['id']
    assert client.post(base+'/save-clips',json={'output_ids':[compact['id']]}).status_code==400
    assert client.post(base+'/analyze-output',json={'output_id':compact['id']}).status_code==400
    response=client.post(base+'/save-clips',json={'output_ids':[solo['id']],'scenario':'旁白'})
    assert response.status_code==201,response.text
    reference=response.json()[0]
    assert reference['speaker_name']=='旁白甲' and reference['scenario']=='旁白'
    assert reference['saved'] and reference['review']=='pending' and not reference['transcript']['confirmed']
    again=client.post(base+'/save-clips',json={'output_ids':[solo['id']]}).json()[0]
    assert again['id']==reference['id']
    source=platform.store.get('recordings',original['id'])
    assert set(original_candidates)<=set(source['candidate_ids'])
    assert (platform.data/source['original_path']).read_bytes()==raw
    assert client.get('/api/v1/references/'+reference['id']+'/audio').status_code==200
