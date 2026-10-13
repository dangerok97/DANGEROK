import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
import vm from 'node:vm';
const source=readFileSync(new URL('./anatomyCameraAnchor.ts',import.meta.url),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const mod={exports:{}};
vm.runInNewContext(js,{module:mod,exports:mod.exports});
const {projectAnatomyAnchor,sameAnatomyAnchor}=mod.exports;
const photo={box:[.20,.18,.35,.53],sourceWidth:128,sourceHeight:128,
 capturedCrop:{x:0,y:0,width:128,height:128},photo:true,zoom:1};
test('square photo reprojects after stage grows from landscape to portrait',()=>{
 const landscape=projectAnatomyAnchor(photo,{x:0,y:28,width:128,height:72});
 const portrait=projectAnatomyAnchor(photo,{x:28,y:0,width:72,height:128});
 assert.ok(landscape&&portrait);
 assert.ok(Math.abs((landscape[1]+landscape[3]/2)-(portrait[1]+portrait[3]/2))>.01);
 assert.ok(Math.abs((landscape[0]+landscape[2]/2)-(portrait[0]+portrait[2]/2))>.05);
 assert.ok(landscape.every(Number.isFinite)&&portrait.every(Number.isFinite));
 assert.ok(landscape[0]>=0&&portrait[0]>=0&&landscape[0]+landscape[2]<=1);
 assert.ok(portrait[0]+portrait[2]<=1);
});
test('live crop is remapped from its captured video coordinates',()=>{
 const capture={box:[.2,.3,.4,.4],sourceWidth:1280,sourceHeight:720,
  capturedCrop:{x:0,y:0,width:1280,height:720},photo:false,zoom:1};
 const same=projectAnatomyAnchor(capture,{x:0,y:0,width:1280,height:720});
 const newCrop=projectAnatomyAnchor(capture,{x:280,y:0,width:720,height:720});
 assert.deepEqual(JSON.parse(JSON.stringify(same)),[.2,.3,.4,.4]);
 assert.ok(newCrop&&newCrop[2]>.4);
 assert.ok(newCrop[0]>=0&&newCrop[0]+newCrop[2]<=1);
});
test('out of frame boxes fail closed; unchanged boxes preserve React state',()=>{
 assert.equal(projectAnatomyAnchor(photo,{x:1000,y:1000,width:100,height:100}),null);
 assert.ok(sameAnatomyAnchor([.2,.1,.3,.4],[.2001,.1001,.3,.4]));
 assert.ok(!sameAnatomyAnchor([.2,.1,.3,.4],[.25,.1,.3,.4]));
});
