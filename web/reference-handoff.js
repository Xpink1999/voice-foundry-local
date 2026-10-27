/* One explicit handoff: saved clips -> a reusable voice -> the script editor. */
(()=>{
 'use strict';
 const panel=document.createElement('section');panel.className='reference-handoff panel';panel.hidden=true;
 let refs=[],main=null,name='',voiceID='',scenario='',created=null,working=false,boundContext=null;
 function dismiss(){panel.hidden=true;boundContext=null;refs=[];main=null;created=null;}
 const contextKey=()=>JSON.stringify([state.page,window.voiceWorkspace?.context()]);
 const closeOnContextChange=()=>{if(boundContext!==null&&boundContext!==contextKey()){dismiss();}};
 for(const event of ['voice-context-change','voice-page-change','hashchange'])window.addEventListener(event,closeOnContextChange);
 const esc=value=>VoiceI18n.escape(String(value??''));
 function useVoice(voice){
  $('gen-project').value=voice.project_id||'';renderVoiceOptions();$('gen-voice').value=voice.id;
  previewVoice();navigate('studio');$('gen-text').focus();
 }
 function render(){
  if(created){panel.innerHTML=`<h2>${esc(created.name)}</h2><p role="status">${tr('人物已保存，参考可在后续配音中复用。')}</p><button type="button" class="primary" data-handoff-use>${tr('用此人物配音')}</button><button type="button" class="text-link" data-handoff-close>${tr('继续整理片段')}</button>`;return;}
  panel.innerHTML=`<h2 tabindex="-1">${tr('参考已保存，下一步设置人物')}</h2><p>${tr('已保存 {0} 个片段。可创建人物、添加到已有的人物，或只保留片段。',[refs.length])}</p>
   <p class="hint">${esc(refs.map(r=>r.name||r.original_name).join(' · '))}</p><form><label>${tr('保存到')}<select data-handoff-voice><option value="">${tr('创建新人物')}</option>${state.voices.filter(v=>v.status!=='archived').map(v=>`<option value="${v.id}" ${voiceID===v.id?'selected':''}>${esc(v.name)}</option>`).join('')}</select></label>
   ${voiceID?'':`<label>${tr('人物名称')}<input data-handoff-name required maxlength="100" value="${esc(name)}"></label>`}
   <label>${tr('适用场景')}<input data-handoff-scenario maxlength="80" value="${esc(scenario)}"></label>
   ${!voiceID&&refs.length>1?`<fieldset><legend>${tr('选择默认参考')}</legend><p class="hint">${tr('其他片段作为备选保存，配音时按场景切换。')}</p>${refs.map(ref=>`<label class="checkbox"><input type="radio" name="handoff-main" value="${ref.id}" ${ref.id===main?'checked':''}>${esc(ref.name||ref.original_name)} · ${Number(ref.duration).toFixed(1)} s</label>`).join('')}</fieldset>`:''}
   <p class="hint">${voiceID?tr('已有默认参考保持不变。'):tr('人物保存为草稿，生成结果仍需试听审核。')}</p>
   <p role="alert" data-handoff-error></p><div class="actions"><button type="submit" class="primary">${tr(voiceID?'添加到人物':'保存人物')}</button><button type="button" class="text-link" data-handoff-close>${tr('仅保留片段')}</button></div></form>`;
 }
 panel.addEventListener('input',event=>{if(event.target.matches('[data-handoff-name]'))name=event.target.value;if(event.target.matches('[data-handoff-scenario]'))scenario=event.target.value;});
 panel.addEventListener('change',event=>{if(event.target.matches('[data-handoff-voice]')){voiceID=event.target.value;render();panel.querySelector('[data-handoff-voice]').focus();}if(event.target.name==='handoff-main')main=event.target.value;});
 panel.addEventListener('click',event=>{if(event.target.closest('[data-handoff-use]'))useVoice(created);if(event.target.closest('[data-handoff-close]')){panel.hidden=true;window.dispatchEvent(new Event('reference-handoff-closed'));}});
 panel.addEventListener('submit',async event=>{event.preventDefault();if(working)return;working=true;const submittedContext=boundContext;const button=panel.querySelector('[type=submit]');button.disabled=true;
  try{created=await api('/reference-voices',{method:'POST',body:{reference_id:main,reference_ids:refs.map(r=>r.id),name,voice_id:voiceID||null,scenario}});await refresh(true);if(submittedContext!==boundContext||submittedContext!==contextKey())return;render();panel.querySelector('[data-handoff-use]').focus();window.workflowUI?.voiceSaved(created);}
  catch(error){if(submittedContext===boundContext){panel.querySelector('[data-handoff-error]').textContent=error.message;button.disabled=false;}}finally{working=false;}
 });
 window.referenceHandoff={dismiss,open(items,{name:initial='',after}={}){if(working)return;boundContext=contextKey();refs=items;main=items[0]?.id;if(!main)return;name=initial;voiceID='';scenario='';created=null;(after||$('voice-pane-references')).after(panel);panel.hidden=false;render();panel.scrollIntoView({block:'center',behavior:'smooth'});panel.querySelector('h2').focus();},useVoice};
})();
