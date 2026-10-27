const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=name=>fs.readFileSync(require('node:path').join(__dirname,'../web',name),'utf8');

test('opening project review clears stale local scope without clearing explicit selections',async()=>{
  const text=source('app.js'),start=text.indexOf('let reviewScopeEpoch=0;'),end=text.indexOf("document.addEventListener('click',async event",start);
  const nodes=new Map(),pending=[];
  const state={results:[{id:'selected'}],selected:new Set(['selected'])};
  const context=vm.createContext({state,$:id=>{if(!nodes.has(id))nodes.set(id,{value:'old',checked:true});return nodes.get(id);},navigate(){},renderResults(){},window:{dispatchEvent(){}},Event:class{},toast:assert.fail,api:url=>new Promise(resolve=>pending.push({url,resolve}))});
  vm.runInContext(text.slice(start,end),context);
  const old=vm.runInContext("openReviewScope({batch:'old-batch'})",context);
  await vm.runInContext("openReviewScope({project:'new-project'})",context);
  pending.forEach(item=>item.resolve([{id:'old-job'}]));await old;
  assert.equal(state.reviewBatch,null);assert.equal(state.reviewJob,null);
  assert.equal(nodes.get('review-project').value,'new-project');assert.equal(nodes.get('review-selected-only').checked,false);
  assert.deepEqual([...state.selected],['selected']);
});

test('queue scope can close the previous detail and its event stream',()=>{
  const text=source('app.js'),start=text.indexOf('function closeTaskDetail()'),end=text.indexOf('\nlet reviewScopeEpoch',start);
  let closed=0,stopped=0;const panel={hidden:false},state={detailJob:'old',detailToken:1,eventSource:{close(){closed++;}}};
  const close=vm.runInNewContext(text.slice(start,end)+';closeTaskDetail',{state,$:()=>panel,stopLiveAudio(){stopped++;}});close();
  assert.equal(panel.hidden,true);assert.equal(state.detailJob,null);assert.equal(state.eventSource,null);assert.equal(state.detailToken,2);assert.equal(closed,1);assert.equal(stopped,1);
});

test('longform handoff cannot silently reconfigure a different unsubmitted document',()=>{
  const text=source('longform-ui.js'),start=text.indexOf(' function prepareImport('),end=text.indexOf(' async function revealSegment',start);
  const nodes=new Map();let changed=0,questions=0;
  const field=id=>{if(!nodes.has(id))nodes.set(id,{value:'old',dataset:{},files:id==='lf-file'?[{name:'existing.txt'}]:[]});return nodes.get(id);};
  const prepare=vm.runInNewContext(text.slice(start,end)+';prepareImport',{$:field,confirm(){questions++;return false;},tr:value=>value,toast:assert.fail,view:{},library(){changed++;}});
  assert.equal(prepare({file:null,project:'new',voice:'new-voice'}),false);
  assert.equal(questions,1);assert.equal(changed,0);assert.equal(field('lf-project').value,'old');
  field('lf-import-form').dataset.pending='true';let notices=0;
  const uploading=vm.runInNewContext(text.slice(start,end)+';prepareImport',{$:field,toast(){notices++;},tr:value=>value});
  assert.equal(uploading({file:null,project:'another'}),false);assert.equal(notices,1);
});

test('production handoff includes selected scene reference and does not carry style into Hi-Fi',()=>{
  const text=source('workflow-ui.js'),start=text.indexOf('  function productionContext('),end=text.indexOf('  function offerLongform(',start);
  const values={'gen-project':'project','gen-voice':'voice','gen-reference':'scene','gen-engine':'engine','gen-language':'ja','gen-seed':'23','gen-clone-mode':'hifi','gen-style':'keep quiet'};
  const context=vm.runInNewContext(text.slice(start,end)+';productionContext',{$:id=>({value:values[id]})});
  assert.equal(context().reference,'scene');assert.equal(context().project,'project');assert.equal(context().language,'ja');assert.equal(context().seed,'23');assert.equal(context().style,'');
});
