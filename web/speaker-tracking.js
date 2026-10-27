/* Run-local speaker identity, individual references and compact auditions. */
(()=>{
 'use strict';
 const host=document.createElement('section');host.id='speaker-tracking';host.className='speaker-tracking';host.hidden=true;
 document.getElementById('voice-pane-processing').append(host);
 const startFromRecording=document.createElement('button');startFromRecording.type='button';startFromRecording.className='secondary';startFromRecording.textContent=tr('按人物整理所选录音');document.getElementById('audio-processing-form').after(startFromRecording);
 startFromRecording.onclick=async()=>{const recording_id=document.getElementById('processing-recording').value;if(!recording_id)return;startFromRecording.disabled=true;try{const item=await api('/audio-processing',{method:'POST',body:{recording_id,operations:['track_speakers'],analyze_outputs:false}});await window.voiceWorkspace.openProcessing(item.id);await sync();host.scrollIntoView({block:'start',behavior:'smooth'});}catch(error){toast(error.message,true);}finally{startFromRecording.disabled=false;}};
 const tools=document.createElement('details');tools.className='tracking-tools';tools.open=true;const toolsTitle=document.createElement('summary');toolsTitle.textContent=tr('其他音频处理与历史');tools.append(toolsTitle);const pane=document.getElementById('voice-pane-processing');pane.insertBefore(tools,host);for(const child of [...pane.children]){if(child!==tools&&child!==host)tools.append(child);}let toolsContext=null;
 let context=null,task=null,epoch=0,busy=false,syncing=false,signature='',selected=new Set(),activeSpeaker=null,assembly=null;
 const drafts=new Map(),gapDrafts=new Map(),countDrafts=new Map();
 const esc=value=>VoiceI18n.escape(String(value??''));
 const seconds=value=>tr('{0} 秒',[Number(value||0).toFixed(1)]);
 const url=(item,output)=>`/api/v1/audio-processing/${encodeURIComponent(item.id)}/outputs/${encodeURIComponent(output.id)}`;
 const isActive=()=>state.page==='voices'&&window.voiceWorkspace?.context().pane==='processing';
 function stopAudio(){host.querySelectorAll('audio').forEach(audio=>{audio.pause();audio.removeAttribute('src');audio.load();});}
 async function run(action){if(busy)return;busy=true;host.setAttribute('aria-busy','true');host.querySelectorAll('button').forEach(b=>b.disabled=true);try{await action();}catch(error){toast(error.message,true);}finally{busy=false;host.removeAttribute('aria-busy');host.querySelectorAll('button').forEach(b=>b.disabled=false);updateSelection();}}
 function updateSelection(){const button=host.querySelector('[data-track-action="save"]');if(button)button.disabled=busy||!selected.size||task?.outputs.some(o=>selected.has(o.id)&&(!o.speaker_id||o.duration<.5));const assemble=host.querySelector('[data-track-action="assemble"]');if(assemble)assemble.disabled=busy||!selected.size;const recommended=host.querySelector('[data-track-action="recommended"]');if(recommended)recommended.disabled=busy||!task?.outputs.some(o=>o.speaker_id===activeSpeaker&&o.recommended&&!o.reference_id);const count=host.querySelector('[data-track-count]');if(count)count.textContent=tr('已选择 {0} 个片段',[selected.size]);}
 function render(){
  if(!context)return;
  if(toolsContext!==context.id){tools.open=false;toolsContext=context.id;}
  const next=JSON.stringify([context.id,task?.updated_at,task?.status,task?.progress,activeSpeaker,assembly?.updated_at]);
  if(next===signature)return;signature=next;stopAudio();host.hidden=false;
  const tracking=task?.tracking;
  host.innerHTML=`<div class="tracking-heading"><div><h2>${tr('按人物整理')}</h2><p class="hint">${tr('跟踪同一人物，筛选独白，仅分离重叠部分。原件和已有结果保留。')}</p></div><button type="button" class="secondary" data-track-action="start">${tr(task?'重新整理':'分析人物')}</button></div>`;
  host.insertAdjacentHTML('beforeend',`<label class="tracking-count">${tr('已知人物数量（可选）')}<input data-track-speakers type="number" min="1" max="12" value="${esc(countDrafts.get(context.id)??task?.speaker_count??'')}" placeholder="${esc(tr('自动判断'))}"></label>`);
  const controls=document.createElement('div');controls.className='tracking-run-controls';controls.append(host.querySelector('.tracking-count'),host.querySelector('[data-track-action="start"]'));host.querySelector('.tracking-heading').append(controls);
  if(!task){host.insertAdjacentHTML('beforeend',`<p class="hint">${tr('人物整理需要本机安装 Community-1 模型。')}</p>`);return;}
  if(!['succeeded','failed','cancelled'].includes(task.status)){
   host.insertAdjacentHTML('beforeend',`<p role="status">${esc(uiMessage(task.message||''))}</p><progress max="100" value="${Number(task.progress||0)}"></progress><button type="button" class="text-link" data-track-action="cancel">${tr('停止处理')}</button>`);return;
  }
  if(task.status!=='succeeded'){
   host.insertAdjacentHTML('beforeend',`<p role="status">${tr('本次整理未完成，原件与已有结果保留。')}</p><details><summary>${tr('查看失败原因')}</summary><p>${esc(task.error||'')}</p></details>`);return;
  }
  const speakers=tracking.speakers;
  if(!speakers.some(s=>s.id===activeSpeaker))activeSpeaker=speakers[0]?.id;
  const person=speakers.find(s=>s.id===activeSpeaker);
  const clips=task.outputs.filter(o=>o.kind==='clip'&&o.speaker_id===activeSpeaker);
  const outputs=new Map(task.outputs.map(o=>[o.key,o]));
  host.insertAdjacentHTML('beforeend',`<p class="tracking-summary">${tr('检测到 {0} 个人物；重叠讲话 {1} 秒；{2} 项待确认。',[speakers.length,tracking.overlap_seconds.toFixed(1),tracking.unresolved.length])}</p><div class="tracking-tabs" role="tablist" aria-label="${esc(tr('人物'))}">${speakers.map(s=>`<button type="button" role="tab" aria-selected="${s.id===activeSpeaker}" data-track-action="person" id="track-tab-${esc(s.id)}" aria-controls="track-person-panel" tabindex="${s.id===activeSpeaker?0:-1}" data-speaker="${esc(s.id)}">${esc(s.name||tr('人物 {0}',[speakers.indexOf(s)+1]))}<span>${seconds(s.effective_seconds??s.solo_seconds)}</span></button>`).join('')}</div>`);
  if(person){
   const timeline=outputs.get(person.timeline_key);
   host.insertAdjacentHTML('beforeend',`<div class="tracking-person" id="track-person-panel" role="tabpanel" aria-labelledby="track-tab-${esc(person.id)}"><form data-track-name-form><label>${tr('人物名称')}<input maxlength="100" required data-track-name value="${esc(drafts.get(task.id+person.id)??person.name)}" placeholder="${esc(tr('填写人物名称'))}"></label><button class="secondary" type="submit">${tr('保存名称')}</button></form><div class="tracking-clip-heading"><h3>${tr('独立参考片段')}</h3><span class="hint">${tr('长空白已去除。逐条试听后，选择保存或手动合并。')}</span></div><div class="tracking-actions"><button type="button" class="secondary" data-track-action="recommended">${tr('选择推荐独白')}</button><button type="button" class="secondary" data-track-action="save">${tr('保存所选到参考库')}</button><button type="button" class="secondary" data-track-action="assemble">${tr('按原顺序合并所选')}</button><span class="hint" data-track-count></span><button type="button" class="text-link" data-track-action="library">${tr('打开参考片段库')}</button></div><details class="tracking-compare"><summary>${tr('原件对比与合并间隔')}</summary><label class="tracking-gap">${tr('合并时片段间隔（毫秒）')}<input data-track-gap type="number" min="0" max="1000" value="${esc(gapDrafts.get(task.id)??assembly?.gap_ms??180)}"></label><div class="tracking-audition"><label>${tr('原始录音')}<audio controls preload="none" src="/api/v1/audio-processing/${task.id}/before"></audio></label>${timeline?`<label>${tr('该人物原时间轴')}<audio controls preload="none" src="${url(task,timeline)}"></audio>`:''}</div></details><div data-track-assembly>${assembly?assembly.status==='succeeded'?`<p>${tr('所选语音已合并')}</p><audio controls preload="none" src="${url(assembly,assembly.outputs[0])}"></audio><a class="text-link" href="${url(assembly,assembly.outputs[0])}?download=true">${tr('下载所选合并文件')}</a>`:assembly.status==='failed'?`<p role="status">${esc(assembly.error)}</p>`:`<p role="status">${tr('正在合并所选片段')}</p>`:''}</div><div class="tracking-clips">${clips.map(o=>`<div class="tracking-clip"><label class="checkbox"><input type="checkbox" data-track-select="${o.id}" ${selected.has(o.id)?'checked':''}><span>${esc(o.transcript?.text||tr('暂无转写'))}</span></label><div class="tracking-clip-meta"><span>${Number(o.source_spans[0].source_start).toFixed(1)}–${Number(o.source_spans.at(-1).source_end).toFixed(1)} s</span><span>${tr(o.origin==='solo'?'独白':'重叠分离')}</span>${o.recommended?`<span>${tr('推荐')}</span>`:''}${o.reference_id?`<span>${tr('已保存')}</span>`:''}<span>${o.similarity==null?'—':tr('声纹相似度 {0}',[o.similarity.toFixed(3)])}</span></div><audio controls preload="none" src="${url(task,o)}"></audio><a class="text-link" href="${url(task,o)}?download=true">${tr('下载片段')}</a></div>`).join('')||`<p class="hint">${tr('没有可保存的明确归属片段。')}</p>`}</div></div>`);
  }
  host.insertAdjacentHTML('beforeend',`<details class="tracking-evidence"><summary>${tr('人物跟踪依据与待确认片段')}</summary><p class="hint">${tr('人物编号仅在本次录音内有效。声纹相似度不是身份概率，保存不代表试听审核通过。')}</p><p>${tr('模型')} · ${esc(tracking.model)}</p>${speakers.map(s=>`<p>${esc(s.name||s.id)} · ${tr('独白依据 {0} 段',[s.anchor_count])} · ${seconds(s.effective_seconds??s.solo_seconds)}</p>`).join('')}${tracking.speaker_similarities.map(s=>`<p>${esc(s.left)} / ${esc(s.right)} · ${s.cosine.toFixed(3)}</p>`).join('')}${task.outputs.filter(o=>o.kind==='clip'&&!o.speaker_id).map(o=>`<label class="checkbox"><input type="checkbox" data-track-select="${o.id}" ${selected.has(o.id)?'checked':''}><span>${tr('待确认')} · ${o.source_spans[0].source_start.toFixed(1)}–${o.source_spans.at(-1).source_end.toFixed(1)} s</span></label><audio controls preload="none" src="${url(task,o)}"></audio><a class="text-link" href="${url(task,o)}?download=true">${tr('下载片段')}</a>`).join('')}</details>`);
  updateSelection();
 }
 async function sync(){
  if(!isActive()){stopAudio();return;}if(syncing)return;const current=window.voiceWorkspace.context().id;if(!current)return;syncing=true;
  const ticket=epoch;
  try{const item=await api('/audio-processing/'+current);if(ticket!==epoch||!isActive()||window.voiceWorkspace.context().id!==current)return;
   if(context?.id!==current){context=item;task=null;assembly=null;selected.clear();signature='';}
   if(item.operations.includes('track_speakers'))task=item;
   else {const tasks=await api('/audio-processing');if(ticket!==epoch||!isActive()||window.voiceWorkspace.context().id!==current)return;task=tasks.filter(t=>t.operations.includes('track_speakers')&&t.recording_id===item.recording_id).sort((a,b)=>b.created_at.localeCompare(a.created_at))[0]||null;}
   if(task&&!assembly){const all=await api('/audio-processing');if(ticket!==epoch||!isActive()||window.voiceWorkspace.context().id!==current)return;const speaker=activeSpeaker||task.tracking?.speakers[0]?.id;assembly=all.filter(a=>a.source_processing_id===task.id&&a.operations.includes('assemble_clips')&&a.assembly_inputs?.every(o=>o.speaker_id===speaker)).sort((a,b)=>b.created_at.localeCompare(a.created_at))[0]||null;}
   if(assembly&&!['succeeded','failed','cancelled'].includes(assembly.status)){const updated=await api('/audio-processing/'+assembly.id);if(ticket!==epoch||!isActive()||window.voiceWorkspace.context().id!==current)return;assembly=updated;}
   if(!busy)render();
  }catch(error){if(ticket===epoch&&isActive())toast(error.message,true);}finally{syncing=false;}
 }
 host.addEventListener('input',event=>{if(event.target.matches('[data-track-name]')&&task)drafts.set(task.id+activeSpeaker,event.target.value);if(event.target.matches('[data-track-gap]')&&task)gapDrafts.set(task.id,event.target.value);if(event.target.matches('[data-track-speakers]')&&context)countDrafts.set(context.id,event.target.value);});
 host.addEventListener('change',event=>{const id=event.target.dataset.trackSelect;if(!id)return;event.target.checked?selected.add(id):selected.delete(id);updateSelection();});
 host.addEventListener('submit',event=>{if(!event.target.matches('[data-track-name-form]'))return;event.preventDefault();const identity=task.id,speaker=activeSpeaker,name=host.querySelector('[data-track-name]').value.trim();if(!name)return;run(async()=>{const item=await api(`/audio-processing/${identity}/speakers/${encodeURIComponent(speaker)}`,{method:'PUT',body:{name}});if(task?.id!==identity)return;task=item;drafts.delete(identity+speaker);signature='';render();});});
 host.addEventListener('click',event=>{const button=event.target.closest('[data-track-action]');if(!button)return;const action=button.dataset.trackAction;
  if(action==='person'){activeSpeaker=button.dataset.speaker;assembly=null;selected.clear();signature='';render();return;}
  if(action==='library'){stopAudio();window.voiceWorkspace.showPane('references');return;}
  if(action==='recommended'){selected=new Set(task.outputs.filter(o=>o.speaker_id===activeSpeaker&&o.recommended&&!o.reference_id).map(o=>o.id));signature='';render();return;}
  const identity=task?.id,base=context;
  run(async()=>{
   if(action==='start'){const count=host.querySelector('[data-track-speakers]')?.value;const item=await api('/audio-processing',{method:'POST',body:{recording_id:base.recording_id,operations:['track_speakers'],analyze_outputs:false,...(!base.operations.includes('track_speakers')?{source_processing_id:base.id}:{}),speaker_count:count?Number(count):null}});if(context?.id!==base.id)return;task=item;selected.clear();signature='';render();}
   if(action==='assemble'){const ids=task.outputs.filter(o=>selected.has(o.id)).map(o=>o.id);const person=task.tracking.speakers.find(s=>s.id===activeSpeaker);const item=await api('/audio-processing/'+identity+'/assemble',{method:'POST',body:{output_ids:ids,name:person.name||tr('所选语音'),gap_ms:Number(host.querySelector('[data-track-gap]').value)}});if(task?.id!==identity)return;assembly=item;signature='';render();}
   if(action==='cancel'){await api('/audio-processing/'+identity+'/cancel',{method:'POST'});signature='';}
   if(action==='save'){const ids=[...selected];await api('/audio-processing/'+identity+'/save-clips',{method:'POST',body:{output_ids:ids}});if(task?.id!==identity)return;task=await api('/audio-processing/'+identity);selected.clear();signature='';render();await refresh(true);toast(tr('已保存独立片段；转写和人物仍需试听确认。'));}
  });
 });
 document.addEventListener('play',event=>{if(!host.contains(event.target))return;document.querySelectorAll('audio').forEach(a=>{if(a!==event.target)a.pause();});},true);
 host.addEventListener('keydown',event=>{if(!event.target.matches('[data-track-action="person"]')||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const tabs=[...host.querySelectorAll('[data-track-action="person"]')],index=tabs.indexOf(event.target),next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:tabs.length-1))%tabs.length;const id=tabs[next].dataset.speaker;tabs[next].click();host.querySelector(`[data-speaker="${id}"]`).focus();});
 window.addEventListener('hashchange',()=>{epoch++;stopAudio();signature='';sync();});
 window.addEventListener('voice-context-change',()=>{epoch++;stopAudio();signature='';sync();});
 window.addEventListener('pagehide',()=>{epoch++;stopAudio();});
 setInterval(sync,2500);sync();
})();
