import hashlib
import io
import json
import zipfile
import pytest
from voice_platform import cli, mcp_server


class Requests:
    url = 'http://localhost:1234'

    def __init__(self, **kwargs):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return {'id': 'new-candidate'}


@pytest.mark.parametrize(('arguments', 'path', 'body'), [
    (['regenerate-result', 'result', '--reference-id', 'soft'], '/results/result/regenerate', {'reference_id': 'soft'}),
    (['book-regenerate', 'book', '3', '--start', '--seed', '12'], '/longform/books/book/segments/3/regenerate', {'seed': 12, 'start': True, 'use_book_defaults': False}),
    (['book-use-attempt', 'book', '3', '1'], '/longform/books/book/segments/3/use-attempt', {'attempt': 1}),
])
def test_cli_revisions_preserve_unspecified_frozen_fields(monkeypatch, arguments, path, body):
    client = Requests()
    monkeypatch.setattr(cli, 'Client', lambda **kwargs: client)
    monkeypatch.setattr(cli.sys, 'argv', ['voice', *arguments])
    monkeypatch.setattr(cli, 'show', lambda output: None)
    cli.main()
    assert client.calls == [('POST', path, {'json': body})]


def test_mcp_revision_and_reference_tools_use_current_api(monkeypatch):
    client = Requests()
    monkeypatch.setattr(mcp_server, 'api', lambda: client)
    mcp_server.voice_regenerate_result('result', style='')
    mcp_server.voice_book_regenerate('book', 2, reference_id='ref', start=True)
    mcp_server.voice_book_use_attempt('book', 2, 1)
    mcp_server.voice_update_reference('ref', scenario='', tags=[])
    mcp_server.voice_attach_references('voice', ['ref'])
    assert client.calls == [
        ('POST', '/results/result/regenerate', {'json': {'style': ''}}),
        ('POST', '/longform/books/book/segments/2/regenerate', {'json': {'reference_id': 'ref', 'start': True, 'use_book_defaults': False}}),
        ('POST', '/longform/books/book/segments/2/use-attempt', {'json': {'attempt': 1}}),
        ('PUT', '/references/ref', {'json': {'scenario': '', 'tags': []}}),
        ('POST', '/voices/voice/references', {'json': {'reference_ids': ['ref']}}),
    ]


def test_mcp_book_attempts_only_offer_successful_audio(monkeypatch):
    client = Requests()
    client.request = lambda *args, **kwargs: {'items': [
        {'attempt': 2, 'body': json.dumps({'status': 'failed'})},
        {'attempt': 1, 'body': json.dumps({'status': 'succeeded'})},
    ]}
    monkeypatch.setattr(mcp_server, 'api', lambda: client)
    result = mcp_server.voice_book_attempts('book', 3)
    assert 'audio_url' not in result['items'][0]
    assert result['items'][1]['audio_url'].endswith('/segments/3/attempts/1/audio')


def test_mcp_segment_revision_reaches_backend_and_restores_prior_take(client, monkeypatch):
    from tests.test_regeneration import setup
    from tests.test_longform import wait
    book, _, references = setup(client)

    class HTTPApi:
        url = 'http://testserver'

        def request(self, method, path, **kwargs):
            response = client.request(method, '/api/v1'+path, **kwargs)
            assert response.is_success, response.text
            return response.json()

    monkeypatch.setattr(mcp_server, 'api', HTTPApi)
    route = '/api/v1/longform/books/'+book
    original = mcp_server.voice_book_generation(book, 1)
    mcp_server.voice_book_regenerate(book, 1, reference_id=references[1], seed=12, start=True)
    wait(client, route, lambda value: value['state'] == 'paused')
    current = mcp_server.voice_book_generation(book, 1)
    assert current['reference']['id'] == references[1] and current['take']['seed'] == 12
    history = mcp_server.voice_book_attempts(book, 1)
    assert len(history['items']) == 2 and all('audio_url' in take for take in history['items'])
    mcp_server.voice_book_use_attempt(book, 1, 1)
    restored = mcp_server.voice_book_generation(book, 1)
    assert restored['take']['id'] == original['take']['id']
    assert client.get(route+'/chapters/1').json()['review'] == 'pending'


def test_book_import_passes_cloning_settings_and_rejects_ambiguous_mcp_paths(tmp_path, monkeypatch):
    client = Requests()
    monkeypatch.setattr(mcp_server, 'api', lambda: client)
    with pytest.raises(ValueError, match='绝对文本路径'):
        mcp_server.voice_import_book('book.txt')
    path = tmp_path/'book.txt'
    path.write_text('Chapter 1\nA short line.', encoding='utf-8')
    mcp_server.voice_import_book(str(path), style='', clone_mode='hifi')
    method, route, kwargs = client.calls[-1]
    assert (method, route) == ('POST', '/longform/books')
    assert kwargs['data']['clone_mode'] == 'hifi' and kwargs['data']['style'] == ''


class Stream:
    def __init__(self, data):
        self.data = data
        self.blocks = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    def iter_bytes(self, size):
        for offset in range(0, len(self.data), 7):
            self.blocks += 1
            yield self.data[offset:offset+7]


def package_bytes(name='audio/line.txt'):
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w') as archive:
        archive.writestr(name, 'retained audio metadata')
    return result.getvalue()


def test_regular_export_download_streams_and_keeps_verified_archive(tmp_path):
    data = package_bytes()
    stream = Stream(data)
    client = Requests()
    client.http = type('HTTP', (), {'stream': lambda self, *args: stream})()
    result = cli.copy_export(client, {'id': 'test', 'sha256': hashlib.sha256(data).hexdigest()}, tmp_path)
    folder = tmp_path/'voice-export-test'
    assert (folder/'package.zip').read_bytes() == data
    assert (folder/'audio/line.txt').read_text() == 'retained audio metadata'
    assert stream.blocks > 1 and result['destination'] == str(folder)


@pytest.mark.parametrize('name', ['../outside.txt', 'package.zip'])
def test_regular_export_rejects_escaping_or_archive_overwrite_entries(tmp_path, name):
    data = package_bytes(name)
    client = Requests()
    client.http = type('HTTP', (), {'stream': lambda self, *args: Stream(data)})()
    with pytest.raises(ValueError, match='非法路径'):
        cli.copy_export(client, {'id': 'test', 'sha256': hashlib.sha256(data).hexdigest()}, tmp_path)
    assert not (tmp_path/'outside.txt').exists()
    assert (tmp_path/'voice-export-test/package.zip').read_bytes() == data
