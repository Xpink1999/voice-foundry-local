import os
import subprocess
import sys
import threading
import time

import numpy as np
import pytest
import soundfile as sf

from voice_platform.audio import join_wavs, write_wav
from voice_platform.process_engine import ProcessEngine
from voice_platform.process_owner import ProcessOwner, ProcessExit
from voice_platform.worker_runner import run_command


def test_process_engine_reuses_then_releases_and_reloads(cfg):
    engine = ProcessEngine('tests.fake_engine:FakeEngine', cfg)
    try:
        engine.load()
        process = engine.process
        first_pid = process.pid
        for _ in range(2):
            chunks = list(engine.synthesize({'text':'test', 'streaming':True}))
            assert len(chunks) == 4 and chunks[0].dtype == np.float32
            assert engine.process.pid == first_pid
        engine.unload()
        assert engine.process is None and engine.connection is None
        engine.load()
        assert engine.process.pid != first_pid
        assert list(engine.synthesize({'text':'again'}))
    finally:
        engine.unload()


def test_cancelled_stream_and_inference_error_release_worker(cfg):
    engine = ProcessEngine('tests.fake_engine:FakeEngine', cfg)
    try:
        stream = engine.synthesize({'text':'stream', 'streaming':True})
        assert next(stream).size
        stream.close()
        assert engine.process is None
        with pytest.raises(ValueError, match='injected engine failure'):
            list(engine.synthesize({'text':'FAIL'}))
        assert engine.process is None
    finally:
        engine.unload()


def test_idle_release_and_stop_interrupt_active_worker(cfg):
    from voice_platform.service import Platform
    from voice_platform.schemas import GenerationInput
    cfg['engines'] = {'test':{'adapter':'tests.fake_engine:FakeEngine'}}
    cfg['idle_unload_seconds'] = .1
    platform = Platform(cfg)
    platform.start()
    try:
        job = platform.submit([GenerationInput(text='idle release', max_retries=0)])[0]
        deadline = time.monotonic()+15
        while time.monotonic()<deadline and platform.store.get('jobs', job['id'])['status'] not in {'succeeded','failed'}:
            time.sleep(.1)
        assert platform.store.get('jobs',job['id'])['status'] == 'succeeded'
        while time.monotonic()<deadline and platform.active_engine:
            time.sleep(.1)
        assert platform.active_engine is None and platform.engines['test'].process is None
        platform.engines['test'] = ProcessEngine('tests.fake_engine:BlockingEngine', cfg)
        job = platform.submit([GenerationInput(text='stop active',max_retries=0)])[0]
        while time.monotonic()<deadline and platform.engines['test'].process is None:
            time.sleep(.05)
        started=time.monotonic()
        platform.stop()
        assert time.monotonic()-started < 10
        assert platform.engines['test'].process is None
        assert not platform.worker.is_alive()
    finally:
        platform.stop()


def test_decoding_cancels_and_reaps_child():
    event=threading.Event()
    timer=threading.Timer(.3,event.set)
    timer.start()
    started=time.monotonic()
    try:
        with pytest.raises(InterruptedError):
            run_command([sys.executable,'-c','import time; time.sleep(60)'],event)
        assert time.monotonic()-started < 6
    finally:
        timer.cancel()


@pytest.mark.skipif(os.name != 'nt', reason='Windows process ownership')
def test_job_close_terminates_owned_child():
    process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
    owner=None
    try:
        owner=ProcessOwner(process.pid)
        owner.close()
        process.wait(timeout=5)
    finally:
        if owner:owner.close()
        if process.poll() is None:process.kill();process.wait(timeout=5)


@pytest.mark.skipif(os.name != 'nt', reason='Windows process ownership')
def test_forced_parent_exit_does_not_leave_owned_child():
    code = """import os,subprocess,sys,time
from voice_platform.process_owner import ProcessOwner
child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
owner=ProcessOwner(child.pid)
print(child.pid,flush=True)
time.sleep(.5)
os._exit(0)
"""
    parent=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,text=True)
    watch=None
    try:
        child=int(parent.stdout.readline())
        watch=ProcessExit(child)
        parent.wait(timeout=5)
        deadline=time.monotonic()+5
        while not watch.exited() and time.monotonic()<deadline:time.sleep(.1)
        assert watch.exited()
    finally:
        if watch:watch.close()
        parent.stdout.close()
        if parent.poll() is None:parent.kill();parent.wait(timeout=5)


@pytest.mark.skipif(os.name != 'nt', reason='Windows stop verification')
def test_client_stop_waits_for_original_process_exit(cfg,monkeypatch):
    import httpx
    from voice_platform.client import Client
    from voice_platform.config import installation_id
    monkeypatch.delenv('VOICE_PLATFORM_URL',raising=False)
    process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
    client=Client.__new__(Client)
    client.config=cfg;client.verified=False
    def request(request):
        if request.method=='POST':process.terminate();return httpx.Response(202,json={'stop_requested':True})
        return httpx.Response(200,json={'status':'ok','installation_id':installation_id(cfg),'process_id':process.pid})
    client.http=httpx.Client(base_url='http://localhost',transport=httpx.MockTransport(request))
    try:
        assert client.stop(timeout=5)['stopped']
        process.wait(timeout=1)
        assert process.returncode is not None
    finally:
        client.http.close()
        if process.poll() is None:process.kill();process.wait(timeout=5)


def test_segment_assembly_uses_bounded_reads_and_preserves_samples(tmp_path):
    parts=[]
    for i in range(3):
        path=tmp_path/f'{i}.wav'
        write_wav(path,np.ones(100000,dtype=np.float32)*(i+1)/10,24000)
        parts.append(path)
    checks=[]
    target=tmp_path/'joined.wav'
    join_wavs(target,parts,24000,100,lambda:checks.append(True))
    pcm,rate=sf.read(target,dtype='float32')
    assert rate == 24000 and len(pcm) == 304800
    assert np.array_equal(pcm[:100000],sf.read(parts[0],dtype='float32')[0])
    assert not pcm[100000:102400].any()
    assert len(checks)>=9


def test_waveform_preview_has_bounded_size_and_matches_audio(client):
    from tests.test_platform import submit, wait
    job=wait(client,submit(client)['id'])
    result_id=job['results'][0]
    preview=client.get(f'/api/v1/results/{result_id}/waveform')
    assert preview.status_code==200 and len(preview.content)<6000
    value=preview.json()
    assert len(value['peaks'])==190 and value['duration']>0
    assert 0<max(value['peaks'])<=1


def test_reference_worker_ownership_gate_and_normal_exit(cfg,tmp_path):
    from types import SimpleNamespace
    from voice_platform.worker_runner import run_worker
    class Store:
        def get(self,*args):return {'status':'running'}
        def update(self,*args,**kwargs):pass
    owner=SimpleNamespace(config=cfg,options={'cpu_threads':1,'worker_timeout_seconds':10},
                          stop_event=threading.Event(),store=Store(),process=None)
    result=run_worker(owner,{'mode':'compare','items':[],'text':'test'},tmp_path/'worker','reference_comparisons','test')
    assert result['ranking']==[] and owner.process is None
