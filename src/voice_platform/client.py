import os
import subprocess
import sys
import time
from pathlib import Path
import httpx
from .config import load_config, installation_id

class Client:
    def __init__(self, auto_start=False):
        self.config = load_config()
        self.verified = False
        self.url = os.environ.get("VOICE_PLATFORM_URL", f"http://127.0.0.1:{self.config['port']}").rstrip("/")
        token = os.environ.get(self.config["token_env"])
        self.http = httpx.Client(base_url=self.url, timeout=360, trust_env=False, headers={"Authorization": f"Bearer {token}"} if token else {})
        if auto_start:
            self.ensure_running()

    def request(self, method, path, **kwargs):
        if not self.verified and path != '/health' and 'VOICE_PLATFORM_URL' not in os.environ:
            self.request('GET', '/health')
        response = self.http.request(method, "/api/v1"+path, **kwargs)
        if response.is_error:
            try:
                details = response.json().get("detail", response.text)
            except ValueError:
                details = response.text
            raise ValueError(f"HTTP {response.status_code}: {details}")
        result = response.json()
        if path == '/health' and 'VOICE_PLATFORM_URL' not in os.environ:
            if not isinstance(result, dict) or result.get('status') != 'ok':
                raise ValueError('This port does not provide a healthy Voice Foundry service. Check the port in config/platform.json.')
            identity = result.get('installation_id')
            if identity is None:
                # Older releases expose the data directory through settings.
                settings = self.http.get('/api/v1/settings')
                settings.raise_for_status()
                directory = settings.json().get('data_dir')
                actual = os.path.normcase(str(Path(directory).resolve())) if isinstance(directory, str) else None
                matches = actual == os.path.normcase(str(Path(self.config['data_dir']).resolve()))
            else:
                matches = identity == installation_id(self.config)
            if not matches:
                raise ValueError('This port belongs to another installation. Stop that service or change port in config/platform.json. Use VOICE_PLATFORM_URL only when intentionally connecting to another service.')
            self.verified = True
        return result

    def ensure_running(self):
        try:
            self.request("GET", "/health", timeout=2)
            return
        except (httpx.ConnectError, httpx.ConnectTimeout):
            if "VOICE_PLATFORM_URL" in os.environ:
                raise ValueError("指定的远程服务不可用，不自动启动本地服务")
        log_dir = Path(self.config["log_dir"])
        with (log_dir / "server.log").open("ab") as log:
            options = dict(stdout=log, stderr=log, stdin=subprocess.DEVNULL, cwd=self.config["root"])
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                options["start_new_session"] = True
            process = subprocess.Popen([sys.executable, "-m", "voice_platform.server"], **options)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise ValueError(f"服务启动失败，请查看 {log_dir / 'server.log'}")
            time.sleep(0.2)
            try:
                self.request("GET", "/health", timeout=1)
                return
            except (httpx.ConnectError, httpx.ConnectTimeout):
                pass
        raise ValueError(f"服务启动超时，请查看 {log_dir / 'server.log'}")

    def stop(self, timeout=60):
        from .process_owner import ProcessExit
        try:
            health = self.request('GET', '/health', timeout=2)
        except httpx.ConnectError:
            return dict(stopped=True, already_stopped=True)
        watch = ProcessExit(health['process_id']) if os.name == 'nt' and 'VOICE_PLATFORM_URL' not in os.environ else None
        try:
            self.request('POST', '/maintenance/stop', timeout=5)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if watch is not None:
                    if watch.exited():
                        return dict(stopped=True, process_id=health['process_id'])
                else:
                    try:
                        self.http.get('/api/v1/health', timeout=1).raise_for_status()
                    except httpx.ConnectError:
                        return dict(stopped=True)
                    except httpx.ConnectTimeout:
                        pass  # A timeout alone cannot confirm that a remote process exited.
                time.sleep(.1)
            raise TimeoutError('Service shutdown has not finished. Check server.log; memory release is not yet confirmed.')
        finally:
            if watch:
                watch.close()

    def wait(self, identity, timeout=3600, progress=None):
        end = time.monotonic() + timeout
        previous = None
        while time.monotonic() < end:
            item = self.request("GET", f"/jobs/{identity}")
            current = (item["status"], item["progress"])
            if current != previous and progress:
                progress(item)
            previous = current
            if item["status"] in {"succeeded", "failed", "cancelled"}:
                return item
            time.sleep(0.5)
        raise ValueError("等待超时；任务仍保存在服务中，可查询后续状态")
