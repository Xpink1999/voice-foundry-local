"""Own short-lived worker processes, progress, timeout and cancellation."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

def kill_worker(process):
    if process.poll() is None:
        if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else:process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill()

def run_worker(owner,request,folder,kind,identity):
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/'request.json';path.write_text(json.dumps(dict(request,config=request.get('config_snapshot',owner.config)),ensure_ascii=False),encoding='utf-8')
    environment=dict(os.environ,OMP_NUM_THREADS=str(owner.options['cpu_threads']),MKL_NUM_THREADS=str(owner.options['cpu_threads']),
                     HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONUTF8='1',NUMBA_CACHE_DIR=str(Path(owner.config['root'])/'runtime/numba-cache'))
    with (folder/'worker.log').open('wb') as log_file:
        process=subprocess.Popen([sys.executable,'-m','voice_platform.reference_worker',str(path)],cwd=owner.config['root'],env=environment,
            stdout=log_file,stderr=log_file,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        owner.process=process;started=time.monotonic();last=None
        try:
            while process.poll() is None:
                if owner.stop_event.is_set() or owner.store.get(kind,identity)['status']=='cancel_requested':
                    kill_worker(process);raise InterruptedError('预处理已停止；原始录音和已有片段保留')
                if time.monotonic()-started>owner.options['worker_timeout_seconds']:
                    kill_worker(process);raise TimeoutError('预处理超时，可检查日志后重试')
                progress=folder/'progress.json'
                if progress.exists():
                    try:
                        value=json.loads(progress.read_text(encoding='utf-8'))
                        if value!=last:owner.store.update(kind,identity,**value);last=value
                    except (OSError,ValueError):pass
                owner.stop_event.wait(.35)
            if process.returncode:
                text=(folder/'worker.log').read_text(encoding='utf-8',errors='replace')
                raise ValueError('本地分析失败：'+text[-2200:])
            return json.loads((folder/'result.json').read_text(encoding='utf-8'))
        finally:
            kill_worker(process)
            owner.process=None

