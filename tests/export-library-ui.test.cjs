const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../web/export-library-ui.js'), 'utf8');
const escape = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const packageOf = (id, entries) => ({id, created_at:'2026-10-28', options:{format:'wav', draft:true, adapter:'standard'}, results:entries});
const entry = (result_id, file = `audio/${result_id}.wav`) => ({result_id, file, sha256:'retained-hash', review:'pending'});
function harness(state) {
  const nodes = [], events = {}, opened = [], notices = [];
  class Element {
    constructor(tag) {this.tagName=tag; this.children=[]; this.listeners={}; this.dataset={}; this.details=[]; this.innerHTML=''; this.value=''; nodes.push(this);}
    append(...children) {this.children.push(...children);}
    before(node) {this.previous=node;}
    closest() {return this.parent||null;}
    replaceWith(node) {this.replacedBy=node;}
    setAttribute(name,value) {this[name]=value;}
    addEventListener(name,fn) {this.listeners[name]=fn;}
    querySelectorAll() {return this.details;}
    focus() {this.focused=true;}
  }
  const list = new Element('div'), form=new Element('form'), panel=new Element('div');form.parent=panel;
  const paging = {page:0, scope:null, slice(kind, items, scope) {assert.equal(kind,'exports'); if(scope!==this.scope){this.page=0;this.scope=scope;} return items.slice(this.page*20,this.page*20+20);}};
  const context=vm.createContext({state, $:id=>id==='export-form'?form:list, document:{createElement:tag=>new Element(tag)},
    window:{libraryPaging:paging,addEventListener:(name,fn)=>events[name]=fn},
    tr:(text,args=[])=>text.replace(/\{(\d+)\}/g,(_,index)=>args[index]), e:escape,
    labels:{pending:'Pending review',approved:'Approved'}, date:String,
    empty:(title,body)=>`<div class="empty">${escape(title)} ${escape(body)}</div>`,
    toast:(...args)=>notices.push(args),openReviewScope:scope=>opened.push(scope),
  });
  vm.runInContext(source,context);
  return {list,paging,opened,notices,events,nodes,render:()=>vm.runInContext('renderExports()',context),
    search:nodes.find(node=>node.id==='export-history-search'),
    click:id=>list.listeners.click({target:{closest:()=>({dataset:{exportReturn:id}})}})};
}

test('manifest entries show actual files, source titles and projects without mutating package metadata', () => {
  const state={exports:[packageOf('package-a',[entry('a'),entry('missing','audio/retained-original.wav')])],
    results:[{id:'a',title:'Opening line',project_id:'project'}],projects:[{id:'project',name:'Game dialogue'}]};
  const before=JSON.stringify(state), ui=harness(state);
  assert.match(ui.list.innerHTML,/Opening line/);
  assert.match(ui.list.innerHTML,/Game dialogue/);
  assert.match(ui.list.innerHTML,/audio\/retained-original.wav/);
  assert.match(ui.list.innerHTML,/1 条原结果不可回看/);
  assert.equal((ui.list.innerHTML.match(/data-export-package=/g)||[]).length,1);
  assert.equal(JSON.stringify(state),before);
});

test('search covers every package entry and resets paging while refresh preserves search and expanded contents', () => {
  const state={exports:Array.from({length:22},(_,index)=>packageOf('p'+index,[entry('r'+index)])),
    results:Array.from({length:22},(_,index)=>({id:'r'+index,title:'Line '+index,project_id:'project'})),projects:[{id:'project',name:'Dialogue'}]};
  state.exports[21].results.push(entry('missing','audio/Needle-file.wav'));
  const ui=harness(state), originalSearch=ui.search;
  ui.paging.page=1;ui.render();assert.equal((ui.list.innerHTML.match(/data-export-package=/g)||[]).length,2);
  ui.search.value='dialogue needle';ui.search.listeners.input();
  assert.equal(ui.paging.page,0);assert.match(ui.list.innerHTML,/data-export-package="p21"/);
  assert.equal((ui.list.innerHTML.match(/data-export-package=/g)||[]).length,1);
  ui.list.details=[{dataset:{exportContents:'p21'},open:true}];
  state.results[21].title='Updated title';ui.events['voice-data-ready']();
  assert.equal(ui.search,originalSearch);assert.equal(ui.search.value,'dialogue needle');
  assert.match(ui.list.innerHTML,/Updated title/);
  assert.match(ui.list.innerHTML,/data-export-contents="p21" open/);
  ui.search.value='no such filename';ui.search.listeners.input();assert.match(ui.list.innerHTML,/没有匹配的导出记录/);
});

test('return action rechecks surviving source IDs at click time and never includes unrelated or deleted candidates', () => {
  const state={exports:[packageOf('pack',[entry('a'),entry('b'),entry('b'),entry('deleted')])],
    results:[{id:'a',title:'A'},{id:'deleted',title:'Deleted',deleted_at:'today'},{id:'unrelated',title:'Other'}],projects:[]};
  const ui=harness(state);
  state.results=state.results.filter(result=>result.id!=='a');state.results.push({id:'b',title:'B'});
  const before=JSON.stringify(state);ui.click('pack');
  assert.equal(ui.opened.length,1);assert.deepEqual(Array.from(ui.opened[0].ids),['b']);
  assert.equal(JSON.stringify(state),before);
  state.results=[];ui.click('pack');
  assert.equal(ui.opened.length,1);assert.match(ui.list.innerHTML,/data-export-return="pack" disabled/);
  assert.match(ui.notices[0][0],/无法回看/);
});

test('unavailable source data remains searchable by actual package filename and cannot be opened', () => {
  const state={exports:[packageOf('pack',[entry('missing','audio/Original-voice.wav')])],results:[],projects:[]};
  const ui=harness(state);ui.search.value='Original-voice';ui.search.listeners.input();
  assert.match(ui.list.innerHTML,/Original-voice.wav/);assert.match(ui.list.innerHTML,/原结果不可用，无法回看/);
  assert.match(ui.list.innerHTML,/data-export-return="pack" disabled/);
});

test('titles, filenames, project names and export IDs cannot inject markup or download paths', () => {
  const state={exports:[packageOf('pack/"x',[entry('a','audio/<img src=x>.wav')])],
    results:[{id:'a',title:'<script>bad()</script>',project_id:'p'}],projects:[{id:'p',name:'<img onerror=bad()> '}]};
  const ui=harness(state);
  assert.doesNotMatch(ui.list.innerHTML,/<script>|<img/);
  assert.match(ui.list.innerHTML,/&lt;script&gt;/);
  assert.match(ui.list.innerHTML,/\/exports\/pack%2F%22x\/download/);
});
