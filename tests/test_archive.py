from datetime import datetime,timezone,timedelta
from pathlib import Path
from voice_platform.service import Platform
from .test_platform import submit,wait


def test_manual_archive_restore_keeps_audio_and_review(client,cfg):
    job=wait(client,submit(client)['id']);identity=job['id'];result_id=job['results'][0]
    before=client.get('/api/v1/results/'+result_id).json();path=Path(cfg['data_dir'])/before['path'];original=path.read_bytes()
    response=client.post('/api/v1/jobs/archive',json={'job_ids':[identity]});assert response.status_code==200
    assert response.json()['changed_ids']==[identity]
    assert client.get('/api/v1/jobs').json()==[]
    assert client.get('/api/v1/jobs?archived=true').json()[0]['id']==identity
    assert client.get('/api/v1/jobs/'+identity).json()['archived_at']
    assert client.get('/api/v1/results/'+result_id).json()==before and path.read_bytes()==original
    assert client.get('/api/v1/results/'+result_id+'/audio').content==original
    assert not client.post('/api/v1/jobs/archive',json={'job_ids':[identity]}).json()['changed_ids']
    restored=client.post('/api/v1/jobs/restore',json={'job_ids':[identity]}).json();assert restored['changed_ids']==[identity]
    assert client.get('/api/v1/jobs').json()[0]['id']==identity
    assert client.get('/api/v1/jobs?archived=true').json()==[]
    assert client.get('/api/v1/results/'+result_id).json()==before


def test_archive_rejects_active_or_invalid_batch_without_partial_changes(client):
    store=client.app.state.platform.store
    for identity,status in [('finished','succeeded'),('active','running')]:
        store.save('jobs',dict(id=identity,status=status,project_id=None,created_at='2026-10-22T00:00:00+00:00'))
    response=client.post('/api/v1/jobs/archive',json={'job_ids':['finished','active']});assert response.status_code==400
    assert not store.get('jobs','finished').get('archived_at')
    assert client.post('/api/v1/jobs/archive',json={'job_ids':['finished','missing']}).status_code==404
    assert not store.get('jobs','finished').get('archived_at')
    assert client.post('/api/v1/jobs/archive',json={'job_ids':[]}).status_code==422


def test_age_archive_boundaries_disable_and_restore_retention(cfg):
    platform=Platform(cfg);clock=datetime.now(timezone.utc);old=(clock-timedelta(days=8)).isoformat()
    def save(identity,status,finished=old):
        platform.store.save('jobs',dict(id=identity,status=status,created_at=old,finished_at=finished,project_id=None))
    for status in ('succeeded','failed','cancelled','running','queued','cancel_requested'):save(status,status)
    save('recent','succeeded',(clock-timedelta(days=6)).isoformat())
    assert set(platform.archive_due(force=True,clock=clock))=={'succeeded','failed','cancelled'}
    platform.archive_jobs(['succeeded'],restore=True)
    assert platform.archive_due(force=True,clock=clock+timedelta(hours=1))==[]
    assert set(platform.archive_due(force=True,clock=clock+timedelta(days=8)))=={'succeeded','recent'}
    # A disabled policy must preserve an eligible, unarchived task.
    save('disabled','succeeded');platform.config['task_archive_after_days']=0
    assert platform.archive_due(force=True,clock=clock+timedelta(days=30))==[]
    assert not platform.store.get('jobs','disabled').get('archived_at')


def test_archive_pagination_filters_and_stable_results(client):
    store=client.app.state.platform.store
    for i in range(65):store.save('jobs',dict(id=f'job-{i}',status='succeeded' if i%2 else 'failed',project_id='p' if i%3 else 'q',created_at=datetime.now(timezone.utc).isoformat()))
    first=client.get('/api/v1/jobs/page?limit=25').json();second=client.get('/api/v1/jobs/page?limit=25&offset=25').json()
    assert first['total']==65 and len(first['items'])==25 and not ({j['id'] for j in first['items']}&{j['id'] for j in second['items']})
    ids=[j['id'] for j in first['items'][:10]];client.post('/api/v1/jobs/archive',json={'job_ids':ids})
    assert client.get('/api/v1/jobs/page').json()['total']==55
    archive=client.get('/api/v1/jobs/page?archived=true&limit=4').json();assert archive['total']==10 and len(archive['items'])==4
    filtered=client.get('/api/v1/jobs/page?archived=true&project_id=p&status=failed').json()
    assert all(j['project_id']=='p' and j['status']=='failed' for j in filtered['items'])
    assert client.get('/api/v1/jobs/page?limit=201').status_code==422


def test_retry_archived_failure_creates_visible_fresh_job(client):
    original=client.post('/api/v1/jobs',json={'text':'FAIL','max_retries':0}).json();wait(client,original['id'])
    client.post('/api/v1/jobs/archive',json={'job_ids':[original['id']]})
    retried=client.post('/api/v1/jobs/'+original['id']+'/retry').json()
    assert not retried.get('archived_at') and not retried.get('archive_history') and retried['retry_of']==original['id']
    wait(client,retried['id'])
    assert client.get('/api/v1/jobs/'+original['id']).json()['archived_at']
    assert retried['id'] in {j['id'] for j in client.get('/api/v1/jobs').json()}


def test_archive_setting_persists_and_old_clients_keep_policy(client,cfg):
    values=dict(idle_unload_seconds=60,segment_chars=80,segment_pause_ms=90,max_pending_jobs=10,task_archive_after_days=0)
    assert client.put('/api/v1/settings',json=values).status_code==200
    values.pop('task_archive_after_days')
    client.put('/api/v1/settings',json=values)
    assert client.get('/api/v1/settings').json()['task_archive_after_days']==0
    import json
    assert json.loads(Path(cfg['config_path']).read_text(encoding='utf-8'))['task_archive_after_days']==0
    assert client.put('/api/v1/settings',json=dict(values,task_archive_after_days=-1)).status_code==422
