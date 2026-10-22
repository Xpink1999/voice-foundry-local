import importlib.util
import ast
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_literal_messages_in_all_browser_modules_have_translations():
    catalog = json.loads((ROOT/'web/locales/zh-CN.json').read_text(encoding='utf-8'))
    pattern = r'''\btr\(("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')'''
    for source in (ROOT/'web').glob('*.js'):
        if source.name == 'translations.js':
            continue
        for literal in re.findall(pattern, source.read_text(encoding='utf-8')):
            assert ast.literal_eval(literal) in catalog, (source.name, literal)


def test_browser_bundle_matches_editable_catalogs(tmp_path):
    spec = importlib.util.spec_from_file_location('build_i18n', ROOT/'scripts/build_i18n.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    shutil.copytree(ROOT/'web/locales', tmp_path/'web/locales')
    builder.build(tmp_path)
    assert (tmp_path/'web/translations.js').read_bytes() == (ROOT/'web/translations.js').read_bytes()


def test_static_messages_exist_and_runtime_loads_before_application():
    catalog = json.loads((ROOT/'web/locales/zh-CN.json').read_text(encoding='utf-8'))
    scripts = []

    class Page(HTMLParser):
        def handle_starttag(self, tag, attrs):
            for name, value in attrs:
                if name.startswith('data-i18n'):
                    assert value in catalog, (name, value)
            if tag == 'script':
                scripts.append(dict(attrs)['src'].split('?')[0])

    Page().feed((ROOT/'web/index.html').read_text(encoding='utf-8'))
    assert scripts.index('/translations.js') < scripts.index('/i18n.js') < scripts.index('/app.js')
