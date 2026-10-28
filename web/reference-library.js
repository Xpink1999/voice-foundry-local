/* Named, reusable clips. Audio bytes and human review state are never edited here. */
(() => {
 const pane=$('voice-pane-references'),selected=new Set();
 let editing=null,page=0,signature='',editorEpoch=0,metadataRevision=0,transcriptRevision=0,selectionSignature='';
 const title=ref=>ref.name||ref.source_label||ref.original_name;
 pane.innerHTML=`<div class="workspace-intro"><div><h2>${tr("参考片段库")}</h2><p>${tr("保存同一人物的不同录音，按场景选用。每次配音只使用一段参考。")}</p></div><button type="button" class="secondary" data-voice-pane="quick">${tr("上传录音")}</button></div>
 <div class="toolbar"><label>${tr("搜索片段")}<input id="reference-library-search" type="search" placeholder="${e(tr("名称、场景、标签或备注"))}"></label><label>${tr("人物")}<select id="reference-library-voice"></select></label></div>
 <div class="reference-library-actions"><button type="button" class="secondary" id="reference-select-page">${tr("全选本页")}</button><span id="reference-library-selection" class="hint" role="status"></span><button type="button" class="text-link" id="reference-clear-selected">${tr("清空选择")}</button><label>${tr("添加到人物")}<select id="reference-attach-voice"></select></label><button type="button" class="primary" id="reference-create-voice">${tr("设置人物并配音")}</button><button type="button" class="secondary" id="reference-attach">${tr("添加所选参考")}</button><button type="button" class="text-link" id="reference-delete">${tr("删除所选")}</button></div>
 <details id="reference-selected-details" class="workspace-history" hidden><summary>${tr("查看所选参考")}</summary><ul id="reference-selected-list"></ul></details>
 <button type="button" class="text-link" id="reference-clear-filter">${tr("清除筛选")}</button><div id="reference-library-list"></div><div class="lf-pager"><button type="button" class="secondary" id="reference-prev">${tr("上一页")}</button><span id="reference-library-page" class="hint"></span><button type="button" class="secondary" id="reference-next">${tr("下一页")}</button></div>
 <section id="reference-metadata-editor" class="panel" hidden><h2 id="reference-editor-title">${tr("参考片段详情")}</h2><audio id="reference-detail-audio" controls preload="none"></audio><details class="lf-details"><summary>${tr("来源与授权")}</summary><dl><dt>${tr("来源")}</dt><dd id="reference-detail-source"></dd><dt>${tr("授权说明")}</dt><dd id="reference-detail-authorization"></dd><dt>${tr("授权状态")}</dt><dd id="reference-detail-rights"></dd></dl></details><form id="reference-metadata-form"><label>${tr("参考片段名称")}<input id="reference-metadata-name" maxlength="100" required></label><label>${tr("适用场景")}<input id="reference-metadata-scenario" maxlength="80" placeholder="${e(tr("例如：日常、轻声、激动、旁白"))}"></label><label>${tr("标签（逗号分隔）")}<input id="reference-metadata-tags" maxlength="2400"></label><label>${tr("备注")}<textarea id="reference-metadata-notes" rows="3" maxlength="2000"></textarea></label><p class="hint">${tr("命名和标注不改动录音、授权及转写，也不改变已提交任务。")}</p><div class="actions"><button type="submit" class="primary">${tr("保存标注")}</button><button type="button" class="secondary" id="reference-metadata-cancel">${tr("关闭")}</button></div></form><form id="reference-transcript-form"><h3>${tr("参考音频转写")}</h3><p class="hint">${tr("填写参考原音频中的逐字内容，不是接下来要生成的台词。极致克隆使用这一段音频及其转写。")}</p><label>${tr("本片段的转写")}<textarea id="reference-detail-transcript" rows="4" maxlength="6000"></textarea></label><label class="checkbox"><input type="checkbox" id="reference-detail-confirmed">${tr("我已逐字核对这段参考音频的转写")}</label><button type="submit" class="secondary">${tr("保存转写")}</button><p id="reference-transcript-status" class="hint" role="status"></p></form></section>`;
 function matches(){const query=$('reference-library-search').value.trim().toLowerCase(),voice=state.voices.find(v=>v.id===$('reference-library-voice').value),ids=voice?new Set([voice.reference_id,...(voice.reference_ids||[])]):null;return state.references.filter(ref=>(!ids||ids.has(ref.id))&&JSON.stringify([title(ref),ref.scenario,ref.tags,ref.notes,ref.original_name]).toLowerCase().includes(query));}
 function selection(){
  for(const id of selected)if(!state.references.some(ref=>ref.id===id))selected.delete(id);
  const visible=new Set(matches().slice(page*12,page*12+12).map(ref=>ref.id)),hidden=[...selected].filter(id=>!visible.has(id)).length;
  pane.querySelector('.reference-library-actions').dataset.empty=String(!selected.size);
  $('reference-library-selection').textContent=tr("已选择 {0} 项",[selected.size])+(hidden?' · '+tr("其中 {0} 条被当前筛选或分页隐藏",[hidden]):'');
  $('reference-create-voice').disabled=!selected.size;$('reference-attach').disabled=!selected.size||!$('reference-attach-voice').value;$('reference-delete').disabled=!selected.size;$('reference-clear-selected').disabled=!selected.size;
  $('reference-select-page').disabled=!visible.size;
  pane.querySelectorAll('[data-library-select]').forEach(input=>input.checked=selected.has(input.dataset.librarySelect));
  $('reference-selected-details').hidden=!selected.size;
  const next=JSON.stringify(state.references.filter(ref=>selected.has(ref.id)).map(ref=>[ref.id,title(ref)]));
  if(next!==selectionSignature){selectionSignature=next;$('reference-selected-list').innerHTML=state.references.filter(ref=>selected.has(ref.id)).map(ref=>`<li>${e(title(ref))}</li>`).join('');}
 }
 function render(force=false){
  const snapshot=JSON.stringify([state.references,state.voices]);if(!force&&snapshot===signature)return;signature=snapshot;
  setOptions($('reference-library-voice'),state.voices.map(v=>({id:v.id,name:v.name})),tr("所有人物"));setOptions($('reference-attach-voice'),state.voices.filter(v=>v.status!=='archived'),tr("选择人物"));
  const refs=matches();page=Math.min(page,Math.max(0,Math.ceil(refs.length/12)-1));const visible=refs.slice(page*12,page*12+12);
  $('reference-library-list').innerHTML=visible.map(ref=>{const voices=state.voices.filter(v=>v.reference_id===ref.id||v.reference_ids?.includes(ref.id));return `<article class="reference-library-row"><div class="reference-library-main"><label class="checkbox"><input type="checkbox" data-library-select="${ref.id}" ${selected.has(ref.id)?'checked':''}><strong>${e(title(ref))}</strong></label><p class="hint">${e([ref.scenario,...(ref.tags||[])].filter(Boolean).join(' · ')||tr("未标注场景"))} · ${e(tr("{0} 秒",[ref.duration.toFixed(1)]))}</p>${ref.source_changed?`<p class="reference-warnings">${tr("来源片段归属已修改，请复核此参考。")}</p>`:''}${ref.notes?`<p class="reference-notes">${e(ref.notes)}</p>`:''}<p class="hint">${e(tr("关联人物：{0}",[voices.map(v=>v.name+(v.reference_id===ref.id?' · '+tr("默认参考"):'')).join('、')||tr("未关联")]))}</p><audio controls preload="none" src="/api/v1/references/${ref.id}/audio"></audio></div><div class="reference-row-actions"><button type="button" class="text-link" data-reference-edit="${ref.id}">${tr("详情与转写")}</button><button type="button" class="text-link" data-reference-use="${ref.id}">${tr("用此片段配音")}</button></div></article>`;}).join('')||empty(tr("暂无匹配片段"),state.references.length?tr("清除搜索或更换人物筛选。"):tr("上传录音，试听并勾选片段，命名后保存到这里。"));
  $('reference-library-page').textContent=tr("第 {0} / {1} 页 · 共 {2} 条",[page+1,Math.max(1,Math.ceil(refs.length/12)),refs.length]);$('reference-prev').disabled=page===0;$('reference-next').disabled=(page+1)*12>=refs.length;selection();
 }
 function hasDraft(){return $('reference-metadata-form').dataset.dirty||$('reference-transcript-form').dataset.dirty;}
 function closeEditor(){editorEpoch++;editing=null;$('reference-metadata-editor').hidden=true;const audio=$('reference-detail-audio');audio.pause();audio.removeAttribute('src');audio.load();delete $('reference-metadata-form').dataset.dirty;delete $('reference-transcript-form').dataset.dirty;}
 function edit(id){
  if(editing&&hasDraft()&&!confirm(tr("参考片段尚未保存，是否放弃修改？")))return;
  const ref=state.references.find(r=>r.id===id);if(!ref)return;
  editorEpoch++;editing=id;metadataRevision=transcriptRevision=0;delete $('reference-metadata-form').dataset.dirty;delete $('reference-transcript-form').dataset.dirty;
  $('reference-editor-title').textContent=tr("参考片段详情")+' · '+title(ref);
  $('reference-metadata-name').value=title(ref);$('reference-metadata-scenario').value=ref.scenario||'';$('reference-metadata-tags').value=(ref.tags||[]).join(', ');$('reference-metadata-notes').value=ref.notes||'';
  const audio=$('reference-detail-audio');audio.pause();audio.src='/api/v1/references/'+encodeURIComponent(id)+'/audio';audio.load();
  $('reference-detail-source').textContent=ref.source||tr("未记录");$('reference-detail-authorization').textContent=ref.authorization||tr("未记录");$('reference-detail-rights').textContent=tr(ref.rights_confirmed?"已记录授权":"未确认授权");
  $('reference-detail-transcript').value=ref.transcript?.text||'';$('reference-detail-confirmed').checked=!!ref.transcript?.confirmed;$('reference-transcript-status').textContent=tr(ref.transcript?.confirmed?"转写已确认。":"转写为草稿，请校对。");
  $('reference-metadata-editor').hidden=false;$('reference-metadata-editor').scrollIntoView({behavior:'smooth',block:'start'});$('reference-metadata-name').focus();
 }
 $('reference-clear-filter').onclick=()=>{$('reference-library-search').value='';$('reference-library-voice').value='';page=0;render(true);};
 $('reference-library-search').oninput=()=>{page=0;render(true);};$('reference-library-voice').onchange=()=>{page=0;selected.clear();render(true);};$('reference-attach-voice').onchange=selection;
 $('reference-clear-selected').onclick=()=>{selected.clear();window.referenceHandoff?.dismiss();selection();};
 $('reference-select-page').onclick=()=>{const visible=matches().slice(page*12,page*12+12),all=visible.length&&visible.every(r=>selected.has(r.id));visible.forEach(r=>all?selected.delete(r.id):selected.add(r.id));selection();};
 $('reference-prev').onclick=()=>{page--;render(true);};$('reference-next').onclick=()=>{page++;render(true);};
 pane.addEventListener('change',event=>{if(event.target.dataset.librarySelect){window.referenceHandoff?.dismiss();const id=event.target.dataset.librarySelect;event.target.checked?selected.add(id):selected.delete(id);selection();}});
 pane.addEventListener('click',async event=>{const editButton=event.target.closest('[data-reference-edit]'),useButton=event.target.closest('[data-reference-use]');if(editButton)edit(editButton.dataset.referenceEdit);if(useButton){const ref=state.references.find(r=>r.id===useButton.dataset.referenceUse);if(!ref)return;const compatible=state.models.filter(m=>m.capabilities.cloning),current=compatible.find(m=>m.id===$('gen-engine').value),model=current||compatible.find(m=>m.is_default)||compatible[0];if(!model){toast(tr('尚无支持参考克隆的模型'),true);return;}$('gen-voice').value='';previewVoice();$('gen-engine').value=model.id;$('gen-engine').dispatchEvent(new Event('change'));$('gen-style').value='';$('gen-clone-mode').value='reference';$('gen-reference').value=ref.id;$('gen-reference').dispatchEvent(new Event('change'));navigate('studio');}});
 $('reference-metadata-form').oninput=()=>{metadataRevision++;$('reference-metadata-form').dataset.dirty='1';};
 $('reference-metadata-form').onsubmit=busy($('reference-metadata-form'),async()=>{
  if(!editing)return;const id=editing,ticket=editorEpoch,revision=metadataRevision,body={name:$('reference-metadata-name').value,scenario:$('reference-metadata-scenario').value,tags:$('reference-metadata-tags').value.split(/[,，]/).map(s=>s.trim()).filter(Boolean),notes:$('reference-metadata-notes').value};
  try{await api('/references/'+id,{method:'PUT',body});await refresh(true);if(ticket!==editorEpoch||editing!==id)return;if(revision===metadataRevision)delete $('reference-metadata-form').dataset.dirty;toast(tr("参考标注已保存"));}catch(error){if(ticket===editorEpoch)throw error;}
 });
 $('reference-detail-transcript').oninput=()=>{transcriptRevision++;$('reference-transcript-form').dataset.dirty='1';$('reference-detail-confirmed').checked=false;$('reference-transcript-status').textContent=tr("转写已修改，请重新试听并确认。");};
 $('reference-detail-confirmed').onchange=()=>{transcriptRevision++;$('reference-transcript-form').dataset.dirty='1';};
 $('reference-transcript-form').onsubmit=busy($('reference-transcript-form'),async()=>{
  if(!editing)return;const id=editing,ticket=editorEpoch,revision=transcriptRevision,body={text:$('reference-detail-transcript').value,confirmed:$('reference-detail-confirmed').checked};
  try{await api('/references/'+id+'/transcript',{method:'PUT',body});await refresh(true);if(ticket!==editorEpoch||editing!==id)return;if(revision===transcriptRevision){delete $('reference-transcript-form').dataset.dirty;$('reference-transcript-status').textContent=tr("转写已保存；已提交的任务仍使用原版本。");}else $('reference-transcript-status').textContent=tr("先前版本已保存，当前修改尚未保存。");}catch(error){if(ticket===editorEpoch)throw error;}
 });
 $('reference-metadata-cancel').onclick=()=>{if(hasDraft()&&!confirm(tr("参考片段尚未保存，是否放弃修改？")))return;closeEditor();};
 $('reference-create-voice').onclick=()=>window.referenceHandoff.open(state.references.filter(r=>selected.has(r.id)),{after:pane});
 $('reference-attach').onclick=async()=>{const button=$('reference-attach');button.disabled=true;try{await api('/voices/'+$('reference-attach-voice').value+'/references',{method:'POST',body:{reference_ids:[...selected]}});selected.clear();await refresh(true);render(true);toast(tr("参考已添加，已有默认参考保持不变"));}catch(error){toast(error.message,true);}finally{selection();}};
 $('reference-delete').onclick=()=>window.assetUI?.preview([...selected].map(id=>({kind:'references',id})),false);
 document.addEventListener('assets-changed',()=>{if(editing&&!state.references.some(ref=>ref.id===editing))closeEditor();render(true);});
 document.addEventListener('voice-context-change',()=>{if(!pane.hidden)render();});
 const originalRefresh=refresh;refresh=async function(...args){const result=await originalRefresh(...args);render();return result;};
 window.referenceLibrary={render,name:title,edit,context:()=>editing};render(true);
})();
