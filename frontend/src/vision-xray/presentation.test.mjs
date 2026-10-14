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
  const module={exports:{}};
  const require=name=>load(name.replace('./','')+'.ts');
  vm.runInNewContext(js,{module,exports:module.exports,require,Math,Map,Number});cache.set(name,module.exports);return module.exports;
}
const {VisionPresentation,presentationGeometry,inPolygon,edgeDistance}=load('presentation.ts');
const {VisionGestures,clampZoom,approach}=load('gestures.ts');
const seeds=JSON.parse(readFileSync(resolve(here,'../../../.vision-evidence/seeds.json'),'utf8'));
const remote=seeds.find(s=>s.canonical_key==='remote_control');
const noop=()=>{};
function context(){return new Proxy({}, {get:(obj,key)=>obj[key]??noop,set:(obj,key,value)=>(obj[key]=value,true)});}
const options={progress:1,yaw:.46,pitch:-.22,selected:'',focus:0,zoom:1};
for(const manifest of seeds)test('V2 geometry remains finite and separately addressable: '+manifest.canonical_key,()=>{
  const scene=new VisionPresentation(manifest),ctx=context();
  scene.draw(ctx,390,490,options);
  for(const part of manifest.parts){
    const mesh=presentationGeometry(part);assert.ok(mesh.v.length>20);
    assert.ok(mesh.v.every(v=>v.every(Number.isFinite)));
    assert.ok(mesh.faces.every(f=>f.every(i=>i>=0&&i<mesh.v.length)));
    const bounds=scene.partBounds(part.key);assert.ok(bounds.every(Number.isFinite));assert.ok(bounds[2]>bounds[0]);
  }
});
test('selected battery becomes larger and can be returned to the whole view',()=>{
  const scene=new VisionPresentation(remote),ctx=context();
  scene.draw(ctx,390,470,options);const original=scene.partBounds('battery_a');
  scene.draw(ctx,390,470,{...options,selected:'battery_a',focus:1});const close=scene.partBounds('battery_a');
  assert.ok((close[2]-close[0])>(original[2]-original[0])*2);
  assert.ok(close[1]>50&&close[3]<470);
  assert.equal(scene.hit((close[0]+close[2])/2,(close[1]+close[3])/2),'battery_a');
  scene.draw(ctx,390,470,{...options,selected:'battery_a',focus:0});const restored=scene.partBounds('battery_a');
  assert.ok(restored.every((v,i)=>Math.abs(v-original[i])<.0001));
});
test('six enlarged exploded pieces per page preserve stable pick IDs and selection',()=>{
  const scene=new VisionPresentation(remote),ctx=context();
  const parts=remote.parts;
  assert.equal(parts.length,8);
  const first=parts.slice(0,6).map(p=>p.key),second=parts.slice(6).map(p=>p.key);
  scene.draw(ctx,390,490,{...options,visibleKeys:first});
  for(const part of first){const b=scene.partBounds(part);assert.ok(b&&b.every(Number.isFinite));}
  for(const part of second)assert.equal(scene.partBounds(part),undefined);
  const firstBounds=scene.partBounds(first[0]);
  assert.ok(firstBounds&&firstBounds[0]>=0&&firstBounds[2]<=390);
  scene.draw(ctx,390,490,{...options,visibleKeys:second});
  for(const part of second)assert.ok(scene.partBounds(part));
  for(const part of first)assert.equal(scene.partBounds(part),undefined);
  scene.draw(ctx,390,490,options);
  for(const part of parts)assert.ok(scene.partBounds(part.key));
  scene.draw(ctx,390,490,{...options,visibleKeys:second,selected:first[0],focus:1});
  assert.ok(scene.partBounds(first[0]),'focused part remains visible even outside previous page');
});
test('hollow / diagonal shapes do not pick their empty rectangular corners',()=>{
  assert.equal(inPolygon(1,1,[[0,5],[5,0],[10,5],[5,10]]),false);
  assert.equal(inPolygon(5,5,[[0,5],[5,0],[10,5],[5,10]]),true);
  assert.equal(edgeDistance(5,2,[0,0],[10,0]),2);
  const scene=new VisionPresentation(remote);scene.draw(context(),390,500,options);
  assert.equal(scene.hit(-100,-100),null);
});
test('geometry keeps stable part identifiers and never mutates saved manifests',()=>{
  const serialized=JSON.stringify(remote);new VisionPresentation(remote).draw(context(),390,400,{...options,selected:'pcb',focus:1});
  assert.equal(JSON.stringify(remote),serialized);
});
test('single pointer drag rotates and cannot select a part on release',()=>{
  const g=new VisionGestures();g.down(1,0,0);const d=g.move(1,50,20);
  assert.ok(d.yaw>0&&d.pitch>0);assert.equal(g.up(1,50,20),false);
  g.down(2,8,8);assert.equal(g.up(2,8,8),true);
});
test('pinch scales without rotating or accidental tap, including lifted second finger',()=>{
  const g=new VisionGestures();g.down(1,100,100);g.down(2,200,100);
  const d=g.move(2,240,100);assert.equal(d.zoomFactor,1.4);assert.equal(d.yaw,0);
  assert.equal(g.up(2,240,100),false);assert.equal(g.up(1,100,100),false);
});
test('cancelled pointers, tiny pinches and reset stay safe',()=>{
  const g=new VisionGestures();g.down(1,0,0);assert.equal(g.up(1,0,0,true),false);
  g.down(1,0,0);g.down(2,0,0);assert.ok(Number.isFinite(g.move(2,1,0).zoomFactor));
  g.clear();assert.equal(g.up(1,0,0),false);
});
test('zoom is finite and bounded; reduced motion immediately reaches target',()=>{
  assert.equal(clampZoom(Infinity),1);assert.equal(clampZoom(NaN),1);
  assert.equal(clampZoom(99),3.2);assert.equal(clampZoom(-2),.65);
  assert.equal(approach(0,1,16,true),1);
  assert.ok(Math.abs(approach(approach(0,1,16),1,16)-approach(0,1,32))<1e-9);
});

test('all 160 families fit perspective overview and focused parts at default zoom',()=>{
 assert.equal(seeds.length,160);
 for(const [w,h] of [[390,490],[844,310],[1440,800]])for(const m of seeds){
  const scene=new VisionPresentation(m);
  for(const [yaw,pitch] of [[.46,-.22],[1.1,.5],[-.8,-.6]]){
   const settings={...options,yaw,pitch};scene.draw(context(),w,h,settings);
   for(const p of m.parts){const b=scene.partBounds(p.key);assert.ok(b[0]>=0&&b[1]>=0&&b[2]<=w&&b[3]<=h,m.canonical_key+' overview '+p.key+' '+JSON.stringify(b));}
   for(const p of m.parts){scene.draw(context(),w,h,{...settings,selected:p.key,focus:1});const b=scene.partBounds(p.key);assert.ok(b[0]>=0&&b[1]>=0&&b[2]<=w&&b[3]<=h,m.canonical_key+' focus '+p.key+' '+JSON.stringify(b));}
  }
 }
});
