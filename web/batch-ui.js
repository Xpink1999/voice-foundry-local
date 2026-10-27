/* Preview the exact bounded batch before creating persistent generation jobs. */
(() => {
  'use strict';
  const form = $('batch-form'), submit = form.querySelector('button[type="submit"]');
  const panel = document.createElement('section');
  panel.className = 'batch-preview';
  panel.innerHTML = `<h3>${tr('提交前核对')}</h3><span id="batch-summary" role="status"></span><div id="batch-roles"></div><ul id="batch-errors" class="reference-warnings"></ul><div id="batch-preview-rows"></div>`;
  submit.before(panel);
  $('batch-text').rows = 6;
  for(const value of ['4','5']){const option=document.createElement('option');option.value=value;option.textContent=value;$('batch-candidates').append(option);}
  $('batch-text').before($('batch-summary'));
  const roles = Object.create(null);
  let prepared = null, timer;
  const extra=document.createElement('details');extra.className='batch-common-settings';extra.innerHTML=`<summary>${tr('参考与生成设置')}</summary><div class="form-row"><label>${tr('本次参考片段')}<select id="batch-reference"></select></label><label>${tr('语音模型')}<select id="batch-engine"></select></label></div><label>${tr('声音与演绎描述')}<textarea id="batch-style" rows="2" maxlength="1000"></textarea></label><div class="form-row"><label>${tr('语音语言')}<select id="batch-language">${$('gen-language').innerHTML}</select></label><label>${tr('随机种子')}<input id="batch-seed" type="number" min="0" max="2147483647"></label></div>`;panel.before(extra);
  function defaults(){return {voice_id:$('batch-voice').value||null,project_id:$('batch-project').value||null,candidates:Number($('batch-candidates').value),clone_mode:$('batch-clone-mode').value,reference_id:$('batch-reference').value||null,engine:$('batch-engine').value||null,language:$('batch-language').value,style:$('batch-clone-mode').value==='hifi'?'':$('batch-style').value,...($('batch-seed').value!==''?{seed:Number($('batch-seed').value)}:{})};}
  const messages = {
    json: 'JSON 无法解析，请使用 items 数组或对象数组。', limit: '批量配音最多 200 条，更多内容请使用长文配音。', large: '内容过长，请转到长文配音。',
    text: '台词不能为空。', length: '单条台词超过 60000 字符，请使用长文配音。', title: '名称最多 120 个字符。',
    candidates: '候选数量应为 1–5。', mode: '请选择有效的克隆模式。', seed: '随机种子应为 0–2147483647 的整数。',
    voice: '音色不存在或已归档，请重新选择。', project: '项目不存在，请重新选择。', scope: '项目专属音色不能用于其他项目。',
    hifi: '极致克隆需要参考音频及非空转写。', hifiStyle: '极致克隆不叠加风格描述，请移除 style。'
  };
  function preview() {
    setOptions($('batch-reference'),state.references.filter(r=>r.saved!==false&&r.rights_confirmed),tr('自动使用人物默认参考'));setOptions($('batch-engine'),state.models.map(m=>({id:m.id,name:tr(m.label)})),tr('自动使用人物或默认引擎'));
    $('batch-style').disabled=$('batch-clone-mode').value==='hifi';
    prepared = VoiceWorkflow.parseBatch($('batch-text').value, {voices: state.voices, references: state.references, projects: state.projects, roles,
      defaults:defaults()});
    $('batch-summary').textContent = prepared.items.length ? tr('{0} 条台词 · {1} 个候选音频', [prepared.items.length, prepared.totalCandidates]) : tr('输入或导入台词后，在这里核对人物和内容。');
    const mappings = (prepared.roleBindings || []).filter(binding => !binding.resolved || binding.explicit);
    const unresolvedKey = JSON.stringify([mappings, state.voices, roles]);
    if (panel.dataset.roles !== unresolvedKey) {
      panel.dataset.roles = unresolvedKey;
      $('batch-roles').innerHTML = mappings.map(binding => `<label>${e(tr('为“{0}”选择音色', [binding.role]))} · ${e(projectName(binding.project_id))}<select data-batch-role="${e(binding.key)}"><option value="">${tr('请选择人物音色')}</option>${state.voices.filter(v => VoiceWorkflow.eligibleVoice(v,binding.project_id)).map(v => `<option value="${e(v.id)}" ${binding.voice_id === v.id ? 'selected' : ''}>${e(v.name)}</option>`).join('')}</select></label>`).join('');
    }
    $('batch-errors').innerHTML = prepared.errors.filter(error => error.code !== 'role').slice(0, 12).map(error => {
      const message = error.code === 'field' ? tr('未知字段：{0}', [error.field]) : error.code === 'type' ? tr('字段格式不正确：{0}', [error.field]) : tr(messages[error.code] || '请检查台词配置。');
      return `<li>${e(error.row ? tr('第 {0} 条：{1}', [error.row, message]) : message)}</li>`;
    }).join('');
    const rows = prepared.items.slice(0, 12);
    $('batch-preview-rows').innerHTML = rows.length ? `<div class="table-scroll"><table><thead><tr><th>${tr('名称')}</th><th>${tr('人物音色')}</th><th>${tr('配音内容')}</th></tr></thead><tbody>${rows.map((row, index) => `<tr><td>${e(row.title || tr('台词 {0}', [index + 1]))}</td><td>${e(state.voices.find(v => v.id === row.voice_id)?.name || tr(prepared.errors.some(error=>error.code==='role'&&error.row===index+1)?'待选择人物':'自动声音'))}</td><td>${e(String(row.text || '').slice(0, 100))}${String(row.text || '').length > 100 ? '…' : ''}</td></tr>`).join('')}</tbody></table></div>${prepared.items.length > rows.length ? `<p class="hint">${tr('预览前 {0} 条；提交时包含全部 {1} 条。', [rows.length, prepared.items.length])}</p>` : ''}` : '';
    const blockers = VoiceWorkflow.modelBlockers(prepared.items, state.models, state.voices);
    $('batch-errors').insertAdjacentHTML('beforeend', blockers.map(blocker=>`<li>${e(blocker.engine || '')} · ${e(uiMessage(blocker.reason))} <button type="button" class="text-link" data-batch-models>${tr('模型与系统')}</button></li>`).join(''));
    submit.disabled = !!form.dataset.pending || !prepared.items.length || !!prepared.errors.length || !!blockers.length;
    return prepared;
  }
  form.addEventListener('input', event => {if (event.target.matches('[data-batch-role]')) return; clearTimeout(timer); timer = setTimeout(preview, 180);});
  form.addEventListener('change', event => {
    if (event.target.dataset.batchRole) roles[event.target.dataset.batchRole] = event.target.value;
    preview();
  });
  form.addEventListener('workflow-form-settled', preview);
  panel.addEventListener('click', event=>{if(event.target.closest('[data-batch-models]'))navigate('settings');});
  window.addEventListener('voice-data-ready', preview);
  $('batch-file').onchange = async () => {
    delete form.dataset.uploaded;
    try {
      const file = $('batch-file').files[0]; if (!file) return;
      if (file.size > 4 * 1024 * 1024) {
        if (file.name.toLowerCase().endsWith('.json')) throw Error(tr(messages.limit));
        return window.workflowUI.offerLongform(file,'batch');
      }
      const text = VoiceWorkflow.decodeText(await file.arrayBuffer());
      if (text.length > 1000000) return window.workflowUI.offerLongform(file,'batch');
      $('batch-text').value = text; $('batch-text').dispatchEvent(new Event('input', {bubbles: true})); preview();
      form.dataset.uploaded = 'true';
    } catch (error) {toast(error.message, true);}
  };
  form.onsubmit = busy(form, async () => {
    const result = preview();
    if (!result.items.length || result.errors.length) throw Error(tr('请先修正预览中标出的台词配置。'));
    const blockers = VoiceWorkflow.modelBlockers(result.items, state.models, state.voices);
    if (blockers.length) throw Error(uiMessage(blockers[0].reason));
    const items = result.items.map((item, index) => ({...item, title: item.title || tr('台词 {0}', [index + 1])}));
    const batch = await api('/batches', {method: 'POST', body: {items}});
    $('batch-feedback').hidden = false;
    $('batch-feedback').textContent = tr('已提交 {0} 个任务\n批次 ID: {1}', [batch.jobs.length, batch.batch_id]);
    await refresh(true);
    window.workflowUI.batchSubmitted(batch);
  });
  function prepareImport(values){
    const apply=()=>{for(const key of Object.keys(roles))delete roles[key];$('batch-text').value=values.text||'';$('batch-project').value=values.project||'';renderVoiceOptions();for(const [id,key] of [['batch-voice','voice'],['batch-reference','reference'],['batch-engine','engine'],['batch-language','language'],['batch-style','style'],['batch-seed','seed'],['batch-clone-mode','mode'],['batch-candidates','candidates']])if(values[key]!==undefined)$(id).value=values[key]??'';extra.open=!!(values.reference||values.style||values.mode==='hifi');preview();navigate('batch');$('batch-text').dispatchEvent(new Event('input',{bubbles:true}));$('batch-text').focus();window.workflowUI.notice(tr('已带入当前台词和声音设置。'));
    };
    if($('batch-text').value.trim()&&$('batch-text').value!==values.text){window.workflowUI.notice(tr('批量配音中已有未提交草稿。请选择如何带入当前台词。'),[{label:tr('替换现有台词'),run:apply},{label:tr('保留现有草稿'),run:()=>navigate('batch')}]);return false;}
    apply();return true;
  }
  window.batchUI = {preview, prepareImport, defaults, roles: () => ({...roles}), restoreRoles: value => {
    for (const key of Object.keys(roles)) delete roles[key];
    if (value && typeof value === 'object') for (const [key, id] of Object.entries(value)) if (typeof id === 'string') roles[key] = id;
    preview();
  }};
  preview();
})();
