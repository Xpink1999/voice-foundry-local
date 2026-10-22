"""Live model verification with synthetic, source-known fixtures. Never approves results."""
import hashlib
import json
import time
from datetime import datetime,timezone
from pathlib import Path
import httpx
import librosa
import numpy as np
import soundfile as sf
from voice_platform.config import ROOT


def si_sdr(reference,estimate):
    length=min(len(reference),len(estimate));reference=reference[:length].astype(np.float64);estimate=estimate[:length].astype(np.float64)
    reference-=reference.mean();estimate-=estimate.mean()
    projection=np.dot(estimate,reference)*reference/max(np.dot(reference,reference),1e-12)
    return float(10*np.log10((np.dot(projection,projection)+1e-12)/(np.sum((estimate-projection)**2)+1e-12)))


def main():
    folder=ROOT/'docs/evidence/audio-restoration';fixtures=folder/'fixtures';client=httpx.Client(base_url='http://127.0.0.1:8961/api/v1',timeout=30)
    def get(route):
        r=client.get(route);r.raise_for_status();return r.json()
    cases=[]
    for name,operation in [('overlap','separate'),('music-mix','remove_music'),('noisy','denoise')]:
        path=fixtures/(name+'.wav')
        response=client.post('/recordings',files={'file':('验收 · '+name+'.wav',path.read_bytes())},data=dict(source='本平台合成声音与程序音乐/噪声；source-known 自动验收',authorization='自制测试素材，未批准为正式资产',rights_confirmed='true',smart_reference='false'));response.raise_for_status()
        cases.append(dict(name=name,operation=operation,recording_id=response.json()['id'],source_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    start=time.monotonic()
    while any('task_id' not in c for c in cases):
        for case in cases:
            if 'task_id' in case:continue
            recording=get('/recordings/'+case['recording_id'])
            if recording['status'] not in {'succeeded','failed','cancelled'}:continue
            response=client.post('/audio-processing',json=dict(recording_id=case['recording_id'],operations=[case['operation']],analyze_outputs=False));response.raise_for_status();case['task_id']=response.json()['id'];print('queued',case['name'],case['task_id'],flush=True)
        if time.monotonic()-start>600:raise TimeoutError('fixture analysis did not finish')
        time.sleep(.5)
    for case in cases:
        while True:
            task=get('/audio-processing/'+case['task_id'])
            if task['status'] in {'succeeded','failed','cancelled'}:break
            if time.monotonic()-start>1800:raise TimeoutError('restoration did not finish')
            time.sleep(.5)
        assert task['status']=='succeeded',task.get('error')
        assert hashlib.sha256(client.get('/recordings/'+case['recording_id']+'/original').content).hexdigest()==case['source_sha256']
        before,_=librosa.load(fixtures/(case['name']+'.wav'),sr=16000,mono=True)
        a,_=librosa.load(fixtures/'speaker-a.wav',sr=16000,mono=True);b,_=librosa.load(fixtures/'speaker-b.wav',sr=16000,mono=True)
        speech=[o for o in task['outputs'] if o['role']=='speech']
        audio=[]
        for output in task['outputs']:
            response=client.get(f"/audio-processing/{task['id']}/outputs/{output['id']}");response.raise_for_status()
            assert hashlib.sha256(response.content).hexdigest()==output['sha256']
            (folder/f"{case['name']}-{output['role']}-{output['id'][:6]}.wav").write_bytes(response.content)
        for output in speech:
            y,_=librosa.load(ROOT/'data'/output['path'],sr=16000,mono=True);audio.append(y)
            assert np.isfinite(y).all() and abs(len(y)-len(before))<=2
        if case['operation']=='separate':
            scores=np.array([[si_sdr(reference,y) for y in audio] for reference in (a,b)])
            assignment=[0,1] if scores[0,0]+scores[1,1]>=scores[0,1]+scores[1,0] else [1,0]
            metrics=[dict(speaker=i+1,before_si_sdr_db=si_sdr(reference,before),after_si_sdr_db=float(scores[i,assignment[i]])) for i,reference in enumerate((a,b))]
        else:metrics=[dict(before_si_sdr_db=si_sdr(a,before),after_si_sdr_db=si_sdr(a,audio[0]))]
        for metric in metrics:metric['improvement_db']=metric['after_si_sdr_db']-metric['before_si_sdr_db']
        case.update(metrics=metrics,outputs=task['outputs'],model_sources=task['model_sources'],original_preserved=True,device=task['device'])
        print(case['name'],json.dumps(metrics),flush=True)
    report=dict(verified_at=datetime.now(timezone.utc).isoformat(),scope='controlled synthetic voices/music/noise, actual neural inference; metrics do not replace human listening',cases=cases)
    target=folder/'model-runtime-verification.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('saved',target,flush=True)


if __name__=='__main__':main()
