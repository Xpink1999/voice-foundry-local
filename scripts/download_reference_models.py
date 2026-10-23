"""Pin and verify local-only preprocessing models. No recording is uploaded anywhere."""
import concurrent.futures
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from download_model import ROOT, digest, git_blob, prepare_partial, configured_path

SPECS=[('Systran/faster-whisper-small','whisper-small','models/faster-whisper-small',{'README.md','config.json','model.bin','tokenizer.json','vocabulary.txt'},'mit'),
       ('MIT/ast-finetuned-audioset-10-10-0.4593','ast-audioset','models/AST-AudioSet',{'README.md','config.json','model.safetensors','preprocessor_config.json'},'bsd-3-clause')]

def install(repo,slug,directory,names,license_name,evidence_dir='reference-preprocessing',revision=None):
    meta=json.loads((ROOT/'config/model-sources.json').read_text(encoding='utf-8'))[repo]
    if revision and meta['sha']!=revision:raise ValueError('Pinned model revision mismatch: '+repo)
    if meta.get('cardData',{}).get('license')!=license_name:raise ValueError('Model card license mismatch: '+repo)
    target=ROOT/directory
    target.mkdir(parents=True,exist_ok=True)
    def download(item):
        name=item['rfilename'];path=target/name;expected=item.get('lfs',{}).get('sha256')
        def valid(p):
            return p.exists() and p.stat().st_size==item['size'] and (digest(p)==expected if expected else git_blob(p)==item['blobId'])
        if valid(path):return dict(file=name,sha256=digest(path),bytes=path.stat().st_size)
        temp=path.with_suffix(path.suffix+'.partial')
        for attempt in range(4):
            try:
                prepare_partial(temp, item['size'])
                offset=temp.stat().st_size if temp.exists() else 0
                route='resolve' if expected or attempt%2 else 'raw'
                req=urllib.request.Request(f'https://huggingface.co/{repo}/{route}/{meta["sha"]}/{name}'+('?download=true' if attempt>=2 else ''),headers={'Range':f'bytes={offset}-'} if offset else {})
                with urllib.request.urlopen(req,timeout=120) as response,temp.open('ab' if offset and response.status==206 else 'wb') as out:
                    while block:=response.read(4*1024*1024):out.write(block)
                if not valid(temp):raise ValueError('file identity mismatch')
                temp.replace(path)
                print('verified',repo,name,flush=True)
                return dict(file=name,sha256=digest(path),bytes=path.stat().st_size)
            except Exception as error:
                print('download',repo,name,type(error).__name__,str(error),flush=True)
                if attempt==3:raise
                time.sleep(1+attempt)
    selected=[f for f in meta['siblings'] if f['rfilename'] in names]
    assert {f['rfilename'] for f in selected}==names
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        files=list(pool.map(download,selected))
    (target/'provenance.json').write_text(json.dumps(dict(model=repo,revision=meta['sha'],license=license_name,source=f'https://huggingface.co/{repo}',files=files),ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    specs = [(repo, slug, configured_path(key, 'reference_preprocessing'), names, license_name)
             for (repo, slug, directory, names, license_name), key in zip(SPECS, ('whisper_dir', 'classifier_dir'))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda spec:install(*spec),specs))
    repo=ROOT/'vendor/Resemblyzer'
    commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    assert commit=='15d828edebe06bc72b9cabc8ef8ca5ab2cb457ce'
    target=configured_path('speaker_dir','reference_preprocessing');target.mkdir(parents=True,exist_ok=True)
    source=repo/'resemblyzer/pretrained.pt';dest=target/'pretrained.pt'
    if not dest.exists():
        try:os.link(source,dest)
        except OSError:shutil.copy2(source,dest)
    assert digest(source)==digest(dest)
    (target/'provenance.json').write_text(json.dumps(dict(model='resemble-ai/Resemblyzer',revision=commit,license='apache-2.0',source='https://github.com/resemble-ai/Resemblyzer',files=[dict(file='pretrained.pt',sha256=digest(dest),bytes=dest.stat().st_size)]),indent=2),encoding='utf-8')
    print('Preprocessing models ready.',flush=True)

if __name__=='__main__':main()
