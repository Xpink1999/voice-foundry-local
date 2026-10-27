/* Keep selection, listening, review and export visible in the same workspace. */
(() => {
  'use strict';
  for(const [page,copy] of [['review','这里审核普通配音候选；长文章节请在作品内审核。'],['exports','这里打包普通配音候选；长文导出请在作品内创建。']]){
    const scope=document.createElement('p');scope.className='hint';scope.append(document.createTextNode(tr(copy)+' '));
    const open=document.createElement('button');open.type='button';open.className='text-link';open.textContent=tr('打开长文作品');open.onclick=()=>{navigate('longform');window.longformUI?.library();};scope.append(open);$('page-'+page).querySelector('.page-heading').after(scope);
  }
  let batchIds = null, exporting = false, approving = false, exportSignature = null;
  const dialog = $('review-dialog'), approval = $('review-confirm'), direct = document.createElement('button');
  direct.type = 'button'; direct.className = 'primary'; direct.id = 'review-approve-export'; direct.textContent = tr('批准并准备导出'); approval.after(direct);
  const message = document.createElement('p'); message.id = 'review-action-message'; message.className = 'reference-warnings'; message.setAttribute('role', 'alert'); dialog.querySelector('.dialog-actions').before(message);
  const bar = document.createElement('div'); bar.className = 'panel review-export-bridge';
  bar.innerHTML = `<div class="workspace-intro"><h2>${tr('审核与导出')}</h2></div><div id="review-scope" class="hint"></div><div class="toolbar"><button id="review-batch-approve" class="primary">${tr('审核所选')}</button><button id="review-export-now" class="primary">${tr('导出所选已审核音频')}</button><details class="review-more-actions"><summary>${tr('更多操作')}</summary><div><label>${tr('音频格式')}<select id="review-export-format"><option value="wav">WAV</option><option value="mp3">MP3</option><option value="flac">FLAC</option><option value="ogg">OGG</option></select></label><label class="checkbox"><input id="review-selected-only" type="checkbox">${tr('只看所选')}</label><button id="review-delete-selected" class="text-link">${tr('删除所选')}</button><button id="review-clear-selected" class="text-link">${tr('清空选择')}</button><button class="text-link" id="review-export-advanced">${tr('高级导出设置 ↗')}</button></div></details></div><div id="review-selection-summary" class="selection-summary" role="status"></div><div id="review-export-ready" role="status"></div>`;
  $('result-list').before(bar);
  let resultPage=0, filterSignature='', selectionSignature='';
  const pager=document.createElement('div');pager.className='lf-pager';pager.id='result-pagination';$('result-list').after(pager);
  function pageSlice(items){
    const signature=JSON.stringify([$('review-project').value,$('review-status').value,$('review-search').value,$('review-selected-only').checked,state.reviewJob,state.reviewBatch,state.reviewIds?[...state.reviewIds]:null]);
    if(signature!==filterSignature){filterSignature=signature;resultPage=0;}
    const totalPages=Math.max(1,Math.ceil(items.length/12));resultPage=Math.min(resultPage,totalPages-1);
    pager.innerHTML='<button type="button" class="secondary" id="result-prev" '+(!resultPage?'disabled':'')+'>'+tr("上一页")+'</button><span class="hint">'+tr("第 {0} / {1} 页 · 共 {2} 条",[resultPage+1,totalPages,items.length])+'</span><button type="button" class="secondary" id="result-next" '+(resultPage+1>=totalPages?'disabled':'')+'>'+tr("下一页")+'</button>';
    $('result-prev').onclick=()=>{resultPage--;renderResults();};$('result-next').onclick=()=>{resultPage++;renderResults();};
    return items.slice(resultPage*12,resultPage*12+12);
  }
  window.reviewPaging={slice:pageSlice,items:()=>pageSlice(filteredResults())};
  const originalFilter = filteredResults;
  filteredResults = function () {return originalFilter().filter(result => (!state.reviewBatch || state.reviewBatchJobs?.has(result.job_id)) && (!state.reviewIds || state.reviewIds.has(result.id)) && (!$('review-selected-only').checked || state.selected.has(result.id)));};
  const current = () => state.results.filter(result => state.selected.has(result.id)).map(result => result.id);
  function counts() {
    if (exportSignature && exportSignature !== JSON.stringify(current().sort())) {exportSignature = null; $('review-export-ready').replaceChildren();}
    const summary = VoiceWorkflow.selectionSummary(state.results, state.selected, pageSlice(filteredResults()).map(result => result.id));
    const nextSelectionSignature=JSON.stringify([summary.items.map(item=>[item.id,item.title,item.review]),summary.hidden]);
    if(nextSelectionSignature!==selectionSignature){const expanded=$('review-selection-summary').querySelector('details')?.open;selectionSignature=nextSelectionSignature;
    $('review-selection-summary').innerHTML = summary.items.length ? `<p>${e(tr('已选 {0} 条 · 已审核 {1} 条', [summary.items.length, summary.approved]))}${summary.hidden ? ' · '+e(tr('其中 {0} 条被当前筛选隐藏', [summary.hidden])) : ''}</p><details><summary>${tr('查看所选音频')}</summary><ul>${summary.items.slice(0, 30).map(item => `<li>${e(item.title)} · ${e(labels[item.review])}</li>`).join('')}</ul></details>` : `<p>${e(tr('选择音频后可批量试听、审核和导出。'))}</p>`;
    if(expanded&&$('review-selection-summary').querySelector('details'))$('review-selection-summary').querySelector('details').open=true;}
    $('review-export-now').hidden=!summary.items.length||summary.approved!==summary.items.length;
    $('review-batch-approve').hidden=!summary.items.length||summary.approved===summary.items.length;
    $('review-export-now').disabled = exporting || !summary.items.length || summary.approved !== summary.items.length;
    $('review-batch-approve').disabled = !summary.items.length || summary.approved === summary.items.length;
    $('review-delete-selected').disabled = !summary.items.length;
    $('review-clear-selected').disabled = !summary.items.length;
    $('compare-selected').disabled = !summary.items.length;
    $('review-selected-only').disabled = !summary.items.length && !$('review-selected-only').checked;
    $('review-scope').replaceChildren();
    if ($('review-project').value || $('review-status').value || $('review-search').value || $('review-selected-only').checked || state.reviewJob || state.reviewBatch || state.reviewIds) {
      const clearFilters=document.createElement('button');clearFilters.type='button';clearFilters.className='text-link';clearFilters.textContent=tr('清除筛选');clearFilters.onclick=()=>openReviewScope();$('review-scope').append(clearFilters);
    }
    if(state.reviewBatch||state.reviewIds){const range=document.createElement('span');range.textContent=tr(state.reviewBatch?'当前仅显示本批候选。':'当前仅显示此导出包的候选。');$('review-scope').append(range);}
    if (state.reviewJob) {
      const label = document.createElement('span'); label.textContent = tr('当前仅显示一个任务的候选。');
      const clear = document.createElement('button'); clear.type = 'button'; clear.className = 'text-link'; clear.textContent = tr('查看全部结果'); clear.onclick = () => {openReviewScope(); window.dispatchEvent(new Event('voice-context-change'));};
      $('review-scope').append(label, clear);
    }
    document.querySelectorAll('#result-list [data-action="approve"]').forEach(button => {button.disabled = state.results.find(result => result.id === button.dataset.id)?.review === 'approved';});
  }
  const priorSelection = updateSelection; updateSelection = function () {priorSelection(); counts();};
  function approvalButtons() {approval.disabled = direct.disabled = approving || !$('review-listened').checked;}
  $('review-listened').addEventListener('change', approvalButtons);
  async function approve(exportNext) {
    if (approving) return;
    if (!$('review-listened').checked) {message.textContent = tr('请实际试听后，勾选确认再批准。'); return;}
    const ids = batchIds || [reviewing]; approving = true; approvalButtons(); message.textContent = '';
    try {
      await api('/results/review-batch', {method: 'POST', body: {result_ids: ids, status: 'approved', listened: true, note: $('review-note').value}});
      dialog.close(); await refresh(true); ids.forEach(id => state.selected.add(id));
      if (exportNext) {
        state.selected = new Set(ids); state.reviewJob = null; state.reviewBatch=null;state.reviewIds=null; $('review-status').value = ''; $('review-project').value = ''; $('review-search').value = ''; $('review-selected-only').checked = true;
        $('review-export-ready').textContent = tr('审核已记录。所选音频已显示在下方，可直接选择格式导出。');
      }
      renderResults(); updateSelection(); window.dispatchEvent(new Event('voice-context-change')); toast(tr('试听审核已记录，可直接导出'));
    } catch (error) {message.textContent = error.message;}
    finally {approving = false; approvalButtons();}
  }
  approval.onclick = () => approve(false); direct.onclick = () => approve(true);
  document.addEventListener('click', event => {if (event.target.closest('[data-action="approve"]')) {batchIds = null; message.textContent = ''; dialog.querySelector('p').textContent = tr('请试听后确认是否批准。'); queueMicrotask(approvalButtons);}}, true);
  $('review-batch-approve').onclick = () => {
    batchIds = current(); if (!batchIds.length) return;
    message.textContent = ''; $('review-listened').checked = false; $('review-note').value = '';
    dialog.querySelector('p').textContent = tr('只有实际试听了所选 {0} 条音频后，才能批准。请确认所有选中结果都符合要求。', [batchIds.length]); approvalButtons(); dialog.showModal();
  };
  $('review-selected-only').onchange = () => renderResults();
  $('review-clear-selected').onclick = () => {stopComparison(); state.selected.clear(); $('review-selected-only').checked = false; renderResults();};
  $('review-delete-selected').onclick = () => {stopComparison(); window.assetUI.preview(current().map(id => ({kind: 'results', id})));};
  $('review-export-advanced').onclick = () => {$('export-format').value = $('review-export-format').value.toUpperCase(); navigate('exports');const setup=$('export-package-settings');if(setup){setup.open=true;setup.scrollIntoView({block:'start'});}};
  $('review-export-now').onclick = async () => {
    const ids = current(); if (!ids.length || exporting) return;
    if (ids.some(id => state.results.find(result => result.id === id)?.review !== 'approved')) return;
    exporting = true; counts();
    try {
      await window.exportTasks.start({result_ids:ids,format:$('review-export-format').value});
      exportSignature=JSON.stringify([...ids].sort());
      $('review-export-ready').textContent=tr('导出在后台进行，关闭页面后可回来下载。');
    } catch (error) {$('review-export-ready').textContent = error.message;}
    finally {exporting = false; counts();}
  };
  // Stop and replace comparison listeners rather than accumulating ended handlers.
  let playToken = 0, listening = null, ended = null, failed = null, running = false;
  const stop = document.createElement('button'); stop.id = 'compare-stop'; stop.className = 'text-link'; stop.textContent = tr('停止对比'); stop.hidden = true; $('compare-selected').after(stop);
  $('compare-selected').textContent=tr('连续对比全部所选');
  const comparisonStatus=document.createElement('span');comparisonStatus.className='hint';comparisonStatus.setAttribute('role','status');stop.after(comparisonStatus);
  function releaseComparisonAudio(){
    if(!listening)return;
    if(ended)listening.removeEventListener('ended',ended);
    if(failed)listening.removeEventListener('error',failed);
    listening.pause();listening.removeAttribute('src');listening.load();listening=null;ended=null;failed=null;
  }
  function stopComparison() {
    playToken++; running = false; stop.hidden = true;
    releaseComparisonAudio();comparisonStatus.textContent='';
  }
  stop.onclick = stopComparison;
  $('compare-selected').onclick = async () => {
    stopComparison();
    const items = state.results.filter(item => state.selected.has(item.id));
    if (!items.length) return toast(tr('请先选择要比较的候选'), true);
    document.querySelectorAll('#result-list audio').forEach(audio=>audio.pause());
    running = true; stop.hidden = false; const token = playToken; let index = 0;
    const next = async () => {
      if (token !== playToken) return;
      releaseComparisonAudio();
      if (index >= items.length) {stopComparison();comparisonStatus.textContent=tr('已完成所选 {0} 条音频对比',[items.length]);return;}
      const item=items[index++];listening=new Audio(`/api/v1/results/${encodeURIComponent(item.id)}/audio`);listening.preload='metadata';
      comparisonStatus.textContent=tr('正在对比 {0}/{1}：{2}',[index,items.length,item.title]);
      ended = next; listening.addEventListener('ended', ended, {once: true});
      failed=()=>{if(token!==playToken)return;stopComparison();toast(tr('对比音频读取失败，请重试或检查该结果。'),true);};listening.addEventListener('error',failed,{once:true});
      try {await listening.play();} catch (error) {if(token===playToken){stopComparison();toast(error.message, true);}}
    };
    await next();
  };
  document.addEventListener('play', event => {if (running && event.target !== listening) stopComparison();}, true);
  window.addEventListener('voice-page-change', event => {if (event.detail.page !== 'review') stopComparison();});
  window.addEventListener('pagehide',stopComparison);
  window.reviewPlayback = {stop: stopComparison};
  counts(); approvalButtons();
})();
