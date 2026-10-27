const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../web/jobs-ui.js'), 'utf8');
const deferred = () => {let resolve; const promise = new Promise(done => {resolve=done;}); return {promise,resolve};};

function harness(api) {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {value:'', hidden:false, disabled:false, innerHTML:'', textContent:''});
    return nodes.get(id);
  };
  const state = {projects:[], selected:new Set(['review-selection'])};
  const reviews = [];
  const context = vm.createContext({
    state, $:node, api, URLSearchParams, batchScope:node('batchScope'),
    tr:(text,args=[])=>text.replace(/\{(\d+)\}/g,(_,i)=>args[i]),
    jobHTML:job=>(state.projects.find(project=>project.id===job.project_id)?.name||job.project_id)+':'+job.id,
    empty:()=>'', selection(){}, toast:assert.fail,
    window:{openReviewScope:scope=>reviews.push(scope),dispatchEvent(){}},Event:class {},
  });
  const start=source.indexOf('  async function load()'), end=source.indexOf('  async function change(',start);
  vm.runInContext("const queue={archived:false,batch:null,page:0,size:50,items:[],selected:new Set(),sequence:0,signature:''};"+source.slice(start,end),context);
  const run=code=>vm.runInContext(code,context);
  return {context,node,state,reviews,run,load:()=>run('load()'),setBatch:id=>run(`setBatch(${JSON.stringify(id)})`)};
}

test('queue rows refresh when initial project metadata arrives or its name changes', async () => {
  const job={id:'job',project_id:'project',status:'succeeded'};
  const h=harness(async()=>({items:[job],total:1}));
  await h.load();
  assert.equal(h.node('job-list').innerHTML,'project:job');
  h.state.projects=[{id:'project',name:'Project name'}];
  await h.load();
  assert.equal(h.node('job-list').innerHTML,'Project name:job');
  h.state.projects[0].name='Renamed project';
  await h.load();
  assert.equal(h.node('job-list').innerHTML,'Renamed project:job');
});

test('batch scope resets incompatible filters, requests a bounded server page and only navigates to review', async () => {
  const urls=[];
  const h=harness(async url=>{urls.push(url);return {items:[],total:0};});
  h.run("queue.archived=true;queue.page=4;queue.selected.add('old')");
  h.node('task-project').value='old-project';h.node('task-status').value='failed';
  await h.setBatch('batch/a');
  const params=new URLSearchParams(urls.at(-1).split('?')[1]);
  assert.equal(params.get('batch_id'),'batch/a');assert.equal(params.get('limit'),'50');
  assert.equal(params.get('offset'),'0');assert.equal(params.get('archived'),'false');
  assert.equal(params.has('project_id'),false);assert.equal(params.has('status'),false);
  assert.equal(h.node('batchScope').hidden,false);assert.equal(h.run('queue.selected.size'),0);
  vm.runInContext(source.split('\n').filter(line=>line.includes("$('task-batch-review').onclick=")).join('\n'),h.context);
  h.node('task-batch-review').onclick();
  assert.equal(h.reviews.length,1);assert.equal(h.reviews[0].batch,'batch/a');
  assert.deepEqual([...h.state.selected],['review-selection']);
  h.run('queue.archived=true');h.node('task-archive-view').value='archived';h.node('task-status').value='succeeded';
  await h.setBatch(null);
  assert.equal(h.node('batchScope').hidden,true);
  const cleared=new URLSearchParams(urls.at(-1).split('?')[1]);
  assert.equal(cleared.has('batch_id'),false);assert.equal(cleared.get('archived'),'true');assert.equal(cleared.get('status'),'succeeded');
});

test('a previous queue response cannot replace a newly selected batch', async () => {
  const requests=[];
  const h=harness(url=>{const pending=deferred();requests.push({url,...pending});return pending.promise;});
  const old=h.load(), current=h.setBatch('new-batch');
  requests[1].resolve({items:[{id:'new',project_id:'p',status:'succeeded'}],total:1});await current;
  requests[0].resolve({items:[{id:'old',project_id:'p',status:'succeeded'}],total:1});await old;
  assert.equal(h.node('job-list').innerHTML,'p:new');
  assert.equal(h.node('task-batch-scope').textContent,'本批任务');
  assert.equal(h.run('queue.batch'),'new-batch');
});
