const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const read=name=>fs.readFileSync(path.join(__dirname,'../web',name),'utf8');
const tr=(text,args=[])=>text.replace(/\{(\d+)\}/g,(_,i)=>args[i]);
const deferred=()=>{let resolve;return {promise:new Promise(r=>resolve=r),resolve};};
const node=()=>({classList:{remove(){},add(){}},value:'',dataset:{},disabled:false,hidden:false,innerHTML:'',textContent:'',setAttribute(){},removeAttribute(){},replaceChildren(){this.innerHTML='';},scrollIntoView(){},pause(){}});
test('unchanged select options preserve live selection and do not rebuild the focused control',()=>{
 const src=read('app.js'),start=src.indexOf('function setOptions('),end=src.indexOf('function updateSelectors(',start);
 const set=vm.runInNewContext(src.slice(start,end)+';setOptions',{e:String});let writes=0,html='',value='';const select={get value(){return value},set value(v){value=v},get innerHTML(){return html},set innerHTML(v){writes++;html=v;value=''}};
 const items=[{id:'a',name:'A'},{id:'b',name:'B'}];set(select,items,'Choose');select.value='b';set(select,items,'Choose');assert.equal(writes,1);assert.equal(select.value,'b');set(select,[{id:'b',name:'Renamed'}],'Choose');assert.equal(writes,2);assert.equal(select.value,'b');
});
test('an older voice history response cannot overwrite the newly opened editor bindings',async()=>{
 const src=read('app.js'),start=src.indexOf('async function editVoice('),end=src.indexOf("$('new-voice').onclick",start),nodes=new Map(),requests=new Map(),bound=[];
 const state={voices:['a','b'].map(id=>({id,name:id,tags:[],languages:['en']}))};const field=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id)};
 const edit=vm.runInNewContext(src.slice(start,end)+';editVoice',{state,$:field,tr,e:String,date:String,previewReference(){},toast:assert.fail,api:url=>{const r=deferred();requests.set(url,r);return r.promise},window:{confirm:()=>true,referenceUI:{refreshBindings:voice=>bound.push(voice.id)}}});
 const a=edit('a'),b=edit('b');requests.get('/voices/b/versions').resolve([{version:2,name:'B',updated_at:'now'}]);await b;requests.get('/voices/a/versions').resolve([{version:1,name:'A',updated_at:'now'}]);await a;
 assert.deepEqual(bound,['b']);assert.equal(field('voice-name').value,'b');assert.match(field('voice-history').innerHTML,/B/);assert.doesNotMatch(field('voice-history').innerHTML,/A/);
});
test('busy form acknowledges the saved snapshot without claiming newer edits were saved',async()=>{
 const src=read('app.js'),start=src.indexOf('function busy('),end=src.indexOf('function navigate(',start),listeners={},button=node(),feedback=node(),pending=deferred();
 const form={dataset:{dirty:'true'},querySelector:q=>q==='button[type="submit"]'?button:feedback,setAttribute(){},removeAttribute(){},addEventListener:(type,fn)=>listeners[type]=fn,removeEventListener:type=>delete listeners[type],dispatchEvent(){}};
 const busy=vm.runInNewContext(src.slice(start,end)+';busy',{tr,Event:class{},toast:assert.fail});const submit=busy(form,()=>pending.promise);const work=submit({preventDefault(){}});listeners.input();pending.resolve();await work;
 assert.equal(form.dataset.changedWhilePending,'true');assert.match(feedback.textContent,/当前修改尚未保存/);assert.equal(form.dataset.pending,undefined);assert.deepEqual(Object.keys(listeners),[]);
});
function assetsHarness(view){
 const src=read('assets-ui.js'),start=src.indexOf(' const scopeKey='),end=src.indexOf(' async function open(',start),nodes=new Map(),requests=[];
 const field=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id)};
 const context=vm.createContext({view,kinds:{results:'Results',voices:'Voices',longform_chapters:'Chapters'},$:field,tr,e:String,labels:{draft:'Draft'},date:String,identityLabel:item=>item.id,empty:(a,b)=>a+b,setOptions(){},selection(){field('asset-delete-selected').disabled=!view.selected.size;},api:url=>{const r=deferred();requests.push({url,...r});return r.promise;},URLSearchParams,window:{dispatchEvent(){}},Event:class{}});
 vm.runInContext(src.slice(start,end),context);return {load:()=>vm.runInContext('load()',context),field,requests};
}
test('switching asset category while fetching keeps old rows inert and rejects the stale response',async()=>{
 const view={kind:'results',deleted:false,book:'',offset:0,selected:new Map(),items:[],busy:false};const h=assetsHarness(view);h.field('asset-list').innerHTML='Old row';const first=h.load();assert.equal(h.field('asset-list').inert,true);
 view.kind='voices';await h.load();h.requests[0].resolve({items:[{kind:'results',id:'old',name:'OLD RESPONSE'}],total:1});await first;assert.equal(h.requests.length,2);assert.equal(h.field('asset-list').inert,true);assert.doesNotMatch(h.field('asset-list').innerHTML,/OLD RESPONSE/);
 h.requests[1].resolve({items:[{kind:'voices',id:'new',name:'New voice',status:'draft'}],total:1});await new Promise(setImmediate);assert.match(h.field('asset-list').innerHTML,/New voice/);assert.equal(h.field('asset-list').inert,false);assert.equal(view.items[0].kind,'voices');
});
test('asset chapters without a selected book clear stale selections and pagination',async()=>{
 const view={kind:'longform_chapters',deleted:false,book:'',offset:0,selected:new Map([['old',{}]]),items:[{id:'old'}],busy:false};const h=assetsHarness(view);h.field('asset-pagination').innerHTML='Old pages';const work=h.load();h.requests[0].resolve({items:[]});await work;
 assert.equal(view.items.length,0);assert.equal(view.selected.size,0);assert.equal(h.field('asset-pagination').innerHTML,'');assert.equal(h.field('asset-delete-selected').disabled,true);
});
test('a late design result cannot replace the newer design task',async()=>{
 const src=read('voice-workspace.js'),start=src.indexOf(' async function updateDesign()'),end=src.indexOf(' async function sync()',start),request=deferred(),view={designJob:'a'},nodes=new Map();
 const update=vm.runInNewContext(src.slice(start,end)+';updateDesign',{view,api:()=>request.promise,$:id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id)},tr,e:String,uiMessage:String,labels:{}});
 const work=update();view.designJob='b';request.resolve({id:'a',status:'succeeded',results:['old']});await work;assert.equal(nodes.size,0);assert.equal(view.designRendered,undefined);
});
test('export completion banner is cleared when the chosen candidate set changes',()=>{
 const src=read('export-tasks-ui.js'),start=src.indexOf(' function checkSelection()'),end=src.indexOf(' async function sync()',start);let cleared=0;
 const context=vm.createContext({state:{selected:new Set(['b'])},$:()=>({replaceChildren(){cleared++}})});vm.runInContext("let watched='export-a',watchedIDs=['a'];"+src.slice(start,end)+';checkSelection()',context);assert.equal(vm.runInContext('watched',context),null);assert.equal(cleared,1);
});

