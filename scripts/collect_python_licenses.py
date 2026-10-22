"""Inventory installed distributions and retain license texts, never private metadata.

Run using the isolated runtime after dependency installation. No package code runs.
This inventory describes that environment, not a guarantee about all wheel contents.
"""
import hashlib
import importlib.metadata as metadata
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect(output):
    records = []
    seen = set()
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata['Name'].lower()):
        name = dist.metadata['Name']
        key = re.sub(r'[-_.]+', '-', name).lower()
        if key == 'voice-foundry-local' or key in seen:
            continue
        seen.add(key)
        texts = []
        for file in dist.files or []:
            # Only license material. Do not copy RECORD, direct_url or full METADATA.
            in_metadata = any(part.endswith('.dist-info') for part in file.parts)
            if not (any(part.lower() in ('licenses', 'license') for part in file.parts)
                    or file.name.lower().startswith(('license', 'licence', 'copying', 'notice', 'authors'))):
                continue
            source = Path(dist.locate_file(file))
            if not source.is_file():
                continue
            raw = source.read_bytes()
            raw.decode('utf-8')  # Refuse unexpected binary content.
            relative = (Path(*file.parts[next(i for i, p in enumerate(file.parts) if p.endswith('.dist-info'))+1:])
                        if in_metadata else Path('bundled')/file)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Unsafe license path')
            target = output/'python'/key/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            texts.append(dict(path=target.relative_to(output).as_posix(), sha256=hashlib.sha256(raw).hexdigest()))
        declared = dist.metadata.get('License-Expression') or dist.metadata.get('License') or ''
        classifiers = [v for v in dist.metadata.get_all('Classifier', []) if v.startswith('License ::')]
        # Keep a short display field; full license text is retained separately.
        record = dict(name=name, version=dist.version, declared_license=declared.splitlines()[0][:240] if declared else '',
                      license_classifiers=classifiers, license_texts=texts)
        records.append(record)
    output.mkdir(parents=True, exist_ok=True)
    (output/'python-dependencies.json').write_text(json.dumps(dict(
        scope='Installed dependency metadata and license texts; no binaries or model weights redistributed',
        packages=records), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    missing = [r['name'] for r in records if not r['license_texts']]
    print(json.dumps(dict(packages=len(records), missing_license_texts=missing), ensure_ascii=False))
    return records


if __name__ == '__main__':
    collect(ROOT/'LICENSES')
