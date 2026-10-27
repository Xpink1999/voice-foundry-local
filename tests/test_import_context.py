"""Import and resume retain explicit production choices and fail before mutating state."""
from tests.test_longform import BASE, wait, upload
from tests.test_platform import reference


def test_book_import_freezes_selected_reference_engine_language_and_seed(client):
    clip = reference(client)
    response = client.post(BASE+'/books', files={'file':('book.txt',b'Chapter 1\nA short story.','text/plain')},
                           data=dict(title='Context check',engine='test',reference_id=clip['id'],language='en',seed='2468',style='quiet'))
    assert response.status_code == 202, response.text
    identity = response.json()['id']
    wait(client, BASE+'/books/'+identity, lambda book:book['phase'] in {'ready','failed'})
    snapshot = client.get(BASE+'/books/'+identity+'/configuration').json()['snapshot']
    assert snapshot['reference_snapshot']['id'] == clip['id']
    assert snapshot['engine'] == 'test' and snapshot['seed'] == 2468
    assert snapshot['request']['language'] == 'en' and snapshot['style'] == 'quiet'
    from tests.test_longform import complete
    assert complete(client,identity)['state']=='completed'
    assert client.app.state.platform.engines['test'].calls[-1]['language']=='en'


def test_missing_weights_block_resume_without_changing_book_or_existing_segments(client,monkeypatch):
    identity,_ = upload(client,'Chapter 1\nA small test story.')
    platform = client.app.state.platform
    before = platform.longform.db.book(identity)
    segments = client.get(BASE+'/books/'+identity+'/chapters/1/segments').json()
    engine = platform.engines['test']
    monkeypatch.setattr(engine,'readiness',lambda:dict(available=False,reason='missing test weights'),raising=False)
    book = client.get(BASE+'/books/'+identity).json()
    assert book['engine'] == 'test' and book['readiness']['available'] is False
    response = client.post(BASE+'/books/'+identity+'/resume',json={})
    assert response.status_code == 400 and 'missing test weights' in response.text
    assert platform.longform.db.book(identity) == before
    assert client.get(BASE+'/books/'+identity+'/chapters/1/segments').json() == segments
    monkeypatch.setattr(engine,'readiness',lambda:dict(available=True),raising=False)
    assert client.get(BASE+'/books/'+identity).json()['readiness']['available'] is True


def test_deletion_after_scheduler_lookup_does_not_stop_other_books(client,monkeypatch):
    import threading
    from tests.test_longform import complete
    identity,_=upload(client,'Chapter 1\nFirst book.')
    platform=client.app.state.platform
    runner=platform.longform
    selected=threading.Event()
    original=runner.generate_next
    def delete_during_dispatch(book):
        with platform.store.lock,platform.store.connect() as db:
            db.execute("UPDATE lf_books SET deleted_batch='test-delete',state='paused' WHERE id=?",(book,))
        selected.set()
        raise ValueError('book moved to trash during dispatch')
    monkeypatch.setattr(runner,'generate_next',delete_during_dispatch)
    assert client.post(BASE+'/books/'+identity+'/resume',json={}).status_code==200
    assert selected.wait(3)
    monkeypatch.setattr(runner,'generate_next',original)
    second,_=upload(client,'Chapter 1\nSecond book still runs.')
    assert complete(client,second)['state']=='completed'
    assert all(thread.is_alive() for thread in runner.threads)