test('missing encoder preserves native WAV and rejects transformations before submitting',()=>{
 const src=read('export-support-ui.js'),start=src.indexOf(' const message='),end=src.indexOf(' function render()',start),context=vm.createContext({available:false,state:{results:[{id:'a',sample_rate:24000,channels:1},{id:'b',sample_rate:48000,channels:1}]},tr});vm.runInContext(src.slice(start,end),context);
 const original={result_ids:['a'],format:'wav'};context.body=original;const native=vm.runInContext('ensure(body)',context);assert.equal(native.sample_rate,24000);assert.equal(native.channels,1);assert.equal(original.sample_rate,undefined);
 for(const body of [{result_ids:['a'],format:'mp3'},{result_ids:['a'],format:'wav',normalize:true},{result_ids:['a'],format:'wav',sample_rate:48000},{result_ids:['a','b'],format:'wav'}]){context.body=body;assert.throws(()=>vm.runInContext('ensure(body)',context),/FFmpeg/);}
 vm.runInContext('available=true',context);context.body={result_ids:['a'],format:'ogg'};assert.equal(vm.runInContext('ensure(body)',context).format,'ogg');
});

test('encoder UI leaves uppercase WAV available and applies native settings to the actual option value',async()=>{
 const src=read('export-support-ui.js'),events={},created=[],select={value:'WAV',options:['WAV','MP3','FLAC','OGG'].map(value=>({value,disabled:false})),closest(){return {after(){}}},dispatchEvent(){}};
 const fields={'export-format':select,'export-rate':{value:'48000',options:[{value:'24000'},{value:'48000'}]},'export-channels':{value:'2'},'export-normalize':{checked:true},'export-trim':{checked:true}};
 const context=vm.createContext({state:{page:'exports',selected:new Set(['a']),results:[{id:'a',sample_rate:24000,channels:1}]},$:id=>fields[id]||created.find(e=>e.id===id),tr,api:async()=>({ffmpeg_available:false}),toast:assert.fail,Date,Event:class{},window:{addEventListener:(type,fn)=>events[type]=fn},document:{addEventListener(){},createTextNode:text=>({text}),createElement:tag=>{const e={tag,children:[],setAttribute(){},append(...children){this.children.push(...children)}};created.push(e);return e;}}});
 vm.runInContext(src,context);await events['voice-page-change']();assert.equal(select.options[0].disabled,false);assert.equal(select.options[1].disabled,true);
 created.find(e=>e.tag==='button').onclick();assert.equal(select.value,'WAV');assert.equal(fields['export-rate'].value,'24000');assert.equal(fields['export-channels'].value,'1');assert.equal(fields['export-normalize'].checked,false);assert.equal(fields['export-trim'].checked,false);
});

test('an export started during codec lookup waits for the same availability request',async()=>{
 const src=read('export-support-ui.js'),start=src.indexOf(' async function refreshAvailability('),end=src.indexOf(" document.addEventListener('submit'",start),request=deferred();let requests=0,settled=false;
 const context=vm.createContext({api:()=>{requests++;return request.promise},render(){},Date});vm.runInContext('let loading=false,checkedAt=0,availabilityPromise=null,available=null;'+src.slice(start,end),context);
 const first=vm.runInContext('refreshAvailability()',context),second=vm.runInContext('refreshAvailability()',context).then(()=>settled=true);await Promise.resolve();assert.equal(requests,1);assert.equal(settled,false);request.resolve({ffmpeg_available:false});await Promise.all([first,second]);assert.equal(vm.runInContext('available',context),false);
});
