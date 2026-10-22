import copy
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from voice_platform.api import create_app
from voice_platform.config import load_config

@pytest.fixture
def cfg(tmp_path):
    c = copy.deepcopy(load_config())
    c.update(data_dir=str(tmp_path / "data"), log_dir=str(tmp_path / "logs"), idle_unload_seconds=300,
             allowed_hosts=["testserver", "127.0.0.1", "localhost"],
             engines={"test": {"adapter": "tests.fake_engine:FakeEngine"}, "limited": {"adapter": "tests.fake_engine:LimitedEngine"}}, default_engine="test", segment_chars=15)
    for key in ("data_dir", "log_dir"):
        Path(c[key]).mkdir(parents=True)
    # Controlled restoration workers need model identity snapshots, not real weights.
    # Keep these fixtures in tmp_path so a source-only checkout needs no models/ tree.
    import json
    for key in ('music_dir', 'separation_dir', 'enhancement_dir'):
        folder = tmp_path/'test-model-identities'/key
        folder.mkdir(parents=True)
        (folder/'provenance.json').write_text(json.dumps({'model': 'test-only', 'revision': 'fixture'}), encoding='utf-8')
        c['audio_processing'][key] = str(folder)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(c), encoding="utf-8")
    c["config_path"] = str(config_path)
    return c

@pytest.fixture
def client(cfg):
    with TestClient(create_app(cfg)) as c:
        yield c
