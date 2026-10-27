/* Shared workflow rules. No audio, approvals, credentials or network state are persisted here. */
(() => {
  'use strict';
  const eligibleVoice = (voice, project) => voice && voice.status !== 'archived' && !voice.deleted_at && (!voice.project_id || voice.project_id === project);
  const roleKey = (project, role) => 'scope:' + JSON.stringify([project || '', role]);
  function modelBlockers(items, models = [], voices = []) {
    const fallback = models.find(model => model.is_default) || models[0], blocked = new Map();
    for (const item of items) {
      const engine = item.engine || voices.find(voice => voice.id === item.voice_id)?.engine || fallback?.id;
      const voice=voices.find(voice=>voice.id===item.voice_id);
      if(item.engine&&voice?.engine&&item.engine!==voice.engine){blocked.set(engine,{engine,reason:'音色与引擎不匹配；请选择同一引擎或建立新音色'});continue;}
      const model = models.find(model => model.id === engine);
      if (!model || model.readiness?.available === false) blocked.set(engine || '', {engine, reason:model?.readiness?.reason || '语音引擎不可用，请检查模型设置。'});
    }
    return [...blocked.values()];
  }
  function parseBatch(text, options = {}) {
    const {voices = [], references = [], projects = [], defaults = {}, roles = {}} = options;
    const errors = [], unresolved = new Set(), roleNames = new Set(), bindings = new Map();
    const input = String(text || '').trim();
    let rows = [];
    if (!input) return {items: [], errors: [], unresolved: [], totalCandidates: 0};
    if (input.length > 1000000) return {items: [], errors: [{code: 'large'}], unresolved: [], totalCandidates: 0};
    try {
      if (/^[{[]/.test(input)) {
        const value = JSON.parse(input);
        rows = Array.isArray(value) ? value : value.items;
        if (!Array.isArray(rows)) throw Error('items');
      } else {
        rows = input.split(/\r?\n/).filter(line => line.trim()).map(line => {
          const parts = line.split('|');
          return parts.length >= 3 ? {title: parts[0].trim(), role: parts[1].trim(), text: parts.slice(2).join('|').trim()} : {text: line.trim()};
        });
      }
    } catch {
      return {items: [], errors: [{code: 'json'}], unresolved: [], totalCandidates: 0};
    }
    if (rows.length > 200) errors.push({code: 'limit', count: rows.length});
    const known = new Set(['text','title','project_id','voice_id','reference_id','clone_mode','engine','style','language','seed','candidates','streaming','engine_options','max_retries','role']);
    const items = rows.slice(0, 200).map((row, index) => {
      const fail = (code, extra = {}) => errors.push({code, row: index + 1, ...extra});
      if (!row || typeof row !== 'object' || Array.isArray(row)) {fail('text'); return {text: ''};}
      const item = {...defaults, ...row};
      for (const key of Object.keys(row)) if (!known.has(key)) fail('field', {field: key});
      for (const key of ['style','language','engine','reference_id','voice_id','project_id','role']) if (item[key] != null && typeof item[key] !== 'string') fail('type', {field: key});
      if (typeof item.role === 'string' && item.role) {
        roleNames.add(item.role);
        const key = roleKey(item.project_id, item.role), available = voices.filter(v => eligibleVoice(v, item.project_id));
        const matches = available.filter(v => v.id === item.role || v.name === item.role);
        const assigned = roles[key] || roles[item.role], explicit = typeof assigned === 'string' && !!assigned;
        const chosen = explicit ? available.find(v => v.id === assigned) : matches.length === 1 ? matches[0] : null;
        bindings.set(key, {key, role:item.role, project_id:item.project_id || null, voice_id:chosen?.id || '', resolved:!!chosen, explicit});
        if (chosen) item.voice_id = chosen.id;
        else {item.voice_id = null; unresolved.add(item.role); fail('role', {role: item.role, key});}
      }
      delete item.role;
      // A shared scene reference belongs to the default voice. Explicit per-row
      // references/engines remain authoritative when casting another character.
      if (item.voice_id !== defaults.voice_id) {
        if (!Object.hasOwn(row,'reference_id')) item.reference_id = null;
        if (!Object.hasOwn(row,'engine')) item.engine = null;
      }
      item.title = item.title || '';
      item.candidates = Number(item.candidates ?? 1);
      item.clone_mode = item.clone_mode || 'reference';
      if (typeof item.text !== 'string' || !item.text.trim()) fail('text');
      else if (item.text.length > 60000) fail('length');
      if (typeof item.title !== 'string' || item.title.length > 120) fail('title');
      if (!Number.isInteger(item.candidates) || item.candidates < 1 || item.candidates > 5) fail('candidates');
      if (!['reference', 'hifi'].includes(item.clone_mode)) fail('mode');
      if (item.seed != null && (!Number.isInteger(item.seed) || item.seed < 0 || item.seed > 2147483647)) fail('seed');
      if (item.project_id && !projects.some(p => p.id === item.project_id)) fail('project');
      const voice = voices.find(v => v.id === item.voice_id);
      if (item.voice_id && (!voice || voice.status === 'archived')) fail('voice');
      if (voice?.project_id && voice.project_id !== item.project_id) fail('scope');
      if (item.clone_mode === 'hifi') {
        const reference = references.find(r => r.id === (item.reference_id || voice?.reference_id));
        if (!reference?.transcript?.text) fail('hifi');
        if (typeof item.style === 'string' && item.style.trim()) fail('hifiStyle');
      }
      return item;
    });
    return {items, errors, unresolved: [...unresolved], roles: [...roleNames], roleBindings:[...bindings.values()], totalCandidates: items.reduce((sum, row) => sum + (Number.isFinite(row.candidates) ? row.candidates : 0), 0)};
  }
  function selectionSummary(results, selected, visible) {
    const ids = new Set(selected), shown = new Set(visible);
    const items = results.filter(item => ids.has(item.id));
    return {items, approved: items.filter(r => r.review === 'approved').length, hidden: items.filter(r => !shown.has(r.id)).length};
  }
  function decodeRoute(hash) {
    try {
      const [page = 'studio', item, chapter, book] = String(hash || '').replace(/^#\/?/, '').split('/').map(decodeURIComponent);
      if (!['studio','voices','projects','batch','tasks','review','exports','settings','longform','assets'].includes(page)) return {page: 'studio'};
      if (page === 'voices') return {page, pane: ['quick','library','references','design','processing'].includes(item) ? item : 'quick', id: chapter || null};
      if (page === 'longform') return {page, id: item || null, chapter: /^[1-9]\d*$/.test(chapter || '') && Number.isSafeInteger(Number(chapter)) ? Number(chapter) : null};
      if (page === 'assets') return {page, kind: item || 'results', trash: chapter === 'trash', book: book || ''};
      if(page==='review'&&item==='selection')return {page,selection:true};
      if(['tasks','review'].includes(page)&&item==='batch')return {page,batch:chapter||null};
      return {page, id: ['tasks','review'].includes(page) ? item || null : null};
    } catch {return {page: 'studio'};}
  }
  function decodeText(bytes) {
    const data = new Uint8Array(bytes);
    if (data[0] === 255 && data[1] === 254) return new TextDecoder('utf-16le', {fatal: true}).decode(data);
    if (data[0] === 254 && data[1] === 255) return new TextDecoder('utf-16be', {fatal: true}).decode(data);
    try {return new TextDecoder('utf-8', {fatal: true}).decode(data);}
    catch {return new TextDecoder('gb18030', {fatal: true}).decode(data);}
  }
  const rules = {parseBatch, eligibleVoice, roleKey, modelBlockers, selectionSummary, decodeRoute, decodeText};
  if (typeof module !== 'undefined' && module.exports) module.exports = rules;
  else window.VoiceWorkflow = rules;
})();
