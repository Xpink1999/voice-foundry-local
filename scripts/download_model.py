"""Fetch one pinned official snapshot, resume downloads, verify LFS hashes."""
import concurrent.futures
import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = "openbmb/VoxCPM2"

def configured_path(key, section=None):
    config = json.loads(Path(os.environ.get('VOICE_PLATFORM_CONFIG', '').strip() or ROOT/'config/platform.json').read_text(encoding='utf-8-sig'))
    value = config[section][key] if section else config[key]
    path = Path(value)
    return path if path.is_absolute() else ROOT/path

def fetch(url):
    with urllib.request.urlopen(url, timeout=90) as response:
        return response.read()

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b""):
            h.update(block)
    return h.hexdigest()

def git_blob(path):
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()

def prepare_partial(path, expected_size):
    # A complete but invalid partial must not trigger an endless HTTP Range 416 retry.
    if path.exists() and path.stat().st_size >= expected_size:
        path.unlink()

def main():
    dest = configured_path('model_dir')
    dest.mkdir(parents=True, exist_ok=True)
    meta = json.loads((ROOT / "config/model-sources.json").read_text(encoding="utf-8"))[MODEL]
    revision = meta["sha"]
    needed = meta["siblings"]

    def download(item):
        name = item["rfilename"]
        path = dest / name
        expected_hash = item.get("lfs", {}).get("sha256")
        if path.exists() and path.stat().st_size == item["size"] and (digest(path) == expected_hash if expected_hash else git_blob(path) == item["blobId"]):
            return dict(file=name, bytes=path.stat().st_size, sha256=digest(path))
        partial = path.with_suffix(path.suffix + ".partial")
        for attempt in range(5):
            try:
                prepare_partial(partial, item['size'])
                offset = partial.stat().st_size if partial.exists() else 0
                route = "resolve" if item.get("lfs") else "raw"
                request = urllib.request.Request(f"https://huggingface.co/{MODEL}/{route}/{revision}/{name}", headers={"Range": f"bytes={offset}-"} if offset else {})
                with urllib.request.urlopen(request, timeout=120) as response:
                    append = offset and response.status == 206
                    with partial.open("ab" if append else "wb") as out:
                        while block := response.read(4*1024*1024):
                            out.write(block)
                if partial.stat().st_size != item["size"]:
                    raise ValueError(f"wrong size: {name}")
                actual = digest(partial)
                if expected_hash and expected_hash != actual:
                    partial.unlink()
                    raise ValueError(f"SHA256 mismatch: {name}")
                if not expected_hash and git_blob(partial) != item["blobId"]:
                    partial.unlink()
                    raise ValueError(f"Git blob mismatch: {name}")
                partial.replace(path)
                print(f"verified {name}: {path.stat().st_size}", flush=True)
                return dict(file=name, bytes=path.stat().st_size, sha256=actual)
            except Exception as error:
                print(f"download attempt {attempt+1} {name}: {type(error).__name__}: {error}", flush=True)
                if attempt == 4:
                    raise
                time.sleep(min(2**attempt, 15))

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        files = list(pool.map(download, needed))
    provenance = dict(model=MODEL, revision=revision, source=f"https://huggingface.co/{MODEL}", license="apache-2.0",
                      code_revision="cce58a5b59303c9bd63d12f23afe6a49a4a80c59", files=files)
    (dest / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Model snapshot verified:", revision)

if __name__ == "__main__":
    main()
