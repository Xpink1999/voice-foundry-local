"""Optional local diarization environment and licensed, pinned model snapshot.

Run with the installed platform Python after accepting the model's access terms.
Credentials are read by huggingface_hub; they are never copied into configuration.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import venv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from voice_platform.config import load_config
from voice_platform.audio import sha256


def main():
    from huggingface_hub import HfApi, snapshot_download, get_token
    token=get_token()
    config=load_config()
    root=Path(config['root'])
    python=Path(config['speaker_tracking']['python'])
    python=python if python.is_absolute() else root/python
    # Only the optional, dedicated environment is created or changed.
    environment=python.parent.parent
    environment.resolve().relative_to((root/'runtime').resolve())
    os.environ['TEMP']=os.environ['TMP']=str(root/'runtime'/'tmp')
    Path(os.environ['TEMP']).mkdir(parents=True,exist_ok=True)
    if not python.is_file():venv.EnvBuilder(with_pip=True).create(environment)
    from sysconfig import get_paths
    base=Path(get_paths()['purelib'])
    target=environment/('Lib/site-packages' if os.name=='nt' else f'lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages')
    target.mkdir(parents=True,exist_ok=True)
    # Relative entries work under Windows paths containing Chinese characters.
    (target/'voice-foundry-base.pth').write_text('\n'.join(os.path.relpath(p,target) for p in (base,root/'src'))+'\n',encoding='utf-8')
    subprocess.run([str(python),'-m','pip','install','pyannote.audio==4.0.4','torchcodec==0.7.0',
                    'huggingface-hub<1','torch==2.8.0','torchaudio==2.8.0'],check=True)
    repo='pyannote/speaker-diarization-community-1'
    info=HfApi(token=token).model_info(repo,revision='3533c8cf8e369892e6b79ff1bf80f7b0286a54ee',files_metadata=True)
    if info.card_data.get('license')!='cc-by-4.0':raise ValueError('Review changed model license before installation')
    model=Path(config['speaker_tracking']['model_dir'])
    model=model if model.is_absolute() else root/model
    names=[f.rfilename for f in info.siblings if f.rfilename.endswith(('.yaml','.json','.bin','.safetensors','.npz','.md','.txt')) or f.rfilename=='LICENSE']
    snapshot_download(repo,revision=info.sha,local_dir=model,allow_patterns=names,max_workers=2,token=token)
    files=[]
    for name in names:
        path=model/name
        digest=sha256(path)
        entry=next(f for f in info.siblings if f.rfilename==name)
        if entry.lfs and digest!=entry.lfs.sha256:raise ValueError('Model hash mismatch: '+name)
        files.append(dict(file=name,sha256=digest,bytes=path.stat().st_size))
    (model/'provenance.json').write_text(json.dumps(dict(model=repo,revision=info.sha,license='cc-by-4.0',
        source='https://huggingface.co/'+repo,files=files),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Speaker tracking ready. Recordings stay on this computer.')


if __name__=='__main__':main()
