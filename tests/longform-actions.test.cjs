const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../web/longform-ui.js'),'utf8');
function deferred(){let resolve,reject;const promise=new Promise((ok,no)=>{resolve=ok;reject=no;});return {promise,resolve,reject};}
function harness(){
 const nodes=new Map(),requests=[],notices=[];
 const node=id=>{if(!nodes.has(id))nodes.set(id,{disabled:false,isConnected:true,checked:false,value:''});return nodes.get(id);};
 const view={book:'book-a',chapter:3,sequence:10,bookData:{chapters:5},signatures:{},segmentOffset:0};
 let syncs=0;const context=vm.createContext({view,state:{page:'longform'},$:node,tr:s=>s,uiMessage:s=>s,toast:(...args)=>notices.push(args),sync:async()=>{syncs++;},api:(url,options)=>{const response=deferred();requests.push({url,options,...response});return response.promise;},playSegment:assert.fail,openChapter:assert.fail});
 const start=source.indexOf(' const ensureReady='),end=source.indexOf(" $('lf-export-form').onsubmit",start);vm.runInContext(source.slice(start,end),context);
 const click=id=>node(id).onclick({currentTarget:node(id)});
 return {context,node,view,requests,notices,click,syncs:()=>syncs};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('retry all keeps the originating book through navigation and blocks duplicate submission',async()=>{
 const h=harness(),first=h.click('lf-retry-failed'),duplicate=h.click('lf-retry-failed');await duplicate;
 assert.equal(h.requests.length,1);assert.equal(h.requests[0].url,'/longform/books/book-a/retry-failed');
 h.view.book='book-b';h.view.chapter=8;h.view.sequence++;
 h.requests[0].resolve({});await tick();assert.equal(h.requests[1].url,'/longform/books/book-a/resume');
 h.requests[1].resolve({});await first;assert.equal(h.syncs(),0);assert.equal(h.node('lf-retry-failed').disabled,false);
});
test('retrying a segment resumes only its original chapter after navigation',async()=>{
 const h=harness();h.context.target={dataset:{lfRetry:'17'},disabled:false,isConnected:true};
 const start=source.indexOf('if(target.dataset.lfRetry)'),end=source.indexOf('if(target.dataset.lfRedo',start);
 const pending=vm.runInContext('(async()=>{'+source.slice(start,end)+'})()',h.context);
 assert.equal(h.requests[0].url,'/longform/books/book-a/segments/17/retry');h.view.book='book-b';h.view.chapter=4;h.view.sequence++;
 h.requests[0].resolve({});await tick();assert.equal(h.requests[1].url,'/longform/books/book-a/resume');assert.equal(h.requests[1].options.body.chapter_no,3);
 h.requests[1].resolve({});await pending;
});
test('failed operations release their guard so the same book can retry',async()=>{
 const h=harness();let pending=h.click('lf-resume');h.requests[0].reject(Error('Temporary failure'));await pending;
 assert.equal(h.notices[0][0],'Temporary failure');assert.equal(h.node('lf-resume').disabled,false);assert.equal(h.syncs(),1);
 pending=h.click('lf-resume');assert.equal(h.requests.length,2);h.requests[1].resolve({});await pending;
});
test('late next-chapter responses cannot open a chapter in the newly selected book',async()=>{
 const h=harness();const start=source.indexOf(" $('lf-next-chapter').onclick="),end=source.indexOf('\n function prepareImport',start);vm.runInContext(source.slice(start,end),h.context);
 const pending=h.click('lf-next-chapter');h.view.book='book-b';h.view.sequence++;
 h.requests[0].resolve({items:[{no:4}],total:2});await pending;assert.equal(h.view.chapter,3);assert.equal(h.node('lf-next-chapter').disabled,false);
});
test('issue location stops before applying an old page offset after book switching',async()=>{
 const h=harness(),chapterOpen=deferred();h.context.openChapter=()=>{h.view.sequence++;return chapterOpen.promise;};
 const start=source.indexOf(' async function revealSegment('),end=source.indexOf('\n window.longformUI=',start);vm.runInContext(source.slice(start,end),h.context);
 const pending=vm.runInContext('revealSegment(17)',h.context);h.requests[0].resolve({chapter_no:3,offset:25});await tick();
 h.view.book='book-b';h.view.sequence++;chapterOpen.resolve();await pending;assert.equal(h.view.segmentOffset,0);assert.equal(h.syncs(),0);
});
