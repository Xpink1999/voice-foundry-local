"""Recoverable deletion, reference guards and review-to-export contracts."""
import hashlib
from pathlib import Path
import pytest
from tests.test_longform import upload,complete,wait,BASE
from voice_platform.store import uid,now

def selection(kind,*ids):return {'items':[{'kind':kind,'id':i} for i in ids]}
def result(client,text='用于验证可恢复删除的测试音频。'):
    job=client.post('/api/v1/jobs',json={'text':text,'max_retries':0}).json();done=wait(client,'/api/v1/jobs/'+job['id'],lambda x:x['status']=='succeeded');return done,client.get('/api/v1/results/'+done['results'][0]).json()

def test_task_cascade_delete_restore_keeps_audio_and_review(client):
    job,item=result(client);platform=client.app.state.platform;raw=(platform.data/item['path']).read_bytes()
    request=selection('jobs',job['id']);preview=client.post('/api/v1/assets/delete-preview',json=request).json();assert preview['counts']=={'jobs':1,'results':1}
    deleted=client.post('/api/v1/assets/delete',json=request);assert deleted.status_code==200,deleted.text;batch=deleted.json()['batch_id']
    assert client.get('/api/v1/jobs/page').json()['total']==0
    assert not client.get('/api/v1/results').json()
    assert (platform.data/item['path']).read_bytes()==raw
    trash=client.get('/api/v1/assets?kind=results&deleted=true').json();assert trash['total']==1
    assert client.post('/api/v1/assets/restore-batch/'+batch).json()['restored']==2
    assert client.get('/api/v1/results').json()[0]['review']=='pending'
    assert hashlib.sha256((platform.data/item['path']).read_bytes()).hexdigest()==item['sha256']

def test_reference_guard_and_atomic_batch(client):
    platform=client.app.state.platform;identity=uid();path=platform.data/'retained-reference.wav';path.write_bytes(b'owned fixture bytes')
    ref=dict(id=identity,name='测试参考',original_name='测试参考',path=path.name,rights_confirmed=True,saved=True,status='ready',duration=6,sample_rate=16000,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source='test fixture',authorization='test only',transcript={'text':'文本','confirmed':True})
    platform.store.save('references',ref)
    voice=client.post('/api/v1/voices',json={'name':'依赖参考的人物','reference_id':identity}).json();assert 'id' in voice
    project=client.post('/api/v1/projects',json={'name':'保留项目'}).json()
    request={'items':[{'kind':'references','id':identity},{'kind':'projects','id':project['id']}]}
    assert client.post('/api/v1/assets/delete-preview',json=request).json()['blocked']
    assert client.post('/api/v1/assets/delete',json=request).status_code==400
    assert client.get('/api/v1/projects').json()[0]['id']==project['id']
    request['items'].append({'kind':'voices','id':voice['id']});deleted=client.post('/api/v1/assets/delete',json=request);assert deleted.status_code==200,deleted.text
    assert path.exists() and not client.get('/api/v1/voices').json() and not client.get('/api/v1/references').json()
    assert client.post('/api/v1/jobs',json={'text':'不能使用已删除的人物','voice_id':voice['id']}).status_code==400
    client.post('/api/v1/assets/restore-batch/'+deleted.json()['batch_id']);assert client.get('/api/v1/voices').json()[0]['id']==voice['id']

def test_chapter_segment_restore_does_not_resurrect_previously_deleted_rows(client):
    identity,_=upload(client,'第一章 开始\n这是第一章的内容。\n第二章 结束\n这是第二章的内容。');complete(client,identity)
    for n in [1,2]:assert client.post(f'{BASE}/books/{identity}/chapters/{n}/review',json={'status':'approved','listened':True,'reviewer':'test fixture'}).status_code==200
    before=client.get(f'{BASE}/books/{identity}').json();segment=client.post('/api/v1/assets/delete',json=selection('longform_segments',identity+':1'));assert segment.status_code==200,segment.text
    assert client.get(f'{BASE}/books/{identity}/chapters/2').json()['review']=='approved'
    chapter=client.post('/api/v1/assets/delete',json=selection('longform_chapters',identity+':1'));assert chapter.status_code==200,chapter.text
    assert client.get(f'{BASE}/books/{identity}/chapters').json()['total']==1
    assert client.post('/api/v1/assets/restore',json=selection('longform_segments',identity+':1')).status_code==400
    assert client.post('/api/v1/assets/restore-batch/'+chapter.json()['batch_id']).status_code==200
    rows=client.get(f'{BASE}/books/{identity}/chapters/1/segments').json();assert all(s['no']!=1 for s in rows['items'])
    client.post('/api/v1/assets/restore-batch/'+segment.json()['batch_id']);after=client.get(f'{BASE}/books/{identity}').json();assert after['segments']==before['segments'] and after['done']==before['done']
    assert client.get(f'{BASE}/books/{identity}/chapters/2').json()['review']=='approved'
    assert client.get(f'{BASE}/books/{identity}/chapters/1').json()['review']=='pending'

