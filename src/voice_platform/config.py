import json
import os
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def installation_id(config):
    paths = [os.path.normcase(str(Path(config[key]).resolve())) for key in ('root', 'data_dir')]
    return hashlib.sha256('\0'.join(paths).encode('utf-8')).hexdigest()

def load_config(path=None):
    source = Path(path or os.environ.get("VOICE_PLATFORM_CONFIG", ROOT / "config/platform.json")).resolve()
    cfg = json.loads(source.read_text(encoding="utf-8-sig"))
    cfg["root"] = str(ROOT)
    cfg["config_path"] = str(source)
    cfg.setdefault('cache_dir', 'runtime/model-cache')
    for key in ("data_dir", "model_dir", "log_dir", "cache_dir"):
        p = Path(cfg[key])
        cfg[key] = str(p if p.is_absolute() else ROOT / p)
        Path(cfg[key]).mkdir(parents=True, exist_ok=True)
    # Runtime libraries must not depend on another application's global model cache.
    cache = Path(cfg['cache_dir'])
    for key, folder in {'HF_HOME':'huggingface', 'HF_HUB_CACHE':'huggingface/hub',
                        'HF_MODULES_CACHE':'huggingface/modules', 'TORCH_HOME':'torch'}.items():
        os.environ[key] = str(cache/folder)
    os.environ.pop('TRANSFORMERS_CACHE', None)
    if cfg["host"] not in ("127.0.0.1", "localhost", "::1") and not os.getenv(cfg["token_env"]):
        raise ValueError("远程监听必须先配置 token_env 指定的鉴权令牌")
    return cfg
