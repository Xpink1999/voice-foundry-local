/* Find an export by its contents and return to its surviving source candidates. */
(() => {
  'use strict';
  const list = $('export-list');
  if (!list) return;
  const form=$('export-form');let setup;
  if(form){setup=document.createElement('details');setup.id='export-package-settings';setup.className='panel export-setup';const summary=document.createElement('summary');summary.textContent=tr('新建导出包');const panel=form.closest('.panel');if(panel)panel.replaceWith(setup);else form.before(setup);setup.append(summary,form);}
  const tools = document.createElement('div');
  tools.className = 'toolbar';
  const label = document.createElement('label');
  const caption = document.createElement('span');
  caption.textContent = tr('搜索导出记录');
  const search = document.createElement('input');
  search.id = 'export-history-search'; search.type = 'search';
  search.placeholder = tr('项目、标题或包内文件名');
  label.append(caption, search);
  const clear = document.createElement('button');
  clear.type = 'button'; clear.className = 'text-link';
  clear.textContent = tr('清除搜索'); clear.hidden = true;
  const count = document.createElement('span');
  count.className = 'hint'; count.setAttribute('role', 'status');
  tools.append(label, clear, count); list.before(tools);
  let query = '', dataSignature = '', initialized = false;
  const expanded = new Set();
  const availableResults = () => new Map(state.results.filter(result => !result.deleted_at).map(result => [result.id, result]));
  function describe(item, results) {
    // Export manifests contain entries, not result IDs or full result snapshots.
    const entries = (item.results || []).map(entry => ({...entry, source: results.get(entry.result_id)}));
    const ids = [...new Set(entries.filter(entry => entry.source).map(entry => entry.result_id))];
    const titles = entries.map(entry => entry.source?.title || String(entry.file || '').replace(/\\/g, '/').split('/').pop() || tr('原结果不可用'));
    const projects = [...new Set(entries.filter(entry => entry.source).map(({source}) => {
      if (!source.project_id) return tr('独立创作');
      return state.projects.find(project => project.id === source.project_id && !project.deleted_at)?.name || tr('原项目不可用');
    }))];
    const title = titles[0] ? titles[0] + (entries.length > 1 ? ' · ' + tr('等 {0} 条音频', [entries.length]) : '') : tr('导出记录');
    const format = String(item.options?.format || '').toUpperCase();
    const status = tr(item.options?.draft ? '草稿' : '正式资产');
    return {item, entries, ids, title, projects, format, status,
      searchText: [titles.join(' '), projects.join(' '), entries.map(entry => entry.file).join(' '), format, status, item.options?.adapter, date(item.created_at)].join(' ').toLocaleLowerCase()};
  }
  function signature() {
    return JSON.stringify([state.exports, state.results.map(result => [result.id, result.title, result.project_id, result.deleted_at]), state.projects.map(project => [project.id, project.name, project.deleted_at])]);
  }
  renderExports = function () {
    if(setup&&state.ready&&!initialized){initialized=true;setup.open=!state.exports.length&&!!state.selected.size;}
    for (const details of list.querySelectorAll('details[data-export-contents]')) {
      if (details.open) expanded.add(details.dataset.exportContents); else expanded.delete(details.dataset.exportContents);
    }
    const results = availableResults();
    const records = state.exports.filter(item => !item.deleted_at).map(item => describe(item, results));
    const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    const filtered = records.filter(record => terms.every(term => record.searchText.includes(term)));
    const byId = new Map(filtered.map(record => [record.item.id, record]));
    const items = filtered.map(record => record.item);
    const visible = window.libraryPaging?.slice('exports', items, terms.join(' ')) || items;
    const renderSignature=JSON.stringify([signature(),query,visible.map(item=>item.id)]);
    if(list.dataset.renderSignature===renderSignature){dataSignature=signature();return;}
    list.dataset.renderSignature=renderSignature;
    count.textContent = tr('{0} 条导出记录', [filtered.length]); clear.hidden = !query;
    list.innerHTML = visible.map(item => {
      const record = byId.get(item.id), unavailable = record.entries.filter(entry => !entry.source).length;
      const entries = record.entries.map(entry => `<li><b>${e(entry.source?.title || tr('原结果不可用'))}</b><p class="hint">${e(tr('文件：{0}', [entry.file || '']))}</p><p class="hint">${e(tr('打包时：{0}', [labels[entry.review] || entry.review || tr('未知')]))}${entry.source ? '' : ' · ' + e(tr('原结果不可用，无法回看。'))}</p></li>`).join('');
      return `<div class="job-row" data-export-package="${e(item.id)}"><div class="job-main"><b>${e(record.title)}</b><p>${e(record.projects.join(' · ') || tr('原结果不可用'))} · ${e(tr('{0} 个结果 · {1} · {2}', [record.entries.length, record.format, record.status]))}</p><p class="hint">${e(tr('{0} · {1} · 包含元数据与来源清单', [date(item.created_at), item.options?.adapter || '']))}</p><details data-export-contents="${e(item.id)}" ${expanded.has(item.id) ? 'open' : ''}><summary>${e(tr('查看包内清单（{0} 条）', [record.entries.length]))}</summary><ul>${entries}</ul></details><div class="actions"><button type="button" class="text-link" data-export-return="${e(item.id)}" ${record.ids.length ? '' : 'disabled'}>${e(tr('返回这些候选'))}</button>${unavailable ? `<span class="hint">${e(tr('{0} 条原结果不可回看', [unavailable]))}</span>` : ''}</div></div><a class="text-link" href="/api/v1/exports/${encodeURIComponent(item.id)}/download" download>${e(tr('下载 ZIP ↓'))}</a></div>`;
    }).join('') || empty(tr(terms.length ? '没有匹配的导出记录' : '还没有导出记录'), tr(terms.length ? '清除搜索，或换一个项目、标题或文件名。' : '选择审核结果后导出。'));
    dataSignature = signature();
  };
  search.addEventListener('input', () => {query = search.value; renderExports();});
  clear.onclick = () => {search.value = query = ''; renderExports(); search.focus();};
  list.addEventListener('click', event => {
    const button = event.target.closest('[data-export-return]');
    if (!button) return;
    const item = state.exports.find(record => record.id === button.dataset.exportReturn && !record.deleted_at);
    const ids = item ? describe(item, availableResults()).ids : [];
    if (!ids.length) {renderExports(); toast(tr('原结果不可用，无法回看。'), true); return;}
    openReviewScope({ids});
  });
  window.addEventListener('voice-data-ready', () => {if (dataSignature !== signature()) renderExports();});
  renderExports();
})();
