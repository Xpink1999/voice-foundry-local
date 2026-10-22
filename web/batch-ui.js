/* Preview the exact bounded batch before creating persistent generation jobs. */
(() => {
  'use strict';
  const form = $('batch-form'), submit = form.querySelector('button[type="submit"]');
  const panel = document.createElement('section');
  panel.className = 'batch-preview';
  panel.innerHTML = `<h3>${tr('提交前核对')}</h3><span id="batch-summary" role="status"></span><div id="batch-roles"></div><ul id="batch-errors" class="reference-warnings"></ul><div id="batch-preview-rows"></div>`;
  submit.before(panel);
  $('batch-text').rows = 6;
  $('batch-text').before($('batch-summary'));
  const roles = Object.create(null);
  let prepared = null, timer;
  const messages = {
    json: 'JSON 无法解析，请使用 items 数组或对象数组。', limit: '批量配音最多 200 条，更多内容请使用长文配音。', large: '内容过长，请转到长文配音。',
    text: '台词不能为空。', length: '单条台词超过 60000 字符，请使用长文配音。', title: '名称最多 120 个字符。',
    candidates: '候选数量应为 1–5。', mode: '请选择有效的克隆模式。', seed: '随机种子应为 0–2147483647 的整数。',
    voice: '音色不存在或已归档，请重新选择。', project: '项目不存在，请重新选择。', scope: '项目专属音色不能用于其他项目。',
    hifi: '极致克隆需要参考音频及非空转写。', hifiStyle: '极致克隆不叠加风格描述，请移除 style。'
  };
  function preview() {
    prepared = VoiceWorkflow.parseBatch($('batch-text').value, {voices: state.voices, references: state.references, projects: state.projects, roles,
      defaults: {voice_id: $('batch-voice').value || null, project_id: $('batch-project').value || null, candidates: Number($('batch-candidates').value), clone_mode: $('batch-clone-mode').value}});
    $('batch-summary').textContent = prepared.items.length ? tr('{0} 条台词 · {1} 个候选音频', [prepared.items.length, prepared.totalCandidates]) : tr('输入或导入台词后，在这里核对人物和内容。');
    const mappings = (prepared.roles || []).filter(role => roles[role] || state.voices.filter(voice => voice.name === role || voice.id === role).length !== 1);
    const unresolvedKey = JSON.stringify([mappings, state.voices.map(voice => [voice.id, voice.name]), roles]);
    if (panel.dataset.roles !== unresolvedKey) {
      panel.dataset.roles = unresolvedKey;
      $('batch-roles').innerHTML = mappings.map(role => `<label>${e(tr('为“{0}”选择音色', [role]))}<select data-batch-role="${e(role)}"><option value="">${tr('请选择人物音色')}</option>${state.voices.filter(v => v.status !== 'archived').map(v => `<option value="${e(v.id)}" ${roles[role] === v.id ? 'selected' : ''}>${e(v.name)}</option>`).join('')}</select></label>`).join('');
    }
    $('batch-errors').innerHTML = prepared.errors.filter(error => error.code !== 'role').slice(0, 12).map(error => {
      const message = error.code === 'field' ? tr('未知字段：{0}', [error.field]) : error.code === 'type' ? tr('字段格式不正确：{0}', [error.field]) : tr(messages[error.code] || '请检查台词配置。');
      return `<li>${e(error.row ? tr('第 {0} 条：{1}', [error.row, message]) : message)}</li>`;
    }).join('');
    const rows = prepared.items.slice(0, 12);
    $('batch-preview-rows').innerHTML = rows.length ? `<div class="table-scroll"><table><thead><tr><th>${tr('名称')}</th><th>${tr('人物音色')}</th><th>${tr('配音内容')}</th></tr></thead><tbody>${rows.map((row, index) => `<tr><td>${e(row.title || tr('台词 {0}', [index + 1]))}</td><td>${e(state.voices.find(v => v.id === row.voice_id)?.name || tr('自动声音'))}</td><td>${e(String(row.text || '').slice(0, 100))}${String(row.text || '').length > 100 ? '…' : ''}</td></tr>`).join('')}</tbody></table></div>${prepared.items.length > rows.length ? `<p class="hint">${tr('预览前 {0} 条；提交时包含全部 {1} 条。', [rows.length, prepared.items.length])}</p>` : ''}` : '';
    submit.disabled = !!form.dataset.pending || !prepared.items.length || !!prepared.errors.length;
    return prepared;
  }
  form.addEventListener('input', event => {if (event.target.matches('[data-batch-role]')) return; clearTimeout(timer); timer = setTimeout(preview, 180);});
  form.addEventListener('change', event => {
    if (event.target.dataset.batchRole) roles[event.target.dataset.batchRole] = event.target.value;
    preview();
  });
  form.addEventListener('workflow-form-settled', preview);
  window.addEventListener('voice-data-ready', preview);
  $('batch-file').onchange = async () => {
    delete form.dataset.uploaded;
    try {
      const file = $('batch-file').files[0]; if (!file) return;
      if (file.size > 4 * 1024 * 1024) {
        if (file.name.toLowerCase().endsWith('.json')) throw Error(tr(messages.limit));
        return window.workflowUI.offerLongform(file);
      }
      const text = VoiceWorkflow.decodeText(await file.arrayBuffer());
      if (text.length > 1000000) return window.workflowUI.offerLongform(file);
      state.batchJSON = null; $('batch-text').value = text; $('batch-text').dispatchEvent(new Event('input', {bubbles: true})); preview();
      form.dataset.uploaded = 'true';
    } catch (error) {toast(error.message, true);}
  };
  form.onsubmit = busy(form, async () => {
    const result = preview();
    if (!result.items.length || result.errors.length) throw Error(tr('请先修正预览中标出的台词配置。'));
    const items = result.items.map((item, index) => ({...item, title: item.title || tr('台词 {0}', [index + 1])}));
    const batch = await api('/batches', {method: 'POST', body: {items}});
    $('batch-feedback').hidden = false;
    $('batch-feedback').textContent = tr('已提交 {0} 个任务\n批次 ID: {1}', [batch.jobs.length, batch.batch_id]);
    await refresh(true);
    window.workflowUI.batchSubmitted(batch);
  });
  window.batchUI = {preview, roles: () => ({...roles}), restoreRoles: value => {
    for (const key of Object.keys(roles)) delete roles[key];
    if (value && typeof value === 'object') for (const [key, id] of Object.entries(value)) if (typeof id === 'string') roles[key] = id;
    preview();
  }};
  preview();
})();
