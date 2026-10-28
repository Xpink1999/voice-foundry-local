const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/reference-library.js'),'utf8');
function harness(){
 const nodes=new Map(),events={},requests=[],notices=[];let apiReply=async()=>({});
 class Element{
  constructor(id){this.id=id;this.value='';this.dataset={};this.hidden=false;this.checked=false;this.disabled=false;this.innerHTML='';this.textContent='';this.events={};}
  querySelector(selector){return selector==='.reference-library-actions'?node('actions'):null;}
  querySelectorAll(){return [];}
  addEventListener(type,fn){this.events[type]=fn;}
  scrollIntoView(){} focus(){} pause(){this.paused=true;}load(){this.loaded=true;}
  removeAttribute(name){delete this[name];}
 }
 const node=id=>{if(!nodes.has(id))nodes.set(id,new Element(id));return nodes.get(id);};
 const state={references:Array.from({length:15},(_,i)=>({id:'ref-'+i,name:'Clip '+i,original_name:'source.wav',duration:6,scenario:i%2?'Quiet':'Narration',tags:['demo'],source:'Synthetic source',authorization:'Fixture only',rights_confirmed:true,transcript:{text:'Original '+i,confirmed:true}})),voices:[{id:'voice',name:'Actor',reference_ids:['ref-0']}]};
 const context=vm.createContext({state,$:node,tr:(s,args=[])=>s.replace(/\{(\d+)\}/g,(_,i)=>args[i]),e:s=>String(s??'').replace(/</g,'&lt;'),
  document:{addEventListener:(type,fn)=>events[type]=fn},window:{referenceHandoff:{dismiss(){}},dispatchEvent(){}},
  setOptions:(el,items)=>{if(!items.some(item=>item.id===el.value))el.value='';},empty:(a,b)=>a+' '+b,
  confirm:()=>true,busy:(form,fn)=>async()=>fn(),refresh:async()=>{},toast:(...args)=>notices.push(args),
  api:(url,opts)=>{requests.push({url,opts});return apiReply(url,opts);},previewVoice(){},navigate(){},Event:class{}
 });
 vm.runInContext(source,context);
 return {node,state,requests,notices,context,setReply(fn){apiReply=fn;},edit:id=>context.window.referenceLibrary.edit(id),render:()=>context.window.referenceLibrary.render(true),
  select(id,checked=true){node('voice-pane-references').events.change({target:{dataset:{librarySelect:id},checked}});}};
}
test('reference selection exposes off-page clips and can clear all selections',()=>{
 const h=harness();h.select('ref-0');h.node('reference-next').onclick();
 assert.match(h.node('reference-library-selection').textContent,/1.*隐藏/);
 assert.match(h.node('reference-selected-list').innerHTML,/Clip 0/);
 assert.equal(h.node('reference-selected-details').hidden,false);
 h.node('reference-clear-selected').onclick();
 assert.equal(h.node('reference-create-voice').disabled,true);
 assert.equal(h.node('reference-selected-details').hidden,true);
});
test('filtered references retain visible hidden-selection disclosure',()=>{
 const h=harness();h.select('ref-0');h.node('reference-library-search').value='Quiet';h.node('reference-library-search').oninput();
 assert.match(h.node('reference-library-selection').textContent,/1.*隐藏/);
 h.node('reference-select-page').onclick();
 assert.match(h.node('reference-library-selection').textContent,/8.*1.*隐藏/);
});
test('reference details keep source rights read-only and invalidate transcript confirmation on edit',async()=>{
 const h=harness();h.edit('ref-0');
 assert.equal(h.node('reference-detail-source').textContent,'Synthetic source');
 assert.equal(h.node('reference-detail-authorization').textContent,'Fixture only');
 assert.equal(h.node('reference-detail-confirmed').checked,true);
 assert.equal(h.node('reference-detail-audio').src,'/api/v1/references/ref-0/audio');
 h.node('reference-detail-transcript').value='Corrected transcript';h.node('reference-detail-transcript').oninput();
 assert.equal(h.node('reference-detail-confirmed').checked,false);
 h.node('reference-detail-confirmed').checked=true;h.node('reference-detail-confirmed').onchange();
 await h.node('reference-transcript-form').onsubmit();
 assert.equal(h.requests[0].url,'/references/ref-0/transcript');
 assert.deepEqual(JSON.parse(JSON.stringify(h.requests[0].opts.body)),{text:'Corrected transcript',confirmed:true});
 assert.equal(h.node('reference-transcript-form').dataset.dirty,undefined);
});
test('a completed metadata save for A does not dismiss or overwrite the new B editor',async()=>{
 const h=harness();h.edit('ref-0');h.node('reference-metadata-name').value='A new';h.node('reference-metadata-form').oninput();
 let done;h.setReply(()=>new Promise(resolve=>done=resolve));const pending=h.node('reference-metadata-form').onsubmit();
 h.edit('ref-1');h.node('reference-metadata-name').value='B unsaved';h.node('reference-metadata-form').oninput();done({});await pending;
 assert.equal(h.requests[0].url,'/references/ref-0');assert.equal(h.requests[0].opts.body.name,'A new');
 assert.equal(h.node('reference-metadata-name').value,'B unsaved');assert.equal(h.node('reference-metadata-editor').hidden,false);assert.equal(h.node('reference-metadata-form').dataset.dirty,'1');
});
test('transcript save preserves edits made during submission and cannot confirm a changed draft',async()=>{
 const h=harness();h.edit('ref-0');h.node('reference-detail-transcript').value='First version';h.node('reference-detail-transcript').oninput();
 let done;h.setReply(()=>new Promise(resolve=>done=resolve));const pending=h.node('reference-transcript-form').onsubmit();
 h.node('reference-detail-transcript').value='Second unsaved';h.node('reference-detail-transcript').oninput();done({});await pending;
 assert.equal(h.node('reference-detail-transcript').value,'Second unsaved');assert.equal(h.node('reference-detail-confirmed').checked,false);assert.equal(h.node('reference-transcript-form').dataset.dirty,'1');assert.match(h.node('reference-transcript-status').textContent,/当前修改尚未保存/);
});
test('transcript A finishing after opening B leaves B transcript and status untouched',async()=>{
 const h=harness();h.edit('ref-0');let done;h.setReply(()=>new Promise(resolve=>done=resolve));const pending=h.node('reference-transcript-form').onsubmit();
 h.edit('ref-1');const status=h.node('reference-transcript-status').textContent;done({});await pending;
 assert.equal(h.node('reference-detail-transcript').value,'Original 1');assert.equal(h.node('reference-transcript-status').textContent,status);
 h.node('reference-metadata-cancel').onclick();assert.equal(h.node('reference-detail-audio').src,undefined);assert.equal(h.node('reference-metadata-editor').hidden,true);
});
