import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
import ts from 'typescript';
const here=dirname(fileURLToPath(import.meta.url));
function load(name){
  const source=readFileSync(resolve(here,name),'utf8');
  const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const module={exports:{}};vm.runInNewContext(js,{module,exports:module.exports,Float32Array,Math});return module.exports;
}
const {geometry,coverBox}=load('scene.ts');
const {ObjectTracker}=load('tracking.ts');
const fixtures=JSON.parse(readFileSync(resolve(here,'../../../.vision-evidence/seeds.json'),'utf8'));
for(const manifest of fixtures)test('separable geometry: '+manifest.canonical_key,()=>{
  for(const part of manifest.parts){
    const m=geometry(part);assert.ok(m.v.length>20);assert.ok(m.e.length>10);
    assert.ok(m.v.every(v=>v.length===3&&v.every(Number.isFinite)));
    assert.ok(m.e.every(edge=>edge.every(i=>i>=0&&i<m.v.length)));
  }
});
test('cover mapping accounts for crop offsets',()=>{
  const box=coverBox([.25,.25,.5,.5],640,480,480,480);
  assert.ok(Math.abs(box[0]-1/6)<1e-8);assert.ok(Math.abs(box[2]-2/3)<1e-8);
});
function frame(shift=0,blank=false){
  const width=160,height=120,data=new Float32Array(width*height);data.fill(180);
  if(!blank)for(let y=24;y<96;y++)for(let x=64+shift;x<96+shift;x++)data[y*width+x]=((x-shift)*23+y*37)%110;
  return {width,height,data};
}
test('tracks translated texture and hides when object disappears',()=>{
  const tracker=new ObjectTracker(frame(),[.4,.2,.2,.6]);
  assert.ok(tracker.update(frame()).visible);
  const moved=tracker.update(frame(5));assert.ok(moved.visible);assert.ok(Math.abs(moved.box[0]-(.4+5/160))<.02);
  assert.equal(tracker.update(frame(0,true)).visible,false);
});
test('uniform frames do not become object anchors',()=>{
  const tracker=new ObjectTracker(frame(0,true),[.4,.2,.2,.6]);assert.equal(tracker.update(frame(0,true)).visible,false);
});
