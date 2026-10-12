import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
import ts from 'typescript';
const here=dirname(fileURLToPath(import.meta.url));
const source=readFileSync(resolve(here,'anatomyVolume.ts'),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const module={exports:{}};
vm.runInNewContext(code,{module,exports:module.exports,Math,Number,Array});
const {tracePath,boundsForPath,volumeClusters,poseFromLandmarks,hitVolume,drawVolume}=module.exports;
const regions=[
 {id:'heart',label:'Cuore',d:'M156 176 Q143 158 136 177 Q132 194 160 218 Q188 194 184 177 Q175 159 162 176 Z'},
 {id:'lungs',label:'Polmoni',d:'M130 153 Q143 137 152 161 L150 230 Q119 231 122 184 Z M168 161 Q181 137 194 153 L198 184 Q201 231 170 230 Z'}
];
test('all visible body shapes are split into bounded independent 3D volumes',()=>{
 const pieces=boundsForPath(regions[1].d);
 assert.equal(pieces.length,2);
 assert.ok(pieces.every(b=>b.w>0&&b.h>0));
 const clusters=volumeClusters(regions,'organs');
 assert.equal(clusters.length,3);
 assert.ok(clusters.every(c=>c.rz>0&&c.rx>0&&c.ry>0));
});
test('one-time orientation is approximate when shoulder coordinates are valid',()=>{
 const pose=poseFromLandmarks({left_shoulder:[.7,.3],right_shoulder:[.3,.34]});
 assert.equal(pose.reliability,'approximate');assert.ok(Math.abs(pose.tilt)>.04);
 assert.equal(poseFromLandmarks(null).reliability,'neutral');
 assert.equal(poseFromLandmarks({left_shoulder:[0,0],right_shoulder:[0,0]}).reliability,'neutral');
});
test('touch selection chooses nearest volume marker',()=>{
 const hits=[{id:'a',x:30,y:20,radius:15,depth:1},{id:'b',x:100,y:140,radius:18,depth:2}];
 assert.equal(hitVolume(hits,31,19),'a');
 assert.equal(hitVolume(hits,99,139),'b');
 assert.equal(hitVolume(hits,300,400),null);
});
test('procedural 3D projects shaded triangles without provider or external assets',()=>{
 let faces=0;
 const ctx={
  save(){},restore(){},fillRect(){},beginPath(){},moveTo(){},lineTo(){},closePath(){},
  fill(){faces++},stroke(){},arc(){},
  createRadialGradient(){return {addColorStop(){}}},
  set fillStyle(_v){},set strokeStyle(_v){},set lineWidth(_v){}
 };
 const hits=drawVolume(ctx,320,520,regions,'organs','full_body',
 {yaw:.28,pitch:-.1,zoom:1,selected:'heart',explode:.05},
 '0 10 320 586');
 assert.ok(faces>100);assert.equal(hits.length,3);
 assert.ok(hits.every(hit=>Number.isFinite(hit.x)&&Number.isFinite(hit.y)));
});

test('sampled quadratic outlines become a closed organ contour, not its control-point bounding box',()=>{
 const curves=tracePath('M10 20 Q20 0 30 20 Q20 40 10 20 Z');
 assert.equal(curves.length,1);assert.equal(curves[0].closed,true);
 assert.ok(curves[0].points.length>8);
 const box=boundsForPath('M10 20 Q20 0 30 20 Q20 40 10 20 Z')[0];
 assert.ok(box.y>1&&box.y<=10,'true curve extrema should be sampled, not control points');
 const parts=volumeClusters([{id:'heart',label:'Cuore',d:'M10 20 Q20 0 30 20 Q20 40 10 20 Z'}],'organs');
 assert.equal(parts[0].shape,'contour');
});
test('branched open nerves use individually swept 3D tubes rather than whole-path ellipsoids',()=>{
 const parts=volumeClusters([{id:'vagus',label:'Vago',d:'M155 83 Q146 124 149 163 Q142 201 149 256 M165 83 Q174 124 171 163 Q178 201 171 256'}],'nerves');
 assert.equal(parts.length,2);
 assert.ok(parts.every(part=>part.shape==='tube'&&part.trace?.points.length>8));
 assert.notEqual(parts[0].cx,parts[1].cx);
});
test('tube picking follows the projected nerve rather than its remote bounding centre',()=>{
 const hits=[{id:'nerve',x:60,y:80,radius:10,depth:0,path:[{x:10,y:10},{x:190,y:10}]},
             {id:'heart',x:90,y:100,radius:15,depth:0}];
 assert.equal(hitVolume(hits,170,14),'nerve');
 assert.equal(hitVolume(hits,170,90),null);
});
test('explode spacing actually separates anatomy components in depth',()=>{
 const noop=()=>{};
 const ctx={save:noop,restore:noop,fillRect:noop,beginPath:noop,moveTo:noop,lineTo:noop,closePath:noop,fill:noop,stroke:noop,arc:noop,
 createRadialGradient(){return {addColorStop:noop}},set fillStyle(_v){},set strokeStyle(_v){},set lineWidth(_v){}};
 const a=drawVolume(ctx,320,520,regions,'organs','full_body',{yaw:.28,pitch:-.1,zoom:1,selected:'heart',explode:0},'0 10 320 586');
 const b=drawVolume(ctx,320,520,regions,'organs','full_body',{yaw:.28,pitch:-.1,zoom:1,selected:'heart',explode:.7},'0 10 320 586');
 assert.equal(a.length,b.length);
 assert.ok(a.slice(1).some((point,i)=>Math.abs(point.depth-b[i+1].depth)>.02));
});
