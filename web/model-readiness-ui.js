/* Every generation entry uses the same metadata-only check. Playback stays available. */
(()=>{
 'use strict';
 const fallback=()=>state.models.find(model=>model.is_default)?.id || state.models[0]?.id;
 const blocker=engine=>VoiceWorkflow.modelBlockers([{engine:engine || fallback()}],state.models,state.voices)[0];
 function ensure(engine){const problem=blocker(engine);if(problem)throw Error(uiMessage(problem.reason));}
 function check(form,engine,baseDisabled=!!form?.dataset.pending){
  if(!form)return;
  form.dataset.readinessEngine=engine || fallback() || '';
  const problem=blocker(engine);let notice=form.querySelector('[data-model-readiness]');
  if(!notice){notice=document.createElement('p');notice.dataset.modelReadiness='';notice.className='reference-warnings';notice.setAttribute('role','status');form.querySelector('[type=submit]').before(notice);}
  notice.hidden=!problem;
  if(problem){notice.replaceChildren(document.createTextNode(uiMessage(problem.reason)+' '));const open=document.createElement('button');open.type='button';open.className='text-link';open.textContent=tr('模型与系统');open.onclick=()=>navigate('settings');notice.append(open);}
  form.querySelector('[type=submit]').disabled=baseDisabled || !!problem;
 }
 function sync(){
  if(!state.ready)return;
  check($('generate-form'),$('gen-engine').value);check($('design-voice-form'),$('design-engine').value);
  const voice=state.voices.find(v=>v.id===$('lf-voice')?.value);check($('lf-import-form'),$('lf-engine').value||voice?.engine);window.regenerationUI?.refreshReadiness();
 }
 document.addEventListener('submit',event=>{if(event.target.dataset.readinessEngine===undefined)return;try{ensure(event.target.dataset.readinessEngine);}catch(error){event.preventDefault();event.stopImmediatePropagation();toast(error.message,true);}},true);
 document.addEventListener('change',event=>{if(['gen-engine','gen-voice','design-engine','lf-project','lf-voice','lf-engine'].includes(event.target.id))sync();});
 window.addEventListener('voice-page-change',sync);window.addEventListener('voice-data-ready',sync);document.addEventListener('workflow-form-settled',sync);
 window.modelReadiness={blocker,check,ensure};setInterval(sync,2500);sync();
})();