def test_book_delete_refuses_busy_then_restores_entire_checkpoint(client):
    identity,_=upload(client,'第一章 开始\n'+('这是一段需要持续生成的测试文字。'*100));client.post(f'{BASE}/books/{identity}/resume',json={})
    assert client.post('/api/v1/assets/delete',json=selection('longform_books',identity)).status_code==400
    client.post(f'{BASE}/books/{identity}/pause');platform=client.app.state.platform
    wait(client,f'{BASE}/books/{identity}/chapters/1/segments',lambda x:all(s['status']!='running' for s in x['items']))
    before=platform.longform.db.book(identity);deleted=client.post('/api/v1/assets/delete',json=selection('longform_books',identity));assert deleted.status_code==200,deleted.text
    assert client.get(f'{BASE}/books').json()['total']==0
    assert (platform.data/before['original_path']).exists()
    assert client.post(f'{BASE}/books/{identity}/resume',json={}).status_code==400
    assert client.post('/api/v1/assets/restore-batch/'+deleted.json()['batch_id']).status_code==200
    assert client.get(f'{BASE}/books').json()['total']==1

@pytest.mark.parametrize('kind',['exports','audio_processing','reference_comparisons'])
def test_terminal_records_delete_restore(client,kind):
    platform=client.app.state.platform;identity=uid();platform.store.save(kind,dict(id=identity,title='测试记录',status='succeeded',state='succeeded',created_at=now(),child_recording_ids=[]))
    out=client.post('/api/v1/assets/delete',json=selection(kind,identity));assert out.status_code==200,out.text
    assert platform.store.list(kind)==[]
    assert client.post('/api/v1/assets/restore-batch/'+out.json()['batch_id']).json()['restored']==1
    assert platform.store.list(kind)[0]['id']==identity

def test_batch_review_atomic_and_export_after_approval(client):
    job,one=result(client);job,two=result(client,'第二条测试。');ids=[one['id'],two['id']]
    assert client.post('/api/v1/results/review-batch',json={'result_ids':ids,'status':'approved'}).status_code==422
    assert client.post('/api/v1/results/review-batch',json={'result_ids':[one['id'],'missing'],'status':'approved','listened':True}).status_code==404
    assert client.get('/api/v1/results/'+one['id']).json()['review']=='pending'
    reviewed=client.post('/api/v1/results/review-batch',json={'result_ids':ids,'status':'approved','listened':True,'reviewer':'test fixture'});assert reviewed.json()['reviewed']==2
    export=client.post('/api/v1/exports',json={'result_ids':ids});assert export.status_code==201,export.text
    deleted=client.post('/api/v1/assets/delete',json=selection('exports',export.json()['id']));assert deleted.status_code==200
    assert client.get('/api/v1/exports').json()==[]
    client.post('/api/v1/assets/delete',json=selection('results',one['id']))
    assert client.post('/api/v1/exports',json={'result_ids':[one['id']]}).status_code==400


def test_empty_chapter_review_block_and_busy_restore(client):
    identity,_=upload(client,'第一章 空章测试\n原始内容应保留。\n第二章 继续\n'+('还有很多没有完成的文字。'*30))
    rows=client.get(f'{BASE}/books/{identity}/chapters/1/segments').json()['items']
    deletion=client.post('/api/v1/assets/delete',json=selection('longform_segments',*[identity+':'+str(r['no']) for r in rows]));assert deletion.status_code==200
    assert client.post(f'{BASE}/books/{identity}/chapters/1/review',json={'status':'approved','listened':True,'reviewer':'test fixture'}).status_code==400
    client.post(f'{BASE}/books/{identity}/resume',json={})
    assert client.post('/api/v1/assets/restore-batch/'+deletion.json()['batch_id']).status_code==400
    client.post(f'{BASE}/books/{identity}/pause')
    wait(client,f'{BASE}/books/{identity}/chapters/2/segments',lambda x:all(s['status']!='running' for s in x['items']))
    restored=client.post('/api/v1/assets/restore-batch/'+deletion.json()['batch_id']);assert restored.status_code==200,restored.text
