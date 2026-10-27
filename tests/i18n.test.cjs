const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.join(__dirname, '../web');

function page({languages = ['zh-CN'], saved, blocked = false, fields = [], files = [], confirm = true, forms = {}, initialDraft} = {}) {
  const handlers = {}, values = new Map(saved ? [['voice-foundry-language', saved]] : []);
  const session = new Map(initialDraft ? [['voice-foundry-language-draft', JSON.stringify(initialDraft)]] : []);
  const storage = map => ({
    getItem: key => {if (blocked) throw Error('blocked'); return map.get(key) ?? null;},
    setItem: (key, value) => {if (blocked) throw Error('blocked'); map.set(key, value);},
    removeItem: key => map.delete(key)
  });
  const location = {href: 'http://localhost:8961/', search: '', assign(url) {this.assigned = url;}, reload() {this.reloaded = true;}};
  const document = {
    querySelectorAll: selector => selector.startsWith('input[id]') ? fields : selector === 'input[type="file"]' ? files : [],
    querySelector: () => null,
    getElementById: id => forms[id] || fields.find(field => field.id === id) || (id === 'ui-language' ? {} : null),
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
  assert.equal(result.location.reloaded, true);
});

test('changing language from a hash workspace reloads instead of only navigating its fragment', () => {
  const result = page();
  result.location.href = 'http://localhost:8961/#review';
  result.i18n.changeLanguage('en');
  assert.equal(result.location.reloaded, true);
  assert.equal(result.location.assigned, undefined);
  assert.equal(result.values.get('voice-foundry-language'), 'en');
});

test('storage restrictions retain usable language selection', () => {
  const result = page({blocked: true});
  result.i18n.changeLanguage('ko');
  assert.equal(result.location.assigned, 'http://localhost:8961/?ui_lang=ko');
  assert.equal(result.i18n.changingLanguage, false);
});

test('language draft restoration does not turn unchanged forms into unsaved changes', () => {
  const voice = {dataset:{}}, settings = {dataset:{}};
  const field = {id:'voice-status',tagName:'SELECT',type:'select-one',value:'draft',options:[{value:'draft'}],dispatchEvent(){voice.dataset.dirty='true';}};
  const result = page({forms:{'voice-form':voice,'settings-form':settings},fields:[field],initialDraft:{fields:{'voice-status':'draft'},selected:[],page:'studio',savedAt:Date.now()}});
  result.handlers['voice-data-ready']();
  assert.equal(voice.dataset.dirty,undefined);
  assert.equal(settings.dataset.dirty,undefined);
  assert.equal(result.i18n.restoringDraft,false);
});

test('real unsaved form changes survive a language change', () => {
  const voice = {dataset:{}}, settings = {dataset:{}};
  const result = page({forms:{'voice-form':voice,'settings-form':settings},initialDraft:{fields:{},selected:[],page:'studio',dirtyForms:['voice-form'],savedAt:Date.now()}});
  result.handlers['voice-data-ready']();
  assert.equal(voice.dataset.dirty,'true');
  assert.equal(settings.dataset.dirty,undefined);
});

test('language changes rebuild system defaults and preserve authored Chinese text', () => {
  const fields = [
    {id:'reference-source',type:'text',value:'本机上传的参考录音'},
    {id:'reference-auth',type:'text',value:'授权书编号：甲字第 8 号'},
    {id:'design-text',type:'textarea',value:'这是一段用于试听音色的示例文本。'},
    {id:'project-kind',type:'text',dataset:{i18nValue:'通用'},value:'通用'},
    {id:'gen-text',type:'textarea',value:'保留这段中文台词'},
    {id:'voice-name',type:'text',value:'示例人物 A'}
  ];
  const result = page({fields});
  result.i18n.changeLanguage('en');
  const draft = JSON.parse(result.session.get('voice-foundry-language-draft'));
  assert.deepEqual(draft.fields, {'reference-auth':'授权书编号：甲字第 8 号','gen-text':'保留这段中文台词','voice-name':'示例人物 A'});
});

