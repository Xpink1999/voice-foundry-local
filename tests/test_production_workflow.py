"""Production corrections retain source text, earlier takes and review boundaries."""
from tests.test_regeneration import setup
from tests.test_longform import BASE,wait
from tests.test_restoration import until


def test_production_text_revision_preserves_source_and_old_take(client):
    book,_,_=setup(client);url=f'{BASE}/books/{book}'
    original=client.get(url+'/segments/1/generation').json()
    platform=client.app.state.platform
    source=platform.data/platform.longform.db.book(book)['normalized_path'];raw=source.read_bytes()
    response=client.post(url+'/segments/1/regenerate',json=dict(text='修正后的专名与台词。',start=True))
    assert response.status_code==200,response.text
    wait(client,url,lambda b:b['state']=='paused')
    info=client.get(url+'/segments/1/generation').json()
    assert info['text']=='修正后的专名与台词。' and source.read_bytes()==raw
    reset=client.post(url+'/segments/1/regenerate',json=dict(use_book_defaults=True,start=True))
    assert reset.status_code==200,reset.text
    wait(client,url,lambda b:b['state']=='paused')
    assert client.get(url+'/segments/1/generation').json()['text']=='修正后的专名与台词。'
    assert client.get(url+'/chapters/1').json()['review']=='pending'
    assert client.get(url+'/segments/1/attempts/1/audio').status_code==200
    assert client.post(url+'/segments/1/use-attempt',json=dict(attempt=1)).status_code==200
    assert client.get(url+'/segments/1/generation').json()['text']==original['text']


def test_manual_issue_survives_success_and_blocks_review(client):
    book,_,_=setup(client);url=f'{BASE}/books/{book}'
    assert client.put(url+'/segments/1/issue',json=dict(note='专名发音待确认')).status_code==200
    assert client.get(url+'/issues').json()['items'][0]['note']=='专名发音待确认'
    assert client.post(url+'/chapters/1/review',json=dict(status='approved',listened=True)).status_code==400
    assert client.put(url+'/segments/1/issue',json=dict(resolved=True)).status_code==200
    assert client.get(url+'/issues').json()['total']==0
    assert client.get(url+'/chapters/1').json()['review']=='pending'
    assert client.post(url+'/chapters/1/review',json=dict(status='approved',listened=True)).status_code==200


def test_problem_location_covers_later_chapter_and_segment_pages(client):
    text=''.join(f'第{i}章 内容\n'+('这是一句用于分页定位的文本。'*500 if i==51 else '这是测试内容。')+'\n' for i in range(1,53))
    book=client.post(BASE+'/books',files={'file':('test.txt',text.encode())}).json()['id'];url=BASE+'/books/'+book
    wait(client,url,lambda b:b['phase']=='ready')
    segments=client.get(url+'/chapters/51/segments?limit=100').json()['items'];assert len(segments)>25
    target=segments[-1]['no']
    assert client.put(f'{url}/segments/{target}/issue',json=dict(note='第二页问题')).status_code==200
    location=client.get(f'{url}/segments/{target}/locate').json()
    assert location['chapter_no']==51 and location['offset']>=25
    listed=client.get(f'{url}/chapters/51/segments?offset={location["offset"]}&limit=25').json()['items']
    assert target in [row['no'] for row in listed]


def test_ordinary_revision_can_be_recovered_from_original_result(client):
    job=client.post('/api/v1/jobs',json=dict(text='原始台词。')).json()
    job=until(client,'jobs/'+job['id'],lambda j:j['status']=='succeeded');identity=job['results'][0]
    revised=client.post(f'/api/v1/results/{identity}/regenerate',json=dict(text='修正台词。')).json()
    done=until(client,'jobs/'+revised['id'],lambda j:j['status']=='succeeded')
    assert client.get('/api/v1/results/'+done['results'][0]).json()['original_text']=='修正台词。'
    assert client.get('/api/v1/results/'+identity).json()['original_text']=='原始台词。'
    history=client.get(f'/api/v1/results/{identity}/revisions').json()
    assert history[0]['id']==done['id'] and history[0]['results']==done['results']
