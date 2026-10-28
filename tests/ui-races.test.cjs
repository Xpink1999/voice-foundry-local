const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const read = file => fs.readFileSync(path.join(__dirname, '../web', file), 'utf8');
const deferred = () => {let resolve; const promise = new Promise(done => {resolve=done;}); return {promise,resolve};};
const element = () => ({hidden:false,disabled:false,textContent:'',innerHTML:'',checked:true,replaceChildren(){this.innerHTML='';},scrollIntoView(){}});

test('an older job detail response cannot replace the newly selected job or open a second event source', async () => {
  const source=read('app.js'),start=source.indexOf('async function showJob('),end=source.indexOf("\ndocument.addEventListener('click',async event",start);
  const pending=new Map(),nodes=new Map(),streams=[];
  const state={page:'tasks'};
  class EventSource {constructor(url){this.url=url;this.closed=false;streams.push(this);}close(){this.closed=true;}addEventListener(){}}
  const showJob=vm.runInNewContext(source.slice(start,end)+';showJob',{
    state,$:id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);},
    api:url=>{const item=deferred();pending.set(url,item);return item.promise;},
    stopLiveAudio(){},e:String,tr:label=>label,date:String,EventSource,Event:class {},window:{dispatchEvent(){}},toast:assert.fail,
  });
  const first=showJob('a'),second=showJob('b');
  pending.get('/jobs/b').resolve({title:'B',text:'B text',engine:'test',seed:1});await second;
  pending.get('/jobs/a').resolve({title:'A',text:'A text',engine:'test',seed:1});await first;
  assert.equal(streams.length,1);
  assert.equal(streams[0].url,'/api/v1/jobs/b/stream');
  assert.match(nodes.get('job-detail').innerHTML, /B text/);
  assert.doesNotMatch(nodes.get('job-detail').innerHTML,/A text/);
});

test('leaving task details before the request finishes cannot create a hidden live stream', async () => {
  const source=read('app.js'),start=source.indexOf('async function showJob('),end=source.indexOf("\ndocument.addEventListener('click',async event",start);
  const request=deferred(),state={page:'tasks'};
  const showJob=vm.runInNewContext(source.slice(start,end)+';showJob',{
    state,api:()=>request.promise,stopLiveAudio(){},EventSource:class {constructor(){assert.fail('offscreen stream');}},
  });
  const pending=showJob('a');state.page='studio';request.resolve({});await pending;
});

test('delete preview responses remain tied to the latest requested asset selection', async () => {
  const source=read('assets-ui.js'),start=source.indexOf(' async function preview(items)'),end=source.indexOf(' async function changed(detail)',start);
  const requests=[],nodes=new Map(),dialog={open:false,showModal(){this.open=true;},addEventListener(){}};
  const context=vm.createContext({
    dialog,api:(_url,options)=>{const item=deferred();requests.push({options,item});return item.promise;},
    $:id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);},tr:(label,args=[])=>label.replace(/\{(\d+)\}/g,(_,index)=>args[index]),e:String,identityLabel:item=>item.id,
  });
  vm.runInContext('let pending=null,previewToken=0,previewReady=false,deleting=false;const kinds={results:"results"};'+source.slice(start,end),context);
  const first=vm.runInContext('preview([{kind:"results",id:"A"}])',context);
  const second=vm.runInContext('preview([{kind:"results",id:"B"}])',context);
  const result=name=>({total:1,counts:{results:1},items:[{id:name,name}],note:'',blocked:[]});
  requests[1].item.resolve(result('B'));await second;
  requests[0].item.resolve(result('A'));await first;
  assert.match(nodes.get('asset-preview-items').innerHTML, /B/);
  assert.doesNotMatch(nodes.get('asset-preview-items').innerHTML, /A/);
  assert.equal(vm.runInContext('pending[0].id',context),'B');
  assert.equal(nodes.get('asset-delete-confirm').disabled,false);
});

test('chapter playback ignores a first-audio response after navigation', async () => {
  const source=read('longform-ui.js'),line=source.split('\n').find(line=>line.includes("$('lf-play-chapter').onclick="));
  const request=deferred(),button={isConnected:true},view={sequence:1,book:'book',chapter:1,signatures:{}},state={page:'longform'};
  const start=source.indexOf(' const pendingActions='),end=source.indexOf(" $('lf-resume').onclick=",start);
  vm.runInNewContext(source.slice(start,end)+line,{view,state,$:()=>button,api:()=>request.promise,sync:async()=>{},toast:()=>assert.fail('unexpected error'),playSegment:()=>assert.fail('stale chapter played'),tr:label=>label});
  const pending=button.onclick();state.page='studio';request.resolve({item:{no:1}});await pending;
});

test('submitting a new batch clears a previous single-job detail and its live stream', () => {
  const source=read('workflow-ui.js'),start=source.indexOf('  function batchSubmitted(batch)'),end=source.indexOf('  function offerLongform(',start);
  const nodes=new Map(),pages=[],batches=[];let closed=0,stopped=0;
  const state={detailJob:'old-job',detailToken:1,eventSource:{close(){closed++;}}};
  const submitted=vm.runInNewContext(source.slice(start,end)+';batchSubmitted',{
    state,$:id=>{if(!nodes.has(id))nodes.set(id,{...element(),dispatchEvent(){}});return nodes.get(id);},
    stopLiveAudio(){stopped++;},navigate:page=>pages.push(page),notice(){},tr:label=>label,Event:class {},window:{jobArchiveUI:{setBatch:id=>batches.push(id)}},
  });
  submitted({jobs:['a','b'],batch_id:'new-batch'});
  assert.equal(state.detailJob,null);
  assert.equal(state.eventSource,null);
  assert.equal(nodes.get('job-detail').hidden,true);
  assert.equal(closed,1);assert.equal(stopped,1);assert.deepEqual(pages,['tasks']);assert.deepEqual(batches,['new-batch']);
});

test('a new hash navigation during route loading is applied after the old request finishes', async () => {
  const source=read('workflow-ui.js'),start=source.indexOf('  async function applyRoute()'),end=source.indexOf("  window.addEventListener('popstate'",start);
  const request=deferred(),pages=[],writes=[],scheduled=[],location={hash:'#tasks/old'};
  const context=vm.createContext({
    location,history:{replaceState(_a,_b,value){writes.push(value);}},navigate:page=>pages.push(page),
    showJob:()=>request.promise,VoiceWorkflow:{decodeRoute:hash=>({page:hash.split('/')[0].slice(1),id:hash.split('/')[1]})},
    route:()=>location.hash,clearTimeout(){},setTimeout:fn=>{scheduled.push(fn);return scheduled.length;},notice:assert.fail,
  });
  vm.runInContext('let ready=true,applying=false,routeTimer;'+source.slice(start,end),context);
  const pending=vm.runInContext('applyRoute()',context);
  location.hash='#batch';request.resolve();await pending;
  assert.deepEqual(writes,[]);
  assert.equal(scheduled.length,1);await scheduled[0]();
  assert.deepEqual(pages,['tasks','batch']);assert.deepEqual(writes,['#batch']);
});
