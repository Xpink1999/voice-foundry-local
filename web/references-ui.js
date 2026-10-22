/* Shared voice bindings and per-generation reference selection. */
(() => {
 const binding=document.createElement('details');binding.id='voice-reference-set';binding.className='reference-bindings';$('voice-reference').closest('label').after(binding);
 const generation=document.createElement('div');generation.className='reference-generation';generation.innerHTML=("<label>"+tr("本次参考片段")+"<select id=\"gen-reference\"><option value=\"\">"+tr("使用人物主参考")+"</option></select></label><label>"+tr("克隆模式")+"<select id=\"gen-clone-mode\"><option value=\"reference\">"+tr("可控声音克隆")+"</option><option value=\"hifi\">"+tr("极致克隆 · 参考音频与精确转写")+"</option></select></label><p id=\"gen-reference-note\" class=\"hint\"></p><details id=\"gen-transcript-review\" class=\"lf-details\" hidden><summary>"+tr("核对本次参考的完整转写")+"</summary><p class=\"hint\">"+tr("填写参考原音频中的逐字内容，不是接下来要生成的台词。极致克隆使用这一段音频及其转写。")+"</p><label>"+tr("参考音频转写")+"<textarea id=\"gen-reference-transcript\" maxlength=\"6000\" rows=\"3\"></textarea></label><label class=\"checkbox\"><input id=\"gen-reference-transcript-confirmed\" type=\"checkbox\">"+tr("我已逐字核对这段参考音频的转写")+"</label><button id=\"gen-save-transcript\" type=\"button\" class=\"secondary\">"+tr("保存转写")+"</button><p id=\"gen-transcript-status\" class=\"hint\" role=\"status\"></p></details>");$('gen-voice').closest('label').after(generation);
 let editingReference=null;
 const refName=r=>tr("{0} · {1} 秒{2}", [r.source_label||r.original_name,r.duration.toFixed(1),r.transcript?.text?' · '+r.transcript.text.slice(0,18)+(r.transcript.text.length>18?'…':''):'']);
 function refreshBindings(voice){
  const specified=voice!==undefined,previous=specified?(voice?.reference_ids||[voice?.reference_id].filter(Boolean)):[...binding.querySelectorAll('[data-bound-ref]:checked')].map(el=>el.dataset.boundRef);
  const scenes=specified?(voice?.reference_scenarios||{}):Object.fromEntries([...binding.querySelectorAll('[data-ref-scene]')].map(el=>[el.dataset.refScene,el.value]));
  binding.innerHTML=("<summary>"+tr("其他场景参考（可选）")+"</summary><p class=\"hint\">"+tr("同一个人物可保留多个片段。每次生成只使用其中一个，不拼接。")+"</p><div class=\"reference-binding-list\">")+state.references.map(r=>("<div class=\"reference-binding-row\"><label class=\"checkbox\"><input type=\"checkbox\" data-bound-ref=\""+(r.id)+"\" "+(previous.includes(r.id)?'checked':'')+">"+(e(refName(r)))+"</label><input data-ref-scene=\""+(r.id)+"\" value=\""+(e(scenes[r.id]||''))+"\" placeholder=\""+VoiceI18n.escape(tr("如：平静旁白 / 激动对白"))+"\" maxlength=\"80\" aria-label=\""+VoiceI18n.escape(tr("{0}的场景标签", [e(r.original_name)]))+"\"></div>")).join('')+'</div>';
  window.voiceWorkspace?.refreshLibrary();
 }
 function updateGeneration(voice){
  const select=$('gen-reference'),old=select.value,allowed=voice?new Set([...(voice.reference_ids||[]),voice.reference_id].filter(Boolean)):null;
  const refs=state.references.filter(r=>!allowed||allowed.has(r.id));
  select.innerHTML=("<option value=\"\">"+tr("使用人物主参考")+"</option>")+refs.map(r=>`<option value="${r.id}">${e(voice?.reference_scenarios?.[r.id]||refName(r))}</option>`).join('');if(refs.some(r=>r.id===old))select.value=old;
  const caps=state.models.find(m=>m.id===$('gen-engine').value)?.capabilities;$('gen-clone-mode').querySelector('[value="hifi"]').disabled=!caps?.hifi_cloning;if(!caps?.hifi_cloning)$('gen-clone-mode').value='reference';updateNote();
 }
 function updateNote(){
  const voice=state.voices.find(v=>v.id===$('gen-voice').value),id=$('gen-reference').value||voice?.reference_id,ref=state.references.find(r=>r.id===id),caps=state.models.find(m=>m.id===$('gen-engine').value)?.capabilities;
  $('gen-transcript-review').hidden=!ref;if(editingReference!==id){editingReference=id;$('gen-reference-transcript').value=ref?.transcript?.text||'';$('gen-reference-transcript-confirmed').checked=!!ref?.transcript?.confirmed;$('gen-transcript-review').open=false;$('gen-transcript-status').textContent='';}
  const hifi=$('gen-clone-mode').value==='hifi'&&!caps?.hifi_style_control;$('gen-style').disabled=hifi||!caps?.voice_design;document.querySelectorAll('[data-style]').forEach(b=>b.disabled=$('gen-style').disabled);
  $('gen-reference-note').textContent=ref?`${refName(ref)}。${ref.transcript?.text?(ref.transcript.confirmed?tr("转写已确认。"):tr("转写为草稿，请校对。")):tr("极致克隆需要参考音频的精确转写。")}`:tr("选择人物主参考，或即兴设计新声音。");if(!hifi&&ref)$('gen-reference-note').textContent+=tr(" 可在声音与演绎描述中输入情绪、语速或风格，效果为近似控制。");if(hifi)$('gen-reference-note').textContent+=tr(" 极致克隆沿用参考演绎，不叠加风格指令；需控制语气时切换可控声音克隆。");
 }
 $('gen-save-transcript').onclick=async()=>{if(!editingReference)return;try{await api('/references/'+editingReference+'/transcript',{method:'PUT',body:{text:$('gen-reference-transcript').value,confirmed:$('gen-reference-transcript-confirmed').checked}});$('gen-transcript-status').textContent=tr("本次参考转写已保存；已提交的长文和任务仍保留原版本。");await refresh(true);}catch(error){$('gen-transcript-status').textContent=error.message;}};
 $('gen-reference').onchange=updateNote;$('gen-clone-mode').onchange=updateNote;$('gen-engine').addEventListener('change',()=>updateGeneration(state.voices.find(v=>v.id===$('gen-voice').value)));
 window.referenceUI={refreshBindings,updateGeneration,selectedIDs:()=>[...binding.querySelectorAll('[data-bound-ref]:checked')].map(el=>el.dataset.boundRef),scenarios:()=>Object.fromEntries([...binding.querySelectorAll('[data-bound-ref]:checked')].map(el=>[el.dataset.boundRef,binding.querySelector(`[data-ref-scene="${el.dataset.boundRef}"]`).value]).filter(([,v])=>v.trim()))};
 refreshBindings();updateGeneration(state.voices.find(v=>v.id===$('gen-voice').value));
})();
