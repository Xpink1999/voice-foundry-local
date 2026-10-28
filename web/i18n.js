/* Interface language is independent of speech language and user-authored content. */
(() => {
  'use strict';
  const catalogs = window.voiceTranslations;
  const supported = ['zh-CN', 'en', 'ja', 'ko'];
  const preferenceKey = 'voice-foundry-language';
  const draftKey = 'voice-foundry-language-draft';
  function normalize(value) {
    const language = String(value || '').toLowerCase().split(/[-_]/)[0];
    return {zh: 'zh-CN', en: 'en', ja: 'ja', ko: 'ko'}[language] || null;
  }
  function detect(languages = navigator.languages || [navigator.language]) {
    return languages.map(normalize).find(Boolean) || 'en';
  }
  let preference = 'system';
  try {
    const saved = localStorage.getItem(preferenceKey);
    if (supported.includes(saved)) preference = saved;
  } catch { /* Language selection also works without local storage. */ }
  const query = new URLSearchParams(location.search).get('ui_lang');
  if (supported.includes(query)) preference = query;
  const locale = preference === 'system' ? detect() : preference;
  function translate(key, values = []) {
    if (key === null || key === undefined) return '';
    const message = catalogs[locale]?.[key] ?? catalogs['zh-CN']?.[key] ?? key;
    return String(message).replace(/\{(\d+)\}/g, (token, index) =>
      values[index] === undefined ? token : String(values[index]));
  }
  const serviceTemplates = Object.keys(catalogs['zh-CN']).filter(key => /[\u3400-\u9fff]/.test(key) && /\{\d+\}/.test(key)).map(key => {
    const slots = [], pieces = key.split(/(\{\d+\})/g);
    const pattern = pieces.map(piece => {
      const slot = piece.match(/^\{(\d+)\}$/);
      if (slot) { slots.push(Number(slot[1])); return '([\\s\\S]*?)'; }
      return piece.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }).join('');
    return {key, slots, pattern: new RegExp('^' + pattern + '$'), specificity: key.replace(/\{\d+\}/g, '').length};
  }).sort((a, b) => b.specificity - a.specificity);
  function serviceMessage(value, depth = 0) {
    const text = String(value ?? '');
    if (Object.hasOwn(catalogs['zh-CN'], text)) return translate(text);
    if (depth < 3 && text.includes(' → ')) return text.split(' → ').map(part => serviceMessage(part, depth + 1)).join(' → ');
    // Only service-owned messages use this bridge. Never pass names, scripts or transcripts here.
    if (depth < 3 && text.length < 10000 && /[\u3400-\u9fff]/.test(text)) {
      for (const template of serviceTemplates) {
        const match = text.match(template.pattern);
        if (!match) continue;
        const values = [];
        template.slots.forEach((slot, index) => { values[slot] = serviceMessage(match[index + 1], depth + 1); });
        return translate(template.key, values);
      }
    }
    return text;
  }
  const defaultFields = {
    'reference-source': '本机上传的参考录音',
    'reference-auth': '用户确认拥有此次语音参考用途所需授权',
    'design-text': '这是一段用于试听音色的示例文本。',
    'compare-text': '这是一段用于比较音色的示例文本。'
  };
  function defaultKey(field, value) {
    const key = field.dataset?.i18nValue || defaultFields[field.id];
    return key && supported.some(code => catalogs[code]?.[key] === value) ? key : null;
  }
  function validationMessage(item) {
    const ctx = item.ctx || {};
    const simple = {missing:'必填项',int_parsing:'需要整数',int_type:'需要整数',float_parsing:'需要数字',float_type:'需要数字',bool_parsing:'需要有效的布尔值',bool_type:'需要有效的布尔值',string_type:'需要文本',literal_error:'请选择有效选项',enum:'请选择有效选项',string_pattern_mismatch:'命名规则不匹配',list_type:'数据格式不正确',dict_type:'数据格式不正确'};
    if (simple[item.type]) return translate(simple[item.type]);
    const limits = {string_too_short:['至少需要 {0} 个字符','min_length'],string_too_long:['最多允许 {0} 个字符','max_length'],too_short:['至少需要 {0} 项','min_length'],too_long:['最多允许 {0} 项','max_length'],greater_than_equal:['数值至少为 {0}','ge'],less_than_equal:['数值最多为 {0}','le'],greater_than:['数值必须大于 {0}','gt'],less_than:['数值必须小于 {0}','lt']};
    if (limits[item.type] && ctx[limits[item.type][1]] !== undefined) return translate(limits[item.type][0], [ctx[limits[item.type][1]]]);
    return serviceMessage(String(item.msg || translate('请求失败')).replace(/^Value error, /, ''));
  }
  const escape = value => String(value ?? '').replace(/[&<>"']/g, character =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
  function applyStatic(root = document) {
    root.querySelectorAll('[data-i18n]').forEach(node => {
      node.textContent = translate(node.dataset.i18n);
    });
    for (const attribute of ['placeholder', 'aria-label', 'title', 'value', 'data-style', 'data-design-style']) {
      root.querySelectorAll(`[data-i18n-${attribute}]`).forEach(node => {
        const source = node.getAttribute('data-i18n-' + attribute);
        if (attribute === 'value') node.value = translate(source);
        else node.setAttribute(attribute, translate(source));
      });
    }
    document.documentElement.lang = locale;
  }
  function captureDraft() {
    const fields = {};
    document.querySelectorAll('input[id], textarea[id], select[id]').forEach(input => {
      // Listening confirmations are deliberately never restored as approval.
      if (['file', 'password', 'checkbox', 'radio', 'hidden'].includes(input.type) || input.id === 'ui-language') return;
      // Rebuild untouched system defaults in the destination language; keep authored text verbatim.
      if (!defaultKey(input, input.value)) fields[input.id] = input.value;
    });
    return {
      fields,
      page: document.querySelector('.page.active')?.id.replace(/^page-/, '') || 'studio',
      pane: document.querySelector('[data-voice-pane][aria-selected="true"]')?.dataset.voicePane,
      selected: typeof state !== 'undefined' ? [...state.selected] : [],
      editing: typeof state !== 'undefined' ? state.editing : null,
      voiceReferences: window.referenceUI ? {ids:window.referenceUI.selectedIDs(),scenes:window.referenceUI.scenarios()} : null,
      referenceEditing:window.referenceLibrary?.context?.()||null,
      dirtyForms: ['settings-form', 'voice-form','reference-metadata-form','reference-transcript-form'].filter(id => document.getElementById(id)?.dataset?.dirty),
      savedAt: Date.now()
    };
  }
  let changingLanguage = false, restoringDraft = false;
  function changeLanguage(mode) {
    if (!['system', ...supported].includes(mode)) return;
    const next = mode === 'system' ? detect() : mode;
    const hasFiles = [...document.querySelectorAll('input[type="file"]')].some(input => input.files?.length);
    const transient=document.querySelector('#reference-metadata-form[data-dirty],#reference-transcript-form[data-dirty],[data-unsaved]');
    if(next!==locale&&transient&&!window.confirm(translate('参考编辑尚未保存。请先保存，或确认放弃这些修改后切换语言。'))){document.getElementById('ui-language').value=preference;return;}
    if (next !== locale && hasFiles && !window.confirm(translate('切换语言会刷新界面。未提交的文本会保留，但文件需要重新选择。继续吗？'))) {
      document.getElementById('ui-language').value = preference;
      return;
    }
    let stored = false;
    try { localStorage.setItem(preferenceKey, mode); stored = true; } catch { /* Use URL fallback. */ }
    if (next === locale) { preference = mode; return; }
    try { sessionStorage.setItem(draftKey, JSON.stringify(captureDraft())); changingLanguage = true; } catch { /* Keep unsaved-change protection when a draft cannot be saved. */ }
    const url = new URL(location.href);
    if (stored) url.searchParams.delete('ui_lang');
    else url.searchParams.set('ui_lang', next);
    // Assigning the same URL with a workspace hash only performs a fragment navigation.
    // Rebuild the document so both static and dynamically created controls use the new locale.
    if (url.href === location.href) location.reload();
    else location.assign(url.href);
  }
  let draft;
  try {
    draft = JSON.parse(sessionStorage.getItem(draftKey));
    sessionStorage.removeItem(draftKey);
    if (!draft || Date.now() - draft.savedAt > 10 * 60 * 1000) draft = null;
  } catch { draft = null; }
  function restoreDraft() {
    if (!draft) return;
    restoringDraft = true;
    try {
    // Keep draft ownership: restoring an edit must never turn it into a new person.
    if(draft.editing&&typeof state!=='undefined'&&state.voices.some(v=>v.id===draft.editing)){
      state.editing=draft.editing;document.getElementById('voice-editor').hidden=false;
      document.getElementById('voice-editor-title').textContent=translate('编辑音色 · 保存将创建新版本');
    }
    if(draft.referenceEditing)window.referenceLibrary?.edit(draft.referenceEditing);
    // Run after data-backed selectors have been populated, then restore text last.
    for (const [id, value] of Object.entries(draft.fields)) {
      const field = document.getElementById(id);
      if (field?.tagName === 'SELECT' && [...field.options].some(option => option.value === value)) {
        field.value = value;
        field.dispatchEvent(new Event('change', {bubbles: true}));
      }
    }
    for (const [id, value] of Object.entries(draft.fields)) {
      const field = document.getElementById(id);
      if (field && field.tagName !== 'SELECT' && !['file', 'password', 'checkbox', 'radio', 'hidden'].includes(field.type)) field.value = defaultKey(field, value) ? translate(defaultKey(field, value)) : value;
    }
    if (typeof state !== 'undefined') {
      state.selected = new Set(draft.selected.filter(id => state.results.some(result => result.id === id)));
      updateSelection();
    }
    document.querySelector(`[data-page="${draft.page}"]`)?.click();
    if (draft.page === 'voices' && ['quick', 'library', 'references', 'design', 'processing'].includes(draft.pane))
      document.querySelector(`[data-voice-pane="${draft.pane}"]`)?.click();
    document.getElementById('gen-text')?.dispatchEvent(new Event('input'));
    for (const id of ['settings-form', 'voice-form','reference-metadata-form','reference-transcript-form']) {
      const form = document.getElementById(id);
      if (!form?.dataset) continue;
      if (draft.dirtyForms?.includes(id)) form.dataset.dirty = 'true';
      else delete form.dataset.dirty;
    }
    if(draft.voiceReferences&&window.referenceUI)window.referenceUI.refreshBindings({reference_ids:draft.voiceReferences.ids,reference_scenarios:draft.voiceReferences.scenes});
    if(draft.dirtyForms?.includes('reference-transcript-form')){const confirmed=document.getElementById('reference-detail-confirmed');if(confirmed)confirmed.checked=false;}
    const unsaved = document.getElementById('settings-unsaved');
    if (unsaved) unsaved.hidden = !document.getElementById('settings-form')?.dataset?.dirty;
    draft = null;
    } finally { restoringDraft = false; }
  }
  window.VoiceI18n = {translate, message: serviceMessage, validationMessage, locale, normalize, detect, changeLanguage, applyStatic, escape, captureDraft,
    isSystemDefault: (field,value) => !!defaultKey(field,value),
    get changingLanguage() {return changingLanguage;}, get restoringDraft() {return restoringDraft;}};
  window.tr = translate;
  window.uiMessage = serviceMessage;
  window.addEventListener('voice-data-ready', restoreDraft, {once: true});
  window.addEventListener('languagechange', () => { if (preference === 'system') changeLanguage('system'); });
  document.addEventListener('DOMContentLoaded', () => {
    applyStatic();
    const picker = document.getElementById('ui-language');
    picker.value = preference;
    picker.onchange = () => changeLanguage(picker.value);
  });
})();
