"""Check this installation without generating audio or reading user assets."""
import argparse
import importlib
import io
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(profile='core', models=False):
    from voice_platform.config import load_config
    config = load_config()
    checks = []

    def run(name, action):
        print('Checking '+name+'...', file=sys.stderr, flush=True)
        try:
            detail = action()
            checks.append(dict(name=name, ok=True, detail=detail))
        except Exception as error:
            checks.append(dict(name=name, ok=False, detail=f'{type(error).__name__}: {error}'))
        print(('OK: ' if checks[-1]['ok'] else 'FAILED: ')+name, file=sys.stderr, flush=True)

    def python():
        if sys.version_info[:2] != (3, 11):
            raise ValueError('Use the project-local Python 3.11 environment created by install.ps1.')
        if Path(sys.prefix).resolve() != (ROOT/'.venv').resolve():
            raise ValueError('Run .venv/Scripts/python.exe scripts/check_install.py; global Python is not this installation.')
        return sys.version.split()[0]

    def imports(names):
        for name in names:
            importlib.import_module(name)
        return names

    def wav():
        import numpy as np
        import soundfile as sf
        audio = io.BytesIO()
        sf.write(audio, np.zeros(1600), 16000, format='WAV')
        audio.seek(0)
        assert sf.info(audio).frames == 1600
        return 'WAV encode/decode available'

    run('python', python)
    run('service imports', lambda: imports(['voice_platform.api', 'mcp', 'httpx']))
    run('audio I/O', wav)
    warnings = []
    if not shutil.which(config['ffmpeg']):
        warnings.append('FFmpeg was not found. WAV TTS remains available; recording upload, encoded exports and audio processing require FFmpeg on PATH or its absolute path in config/platform.json.')
    if profile == 'inference':
        def cuda():
            try:
                import torch
            except OSError as error:
                raise RuntimeError('PyTorch DLL loading failed. Check the Microsoft Visual C++ x64 runtime: https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist . Original error: '+str(error)) from error
            if torch.__version__ != '2.8.0+cu128':
                raise ValueError('Expected torch 2.8.0+cu128; rerun install.ps1.')
            if config['device'].startswith('cuda'):
                if not torch.cuda.is_available():
                    raise ValueError('CUDA is unavailable. Install a compatible NVIDIA driver, then rerun this check. CoreOnly can inspect the interface without CUDA.')
                assert (torch.ones(4, device=config['device'])*2).sum().item() == 8
                return dict(torch=torch.__version__, gpu=torch.cuda.get_device_name(0))
            return dict(torch=torch.__version__, device=config['device'])

        def sources():
            sys.path.insert(0, str(ROOT/'vendor/VoxCPM/src'))
            sys.path.insert(0, str(ROOT/'vendor/Resemblyzer'))
            imports(['voxcpm', 'resemblyzer', 'faster_whisper', 'silero_vad', 'opencc'])
            from voice_platform.processing_engines import namespace
            namespace('vf_clearvoice', ROOT/'vendor/ClearerVoice-Studio/clearvoice/clearvoice')
            namespace('models', ROOT/'vendor/Music-Source-Separation-Training/models')
            namespace('models.bs_roformer', ROOT/'vendor/Music-Source-Separation-Training/models/bs_roformer')
            return imports(['vf_clearvoice.models.mossformer2_ss.mossformer2',
                            'vf_clearvoice.models.mossformer2_se.mossformer2_se_wrapper',
                            'vf_clearvoice.utils.decode', 'models.bs_roformer.mel_band_roformer'])

        run('CUDA runtime', cuda)
        run('inference sources and imports', sources)
    if models:
        def weights():
            def resolve(value):
                path = Path(value)
                return path if path.is_absolute() else ROOT/path
            folders = [Path(config['model_dir'])]
            folders += [resolve(config['reference_preprocessing'][key]) for key in ('whisper_dir', 'classifier_dir', 'speaker_dir')]
            folders += [resolve(config['audio_processing'][key]) for key in ('music_dir', 'separation_dir', 'enhancement_dir')]
            for folder in folders:
                from voice_platform.audio import sha256
                record = json.loads((folder/'provenance.json').read_text(encoding='utf-8'))
                if not record['files']:
                    raise ValueError('Empty model download record: '+str(folder))
                for item in record['files']:
                    path = (folder/item['file']).resolve()
                    if not path.is_relative_to(folder.resolve()) or path.stat().st_size != item['bytes']:
                        raise ValueError('Missing or incomplete model: '+str(path))
                    if sha256(path) != item['sha256']:
                        raise ValueError('Model hash mismatch; rerun install.ps1: '+str(path))
            return '7 model directories present; all recorded SHA-256 hashes match'
        run('model files', weights)
    return dict(profile=profile, models_checked=models, ok=all(item['ok'] for item in checks), checks=checks, warnings=warnings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['core', 'inference'], default='inference')
    parser.add_argument('--models', action='store_true')
    args = parser.parse_args()
    report = check(args.profile, args.models)
    target = ROOT/'runtime/install-check.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