test('legacy drafts do not restore Chinese defaults into English, Japanese or Korean', () => {
  for (const saved of ['en','ja','ko']) {
    const fields = [
      {id:'reference-source',tagName:'INPUT',type:'text',value:''},
      {id:'reference-auth',tagName:'INPUT',type:'text',value:''},
      {id:'gen-text',tagName:'TEXTAREA',type:'textarea',value:'',dispatchEvent(){}}
    ];
    const result = page({saved,fields,initialDraft:{fields:{'reference-source':'本机上传的参考录音','reference-auth':'用户确认拥有此次语音参考用途所需授权','gen-text':'用户台词不变'},selected:[],page:'studio',savedAt:Date.now()}});
    result.handlers['voice-data-ready']();
    assert.equal(fields[0].value,result.i18n.translate('本机上传的参考录音'));
    assert.equal(fields[1].value,result.i18n.translate('用户确认拥有此次语音参考用途所需授权'));
    assert.equal(fields[2].value,'用户台词不变');
  }
});

test('service templates localize progress, errors and nested labels while preserving parameters', () => {
  const {i18n} = page({saved:'en'});
  assert.equal(i18n.message('转写并分析候选 2/8'),'Transcribing and analyzing candidate 2/8');
  assert.equal(i18n.message('正在执行 去背景音乐 · 1/2'),'Running Remove background music · 1/2');
  assert.equal(i18n.message('引擎参数 temperature 超出允许范围'),'Engine parameter temperature is outside the allowed range');
  assert.equal(i18n.message('参考仍被人物「林先生」使用，请先解除绑定或同时删除人物'),'Reference is used by “林先生”. Unlink it or delete the voice together');
  assert.equal(i18n.message('未知的原始诊断内容'),'未知的原始诊断内容');
  assert.equal(i18n.translate('本机上传的参考录音.wav'),'本机上传的参考录音.wav');
});

test('validation details use the selected language and retain numeric limits', () => {
  for (const saved of ['zh-CN','en','ja','ko']) {
    const {i18n} = page({saved});
    assert.equal(i18n.validationMessage({type:'string_too_long',ctx:{max_length:300}}),i18n.translate('最多允许 {0} 个字符',[300]));
    assert.equal(i18n.validationMessage({type:'missing'}),i18n.translate('必填项'));
    assert.equal(i18n.validationMessage({type:'value_error',msg:'Value error, 请先恢复原候选'}),i18n.translate('请先恢复原候选'));
  }
});

test('all four catalogs have matching nonempty messages and placeholders', () => {
  const catalogs = Object.fromEntries(['zh-CN', 'en', 'ja', 'ko'].map(code =>
    [code, JSON.parse(fs.readFileSync(path.join(web, 'locales', code + '.json'), 'utf8'))]));
  const keys = Object.keys(catalogs['zh-CN']).sort();
  for (const [code, catalog] of Object.entries(catalogs)) {
    assert.deepEqual(Object.keys(catalog).sort(), keys, code);
    for (const [key, message] of Object.entries(catalog)) {
      assert.ok(message.trim(), `${code}: ${key}`);
      if (['en','ko'].includes(code)) assert.ok(!/[\u3400-\u9fff]/.test(message), `${code}: untranslated Chinese in ${key}`);
      assert.deepEqual((message.match(/\{\d+\}/g) || []).sort(), (key.match(/\{\d+\}/g) || []).sort(), `${code}: ${key}`);
    }
  }
  for (const filename of fs.readdirSync(web).filter(name => name.endsWith('.js') && name !== 'translations.js')) {
    const source = fs.readFileSync(path.join(web, filename), 'utf8');
    for (const match of source.matchAll(/\btr\(("(?:[^"\\]|\\.)*")/g))
      assert.ok(Object.hasOwn(catalogs['zh-CN'], JSON.parse(match[1])), `${filename}: ${match[1]}`);
  }
});
