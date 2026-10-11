import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
function load(name){
 const code=ts.transpileModule(readFileSync(new URL(name,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const m={exports:{}};vm.runInNewContext(code,{module:m,exports:m.exports,setTimeout,clearTimeout,Promise,Math});return m.exports;
}
const {CameraTorch,cameraCrop,sameCrop,clampCameraZoom,drawCameraCrop}=load('./cameraControls.ts');
const {filterCatalog}=load('./catalogSearch.ts');
const plain=value=>JSON.parse(JSON.stringify(value));
function track({supported=true,fail=false,ignore=false,sync=false}={}){
 const t={readyState:'live',light:false,calls:[],getCapabilities:()=>({torch:supported}),getSettings:()=>({torch:t.light}),stop:()=>{t.readyState='ended';t.light=false;},applyConstraints:constraint=>{
  const value=constraint.advanced[0].torch;t.calls.push(value);
  if(sync)throw new Error('sync');
  if(fail)return Promise.reject(new Error('device unavailable'));
  if(!ignore&&t.readyState==='live')t.light=value;
  return Promise.resolve();
 }};return t;
}
test('actual track confirmation controls torch indicator and off',async()=>{
 const t=track(),events=[],c=new CameraTorch(t,s=>events.push(s));
 assert.equal(c.snapshot().on,false);await c.toggle();assert.equal(c.snapshot().on,true);assert.equal(t.light,true);
 await c.toggle();assert.equal(c.snapshot().on,false);assert.equal(t.light,false);assert.ok(events.some(s=>s.busy));
});
test('unsupported torch is never offered as a functioning command',async()=>{
 const t=track({supported:false}),c=new CameraTorch(t,()=>{});await c.toggle();assert.equal(t.calls.length,0);assert.equal(c.snapshot().supported,false);
});
test('missing or throwing capability API has conservative fallback',()=>{
 for(const getter of [undefined,()=>{throw new Error('not supported');}]){
  const t=track();t.getCapabilities=getter;const c=new CameraTorch(t,()=>{});assert.equal(c.snapshot().supported,false);
 }
});
test('capability arrays are supported without user-agent sniffing',()=>{
 const t=track();t.getCapabilities=()=>({torch:[true,false]});assert.equal(new CameraTorch(t,()=>{}).snapshot().supported,true);
});
test('ignored torch constraint cannot produce a false on indicator',async()=>{
 const t=track({ignore:true}),c=new CameraTorch(t,()=>{});await c.toggle();assert.equal(c.snapshot().on,false);assert.ok(c.snapshot().message);assert.equal(c.snapshot().supported,false);
});
test('rejected and synchronous constraints are reported, not unhandled',async()=>{
 for(const args of [{fail:true},{sync:true}]){
  const c=new CameraTorch(track(args),()=>{});await c.toggle();assert.equal(c.snapshot().on,false);assert.equal(c.snapshot().busy,false);assert.ok(c.snapshot().message);
 }
});
test('stop while torch command pending never updates a later session',async()=>{
 let finish;const t=track(),events=[];const orig=t.applyConstraints;
 t.applyConstraints=value=>value.advanced[0].torch?new Promise(r=>{finish=r;}):orig(value);
 const c=new CameraTorch(t,s=>events.push(s));const op=c.toggle();await Promise.resolve();
 c.dispose();const count=events.length;finish();await op;
 assert.equal(t.readyState,'ended');assert.equal(t.light,false);assert.equal(events.length,count);assert.ok(t.calls.includes(false));
});
test('torch requests are serialised and double tap does not re-enter',async()=>{
 let finish;const t=track();t.applyConstraints=()=>new Promise(r=>{finish=r;});
 const c=new CameraTorch(t,()=>{}),one=c.toggle();await Promise.resolve();await c.toggle();finish();await one;c.dispose();
});
test('digital zoom is bounded and nonfinite input is rejected safely',()=>{
 assert.equal(clampCameraZoom(7),3);assert.equal(clampCameraZoom(-1),1);assert.equal(clampCameraZoom(NaN),1);
});
test('cover crop and 2x zoom match the displayed central source area',()=>{
 assert.deepEqual(plain(cameraCrop(640,480,480,480,1)),{x:80,y:0,width:480,height:480});
 assert.deepEqual(plain(cameraCrop(640,480,480,480,2)),{x:200,y:120,width:240,height:240});
 const c=cameraCrop(1920,1080,390,600,3);assert.ok(Math.abs(c.width/c.height-390/600)<1e-8);assert.ok(c.x>=0&&c.y>=0);
 assert.ok(sameCrop(c,c));assert.equal(sameCrop(c,cameraCrop(1920,1080,600,390,3)),false);
});
test('capture uses crop for source coordinates, not only CSS magnification',()=>{
 let args;drawCameraCrop({drawImage:(...a)=>args=a},'video',{x:200,y:120,width:240,height:240},480,480);
 assert.deepEqual(args,['video',200,120,240,240,0,0,480,480]);
 assert.throws(()=>cameraCrop(0,480,390,600,1));
});
test('catalogue search uses accents, multiple words, aliases and category',()=>{
 const entries=[{canonical_key:'usb_flash_drive',title:'Chiavetta USB',category:'Elettronica',aliases:['thumb_drive']},{canonical_key:'capped_pen',title:'Penna con cappuccio',category:'Scrivania'}];
 assert.equal(filterCatalog(entries,'thumb drive').length,1);assert.equal(filterCatalog(entries,'CHÍAVETTA usb','Elettronica').length,1);
 assert.equal(filterCatalog(entries,'penna','Elettronica').length,0);assert.equal(filterCatalog(entries,'','Tutti').length,2);
 assert.equal(filterCatalog(entries,'inesistente').length,0);
});
