const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname,'../web/theme.js'),'utf8');
function browser({stored=null,dark=false,storageDisabled=false}={}) {
  const listeners={},mediaListeners={};
  const media={matches:dark,addEventListener:(type,fn)=>mediaListeners[type]=fn};
  const root={dataset:{}};
  const storage=new Map(stored?[['voice-foundry-theme',stored]]:[]);
  const context={document:{documentElement:root},localStorage:{getItem:key=>{if(storageDisabled)throw Error('disabled');return storage.get(key)||null;},setItem:(key,value)=>{if(storageDisabled)throw Error('disabled');storage.set(key,value);}},CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},window:{matchMedia:()=>media,addEventListener:(type,fn)=>listeners[type]=fn,dispatchEvent:event=>listeners[event.type]?.(event)}};
  vm.runInNewContext(source,context);
  return {root,storage,context,media:dark=>{media.matches=dark;mediaListeners.change();},storageEvent:value=>listeners.storage({key:'voice-foundry-theme',newValue:value})};
}
test('automatic mode follows browser/system color changes live',()=>{const b=browser();assert.equal(b.root.dataset.theme,'light');b.media(true);assert.equal(b.root.dataset.theme,'dark');b.media(false);assert.equal(b.root.dataset.theme,'light');});
test('manual palette persists, overrides media, and automatic mode restores following',()=>{const b=browser({dark:true});b.context.window.voiceTheme.set('light');b.media(true);assert.equal(b.root.dataset.theme,'light');assert.equal(b.storage.get('voice-foundry-theme'),'light');const reloaded=browser({stored:b.storage.get('voice-foundry-theme'),dark:true});assert.equal(reloaded.root.dataset.theme,'light');b.context.window.voiceTheme.set('system');assert.equal(b.root.dataset.theme,'dark');b.media(false);assert.equal(b.root.dataset.theme,'light');});
test('cross-tab preference changes synchronize',()=>{const b=browser();b.storageEvent('dark');assert.equal(b.root.dataset.theme,'dark');b.storageEvent(null);assert.equal(b.root.dataset.theme,'light');});
test('disabled storage and invalid preferences have safe usable defaults',()=>{const b=browser({storageDisabled:true,dark:true});b.context.window.voiceTheme.set('light');assert.equal(b.root.dataset.theme,'light');assert.equal(browser({stored:'invalid',dark:true}).root.dataset.theme,'dark');});
