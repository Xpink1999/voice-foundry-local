import io
import json
import zipfile
import numpy as np
import soundfile as sf
from tests.test_longform import BASE,wait
from tests.fake_engine import FakeEngine


def setup(client):
    refs=[]
    for index in range(2):
        audio=io.BytesIO();sf.write(audio,.1*np.sin(np.arange(16000)*(.1+index*.01)),16000,format='WAV')
        ref=client.post('/api/v1/references',files={'file':('ref.wav',audio.getvalue())},data={'source':'test synthetic','authorization':'fixture only','rights_confirmed':'true'}).json()
        client.put('/api/v1/references/'+ref['id'],json={'name':['calm','soft'][index]})
        refs.append(ref['id'])
    voice=client.post('/api/v1/voices',json={'name':'fixture','engine':'test','style':'warm','reference_id':refs[0],'reference_ids':refs}).json()
    book=client.post(BASE+'/books',files={'file':('book.txt','第一章 开始\n灯光渐暗，故事开始。\n第二章 后续\n明天我们继续。'.encode())},data={'voice_id':voice['id']}).json()['id']
    wait(client,f'{BASE}/books/{book}',lambda b:b['phase']=='ready')
    client.post(f'{BASE}/books/{book}/resume',json={'chapter_no':1})
    wait(client,f'{BASE}/books/{book}',lambda b:b['state']=='paused')
    return book,voice,refs


def test_reference_redo_is_one_segment_frozen_and_exported_with_provenance(client):
    book,voice,refs=setup(client);url=f'{BASE}/books/{book}'
    original=client.get(url+'/chapters/1/segments').json()['items'][0]
    audio=client.get(url+'/segments/1/audio').content
    client.post(url+'/chapters/1/review',json={'status':'approved','listened':True})
    result=client.post(url+'/segments/1/regenerate',json={'reference_id':refs[1],'style':'soft and slow','seed':123,'start':True})
    assert result.status_code==200,result.text
    wait(client,url,lambda b:b['state'] in {'paused','completed'})
    current=client.get(url+'/chapters/1/segments').json()['items'][0]
    assert current['take']['reference_id']==refs[1] and current['take']['seed']==123
    assert current['take']['style']=='soft and slow' and current['attempt']==2
    assert client.get(url+'/chapters/2/segments').json()['items'][0]['attempt']==0
    assert client.get(url+'/chapters/1').json()['review']=='pending'
    assert client.get(url+'/segments/1/attempts/1/audio').content==audio
    assert client.post(url+'/exports',json={'chapter_no':1}).status_code==400
    export=client.post(url+'/exports',json={'chapter_no':1,'draft':True}).json()
    completed=wait(client,BASE+'/exports/'+export['id'],lambda e:e['state'] in {'succeeded','failed'})
    assert completed['state']=='succeeded',completed
    with zipfile.ZipFile(io.BytesIO(client.get(BASE+'/exports/'+export['id']+'/download').content)) as archive:
        profiles=[json.loads(line) for line in archive.read('generation-profiles.jsonl').decode().splitlines()]
        assert len(profiles)==1 and profiles[0]['snapshot']['reference_snapshot']['id']==refs[1]
    old=client.post(url+'/segments/1/use-attempt',json={'attempt':1})
    assert old.status_code==200 and old.json()['take']['id']==original['take']['id']
    assert client.get(url+'/segments/1/generation').json()['reference']['id']==refs[0]
    assert client.get(url+'/chapters/1').json()['review']=='pending'


def test_invalid_redo_is_atomic_and_failed_redo_can_restore_original(client,monkeypatch):
    book,_,refs=setup(client);url=f'{BASE}/books/{book}'
    before=client.get(url+'/chapters/1').json();audio=client.get(url+'/segments/1/audio').content
    # An untranscribed Hi-Fi selection must fail before invalidating the chapter.
    monkeypatch.setattr(FakeEngine,'capabilities',lambda self:dict(tts=True,voice_design=True,cloning=True,hifi_cloning=True,streaming=False,languages=['zh','en'],parameters={'test_strength':{'type':'number','default':1.5,'min':0,'max':3}}))
    bad=client.post(url+'/segments/1/regenerate',json={'reference_id':refs[1],'clone_mode':'hifi','start':True})
    assert bad.status_code==400 and client.get(url+'/chapters/1').json()==before
    FakeEngine.failures=1
    try:
        assert client.post(url+'/segments/1/regenerate',json={'reference_id':refs[1],'start':True}).status_code==200
        wait(client,url,lambda b:b['state']=='attention')
    finally:FakeEngine.failures=0
    assert client.get(url+'/segments/1/attempts/1/audio').content==audio
    restored=client.post(url+'/segments/1/use-attempt',json={'attempt':1})
    assert restored.status_code==200 and restored.json()['attempt']==2
    assert client.get(url).json()['failed']==0
    assert client.post(url+'/segments/1/use-attempt',json={'attempt':2}).status_code==400


