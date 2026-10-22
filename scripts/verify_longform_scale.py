"""Isolated real HTTP import benchmark; never synthesizes millions of characters."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import socket
import subprocess
import sys
import time
import httpx
from voice_platform.config import ROOT,load_config

class Counters(ctypes.Structure):
    _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(name,ctypes.c_size_t) for name in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage']]
def memory(pid):
    api=ctypes.WinDLL('kernel32',use_last_error=True);api.OpenProcess.restype=ctypes.c_void_p;api.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=api.OpenProcess(0x0410,False,pid)
    if not handle:raise OSError(ctypes.get_last_error())
    try:
        value=Counters();value.cb=ctypes.sizeof(value);psapi=ctypes.WinDLL('psapi');psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_ulong]
        if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(value),value.cb):raise OSError(ctypes.get_last_error())
        return dict(working_set=value.WorkingSetSize,peak_working_set=value.PeakWorkingSetSize,private_bytes=value.PrivateUsage)
    finally:api.CloseHandle(handle)
def main():
    try:
        occupied=socket.create_connection(('127.0.0.1',8962),timeout=.2)
    except OSError:pass
    else:
        occupied.close();raise RuntimeError('8962 已被占用，不复用或停止未知服务')
    folder=ROOT/'runtime/longform-scale';folder.mkdir(exist_ok=True);config=load_config();config.update(port=8962,data_dir=str(folder/'data'),log_dir=str(folder/'logs'),default_engine='test',engines={'test':{'adapter':'tests.fake_engine:FakeEngine'}})
    config_path=folder/'config.json';config_path.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8');environment={**os.environ,'VOICE_PLATFORM_CONFIG':str(config_path)}
    with (folder/'server.log').open('wb') as log:
        process=subprocess.Popen([sys.executable,'-m','voice_platform.server'],cwd=ROOT,env=environment,stdout=log,stderr=log)
        client=httpx.Client(base_url='http://127.0.0.1:8962',timeout=600,trust_env=False)
        owned=False
        try:
            deadline=time.monotonic()+40
            while True:
                try:health=client.get('/api/v1/health').json();break
                except httpx.ConnectError:
                    if time.monotonic()>deadline:raise RuntimeError('scale service did not start')
                    time.sleep(.1)
            settings=client.get('/api/v1/settings').json()
            if Path(settings['data_dir']).resolve()!=(folder/'data').resolve():raise RuntimeError('校验服务数据目录不匹配')
            owned=True;pid=health['process_id'];baseline=memory(pid);records=[]
            for length in [10_000_000,30_000_000]:
                path=folder/f'continuous-{length}.txt';unit='连续长文没有章节也没有换行，系统仍须完整保留所有内容并自动拆分。';block=unit*2048;left=length;digest=hashlib.sha256()
                with path.open('wb') as stream:
                    while left:
                        piece=block[:min(left,len(block))];raw=piece.encode('utf-8');stream.write(raw);digest.update(raw);left-=len(piece)
                before=memory(pid);started=time.monotonic()
                with path.open('rb') as source:response=client.post('/api/v1/longform/books',files={'file':(path.name,source,'text/plain')},data={'title':f'隔离规模验收 {length} 字符','encoding':'auto'})
                response.raise_for_status();identity=response.json()['id'];samples=[]
                while True:
                    book=client.get('/api/v1/longform/books/'+identity).json();samples.append(memory(pid))
                    if book['phase'] in {'ready','failed'}:break
                    if time.monotonic()-started>600:raise TimeoutError(book)
                    time.sleep(.15)
                assert book['phase']=='ready' and book['chars']==length and book['source_sha256']==digest.hexdigest(),book
                chapters=client.get(f'/api/v1/longform/books/{identity}/chapters?limit=1').json();chapter=chapters['items'][0]['no'];page_started=time.monotonic();response=client.get(f'/api/v1/longform/books/{identity}/chapters/{chapter}/segments?limit=25');page=response.json();page_seconds=time.monotonic()-page_started
                assert len(page['items'])==25 and all(len(s['text'])<=160 for s in page['items'])
                with sqlite3.connect(folder/'data/platform.sqlite3') as db:
                    normalized=ROOT/'runtime/longform-scale/data'/book['normalized_path'];assert hashlib.file_digest(normalized.open('rb'),'sha256').hexdigest()==digest.hexdigest()
                    assert db.execute("SELECT COUNT(*) FROM entities WHERE kind='jobs'").fetchone()[0]==0
                    plan=db.execute("EXPLAIN QUERY PLAN SELECT no FROM lf_segments WHERE book_id=? AND deleted_batch IS NULL AND status='pending' ORDER BY no LIMIT 1",(identity,)).fetchall()
                    assert any('INDEX' in row[-1] for row in plan)
                result=dict(characters=length,source_bytes=path.stat().st_size,book_id=identity,chapters=book['chapters'],segments=book['segments'],elapsed_seconds=round(time.monotonic()-started,3),memory_before=before,memory_peak_sampled={k:max(s[k] for s in samples) for k in samples[0]},page_25_response_bytes=len(response.content),page_25_seconds=round(page_seconds,4),query_plan=plan,source_sha256=digest.hexdigest(),normalized_text_hash_equal=True,ordinary_jobs_created=0)
                records.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
            output=ROOT/'docs/evidence/longform/scale-verification.json';output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(dict(scope='isolated real HTTP, indexed SQLite and actual Windows process memory; test speech adapter, no whole-book synthesis',baseline=baseline,cases=records),ensure_ascii=False,indent=2),encoding='utf-8')
        finally:
            try:
                if owned:client.post('/api/v1/maintenance/stop');process.wait(timeout=30)
                elif process.poll() is None:subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
            except Exception:
                if process.poll() is None:subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
            client.close()
if __name__=='__main__':main()
