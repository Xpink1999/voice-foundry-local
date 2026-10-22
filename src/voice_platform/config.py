import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def load_config(path=None):
    source = Path(path or os.environ.get("VOICE_PLATFORM_CONFIG", ROOT / "config/platform.json")).resolve()
    cfg = json.loads(source.read_text(encoding="utf-8-sig"))
    cfg["root"] = str(ROOT)
    cfg["config_path"] = str(source)
    for key in ("data_dir", "model_dir", "log_dir"):
        p = Path(cfg[key])
        cfg[key] = str(p if p.is_absolute() else ROOT / p)
        Path(cfg[key]).mkdir(parents=True, exist_ok=True)
    if cfg["host"] not in ("127.0.0.1", "localhost", "::1") and not os.getenv(cfg["token_env"]):
        raise ValueError("远程监听必须先配置 token_env 指定的鉴权令牌")
    return cfg
