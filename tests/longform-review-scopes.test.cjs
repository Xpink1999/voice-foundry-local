const {test}=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');const path=require('node:path');
const source=name=>fs.readFileSync(path.join(__dirname,'../web',name),'utf8');
function deferred(){let resolve,reject;const promise=new Promise((ok,no)=>{resolve=ok;reject=no;});return {promise,resolve,reject};}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function issueHarness(){
 const callbacks={},nodes=new Map(),requests=[],listeners={};let book='book-a';
 const node=key=>{if(!nodes.has(key))nodes.set(key,{innerHTML:'',textContent:'',disabled:false,replaceChildren(){this.innerHTML='';this.textContent='';},querySelector:node,querySelectorAll:()=>[],prepend(){}});return nodes.get(key);};
 const context=vm.createContext({state:{page:'longform'},$:node,tr:(s,args=[])=>s.replace(/\{(\d+)\}/g,(_,i)=>args[i]),e:String,uiMessage:String,toast:assert.fail,document:{createElement:()=>node('host'),addEventListener:(name,fn)=>listeners[name]=fn},window:{longformUI:{context:()=>({book}),revealSegment:assert.fail},addEventListener:(name,fn)=>callbacks[name]=fn},setInterval:fn=>{callbacks.poll=fn;},api:(url,options)=>{const response=deferred();requests.push({url,options,...response});return response.promise;}});
 vm.runInContext(source('longform-issues-ui.js'),context);
 return {node,requests,callbacks,context,switchBook(next){book=next;return callbacks['voice-context-change']();},clickResolve(id,origin){const target={dataset:{resolveIssue:id,issueBook:origin},disabled:false};return listeners.click({target:{closest:selector=>selector==='[data-resolve-issue]'?target:null}});}};
}
test('switching books clears old issues immediately and rejects the old response',async()=>{
 const h=issueHarness();const pending=h.callbacks.poll();h.node('[data-issue-list]').innerHTML='Old book rows';
 h.switchBook('book-b');assert.equal(h.node('[data-issue-list]').innerHTML,'');assert.equal(h.requests.length,2);
 h.requests[1].resolve({total:1,items:[{segment_no:5,chapter_no:2,note:'B issue',manual:true}]});await tick();assert.match(h.node('[data-issue-list]').innerHTML,/B issue/);
 h.requests[0].resolve({total:1,items:[{segment_no:5,chapter_no:2,note:'A issue',manual:true}]});await pending;assert.doesNotMatch(h.node('[data-issue-list]').innerHTML,/A issue/);
});
test('an old book issue button cannot update the newly selected book',async()=>{
 const h=issueHarness();h.switchBook('book-b');const count=h.requests.length;await h.clickResolve('5','book-a');assert.equal(h.requests.length,count);
 const pending=h.clickResolve('5','book-b');assert.equal(h.requests.at(-1).url,'/longform/books/book-b/segments/5/issue');h.requests.at(-1).resolve({});await pending;
});
test('older page responses cannot replace the current issue page',async()=>{
 const h=issueHarness();const first=h.callbacks.poll();h.requests[0].resolve({total:75,items:[]});await first;
 h.node('[data-issue-more]').onclick();assert.match(h.requests[1].url,/offset=50$/);h.node('[data-issue-prev]').onclick();assert.match(h.requests[2].url,/offset=0$/);
 h.requests[2].resolve({total:75,items:[{segment_no:1,chapter_no:1,note:'First page'}]});await tick();h.requests[1].resolve({total:75,items:[{segment_no:60,chapter_no:1,note:'Old page'}]});await tick();assert.match(h.node('[data-issue-list]').innerHTML,/First page/);assert.doesNotMatch(h.node('[data-issue-list]').innerHTML,/Old page/);assert.equal(h.node('[data-issue-prev]').disabled,true);
});
test('version history keeps the latest requested page when responses arrive out of order',async()=>{
 const nodes=new Map(),requests=[];const node=id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);};
 const context=vm.createContext({context:{kind:'segment',book:'book-a',no:1,info:{}},token:1,historyOffset:20,historyEpoch:0,historyRenderedOffset:0,busy:false,state:{references:[]},$:node,tr:(s,args=[])=>s.replace(/\{(\d+)\}/g,(_,i)=>args[i]),e:String,uiMessage:String,refName:()=>'',segmentURL:()=>'/segment',api:url=>{const response=deferred();requests.push({url,...response});return response.promise;}});
 const text=source('regeneration-ui.js'),start=text.indexOf(' async function versions()'),end=text.indexOf(" $('regeneration-latest').onclick",start);vm.runInContext(text.slice(start,end),context);
 const older=vm.runInContext('versions()',context);context.historyOffset=0;const latest=vm.runInContext('versions()',context);
 const item=attempt=>({attempt,body:JSON.stringify({id:String(attempt),status:'failed',error:'Version '+attempt})});requests[1].resolve({total:40,items:[item(40)]});await latest;requests[0].resolve({total:40,items:[item(20)]});await older;
 assert.match(node('regeneration-versions').innerHTML,/Version 40/);assert.doesNotMatch(node('regeneration-versions').innerHTML,/Version 20/);assert.equal(node('regeneration-latest').hidden,true);
});

test('failed history pages preserve the last displayed position for a usable retry',async()=>{
 const requests=[];const context=vm.createContext({context:{kind:'segment'},token:1,historyOffset:40,historyEpoch:0,historyRenderedOffset:20,segmentURL:()=>'/segment',api:url=>{const response=deferred();requests.push({url,...response});return response.promise;}});
 const text=source('regeneration-ui.js'),start=text.indexOf(' async function versions()'),end=text.indexOf(" $('regeneration-latest').onclick",start);vm.runInContext(text.slice(start,end),context);
 const failed=vm.runInContext('versions()',context);requests[0].reject(Error('offline'));await assert.rejects(failed,/offline/);assert.equal(context.historyOffset,20);
});
