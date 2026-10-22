"""Build a source-only publication directory from an explicit allowlist.

Existing destinations are refused. No user assets are moved or deleted.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ('src', 'web', 'config', 'scripts', 'tests', 'docs', 'bin', 'LICENSES')
ROOT_FILES = ('README.md', 'README.en.md', 'README.ja.md', 'README.ko.md',
              'LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md',
              'pyproject.toml', 'requirements-inference.txt', 'requirements.lock.txt',
              '.gitignore', '启动语音平台.cmd', '停止语音平台.cmd', '健康检查.cmd')
EXTENSIONS = {'.py', '.js', '.cjs', '.css', '.html', '.json', '.toml', '.md', '.txt', '.ps1', '.cmd'}
SECRETS = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{32,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|https?://[^\s/@]+:[^\s/@]+@)')


def selected_files(root):
    root = root.resolve()
    files = [root/name for name in ROOT_FILES]
    for folder in FOLDERS:
        for path in (root/folder).rglob('*'):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if any(part in ('__pycache__', '.git', '.pytest_cache', '.cache') or part.endswith('.egg-info') for part in rel.parts):
                continue
            if rel.parts[:2] == ('docs', 'evidence'):
                continue
            if folder == 'docs' and (path.name == 'ACCEPTANCE.md' or path.name.endswith('_ACCEPTANCE.md')):
                continue
            if rel.as_posix() == 'scripts/package_source.py':
                continue
            if folder != 'LICENSES' and path.suffix not in EXTENSIONS:
                continue
            if not path.resolve().is_relative_to(root) or path.is_symlink():
                raise ValueError('Symlink or escaped source: '+str(rel))
            files.append(path)
    return sorted(set(files))


def build(root, dest):
    root, dest = root.resolve(), dest.resolve()
    if dest.exists() or dest.is_relative_to(root):
        raise ValueError('Choose a new destination outside the working installation')
    prepared = []
    for path in selected_files(root):
        raw = path.read_bytes()
        text = raw.decode('utf-8-sig')
        rel = path.relative_to(root).as_posix()
        if SECRETS.search(text):
            raise ValueError('Possible secret; review before publication: '+rel)
        if re.search(r'(?:[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s]+|192\.168\.\d+\.\d+)', text, re.I):
            raise ValueError('Machine-specific information: '+rel)
        prepared.append((rel, raw))
    dest.mkdir(parents=True)
    manifest = []
    for rel, raw in prepared:
        target = dest/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        manifest.append(dict(path=rel, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    (dest/'PUBLIC_SOURCE_MANIFEST.json').write_text(json.dumps(dict(
        scope='Source, configuration templates, tests, documentation and third-party license material only',
        excludes=['user assets', 'recordings', 'model weights', 'environments', 'vendor code', 'logs', 'private evidence', 'recovery archives'],
        files=manifest), ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(directory=str(dest), files=len(manifest), bytes=sum(x['bytes'] for x in manifest)), ensure_ascii=False))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', required=True, type=Path)
    build(ROOT, parser.parse_args().dest)
