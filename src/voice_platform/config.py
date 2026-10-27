import json
import os
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def installation_id(config):
    paths = [os.path.normcase(str(Path(config[key]).resolve())) for key in ('root', 'data_dir')]
    return hashlib.sha256('\0'.join(paths).encode('utf-8')).hexdigest()

def load_config(path=None):
    source = Path(path or os.environ.get("VOICE_PLATFORM_CONFIG", '').strip() or ROOT / "config/platform.json").resolve()
    cfg = json.loads(source.read_text(encoding="utf-8-sig"))
    cfg["root"] = str(ROOT)
    cfg["config_path"] = str(source)
    cfg.setdefault('speaker_tracking', {})
    for key,value in dict(model_dir='models/pyannote-community-1', python='runtime/diarization-env/Scripts/python.exe',
                          match_threshold=.65, match_margin=.08, min_turn_seconds=.15, max_clip_seconds=30.,
                          gap_ms=180, trim_pause_ms=120, edge_padding_ms=60).items():
        cfg['speaker_tracking'].setdefault(key,value)
    cfg.setdefault('cache_dir', 'runtime/model-cache')
    for key in ("data_dir", "model_dir", "log_dir", "cache_dir"):
        p = Path(cfg[key])
        cfg[key] = str(p if p.is_absolute() else ROOT / p)
        Path(cfg[key]).mkdir(parents=True, exist_ok=True)
    # Runtime libraries must not depend on another application's global model cache.
    cache = Path(cfg['cache_dir'])
    for key, folder in {'HF_HOME':'huggingface', 'HF_HUB_CACHE':'huggingface/hub',
                        'HF_MODULES_CACHE':'huggingface/modules', 'TORCH_HOME':'torch',
                        'CUDA_CACHE_PATH':'cuda', 'TORCH_EXTENSIONS_DIR':'torch/extensions',
                        'TORCHINDUCTOR_CACHE_DIR':'torch/inductor', 'TRITON_CACHE_DIR':'triton',
                        'NUMBA_CACHE_DIR':'numba'}.items():
        target = cache/folder
        target.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(target)
    os.environ.pop('TRANSFORMERS_CACHE', None)
    if cfg["host"] not in ("127.0.0.1", "localhost", "::1") and not os.getenv(cfg["token_env"]):
        raise ValueError("远程监听必须先配置 token_env 指定的鉴权令牌")
    return cfg
