"""Cross-workflow regressions found in the backend lifecycle audit."""
import pytest
from voice_platform.service import Platform
from voice_platform.store import uid,now
from tests.test_longform import BASE,upload,complete,wait
from tests.test_assets import selection


def test_retry_ignores_deleted_failed_segments_and_keeps_counters(client):
    identity,_=upload(client,'第一章 开始\n第一段正文。\n第二章 后续\n第二段正文。')
    platform=client.app.state.platform
    with platform.store.connect() as db:
        db.execute("UPDATE lf_segments SET status='failed' WHERE book_id=? AND no=1",(identity,))
        db.execute('UPDATE lf_chapters SET failed=1 WHERE book_id=? AND no=1',(identity,))
        db.execute('UPDATE lf_books SET failed=1 WHERE id=?',(identity,))
    assert client.post('/api/v1/assets/delete',json=selection('longform_segments',identity+':1')).status_code==200
    response=client.post(f'{BASE}/books/{identity}/retry-failed',json={})
    assert response.status_code==200 and response.json()['retried']==0
    assert response.json()['book']['failed']==0
    assert client.get(f'{BASE}/books/{identity}/chapters/1').json()['failed']==0
    with platform.store.connect() as db:
        assert db.execute('SELECT status FROM lf_segments WHERE book_id=? AND no=1',(identity,)).fetchone()[0]=='failed'


def test_deleted_book_blocks_child_reads_and_mutations_until_restored(client):
    identity,_=upload(client,'第一章 开始\n需要保留的正文。');complete(client,identity)
    deleted=client.post('/api/v1/assets/delete',json=selection('longform_books',identity)).json()
    for suffix in ('/configuration','/source','/chapters','/chapters/1','/chapters/1/segments','/chapters/1/next-audio','/segments/1/audio','/segments/1/attempts','/segments/1/generation'):
        assert client.get(f'{BASE}/books/{identity}'+suffix).status_code==400,suffix
    assert client.post(f'{BASE}/books/{identity}/pause').status_code==400
    assert client.post(f'{BASE}/books/{identity}/chapters/1/review',json={'status':'approved','listened':True}).status_code==400
    assert client.post('/api/v1/assets/restore-batch/'+deleted['batch_id']).status_code==200
    assert client.get(f'{BASE}/books/{identity}/segments/1/audio').status_code==200


def test_deleted_longform_export_is_not_downloadable_until_restored(client):
    identity,_=upload(client,'第一章 开始\n保留的导出正文。');complete(client,identity)
    created=client.post(f'{BASE}/books/{identity}/exports',json={'draft':True}).json()
    url=f'{BASE}/exports/{created["id"]}'
    wait(client,url,lambda item:item['state']=='succeeded')
    original=client.get(url+'/download').content
    deleted=client.post('/api/v1/assets/delete',json=selection('longform_exports',created['id'])).json()
    assert client.get(url).status_code==404 and client.get(url+'/download').status_code==404
    assert client.post('/api/v1/assets/restore-batch/'+deleted['batch_id']).status_code==200
    assert client.get(url+'/download').content==original


def test_deleted_or_stopping_job_cannot_create_a_hidden_retry(client):
    platform=client.app.state.platform
    job=client.post('/api/v1/jobs',json={'text':'FAIL','max_retries':0}).json()
    wait(client,'/api/v1/jobs/'+job['id'],lambda item:item['status']=='failed')
    deleted=client.post('/api/v1/assets/delete',json=selection('jobs',job['id'])).json()
    before=len(platform.store.list('jobs',include_deleted=True))
    assert client.post('/api/v1/jobs/'+job['id']+'/retry').status_code==400
    assert len(platform.store.list('jobs',include_deleted=True))==before
    client.post('/api/v1/assets/restore-batch/'+deleted['batch_id'])
    platform.shutdown.set()
    try:assert client.post('/api/v1/jobs/'+job['id']+'/retry').status_code==400
    finally:platform.shutdown.clear()


def test_reference_redo_preserves_long_effective_direction_without_relaxing_input(client):
    voice=client.post('/api/v1/voices',json={'name':'long directions','style':'a'*800}).json()
    job=client.post('/api/v1/jobs',json={'voice_id':voice['id'],'text':'test line','style':'b'*800}).json()
    done=wait(client,'/api/v1/jobs/'+job['id'],lambda item:item['status']=='succeeded')
    result=client.post('/api/v1/results/'+done['results'][0]+'/regenerate',json={})
    assert result.status_code==202,result.text
    assert result.json()['style']=='a'*800+', '+'b'*800
    newer=wait(client,'/api/v1/jobs/'+result.json()['id'],lambda item:item['status']=='succeeded')
    repeated=client.post('/api/v1/results/'+newer['results'][0]+'/regenerate',json={})
    assert repeated.status_code==202 and repeated.json()['style']==result.json()['style']
    assert client.post('/api/v1/jobs',json={'text':'test','style':'a'*1001}).status_code==422


