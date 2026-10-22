(() => {
  const queue={archived:false,page:0,size:50,items:[],selected:new Set(),sequence:0,signature:''};
  const toolbar=document.createElement('div');toolbar.className='queue-archive-toolbar';
  toolbar.innerHTML=`<div class="toolbar"><label>任务视图<select id="task-archive-view"><option value="current">当前队列</option><option value="archived">已归档</option></select></label><button id="task-select-page" class="secondary">全选本页已结束任务</button><button id="task-archive-selected" class="secondary" disabled>归档所选</button><span id="task-selection-count" class="hint">已选择 0 项</span></div><p id="task-archive-policy" class="hint"></p>`;
  $('job-list').before(toolbar);
  const pages=document.createElement('div');pages.className='toolbar queue-pages';pages.innerHTML=`<button id="task-prev" class="secondary" disabled>上一页</button><span id="task-page-info" class="hint"></span><button id="task-next" class="secondary" disabled>下一页</button>`;
  $('job-list').after(pages);
  function selection(){const count=queue.selected.size;$('task-selection-count').textContent=`已选择 ${count} 项`;$('task-archive-selected').disabled=!count;$('task-archive-selected').textContent=queue.archived?'恢复所选':'归档所选';}
  async function load(){
    const sequence=++queue.sequence;
    try{
      const params=new URLSearchParams({archived:String(queue.archived),limit:String(queue.size),offset:String(queue.page*queue.size)});
      if($('task-project').value)params.set('project_id',$('task-project').value);
      if($('task-status').value)params.set('status',$('task-status').value);
      const result=await api('/jobs/page?'+params);if(sequence!==queue.sequence)return;
      if(queue.page&&queue.page*queue.size>=result.total){queue.page=Math.max(0,Math.ceil(result.total/queue.size)-1);return load();}
      queue.items=result.items;
      const allowed=new Set(queue.items.filter(j=>['succeeded','failed','cancelled'].includes(j.status)).map(j=>j.id));
      queue.selected=new Set([...queue.selected].filter(id=>allowed.has(id)));
      const signature=JSON.stringify([queue.items,[...queue.selected],queue.archived]);
      if(signature!==queue.signature){queue.signature=signature;$('job-list').innerHTML=queue.items.map(j=>jobHTML(j,true)).join('')||empty(queue.archived?'还没有归档任务':'队列空闲',queue.archived?'已结束任务归档后会显示在这里，可随时恢复。':'新的配音任务会显示在这里，旧任务可归档整理。');}
      const totalPages=Math.max(1,Math.ceil(result.total/queue.size));$('task-page-info').textContent=`${queue.archived?'归档':'当前'} ${result.total} 项 · 第 ${queue.page+1} / ${totalPages} 页 · 每页 ${queue.size} 项`;
      $('task-prev').disabled=queue.page===0;$('task-next').disabled=queue.page+1>=totalPages;
      $('task-archive-policy').textContent=(result.task_archive_after_days?`已结束任务 ${result.task_archive_after_days} 天后自动归档。`:'自动归档已关闭，可手动整理。')+'归档保留音频、审核及导出记录；恢复后重新计时。可在“模型与系统”调整。';selection();
    }catch(error){if(sequence===queue.sequence)toast(error.message,true);}
  }
  function reset(){queue.page=0;queue.selected.clear();load();}
  async function change(ids,restore){
    if(!ids.length)return;
    await api('/jobs/'+(restore?'restore':'archive'),{method:'POST',body:{job_ids:ids}});queue.selected.clear();
    toast(restore?'任务已恢复，音频与审核记录保留':'任务已归档，音频与审核记录保留');await refresh(true);await load();
  }
  $('task-archive-view').onchange=()=>{queue.archived=$('task-archive-view').value==='archived';reset();};
  $('task-project').onchange=reset;$('task-status').onchange=reset;
  $('task-prev').onclick=()=>{queue.page--;queue.selected.clear();load();};$('task-next').onclick=()=>{queue.page++;queue.selected.clear();load();};
  $('task-select-page').onclick=()=>{const available=queue.items.filter(j=>['succeeded','failed','cancelled'].includes(j.status));const clear=available.length>0&&available.every(j=>queue.selected.has(j.id));queue.selected=new Set(clear?[]:available.map(j=>j.id));queue.signature='';load();};
  $('task-archive-selected').onclick=async()=>{try{await change([...queue.selected],queue.archived);}catch(error){toast(error.message,true);}};
  document.addEventListener('change',event=>{const id=event.target.dataset.jobSelect;if(!id)return;if(event.target.checked)queue.selected.add(id);else queue.selected.delete(id);selection();});
  document.addEventListener('click',async event=>{const button=event.target.closest('[data-job-archive]');if(!button)return;try{await change([button.dataset.id],button.dataset.jobArchive==='restore');}catch(error){toast(error.message,true);}});
  window.jobArchiveUI={refresh:load,isSelected:id=>queue.selected.has(id)};
  load();setInterval(()=>{if(state.page==='tasks')load();},2500);
})();
