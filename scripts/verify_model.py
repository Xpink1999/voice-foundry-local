"""Stage 1: real CUDA inference. Never auto-approve listening quality."""
import json
import os
import platform
import sys
import time
from pathlib import Path
import numpy as np
import torch
import soundfile as sf
from voice_platform.audio import sha256, write_wav
from voice_platform.config import ROOT, load_config
from voice_platform.engines.voxcpm import VoxEngine

def main():
    cfg=load_config()
    directory=ROOT/'docs/evidence/stage1'
    directory.mkdir(parents=True,exist_ok=True)
    report=dict(python=sys.version,windows=platform.platform(),torch=torch.__version__,torch_cuda=torch.version.cuda,
                cuda_available=torch.cuda.is_available(),samples=[],human_listening='pending',production_approval=False)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA not available')
    report['gpu']=torch.cuda.get_device_name(0)
    report['cuda_tensor_sum']=(torch.ones(32,device='cuda')*2).sum().item()
    engine=VoxEngine(cfg)
    report['model']=engine.identity()
    start=time.monotonic()
    engine.load()
    report['load_seconds']=time.monotonic()-start
    tasks=[
        ('tts','欢迎来到声场。这是一段本地生成的中文语音。','',None,False),
        ('design','夜色渐深，城市终于安静下来。故事，就从这里开始。','沉稳成年男性，温暖、有叙事感，清晰自然',None,False),
        ('clone','同一个声音，能够跨越不同作品，继续讲述新的故事。','温暖自然',directory/'design.wav',False),
        ('streaming','Hello. This voice is generated locally, and streamed as it is created.','A calm adult male narrator with a warm natural voice',None,True)
    ]
    for name,text,style,reference,streaming in tasks:
        start=time.monotonic()
        request=dict(text=text,style=style,seed=42,engine_options=dict(cfg_value=2.0,inference_timesteps=10),streaming=streaming,
                     reference_path=str(reference) if reference else None)
        chunks=[]
        first_chunk=None
        for chunk in engine.synthesize(request):
            if first_chunk is None:
                first_chunk=time.monotonic()-start
            chunks.append(chunk)
        pcm=np.concatenate(chunks)
        target=directory/f'{name}.wav'
        write_wav(target,pcm,engine.sample_rate)
        elapsed=time.monotonic()-start
        item=dict(name=name,text=text,style=style,seed=42,cfg_value=2.0,inference_timesteps=10,sample_rate=engine.sample_rate,
                  chunks=len(chunks),first_chunk_seconds=first_chunk,elapsed_seconds=elapsed,duration=len(pcm)/engine.sample_rate,
                  rms=float(np.sqrt(np.mean(pcm**2))),peak=float(np.abs(pcm).max()),sha256=sha256(target),file=str(target),
                  reference=str(reference) if reference else None,reference_sha256=sha256(reference) if reference else None,
                  review='pending')
        assert item['duration']>.3 and item['rms']>1e-5 and np.isfinite(pcm).all()
        report['samples'].append(item)
        print(json.dumps({k:item[k] for k in ('name','duration','elapsed_seconds','chunks')},ensure_ascii=False),flush=True)
        (directory/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    report['peak_allocated_mb']=torch.cuda.max_memory_allocated()/1024**2
    engine.unload()
    report['allocated_after_unload_mb']=torch.cuda.memory_allocated()/1024**2
    report['technical_inference']='passed'
    (directory/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Stage 1 technical inference verified; listening approval remains pending.',flush=True)

if __name__=='__main__':
    main()
