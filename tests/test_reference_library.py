import io
import soundfile as sf
import numpy as np


def reference(client, name='recording.wav'):
    buffer=io.BytesIO()
    sf.write(buffer, .1*np.sin(np.arange(6000)*.1), 1000, format='WAV')
    response=client.post('/api/v1/references',files={'file':(name,buffer.getvalue())},
                         data={'source':'synthetic fixture','authorization':'test only','rights_confirmed':'true'})
    assert response.status_code==201,response.text
    return response.json()


def test_annotations_preserve_audio_rights_transcript_and_submitted_snapshots(client):
    ref=reference(client)
    voice=client.post('/api/v1/voices',json={'name':'speaker','engine':'test','reference_id':ref['id']}).json()
    job=client.post('/api/v1/jobs',json={'text':'original task','voice_id':voice['id']}).json()
    audio=client.get('/api/v1/references/'+ref['id']+'/audio').content
    payload={'name':'Quiet narration','scenario':'bedtime','notes':'Natural and unhurried','tags':[' soft ','soft','night']}
    response=client.put('/api/v1/references/'+ref['id'],json=payload)
    assert response.status_code==200,response.text
    edited=response.json()
    assert edited['tags']==['soft','night'] and edited['metadata_history'][0]['name']==''
    assert all(edited[key]==ref[key] for key in ('path','original_path','sha256','source','authorization','rights_confirmed'))
    assert client.get('/api/v1/references/'+ref['id']+'/audio').content==audio
    assert client.get('/api/v1/jobs/'+job['id']).json()['reference_snapshot']==job['reference_snapshot']
    next_job=client.post('/api/v1/jobs',json={'text':'next task','voice_id':voice['id']}).json()
    assert next_job['reference_snapshot']['name']=='Quiet narration'
    # A partial rename must not erase the existing scenario, notes or tags.
    renamed=client.put('/api/v1/references/'+ref['id'],json={'name':'Whisper'}).json()
    assert renamed['scenario']=='bedtime' and renamed['tags']==['soft','night']
    assert len(renamed['metadata_history'])==2
    assert client.put('/api/v1/references/'+ref['id'],json={'path':'replace.wav'}).status_code==422
    assert client.put('/api/v1/references/'+ref['id'],json={'name':'a'*101}).status_code==422


def test_attach_many_clips_keeps_confirmed_default_and_creates_one_version(client):
    refs=[reference(client,'take-'+str(i)+'.wav') for i in range(3)]
    voice=client.post('/api/v1/voices',json={'name':'speaker','engine':'test','reference_id':refs[0]['id'],
        'reference_confirmed':True,'status':'active'}).json()
    client.put('/api/v1/references/'+refs[1]['id'],json={'name':'Excited','scenario':'action'})
    response=client.post('/api/v1/voices/'+voice['id']+'/references',json={'reference_ids':[r['id'] for r in refs[1:]]})
    assert response.status_code==200,response.text
    attached=response.json()
    assert attached['version']==2 and len(attached['reference_ids'])==3
    assert attached['reference_id']==refs[0]['id'] and attached['reference_confirmed'] and attached['status']=='active'
    assert attached['reference_scenarios'][refs[1]['id']]=='action'
    assert len(client.get('/api/v1/voices/'+voice['id']+'/versions').json())==2
    job=client.post('/api/v1/jobs',json={'text':'default','voice_id':voice['id']}).json()
    alternative=client.post('/api/v1/jobs',json={'text':'alternative','voice_id':voice['id'],'reference_id':refs[1]['id']}).json()
    assert job['reference_snapshot']['id']==refs[0]['id']
    assert alternative['reference_snapshot']['id']==refs[1]['id']


def test_invalid_attachment_is_atomic_and_first_attachment_stays_draft(client):
    refs=[reference(client) for _ in range(2)]
    voice=client.post('/api/v1/voices',json={'name':'designed','engine':'test'}).json()
    store=client.app.state.platform.store
    store.update('references',refs[1]['id'],saved=False)
    endpoint='/api/v1/voices/'+voice['id']+'/references'
    assert client.post(endpoint,json={'reference_ids':[r['id'] for r in refs]}).status_code==400
    assert client.get('/api/v1/voices/'+voice['id']).json()==voice
    result=client.post(endpoint,json={'reference_ids':[refs[0]['id']]}).json()
    assert result['reference_id']==refs[0]['id'] and result['status']=='draft' and not result['reference_confirmed']
    store.update('references',refs[0]['id'],deleted_at='test deletion')
    assert client.put('/api/v1/references/'+refs[0]['id'],json={'name':'rename deleted'}).status_code==400


def test_naming_candidates_does_not_implicitly_publish_them(client):
    ref=reference(client)
    store=client.app.state.platform.store
    store.update('references',ref['id'],saved=False)
    assert client.put('/api/v1/references/'+ref['id'],json={'name':'Candidate','scenario':'soft'}).status_code==200
    assert not any(item['id']==ref['id'] for item in client.get('/api/v1/references').json())