def test_reference_restart_resolves_cancel_requested_without_loading_models(cfg):
    platform=Platform(cfg);library=platform.references
    for kind in ('recordings','reference_comparisons'):
        platform.store.save(kind,dict(id=kind,status='cancel_requested',smart_reference={'status':'analyzing'}))
    library.start()
    try:
        for kind in ('recordings','reference_comparisons'):
            item=platform.store.get(kind,kind)
            assert item['status']=='cancelled' and item['smart_reference']['status']=='cancelled'
    finally:library.stop()
    assert not library.thread.is_alive() and platform.engine_process_ids()==[]


def test_recording_cancel_cannot_be_overwritten_by_claim_or_completion(cfg,monkeypatch):
    platform=Platform(cfg);library=platform.references
    item=dict(id=uid(),status='queued',candidate_ids=[],attempt=0,original_name='fixture.wav',original_path='fixture.wav',original_sha256='test',source='test',authorization='test',rights_confirmed=True)
    platform.store.save('recordings',item)
    library.cancel(item['id'])
    monkeypatch.setattr(library,'_decode',lambda *_:pytest.fail('Cancelled item must not decode'))
    with pytest.raises(InterruptedError):library._analyze(item)
    assert platform.store.get('recordings',item['id'])['status']=='cancelled'
    platform.store.update('recordings',item['id'],status='queued')
    monkeypatch.setattr(library,'_decode',lambda *_:item)
    def finish_after_cancel(*args):
        library.cancel(item['id'])
        return dict(clips=[],summary={'models':{}})
    monkeypatch.setattr(library,'_run_worker',finish_after_cancel)
    with pytest.raises(InterruptedError):library._analyze(item)
    assert platform.store.get('recordings',item['id'])['status']=='cancel_requested'
    assert platform.store.list('references')==[]


def test_deleted_recordings_and_references_reject_new_work(client):
    platform=client.app.state.platform
    recording=dict(id=uid(),status='failed',candidate_ids=[],deleted_at=now())
    reference=dict(id=uid(),rights_confirmed=True,deleted_at=now())
    platform.store.save('recordings',recording);platform.store.save('references',reference)
    assert client.post('/api/v1/recordings/'+recording['id']+'/retry').status_code==400
    assert client.post('/api/v1/recordings/'+recording['id']+'/save',json={'reference_ids':[reference['id']]}).status_code==400
    assert client.put('/api/v1/references/'+reference['id']+'/transcript',json={'text':'test'}).status_code==400
    assert client.post('/api/v1/audio-processing',json={'recording_id':recording['id'],'operations':['denoise']}).status_code==400
    assert client.post('/api/v1/reference-voices',json={'name':'test','reference_id':reference['id']}).status_code==400


def test_failed_startup_releases_worker_logger_and_database_lease(cfg,monkeypatch):
    import logging
    from fastapi.testclient import TestClient
    from voice_platform.api import create_app
    app=create_app(cfg);platform=app.state.platform;start=platform.start
    handlers=list(logging.getLogger('voice_platform').handlers)
    def partial_start():
        start()
        raise RuntimeError('injected startup failure')
    monkeypatch.setattr(platform,'start',partial_start)
    with pytest.raises(RuntimeError,match='injected startup failure'):
        with TestClient(app):pass
    assert not platform.worker.is_alive()
    assert not any(t.is_alive() for t in platform.longform.threads)
    assert logging.getLogger('voice_platform').handlers==handlers
    assert platform.engine_process_ids()==[]
    # Reacquiring the same database lease proves failed startup did not keep its lock.
    with TestClient(create_app(cfg)) as client:
        assert client.get('/api/v1/health').json()['worker_alive']


def test_export_cancel_reads_status_after_obtaining_the_shared_lock(cfg,monkeypatch):
    import json,threading
    platform=Platform(cfg);exporter=platform.longform.exporter;book=uid();identity=uid()
    with platform.store.connect() as db:
        db.execute('INSERT INTO lf_books(id,body,phase,state,created_at) VALUES (?,?,?,?,?)',(book,json.dumps({'id':book}),'ready','completed',now()))
    item=dict(id=identity,book_id=book,state='queued',created_at=now())
    exporter.db.save_export(item)
    entered=threading.Event();read=threading.Event();errors=[];original=exporter.db.export
    def observed_read(key):
        value=original(key);read.set();return value
    monkeypatch.setattr(exporter.db,'export',observed_read)
    def cancel():
        entered.set()
        try:exporter.cancel(identity)
        except Exception as error:errors.append(error)
    with platform.store.lock:
        thread=threading.Thread(target=cancel);thread.start();assert entered.wait(1)
        read.wait(.2)
        exporter.db.save_export(dict(item,state='running'))
    thread.join(2)
    assert not thread.is_alive() and not errors
    assert original(identity)['state']=='cancel_requested'
