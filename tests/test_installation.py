import importlib.util
from pathlib import Path
import httpx
import pytest
from voice_platform.client import Client
from voice_platform.config import installation_id


def connected(monkeypatch, config, handler):
    monkeypatch.delenv('VOICE_PLATFORM_URL', raising=False)
    monkeypatch.setattr('voice_platform.client.load_config', lambda: config)
    client = Client()
    client.http.close()
    client.http = httpx.Client(base_url=client.url, transport=httpx.MockTransport(handler))
    return client


def test_local_stop_cannot_target_another_installation(monkeypatch, cfg):
    calls = []
    def handle(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={'status':'ok', 'installation_id':'another-installation'})
    client = connected(monkeypatch, cfg, handle)
    with pytest.raises(ValueError, match='another installation'):
        client.request('POST', '/maintenance/stop')
    assert calls == [('GET', '/api/v1/health')]


def test_local_service_identity_and_explicit_remote_selection(monkeypatch, cfg):
    client = connected(monkeypatch, cfg, lambda r: httpx.Response(200, json={'status':'ok', 'installation_id':installation_id(cfg)}))
    assert client.request('GET', '/health')['installation_id'] == installation_id(cfg)
    assert client.verified
    monkeypatch.setenv('VOICE_PLATFORM_URL', 'http://127.0.0.1:1791')
    client.verified = False
    client.http.close()
    client.http = httpx.Client(base_url='http://127.0.0.1:1791', transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'installation_id':'explicit-remote'})))
    assert client.request('GET', '/health')['installation_id'] == 'explicit-remote'


@pytest.mark.parametrize('same', [True, False])
def test_legacy_service_is_checked_before_use(monkeypatch, cfg, same):
    def handle(request):
        payload = {'status':'ok'} if request.url.path.endswith('/health') else {'data_dir':cfg['data_dir'] if same else str(Path(cfg['data_dir']).parent/'other')}
        return httpx.Response(200, json=payload)
    client = connected(monkeypatch, cfg, handle)
    if same:
        assert client.request('GET', '/health')['status'] == 'ok'
    else:
        with pytest.raises(ValueError, match='another installation'):
            client.request('GET', '/health')


def test_downloader_keeps_resumable_bytes_but_discards_invalid_complete_file(tmp_path):
    source = Path(__file__).resolve().parents[1]/'scripts/download_model.py'
    spec = importlib.util.spec_from_file_location('download_model_test', source)
    downloader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(downloader)
    partial = tmp_path/'model.partial'
    partial.write_bytes(b'123')
    downloader.prepare_partial(partial, 5)
    assert partial.read_bytes() == b'123'
    partial.write_bytes(b'12345')
    downloader.prepare_partial(partial, 5)
    assert not partial.exists()


def test_model_destination_uses_configuration_not_a_previous_installation(tmp_path, monkeypatch):
    import json
    source = Path(__file__).resolve().parents[1]/'scripts/download_model.py'
    spec = importlib.util.spec_from_file_location('download_path_test', source)
    downloader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(downloader)
    monkeypatch.setattr(downloader, 'ROOT', tmp_path)
    monkeypatch.delenv('VOICE_PLATFORM_CONFIG', raising=False)
    (tmp_path/'config').mkdir()
    target = tmp_path/'shared-weights'
    (tmp_path/'config/platform.json').write_text(json.dumps({'model_dir':'own-models', 'reference_preprocessing':{'speaker_dir':str(target)}}), encoding='utf-8')
    assert downloader.configured_path('model_dir') == tmp_path/'own-models'
    assert downloader.configured_path('speaker_dir','reference_preprocessing') == target


def test_unrelated_service_on_the_same_port_is_rejected(monkeypatch, cfg):
    calls = []
    def handle(request):
        calls.append(request.method)
        return httpx.Response(200, json=['not a voice service'])
    client = connected(monkeypatch, cfg, handle)
    with pytest.raises(ValueError, match='Voice Foundry service'):
        client.request('POST', '/maintenance/stop')
    assert calls == ['GET']


def test_model_load_failure_releases_partial_state_and_retry_loads_again(client, monkeypatch):
    from .test_platform import wait
    engine = client.app.state.platform.engines['test']
    attempts = []
    def load():
        attempts.append(True)
        engine.model = True
        if len(attempts) == 1:
            raise RuntimeError('incomplete model installation')
    monkeypatch.setattr(engine, 'load', load)
    job = client.post('/api/v1/jobs', json={'text':'Fresh installation test.', 'max_retries':0}).json()
    assert wait(client, job['id'])['status'] == 'failed'
    health = client.get('/api/v1/health').json()
    assert health['active_engine'] is None and health['loaded_at'] is None
    assert engine.model is None
    retry = client.post('/api/v1/jobs/'+job['id']+'/retry').json()
    assert wait(client, retry['id'])['status'] == 'succeeded'
    assert len(attempts) == 2


def test_runtime_caches_do_not_reuse_another_applications_cache(tmp_path, monkeypatch):
    import os
    import json
    from voice_platform.config import load_config
    monkeypatch.setattr('voice_platform.config.ROOT', tmp_path)
    for key in ('HF_HOME','HF_HUB_CACHE','HF_MODULES_CACHE','TORCH_HOME','TRANSFORMERS_CACHE'):
        monkeypatch.setenv(key, str(tmp_path/'foreign-cache'))
    path = tmp_path/'platform.json'
    path.write_text(json.dumps({'data_dir':'data','model_dir':'models','log_dir':'logs','host':'127.0.0.1','token_env':'TEST_ONLY_TOKEN'}), encoding='utf-8')
    cfg = load_config(path)
    assert Path(cfg['cache_dir']) == tmp_path/'runtime/model-cache'
    assert Path(os.environ['HF_HOME']).is_relative_to(Path(cfg['cache_dir']))
    assert Path(os.environ['TORCH_HOME']).is_relative_to(Path(cfg['cache_dir']))
    assert 'TRANSFORMERS_CACHE' not in os.environ