def test_revision_keeps_frozen_voice_and_selected_transcript(client,monkeypatch):
    book,voice,refs=setup(client);url=f'{BASE}/books/{book}'
    client.put('/api/v1/references/'+refs[1]+'/transcript',json={'text':'first transcript','confirmed':False})
    assert client.post(url+'/segments/1/regenerate',json={'reference_id':refs[1],'seed':22,'start':True}).status_code==200
    wait(client,url,lambda b:b['state']=='paused')
    client.put('/api/v1/references/'+refs[1]+'/transcript',json={'text':'later transcript','confirmed':False})
    # A plain redo retains this segment's frozen profile; selecting the clip explicitly refreshes it.
    assert client.post(url+'/segments/1/regenerate',json={'start':True}).status_code==200
    wait(client,url,lambda b:b['state']=='paused')
    platform=client.app.state.platform
    segment=platform.longform.db.segment(book,1)
    frozen=platform.longform.generation_snapshot(platform.longform.db.book(book),segment)
    assert frozen['reference_snapshot']['transcript']['text']=='first transcript'
    assert client.post(url+'/segments/1/regenerate',json={'reference_id':refs[1],'start':True}).status_code==200
    wait(client,url,lambda b:b['state']=='paused')
    segment=platform.longform.db.segment(book,1)
    assert platform.longform.generation_snapshot(platform.longform.db.book(book),segment)['reference_snapshot']['transcript']['text']=='later transcript'


def test_regular_result_redo_creates_pending_candidate_and_preserves_original(client):
    _,voice,refs=setup(client)
    job=client.post('/api/v1/jobs',json={'voice_id':voice['id'],'text':'test line','seed':33}).json()
    finished=wait(client,'/api/v1/jobs/'+job['id'],lambda j:j['status']=='succeeded');rid=finished['results'][0]
    audio=client.get('/api/v1/results/'+rid+'/audio').content
    client.put('/api/v1/results/'+rid+'/review',json={'status':'approved','listened':True})
    response=client.post('/api/v1/results/'+rid+'/regenerate',json={'reference_id':refs[1],'style':'quiet'})
    assert response.status_code==202,response.text
    assert response.json()['style']=='quiet' and response.json()['reference_snapshot']['id']==refs[1]
    new=wait(client,'/api/v1/jobs/'+response.json()['id'],lambda j:j['status']=='succeeded')
    result=client.get('/api/v1/results/'+new['results'][0]).json()
    assert result['review']=='pending' and result['regenerated_from']==rid and result['parameters']['effective_seed']==33
    assert client.get('/api/v1/results/'+rid).json()['review']=='approved'
    assert client.get('/api/v1/results/'+rid+'/audio').content==audio


def test_generation_profile_hash_is_checked_before_replacing_a_take(client):
    book,_,refs=setup(client);url=f'{BASE}/books/{book}'
    assert client.post(url+'/segments/1/regenerate',json={'reference_id':refs[1],'start':True}).status_code==200
    wait(client,url,lambda b:b['state']=='paused')
    platform=client.app.state.platform;segment=platform.longform.db.segment(book,1)
    with platform.store.connect() as db:
        db.execute('UPDATE lf_generation_profiles SET body=? WHERE book_id=? AND id=?',('{}',book,segment['profile_id']))
    response=client.post(url+'/segments/1/regenerate',json={'start':True})
    assert response.status_code==400 and '哈希' in response.json()['detail']
    assert platform.longform.db.segment(book,1)==segment
    assert client.get(url+'/segments/1/attempts/1/audio').status_code==200
