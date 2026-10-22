const {test} = require('node:test');
const assert = require('node:assert/strict');
const {parseBatch, selectionSummary, decodeRoute, decodeText} = require('../web/workflow.js');
const voices = [{id:'global',name:'Narrator',status:'draft'}, {id:'private',name:'Hero',project_id:'project-a',status:'active'}];
const projects = [{id:'project-a'}, {id:'project-b'}];

test('line roles resolve by name or explicit user mapping without speaking the role fields', () => {
  const result = parseBatch('Opening | Narrator | Hello | world\nHero line | Actor | Go!', {voices, projects, roles:{Actor:'private'}, defaults:{project_id:'project-a',candidates:2}});
  assert.deepEqual(result.errors, []);
  assert.equal(result.items[0].text, 'Hello | world');
  assert.equal(result.items[0].voice_id, 'global');
  assert.equal(result.items[1].voice_id, 'private');
  assert.equal(result.totalCandidates, 4);
  assert.ok(result.items.every(row => !Object.hasOwn(row, 'role')));
});
test('ambiguous and unknown roles remain unresolved until the user chooses', () => {
  const result = parseBatch('A | Narrator | text\nB | Unknown | text', {voices:[...voices,{id:'second',name:'Narrator'}]});
  assert.deepEqual(result.unresolved, ['Narrator','Unknown']);
  assert.equal(result.errors.length, 2);
});
test('JSON rows inherit form defaults while explicit per-row choices are retained', () => {
  const result = parseBatch(JSON.stringify({items:[{text:'one'}, {text:'two',voice_id:'private',project_id:'project-a',candidates:1}]}), {voices, projects, defaults:{voice_id:'global',project_id:'project-b',candidates:3}});
  assert.deepEqual(result.errors, []);
  assert.equal(result.items[0].voice_id, 'global');
  assert.equal(result.items[0].project_id, 'project-b');
  assert.equal(result.items[1].project_id, 'project-a');
  assert.equal(result.totalCandidates, 4);
});
test('batch checks prevent project leakage and unavailable or archived voices', () => {
  assert.equal(parseBatch('[{"text":"line","voice_id":"private","project_id":"project-b"}]', {voices,projects}).errors[0].code, 'scope');
  assert.equal(parseBatch('[{"text":"line","voice_id":"gone"}]', {voices}).errors[0].code, 'voice');
  assert.equal(parseBatch('[{"text":"line","voice_id":"old"}]', {voices:[{id:'old',status:'archived'}]}).errors[0].code, 'voice');
});
test('batch limits and malformed input fail before jobs can be submitted', () => {
  assert.equal(parseBatch('bad\n'.repeat(201)).errors[0].code, 'limit');
  assert.equal(parseBatch('{broken').errors[0].code, 'json');
  assert.equal(parseBatch('[{"text":""}]').errors[0].code, 'text');
  assert.equal(parseBatch(JSON.stringify([{text:'x'.repeat(60001)}])).errors[0].code, 'length');
  assert.equal(parseBatch('[{"text":"ok","typo":true}]').errors[0].code, 'field');
  assert.equal(parseBatch('x'.repeat(1000001)).errors[0].code,'large');
});
test('malformed JSON field types cannot crash the preview or resolve prototype names', () => {
  assert.doesNotThrow(()=>parseBatch('[{"text":"ok","clone_mode":"hifi","style":42,"role":{}}]'));
  assert.ok(parseBatch('[{"text":"ok","style":42}]').errors.some(error=>error.code==='type'));
  assert.deepEqual(parseBatch('Title | constructor | text').unresolved,['constructor']);
});
test('Hi-Fi batches require their own transcript and cannot silently add style', () => {
  const defaults = {clone_mode:'hifi',reference_id:'ref'};
  assert.equal(parseBatch('line',{defaults}).errors[0].code,'hifi');
  const references = [{id:'ref',transcript:{text:'Reference words',confirmed:false}}];
  assert.deepEqual(parseBatch('line',{defaults,references}).errors, []); // Draft transcripts remain previews, never approvals.
  assert.equal(parseBatch('line',{defaults:{...defaults,style:'loud'},references}).errors[0].code,'hifiStyle');
});
test('selection summary includes hidden selected items and removes missing records', () => {
  const result = selectionSummary([{id:'a',review:'approved'},{id:'b',review:'pending'}],['a','b','deleted'],['b']);
  assert.deepEqual(result.items.map(row=>row.id),['a','b']);
  assert.equal(result.hidden,1);assert.equal(result.approved,1);
});
test('routes restore only known workspaces and bounded chapter identifiers', () => {
  assert.deepEqual(decodeRoute('#longform/book-id/12'),{page:'longform',id:'book-id',chapter:12});
  assert.deepEqual(decodeRoute('#voices/library'),{page:'voices',pane:'library',id:null});
  assert.deepEqual(decodeRoute('#longform/book-id/-2'),{page:'longform',id:'book-id',chapter:null});
  assert.deepEqual(decodeRoute('#unknown'),{page:'studio'});
  assert.deepEqual(decodeRoute('#voices/%zz'),{page:'studio'});
  assert.deepEqual(decodeRoute('#assets/voices/trash'),{page:'assets',kind:'voices',trash:true,book:''});
});
test('text import handles BOMs and GB2312-compatible bytes without replacement characters', () => {
  assert.equal(decodeText(new Uint8Array([0xff,0xfe,0x2d,0x4e,0x87,0x65])), '中文');
  assert.equal(decodeText(new Uint8Array([0xfe,0xff,0x4e,0x2d,0x65,0x87])), '中文');
  assert.equal(decodeText(new Uint8Array([0xd6,0xd0,0xce,0xc4])), '中文');
  assert.equal(decodeText(new TextEncoder().encode('日本語')), '日本語');
});
