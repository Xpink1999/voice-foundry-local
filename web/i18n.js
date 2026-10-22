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
  function serviceMessage(value) {
    const text = String(value ?? '');
    // A small explicit bridge for numeric legacy service messages, not user content.
    for (const [pattern, key] of [[/^声线 (\d+)$/, '声线 {0}'], [/^已合成 (\d+) 章$/, '已合成 {0} 章']]) {
      const match = text.match(pattern);
      if (match) return translate(key, [match[1]]);
    }
    return translate(text);
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
      fields[input.id] = input.value;
    });
    return {
      fields,
      page: document.querySelector('.page.active')?.id.replace(/^page-/, '') || 'studio',
      pane: document.querySelector('[data-voice-pane][aria-selected="true"]')?.dataset.voicePane,
      selected: typeof state !== 'undefined' ? [...state.selected] : [],
      savedAt: Date.now()
    };
  }
  function changeLanguage(mode) {
    if (!['system', ...supported].includes(mode)) return;
    const next = mode === 'system' ? detect() : mode;
    const hasFiles = [...document.querySelectorAll('input[type="file"]')].some(input => input.files?.length);
    if (next !== locale && hasFiles && !window.confirm(translate('切换语言会刷新界面。未提交的文本会保留，但文件需要重新选择。继续吗？'))) {
      document.getElementById('ui-language').value = preference;
      return;
    }
    let stored = false;
    try { localStorage.setItem(preferenceKey, mode); stored = true; } catch { /* Use URL fallback. */ }
    if (next === locale) { preference = mode; return; }
    try { sessionStorage.setItem(draftKey, JSON.stringify(captureDraft())); } catch { /* Browser storage may be disabled. */ }
    const url = new URL(location.href);
    if (stored) url.searchParams.delete('ui_lang');
    else url.searchParams.set('ui_lang', next);
    location.assign(url.href);
  }
  let draft;
  try {
    draft = JSON.parse(sessionStorage.getItem(draftKey));
    sessionStorage.removeItem(draftKey);
    if (!draft || Date.now() - draft.savedAt > 10 * 60 * 1000) draft = null;
  } catch { draft = null; }
  function restoreDraft() {
    if (!draft) return;
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
      if (field && field.tagName !== 'SELECT' && !['file', 'password', 'checkbox', 'radio', 'hidden'].includes(field.type)) field.value = value;
    }
    if (typeof state !== 'undefined') {
      state.selected = new Set(draft.selected.filter(id => state.results.some(result => result.id === id)));
      updateSelection();
    }
    document.querySelector(`[data-page="${draft.page}"]`)?.click();
    if (draft.page === 'voices' && ['quick', 'library', 'design', 'processing'].includes(draft.pane))
      document.querySelector(`[data-voice-pane="${draft.pane}"]`)?.click();
    document.getElementById('gen-text')?.dispatchEvent(new Event('input'));
    draft = null;
  }
  window.VoiceI18n = {translate, message: serviceMessage, locale, normalize, detect, changeLanguage, applyStatic, escape, captureDraft};
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
