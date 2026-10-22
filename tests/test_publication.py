import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publication', ROOT/'scripts/package_public.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


def source(tmp_path):
    root = tmp_path/'installation'
    root.mkdir()
    for name in publication.ROOT_FILES:
        (root/name).write_text('source\n', encoding='utf-8')
    for name in ('src/service.py', 'data/recording.wav', 'models/weights.pt',
                 'vendor/repo/source.py', 'runtime/private.json', 'docs/evidence/recording.wav',
                 'docs/evidence/private.json', 'docs/ACCEPTANCE.md', 'dist/backup.zip',
                 'src/__pycache__/module.pyc', 'LICENSES/upstream/LICENSE'):
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('test only\n', encoding='utf-8')
    return root


def test_public_copy_contains_source_and_licenses_but_no_user_material(tmp_path):
    root = source(tmp_path)
    dest = tmp_path/'public'
    records = publication.build(root, dest)
    paths = {x['path'] for x in records}
    assert 'src/service.py' in paths and 'LICENSES/upstream/LICENSE' in paths
    assert all(not p.startswith(('data/', 'models/', 'vendor/', 'runtime/', 'dist/', 'docs/evidence/')) for p in paths)
    assert 'docs/ACCEPTANCE.md' not in paths
    assert json.loads((dest/'PUBLIC_SOURCE_MANIFEST.json').read_text(encoding='utf-8'))['files'] == records
    with pytest.raises(ValueError):
        publication.build(root, dest)


def test_secret_or_machine_path_blocks_copy_before_destination_is_created(tmp_path):
    root = source(tmp_path)
    path = root/'src/service.py'
    dest = tmp_path/'public'
    for text in ('ghp_'+'x'*36, 'C:'+chr(92)+'Users'+chr(92)+'private-person'+chr(92)+'recording.wav'):
        path.write_text(text, encoding='utf-8')
        with pytest.raises(ValueError):
            publication.build(root, dest)
        assert not dest.exists()
