/* Navigation, safe same-tab drafts and handoffs between existing workspaces. */
(() => {
  'use strict';
  const draftKey = 'voice-foundry-work-draft', maxDraftBytes = 400000;
  const fields = ['gen-title','gen-text','gen-style','gen-seed','gen-project','gen-voice','gen-language','gen-candidates','gen-reference','gen-clone-mode',
    'batch-text','batch-project','batch-voice','batch-candidates','batch-clone-mode','batch-reference','batch-engine','batch-language','batch-style','batch-seed','design-description','design-text','design-count','design-engine',
    'lf-title','lf-project','lf-voice','lf-style','lf-encoding','lf-clone-mode','lf-reference','lf-engine','lf-language','lf-seed',
    'review-project','review-status','review-search','voice-search','voice-scope','task-project','task-status','task-archive-view'];
  const defaults = Object.fromEntries(fields.map(id => [id, $(id)?.value || '']));
  let ready = false, applying = false, restoring = false, savedDraft = null, saveTimer, routeTimer, draftWarning = false, routeWritePending = false;
  const banner = document.createElement('div'); banner.className = 'workflow-notice'; banner.hidden = true; banner.id = 'workflow-notice'; banner.setAttribute('role', 'status');
  document.querySelector('.content').prepend(banner);
  function notice(message, actions = []) {
    banner.replaceChildren(); const text = document.createElement('span'); text.textContent = message; banner.append(text);
    for (const action of actions) {const button = document.createElement('button'); button.type = 'button'; button.className = 'text-link'; button.textContent = action.label; button.onclick = action.run; banner.append(button);}
    const close = document.createElement('button'); close.type = 'button'; close.className = 'text-link'; close.textContent = tr('关闭'); close.onclick = () => {banner.hidden = true;}; banner.append(close); banner.hidden = false;
  }
  function saveDraft() {
    if (!ready || restoring) return;
    try {
      const values = Object.fromEntries(fields.filter(id => $(id) && !window.VoiceI18n.isSystemDefault($(id),$(id).value)).map(id => [id, $(id).value]));
      const json = JSON.stringify({at: Date.now(), values, selection: [...state.selected], batchRoles: window.batchUI?.roles()});
      if (json.length > maxDraftBytes) throw Error('quota');
      sessionStorage.setItem(draftKey, json);
      draftWarning = false;
    } catch {if (!draftWarning) notice(tr('草稿暂未保存，请先复制重要文本。')); draftWarning = true;}
  }
  function restoreDraft() {
    if (!savedDraft) return;
    const restoredText = ['gen-title','gen-text','gen-style','batch-text','design-description','lf-title','lf-style'].some(id => savedDraft.values[id]?.trim());
    const changed = Object.entries(savedDraft.values).some(([id,value]) => $(id) && String(value) !== String($(id).value));
    if (!changed && !savedDraft.selection?.length && !Object.keys(savedDraft.batchRoles || {}).length) {savedDraft = null; return;}
    restoring = true;
    // Project selectors must be restored before dependent voice/reference selectors.
    const ordered = [...fields.filter(id => id.endsWith('-project')), ...fields.filter(id => !id.endsWith('-project'))];
    for (const id of ordered) {
      const input = $(id), value = savedDraft.values[id];
      if (!input || typeof value !== 'string') continue;
      if(window.VoiceI18n.isSystemDefault(input,value))continue;
      if (input.tagName === 'SELECT' && ![...input.options].some(option => option.value === value)) continue;
      input.value = value;
      input.dispatchEvent(new Event(input.tagName === 'SELECT' ? 'change' : 'input', {bubbles: true}));
    }
    window.batchUI?.restoreRoles(savedDraft.batchRoles);
    if (Array.isArray(savedDraft.selection)) state.selected = new Set(savedDraft.selection.filter(id => state.results.some(result => result.id === id)));
    renderResults();
    restoring = false; savedDraft = null;
    if (!restoredText && !state.selected.size) return;
    notice(tr('已恢复本标签页的文本草稿。文件和试听确认需要重新选择。'), [{label: tr('清除草稿'), run: () => {
      for (const id of fields) {const input = $(id); if (!input) continue; input.value = defaults[id] || ''; input.dispatchEvent(new Event(input.tagName === 'SELECT' ? 'change' : 'input', {bubbles: true}));}
      clearTimeout(saveTimer); window.batchUI?.restoreRoles({}); state.selected.clear(); renderResults();
      try {sessionStorage.removeItem(draftKey);} catch {} banner.hidden = true;
    }}]);
  }
  try {const parsed = JSON.parse(sessionStorage.getItem(draftKey)); if (parsed && Date.now() - parsed.at < 24 * 3600000 && parsed.values && typeof parsed.values === 'object') savedDraft = parsed;} catch {}
  document.addEventListener('input', event => {if (!fields.includes(event.target.id)) return; clearTimeout(saveTimer); saveTimer = setTimeout(saveDraft, 300);});
  document.addEventListener('change', event => {if (fields.includes(event.target.id) || event.target.dataset.select || event.target.dataset.batchRole) saveDraft();});
  window.addEventListener('pagehide', saveDraft);
  window.addEventListener('beforeunload', event => {
    saveDraft();
    if (window.VoiceI18n.changingLanguage) return;
    if (document.querySelector('form[data-dirty]') || document.querySelector('[data-unsaved]') || [...document.querySelectorAll('input[type="file"]')].some(input => input.files?.length && !input.form?.dataset.uploaded)) {event.preventDefault(); event.returnValue = '';}
  });
  document.addEventListener('workflow-form-success', event => {event.target.dataset.uploaded = 'true'; if (event.target.id === 'settings-form'&&!event.target.dataset.changedWhilePending) {delete event.target.dataset.dirty; $('settings-unsaved').hidden = true;}});
  document.addEventListener('change', event => {if (event.target.type === 'file' && event.target.form) delete event.target.form.dataset.uploaded;});
  function route() {
    let path = state.page;
    if (path === 'voices') {const context = window.voiceWorkspace?.context(); path += '/' + (context?.pane || 'quick'); if (context?.id) path += '/' + encodeURIComponent(context.id);}
    else if (path === 'longform') {const context = window.longformUI?.context(); if (context?.book) {path += '/' + encodeURIComponent(context.book); if (context.chapter) path += '/' + context.chapter;}}
    else if(path==='tasks'){if(state.detailJob&&!$('job-detail').hidden)path+='/'+encodeURIComponent(state.detailJob);else if(window.jobArchiveUI?.context().batch)path+='/batch/'+encodeURIComponent(window.jobArchiveUI.context().batch);}
    else if(path==='review'&&state.reviewIds)path+='/selection';
    else if(path==='review'&&state.reviewBatch)path+='/batch/'+encodeURIComponent(state.reviewBatch);
    else if (path === 'review' && state.reviewJob) path += '/' + encodeURIComponent(state.reviewJob);
    else if (path === 'assets') {const context = window.assetUI.context(); path += '/' + context.kind + '/' + (context.deleted ? 'trash' : 'active'); if (context.book) path += '/' + encodeURIComponent(context.book);}
    return '#' + path;
  }
  function writeRoute() {
    if (!ready || applying || routeWritePending) return;
    routeWritePending = true;
    queueMicrotask(() => {routeWritePending = false; if (!ready || applying) return; const next = route(); if (location.hash !== next) history.pushState(null, '', next);});
  }
  async function applyRoute() {
    if (!ready || applying) return;
    applying = true;
    const requestedHash=location.hash;
    try {
      const target = VoiceWorkflow.decodeRoute(requestedHash);
      navigate(target.page);
      if (target.page === 'voices') {
        window.voiceWorkspace.showPane(target.pane);
        if (target.id && target.pane === 'quick') await window.voiceWorkspace.openRecording(target.id);
        if (target.id && target.pane === 'processing') await window.voiceWorkspace.openProcessing(target.id);
      }
      if (target.page === 'longform') {
        if (target.id) {await window.longformUI.openBook(target.id); if (target.chapter) await window.longformUI.openChapter(target.chapter);}
        else window.longformUI.library();
      }
      if(target.page==='tasks'){if(target.id)await showJob(target.id);else await window.jobArchiveUI.setBatch(target.batch||null);}
      if(target.page==='review')await openReviewScope({job:target.id||null,batch:target.batch||null,ids:target.selection?[...state.selected]:null});
      if (target.page === 'assets') await window.assetUI.restoreContext(target);
    } catch (error) {notice(tr('无法恢复该工作位置：{0}', [error.message]));}
    finally {applying=false;if(location.hash!==requestedHash)scheduleRoute();else history.replaceState(null,'',route());}
  }
  const scheduleRoute = () => {clearTimeout(routeTimer); routeTimer = setTimeout(applyRoute, 0);};
  window.addEventListener('popstate', scheduleRoute); window.addEventListener('hashchange', scheduleRoute);
  window.addEventListener('voice-context-change', writeRoute);
  window.addEventListener('voice-page-change', event => {
    document.querySelectorAll('audio').forEach(audio => {if (!audio.closest('.page.active')) audio.pause();});
    if (event.detail.page !== 'tasks') {state.live = false; state.audioContext?.suspend(); if ($('live-toggle')) $('live-toggle').textContent = tr('启用实时试听');}
    document.querySelectorAll('[data-page]').forEach(button => {if (button.dataset.page === event.detail.page) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');});
    const heading = document.querySelector('.page.active h1'); if (heading) {heading.tabIndex = -1; heading.focus({preventScroll: true});}
    writeRoute();
  });
  // One player at a time, including reference clips, comparisons and chapter audio.
  document.addEventListener('play', event => {
    if (event.target.tagName !== 'AUDIO') return;
    document.querySelectorAll('audio').forEach(audio => {if (audio !== event.target) audio.pause();});
    if (!event.target.dataset.audio) window.reviewPlayback?.stop();
  }, true);
  window.addEventListener('voice-data-ready', () => {
    if (!state.ready) return;
    if (!ready) {ready = true; restoreDraft(); applyRoute();}
    decorateProjects(); refreshExport();
  });
  function voiceSaved(voice) {
    notice(tr('“{0}”已保存，可直接开始配音。', [voice.name]), [{label: tr('使用此音色配音'), run: () => {
      $('gen-project').value = voice.project_id || ''; renderVoiceOptions(); $('gen-voice').value = voice.id; previewVoice(); navigate('studio'); $('gen-text').focus();
    }}, {label: tr('查看人物音色库'), run: () => {navigate('voices'); window.voiceWorkspace.showPane('library');}}]);
  }
  function decorateProjects() {
    $('project-list').querySelectorAll('[data-action="use-project"]').forEach(start => {
      const actions = start.parentElement; if (actions.querySelector('[data-action="project-batch"]')) return;
      for (const [action, label] of [['project-batch','批量配音'],['project-longform','长文配音']]) {const button = document.createElement('button'); button.className = 'text-link'; button.dataset.action = action; button.dataset.id = start.dataset.id; button.textContent = tr(label); actions.append(button);}
    });
  }
  function batchSubmitted(batch) {
    state.detailJob=null;state.detailToken=(state.detailToken||0)+1;state.eventSource?.close();state.eventSource=null;stopLiveAudio();$('job-detail').hidden=true;
    $('task-project').value = ''; $('task-status').value = ''; $('task-archive-view').value = 'current'; $('task-archive-view').dispatchEvent(new Event('change'));
    navigate('tasks');window.jobArchiveUI.setBatch(batch.batch_id);
    notice(tr('已提交 {0} 条台词，任务在后台继续。', [batch.jobs.length]), [{label: tr('返回批量台词'), run: () => navigate('batch')}]);
  }
  function productionContext(prefix='gen') {
    return {project:$(prefix+'-project').value,voice:$(prefix+'-voice').value,reference:$(prefix+'-reference').value,engine:$(prefix+'-engine').value,language:$(prefix+'-language').value,seed:$(prefix+'-seed').value,mode:$(prefix+'-clone-mode').value,style:$(prefix+'-clone-mode').value==='hifi'?'':$(prefix+'-style').value};
  }
  function offerLongform(file = null, source='gen') {
    const context=productionContext(source);
    const structured=source==='batch'&&window.batchUI.preview().roles?.length;
    notice(tr(structured?'长文作品使用一个默认人物。请先确认人物和参考；不会自动沿用多角色分配。':'这份内容更适合长文配音，可按章节生成、续作和审核。'), [{label: tr('转到长文导入'), run: () => {
      const accepted=window.longformUI.prepareImport({...context,file,title:source==='gen'?$('gen-title').value.slice(0,100):'',...(structured?{voice:'',reference:'',engine:'',mode:'reference',style:''}:{})});
      if(accepted){navigate('longform');if(file)document.querySelectorAll('input[type="file"]').forEach(input=>{if(input.id!=='lf-file'&&input.files?.[0]===file)input.value='';});notice(tr('已带入当前声音设置，请核对后导入。'));}
    }}]);
  }
  $('text-file').onchange = async () => {
    const file = $('text-file').files[0]; if (!file) return;
    if (file.size > 4 * 1024 * 1024) return offerLongform(file);
    try {const text = VoiceWorkflow.decodeText(await file.arrayBuffer()); if (text.length > 60000) return offerLongform(file); $('gen-text').value = text; $('gen-text').dispatchEvent(new Event('input', {bubbles: true})); $('text-file').form.dataset.uploaded = 'true';}
    catch (error) {notice(tr('文本编码无法识别，请在长文导入中选择编码。'), [{label: tr('转到长文导入'), run: () => {if(window.longformUI.prepareImport({...productionContext(),file}))navigate('longform');}}]);}
  };
  for (const [id, limit] of [['gen-text',60000], ['batch-text',1000000]]) $(id).addEventListener('paste', event => {
    const text = event.clipboardData?.getData('text/plain'); if (!text) return;
    const input = $(id), combined = input.value.slice(0, input.selectionStart) + text + input.value.slice(input.selectionEnd);
    if (combined.length > limit) {event.preventDefault(); offerLongform(new File([combined], 'narration.txt', {type: 'text/plain;charset=utf-8'}),id==='batch-text'?'batch':'gen');}
  });
  const shortcuts = document.createElement('div'); shortcuts.className = 'workflow-shortcuts';
  shortcuts.innerHTML = `<button type="button" data-workflow="reference" class="text-link">${tr('从录音创建音色')}</button><button type="button" data-workflow="batch" class="text-link">${tr('多条台词 → 批量配音')}</button><button type="button" data-workflow="longform" class="text-link">${tr('整本内容 → 长文配音')}</button>`;
  $('generate-form').before(shortcuts);
  shortcuts.addEventListener('click', event => {const action = event.target.dataset.workflow; if (action === 'reference') {navigate('voices'); window.voiceWorkspace.showPane('quick');} else if(action==='batch')window.batchUI.prepareImport({...productionContext(),text:$('gen-text').value,candidates:$('gen-candidates').value});else if(action==='longform'){const text=$('gen-text').value;if(window.longformUI.prepareImport({...productionContext(),file:text.trim()?new File([text],'narration.txt',{type:'text/plain;charset=utf-8'}):null,title:$('gen-title').value.slice(0,100)})){navigate('longform');notice(tr('已带入当前声音设置，请核对后导入。'));}}});
  const exportSummary = document.createElement('div'); exportSummary.id = 'export-selection'; exportSummary.className = 'selection-summary'; $('export-form').querySelector('.panel-title').after(exportSummary);
  const listPages = new Map();
  const listTargets = {voices: ['voice-list', renderVoices, 12], projects: ['project-list', renderProjects, 12], exports: ['export-list', renderExports, 20]};
  window.libraryPaging = {slice(kind, items, scope = '') {
    const [target, render, size] = listTargets[kind];
    const context = listPages.get(kind) || {page: 0, scope};
    if (context.scope !== scope) {context.page = 0; context.scope = scope;}
    const total = Math.max(1, Math.ceil(items.length / size)); context.page = Math.min(context.page, total - 1); listPages.set(kind, context);
    let controls = $(target + '-pager');
    if (!controls) {controls = document.createElement('div'); controls.id = target + '-pager'; controls.className = 'lf-pager'; $(target).after(controls);}
    controls.innerHTML = `<button type="button" class="secondary" data-list-prev ${context.page ? '' : 'disabled'}>${tr('上一页')}</button><span class="hint">${e(tr('第 {0} / {1} 页 · 共 {2} 条', [context.page + 1, total, items.length]))}</span><button type="button" class="secondary" data-list-next ${context.page + 1 < total ? '' : 'disabled'}>${tr('下一页')}</button>`;
    controls.querySelector('[data-list-prev]').onclick = () => {context.page--; render(); if (kind === 'projects') decorateProjects();};
    controls.querySelector('[data-list-next]').onclick = () => {context.page++; render(); if (kind === 'projects') decorateProjects();};
    return items.slice(context.page * size, context.page * size + size);
  }};
  let exportSummarySignature='';
  function refreshExport() {
    const items = state.results.filter(result => state.selected.has(result.id)), pending = items.filter(result => result.review !== 'approved').length;
    const summarySignature=JSON.stringify(items.map(item=>[item.id,item.review,item.title]));
    if(summarySignature!==exportSummarySignature){const wasOpen=exportSummary.querySelector('details')?.open;exportSummarySignature=summarySignature;exportSummary.innerHTML = `<p>${e(tr('已选 {0} 条 · 待审核 {1} 条', [items.length, pending]))}</p>${items.length ? `<details><summary>${tr('查看所选音频')}</summary><ul>${items.slice(0, 30).map(item => `<li>${e(item.title)} · ${e(labels[item.review])}</li>`).join('')}</ul></details>` : ''}<button type="button" class="text-link" id="export-back-review">${tr(items.length ? '返回试听与审核' : '选择要导出的音频')}</button>`;
    if(wasOpen&&exportSummary.querySelector('details'))exportSummary.querySelector('details').open=true;
    $('export-back-review').onclick = () => navigate('review');}
    const submit = $('export-form').querySelector('[type="submit"]'); submit.disabled = !!$('export-form').dataset.pending || !items.length || (!!pending && !$('export-draft').checked);
  }
  const priorSelection = updateSelection; updateSelection = function () {priorSelection(); refreshExport();};
  $('export-draft').addEventListener('change', refreshExport); $('export-form').addEventListener('workflow-form-settled', refreshExport);
  for (const [id, other] of [['export-trim','export-subtitles'], ['export-subtitles','export-trim']]) $(id).addEventListener('change', () => {if ($(id).checked && $(other).checked) {$(other).checked = false; notice(tr('静音裁剪与分段字幕不能同时使用，已关闭另一选项。'));}});
  const settingsHint = document.createElement('p'); settingsHint.id = 'settings-unsaved'; settingsHint.className = 'reference-warnings'; settingsHint.hidden = true; settingsHint.textContent = tr('设置已修改，尚未保存。'); $('settings-form').prepend(settingsHint);
  $('settings-form').addEventListener('input', () => {if(restoring || window.VoiceI18n.restoringDraft)return;$('settings-form').dataset.dirty = 'true'; settingsHint.hidden = false;});
  const discardSettings = document.createElement('button'); discardSettings.type = 'button'; discardSettings.className = 'text-link'; discardSettings.textContent = tr('放弃未保存的设置'); discardSettings.onclick = async () => {delete $('settings-form').dataset.dirty; settingsHint.hidden = true; await renderSettings();}; $('settings-form').querySelector('[type=submit]').after(discardSettings);
  $('voice-form').addEventListener('input', () => {if(!restoring && !window.VoiceI18n.restoringDraft)$('voice-form').dataset.dirty = 'true';});
  $('voice-form').addEventListener('change', () => {if(!restoring && !window.VoiceI18n.restoringDraft)$('voice-form').dataset.dirty = 'true';});
  document.addEventListener('assets-changed', event => {if (event.detail?.deleted && event.detail.batch) notice(tr('所选资产已移入回收站，原文件保留。'), [{label: tr('撤销本次删除'), run: async () => {await window.assetUI.restoreBatch(event.detail.batch); banner.hidden = true;}}]);});
  for (const [id, label] of [['task-project','所属项目'],['task-status','任务状态'],['review-project','所属项目'],['review-status','审核状态'],['voice-scope','音色范围']]) $(id).setAttribute('aria-label', tr(label));
  window.workflowUI = {voiceSaved, batchSubmitted, offerLongform, notice, saveDraft};
  if (state.ready) {ready = true; restoreDraft(); applyRoute(); renderVoices(); renderProjects(); renderExports(); decorateProjects(); refreshExport();}
})();
