import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
import ts from 'typescript';
const here=dirname(fileURLToPath(import.meta.url)),cache=new Map();
function load(name){
 if(cache.has(name))return cache.get(name);
 const js=ts.transpileModule(readFileSync(resolve(here,name),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const module={exports:{}};const require=n=>load(n.replace('./','')+'.ts');
 vm.runInNewContext(js,{module,exports:module.exports,require,Math,Map,Set,Number,Float32Array});cache.set(name,module.exports);return module.exports;
}
const {walkthroughFor,TourClock}=load('walkthrough.ts');
const {arrivalAt,currentBox,originInView,ARRIVAL_MS}=load('arrival.ts');
const {VisionPresentation}=load('presentation.ts');
const seeds=JSON.parse(readFileSync(resolve(here,'../../../.vision-evidence/seeds.json'),'utf8'));
const remote=seeds.find(s=>s.canonical_key==='remote_control');
const ctx=()=>new Proxy({},{get:(obj,key)=>obj[key]??(()=>{}),set:(obj,key,value)=>(obj[key]=value,true)});
const opts={progress:1,yaw:.46,pitch:-.22,selected:'',focus:0,zoom:1};
for(const manifest of seeds)test('reviewed tour has real parts, valid sources and finite drawing: '+manifest.canonical_key,()=>{
 const original=JSON.stringify(manifest),tour=walkthroughFor(manifest,'seed');assert.equal(tour.steps.length,3);
 assert.ok(tour.sources.length>0);assert.ok(tour.sources.every(s=>new URL(s.url).protocol==='https:'));
 const scene=new VisionPresentation(manifest);
 for(const step of tour.steps){
  assert.ok(step.parts.every(key=>manifest.parts.some(p=>p.key===key)));
  scene.draw(ctx(),390,410,{...opts,tour:{step,phase:.5}});
  assert.ok(step.parts.every(key=>scene.partBounds(key).every(Number.isFinite)));
 }
 assert.equal(JSON.stringify(manifest),original);
});
test('generated models or missing links cannot inherit an authored tour',()=>{
 assert.equal(walkthroughFor(remote,'generated'),null);assert.equal(walkthroughFor(remote),null);
 assert.equal(walkthroughFor({...remote,parts:remote.parts.filter(p=>p.key!=='pcb')},'seed'),null);
 assert.equal(walkthroughFor({...remote,canonical_key:'not_supported'},'seed'),null);
});
test('single-run playback finishes and remains stopped; replay is explicit',()=>{
 const c=new TourClock(3);c.start();for(let i=0;i<180;i++)c.tick(100);
 assert.equal(c.index,2);assert.equal(c.done,true);assert.equal(c.playing,false);assert.equal(c.phase,1);
 c.tick(100);assert.equal(c.index,2);c.toggle();assert.equal(c.index,0);assert.equal(c.playing,true);
});
test('pause, manual steps and reduced-motion manual mode do not progress by themselves',()=>{
 const c=new TourClock(3);c.start(false);c.tick(100);assert.equal(c.elapsed,0);
 c.toggle();c.tick(90);c.stop();c.tick(80);assert.equal(c.elapsed,90);
 c.seek(2);assert.equal(c.index,2);assert.equal(c.playing,false);assert.equal(c.elapsed,0);
 c.seek(-10);assert.equal(c.index,0);c.seek(99);assert.equal(c.index,2);
});
test('clock ignores nonfinite deltas and bounds suspended-frame jumps',()=>{
 const c=new TourClock(3);c.start();c.tick(NaN);c.tick(Infinity);c.tick(-1);assert.equal(c.elapsed,0);
 c.tick(900000);assert.equal(c.elapsed,100);
});
test('arrival first assembles, then opens, ends exactly and obeys reduced motion',()=>{
 assert.equal(arrivalAt(0).progress,0);assert.equal(arrivalAt(220).mix,0);
 assert.equal(arrivalAt(300).progress,0);assert.ok(arrivalAt(1000).progress>.1);
 assert.equal(arrivalAt(ARRIVAL_MS).active,false);assert.equal(arrivalAt(100,true).progress,1);
 assert.equal(arrivalAt(NaN).active,false);
});
test('origin honours cover crop and invalid surfaces are refused',()=>{
 const box=originInView([.25,.25,.5,.5],640,480,480,480);assert.ok(Math.abs(box[0]-1/6)<1e-8);
 assert.equal(originInView([0,0,1,1],0,480,480,480),null);
 assert.equal(originInView([0,0,.01,.01],640,480,480,480),null);
});
function frame(blank=false){const data=new Float32Array(160*120);data.fill(190);if(!blank)for(let y=24;y<96;y++)for(let x=64;x<96;x++)data[y*160+x]=(x*23+y*37)%110;return {data,width:160,height:120};}
test('one-time reacquisition never invents an anchor after the object disappeared',()=>{
 assert.ok(currentBox(frame(),frame(),[.4,.2,.2,.6]));assert.equal(currentBox(frame(),frame(true),[.4,.2,.2,.6]),null);
 assert.equal(currentBox(null,frame(),[.4,.2,.2,.6]),null);
 assert.equal(currentBox(frame(),frame(),[NaN,0,1,1]),null);
});
test('assembled model starts in detected region and finishes exactly in study space',()=>{
 const scene=new VisionPresentation(remote),c=ctx();
 scene.draw(c,390,500,{...opts,progress:0,origin:{box:[.1,.35,.16,.45],mix:0}});
 const a=scene.partBounds('front_shell');assert.ok((a[0]+a[2])/2<150);
 scene.draw(c,390,500,{...opts,origin:{box:[.1,.35,.16,.45],mix:1}});const atEnd=scene.partBounds('pcb');
 scene.draw(c,390,500,opts);assert.ok(scene.partBounds('pcb').every((v,i)=>Math.abs(v-atEnd[i])<1e-8));
});
