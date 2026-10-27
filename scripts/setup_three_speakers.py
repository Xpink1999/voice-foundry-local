"""Optional native three-speaker separator. No recording is sent to a remote service."""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from voice_platform.config import load_config
from voice_platform.audio import sha256


def main():
    from huggingface_hub import HfApi,snapshot_download
    cfg=load_config();root=Path(cfg['root'])
    python=Path(cfg['speaker_tracking']['python']);python=python if python.is_absolute() else root/python
    if not python.is_file():raise ValueError('Install speaker tracking first: scripts/setup_speaker_tracking.py')
    python.resolve().relative_to((root/'runtime').resolve())
    subprocess.run([str(python),'-m','pip','install','speechbrain==1.0.3','torch==2.8.0','torchaudio==2.8.0','huggingface-hub<1'],check=True)
    repository='speechbrain/sepformer-wsj03mix'
    info=HfApi().model_info(repository,files_metadata=True)
    if info.card_data.get('license')!='apache-2.0':raise ValueError('Review changed model license before installation')
    folder=Path(cfg['audio_processing']['three_separation_dir']);folder=folder if folder.is_absolute() else root/folder
    names=['hyperparams.yaml','encoder.ckpt','decoder.ckpt','masknet.ckpt','README.md']
    snapshot_download(repository,revision=info.sha,local_dir=folder,allow_patterns=names,max_workers=2)
    files=[]
    for name in names:
        path=folder/name;digest=sha256(path);entry=next(f for f in info.siblings if f.rfilename==name)
        if entry.lfs and digest!=entry.lfs.sha256:raise ValueError('Model hash mismatch: '+name)
        files.append(dict(file=name,sha256=digest,bytes=path.stat().st_size))
    (folder/'provenance.json').write_text(json.dumps(dict(model=repository,revision=info.sha,license='apache-2.0',
        source='https://huggingface.co/'+repository,native_sample_rate=8000,output_speakers=3,quality_status='not_listening_approved',files=files),indent=2),encoding='utf-8')
    print('Three-speaker candidate installed. Its native 8 kHz output still needs listening review.')


if __name__=='__main__':main()
