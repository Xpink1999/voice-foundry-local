const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.join(__dirname, '../web');

function page({languages = ['zh-CN'], saved, blocked = false, fields = [], files = [], confirm = true} = {}) {
  const handlers = {}, values = new Map(saved ? [['voice-foundry-language', saved]] : []);
  const session = new Map();
  const storage = map => ({
    getItem: key => {if (blocked) throw Error('blocked'); return map.get(key) ?? null;},
    setItem: (key, value) => {if (blocked) throw Error('blocked'); map.set(key, value);},
    removeItem: key => map.delete(key)
  });
  const location = {href: 'http://localhost:8961/', search: '', assign(url) {this.assigned = url;}};
  const document = {
    querySelectorAll: selector => selector.startsWith('input[id]') ? fields : selector === 'input[type="file"]' ? files : [],
    querySelector: () => null,
    getElementById: () => ({}),
    addEventListener(name, callback) {handlers[name] = callback;}
  };
  const window = {addEventListener(name, callback) {handlers[name] = callback;}, confirm: () => confirm};
  const context = vm.createContext({window, document, navigator: {languages}, location,
    localStorage: storage(values), sessionStorage: storage(session), URL, URLSearchParams, Event});
  vm.runInContext(fs.readFileSync(path.join(web, 'translations.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(web, 'i18n.js'), 'utf8'), context);
  return {i18n: window.VoiceI18n, values, session, location, handlers};
}

test('detects supported browser languages with a deterministic fallback', () => {
  assert.equal(page({languages: ['fr-FR', 'ko-KR']}).i18n.locale, 'ko');
  assert.equal(page({languages: ['ja-JP']}).i18n.locale, 'ja');
  assert.equal(page({languages: ['zh-TW']}).i18n.locale, 'zh-CN');
  assert.equal(page({languages: ['fr-FR']}).i18n.locale, 'en');
  assert.equal(page({saved: 'en'}).i18n.locale, 'en');
  assert.equal(page({saved: 'invalid'}).i18n.locale, 'zh-CN');
});

test('interpolation keeps user text intact and unknown messages readable', () => {
  const {i18n} = page({saved: 'en'});
  assert.equal(i18n.translate('第 {0} 段', ['测试原文']), 'Segment 测试原文');
  assert.equal(i18n.translate('user-authored text'), 'user-authored text');
  assert.equal(i18n.translate(undefined), '');
  assert.equal(i18n.translate('未找到 items 列表'), 'Missing items array');
  assert.equal(i18n.message('声线 12'), 'Voice group 12');
  assert.equal(i18n.message('已合成 3 章'), 'Combined 3 chapters');
  assert.equal(i18n.escape('<img src=x onerror=alert(1)>'), '&lt;img src=x onerror=alert(1)&gt;');
});

test('declining a language reload with selected files keeps the current preference', () => {
  const result = page({saved: 'en', files: [{files: [{name: 'reference.wav'}]}], confirm: false});
  result.i18n.changeLanguage('ko');
  assert.equal(result.values.get('voice-foundry-language'), 'en');
  assert.equal(result.location.assigned, undefined);
  assert.equal(result.session.size, 0);
});

test('language preference persists and drafts exclude tokens, files and approvals', () => {
  const fields = [
    {id: 'gen-text', type: 'textarea', value: '用户原文'},
    {id: 'auth-token', type: 'password', value: 'not-to-be-saved'},
    {id: 'reference-file', type: 'file', value: 'not-to-be-saved'},
    {id: 'review-listened', type: 'checkbox', value: 'on'}
  ];
  const result = page({fields});
  result.i18n.changeLanguage('ja');
  assert.equal(result.values.get('voice-foundry-language'), 'ja');
  const draft = JSON.parse(result.session.get('voice-foundry-language-draft'));
  assert.deepEqual(draft.fields, {'gen-text': '用户原文'});
  assert.equal(result.location.assigned, 'http://localhost:8961/');
});

test('storage restrictions retain usable language selection', () => {
  const result = page({blocked: true});
  result.i18n.changeLanguage('ko');
  assert.equal(result.location.assigned, 'http://localhost:8961/?ui_lang=ko');
});

test('all four catalogs have matching nonempty messages and placeholders', () => {
  const catalogs = Object.fromEntries(['zh-CN', 'en', 'ja', 'ko'].map(code =>
    [code, JSON.parse(fs.readFileSync(path.join(web, 'locales', code + '.json'), 'utf8'))]));
  const keys = Object.keys(catalogs['zh-CN']).sort();
  for (const [code, catalog] of Object.entries(catalogs)) {
    assert.deepEqual(Object.keys(catalog).sort(), keys, code);
    for (const [key, message] of Object.entries(catalog)) {
      assert.ok(message.trim(), `${code}: ${key}`);
      assert.deepEqual((message.match(/\{\d+\}/g) || []).sort(), (key.match(/\{\d+\}/g) || []).sort(), `${code}: ${key}`);
    }
  }
  for (const filename of fs.readdirSync(web).filter(name => name.endsWith('.js') && name !== 'translations.js')) {
    const source = fs.readFileSync(path.join(web, filename), 'utf8');
    for (const match of source.matchAll(/\btr\(("(?:[^"\\]|\\.)*")/g))
      assert.ok(Object.hasOwn(catalogs['zh-CN'], JSON.parse(match[1])), `${filename}: ${match[1]}`);
  }
});
