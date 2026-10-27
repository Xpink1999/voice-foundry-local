"""Stage-specific local availability and frozen model manifests."""
import json
import importlib.util
from pathlib import Path
from .audio import sha256


def snapshots(config,freeze_vad=False):
    entries={}
    for section,keys in (('speaker_tracking',('model_dir',)),
                         ('reference_preprocessing',('speaker_dir','whisper_dir')),
                         ('audio_processing',('separation_dir','three_separation_dir'))):
        for key in keys:
            path=Path(config[section][key]);path=path if path.is_absolute() else Path(config['root'])/path
            manifest=path/'provenance.json'
            entries[section+'.'+key]=dict(path=str(path),manifest=json.loads(manifest.read_text(encoding='utf-8')) if manifest.is_file() else None)
    if freeze_vad:
        spec=importlib.util.find_spec('silero_vad')
        if spec:
            path=Path(spec.origin).parent/'data'
            entries['vad']=dict(path=str(path),bundled=True,manifest=dict(model='silero-vad bundled ONNX',
                files=[dict(file=f.name,sha256=sha256(f),bytes=f.stat().st_size) for f in sorted(path.glob('*.onnx'))]))
    return entries


def verify_frozen(entries):
    for entry in entries.values():
        expected=entry['manifest']
        if expected is None:continue
        path=Path(entry['path'])
        if not entry.get('bundled') and json.loads((path/'provenance.json').read_text(encoding='utf-8'))!=expected:
            raise ValueError('模型版本已变化，请重新创建处理任务')
        for item in expected.get('files',[]):
            target=(path/item['file']).resolve();target.relative_to(path.resolve())
            if sha256(target)!=item['sha256']:raise ValueError('模型文件与任务快照不一致')


def readiness(config):
    data=snapshots(config)
    has=lambda name:data[name]['manifest'] is not None
    interpreter=Path(config['speaker_tracking']['python']);interpreter=interpreter if interpreter.is_absolute() else Path(config['root'])/interpreter
    three_package=(interpreter.parent.parent/'Lib/site-packages/speechbrain/__init__.py').is_file()
    return dict(diarization=has('speaker_tracking.model_dir') and interpreter.is_file(),
        solo_references=has('speaker_tracking.model_dir') and interpreter.is_file() and has('reference_preprocessing.speaker_dir') and has('reference_preprocessing.whisper_dir'),
        two_speaker_overlap=has('audio_processing.separation_dir'),
        three_speaker_overlap=has('audio_processing.three_separation_dir') and three_package,
        three_speaker_native_sample_rate=8000,maximum_speakers=3,
        note='本机文件存在不代表音质通过；三人模型为 8 kHz，需试听。')
