const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8');

test('waveform preview uses small peaks without downloading or decoding complete audio', async () => {
  const draw = [], urls = [];
  const canvas = {dataset:{wave:'result-id'}, getContext:()=>({clearRect(){},fillRect(...args){draw.push(args);}})};
  const script = source.slice(source.indexOf('async function loadWave('), source.indexOf('\nfunction updateSelection'));
  const load = vm.runInNewContext(script+';loadWave', {
    fetch:async url=>{urls.push(url);return {ok:true,json:async()=>({peaks:Array(190).fill(.5)})};},
    AudioContext:class {constructor(){throw Error('full-audio decoding is forbidden for a waveform');}},
    getComputedStyle:()=>({getPropertyValue:()=> '#fff'}),document:{documentElement:{}},tr:s=>s,toast:assert.fail
  });
  await load(canvas);
  assert.deepEqual(urls, ['/api/v1/results/result-id/waveform']);
  assert.equal(draw.length,190);
  assert.equal(canvas.dataset.loaded,'yes');
});

test('closing live preview releases its audio context and invalidates queued work', () => {
  let closed = 0;
  const state = {live:true, audioEpoch:4, nextTime:90, audioContext:{close(){closed++;return Promise.resolve();}}};
  const script = source.slice(source.indexOf('function stopLiveAudio('),source.indexOf("\nwindow.addEventListener('pagehide'"));
  const stop = vm.runInNewContext(script+';stopLiveAudio',{state});
  stop();
  assert.equal(closed,1);
  assert.equal(state.audioContext,null);
  assert.equal(state.live,false);
  assert.equal(state.audioEpoch,5);
  assert.equal(state.nextTime,0);
});
