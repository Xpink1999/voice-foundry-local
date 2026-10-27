from voice_platform.store import now


def test_batch_job_scope_is_filtered_before_pagination_and_composes_with_archive(client):
    platform = client.app.state.platform
    platform.config['task_archive_after_days'] = 0
    stamp = now()
    jobs = [
        dict(id='a-1', batch_id='batch-a', project_id='p', status='succeeded'),
        dict(id='a-2', batch_id='batch-a', project_id='p', status='failed'),
        dict(id='a-3', batch_id='batch-a', project_id='q', status='succeeded'),
        dict(id='a-archived', batch_id='batch-a', project_id='p', status='succeeded', archived_at=stamp),
        dict(id='a-deleted', batch_id='batch-a', project_id='p', status='succeeded', deleted_at=stamp),
        dict(id='b-1', batch_id='batch-b', project_id='p', status='succeeded'),
        dict(id='single', project_id='p', status='succeeded'),
    ]
    for job in jobs:
        platform.store.save('jobs', dict(created_at=stamp, **job))

    first = client.get('/api/v1/jobs/page', params={'batch_id': 'batch-a', 'limit': 2}).json()
    second = client.get('/api/v1/jobs/page', params={'batch_id': 'batch-a', 'limit': 2, 'offset': 2}).json()
    assert first['batch_id'] == 'batch-a' and first['total'] == second['total'] == 3
    assert len(first['items']) == 2 and len(second['items']) == 1
    assert {job['id'] for job in first['items'] + second['items']} == {'a-1', 'a-2', 'a-3'}
    filtered = client.get('/api/v1/jobs/page', params={'batch_id': 'batch-a', 'project_id': 'p', 'status': 'failed'}).json()
    assert filtered['total'] == 1 and filtered['items'][0]['id'] == 'a-2'
    current = client.get('/api/v1/jobs', params={'batch_id': 'batch-a'}).json()
    archived = client.get('/api/v1/jobs', params={'batch_id': 'batch-a', 'archived': 'true'}).json()
    assert {job['id'] for job in current} == {'a-1', 'a-2', 'a-3'}
    assert [job['id'] for job in archived] == ['a-archived']
    archived_page = client.get('/api/v1/jobs/page', params={'batch_id': 'batch-a', 'archived': 'true'}).json()
    assert archived_page['total'] == 1 and archived_page['items'] == archived
    assert {job['id'] for job in client.get('/api/v1/jobs').json()} == {'a-1', 'a-2', 'a-3', 'b-1', 'single'}


def test_batch_scope_is_parameterized_and_uses_its_index(client):
    store = client.app.state.platform.store
    identity = "batch' OR 1=1 --"
    for batch, job in [(identity, 'literal'), ('other', 'other')]:
        store.save('jobs', dict(id=job, batch_id=batch, created_at=now(), status='queued'))
    response = client.get('/api/v1/jobs/page', params={'batch_id': identity})
    assert response.status_code == 200
    assert [job['id'] for job in response.json()['items']] == ['literal']
    with store.connect() as db:
        plan = db.execute("EXPLAIN QUERY PLAN SELECT body FROM entities WHERE kind='jobs' AND json_extract(body,'$.batch_id')=?", (identity,)).fetchall()
    assert any('job_batch' in row[-1] for row in plan)
