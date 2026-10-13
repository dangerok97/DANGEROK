import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
import vm from 'node:vm';
const src=readFileSync(new URL('./pixelContour.ts',import.meta.url),'utf8');
const js=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const mod={exports:{}};
vm.runInNewContext(js,{module:mod,exports:mod.exports});
const {extractPixelContour,projectPixelContour,relocateContour}=mod.exports;
function photo(W=160,H=160,bg=[236,239,240]){
 const data=new Uint8ClampedArray(W*H*4);
 for(let y=0;y<H;y++)for(let x=0;x<W;x++){let i=(y*W+x)*4;data.set([...bg,255],i);}
 return {width:W,height:H,data};
}
function paint(f,contains,color=[38,88,151]){
 for(let y=0;y<f.height;y++)for(let x=0;x<f.width;x++){
  if(!contains(x,y))continue;
  f.data.set([...color,255],(y*f.width+x)*4);
 }
}
test('a visually distinct hand silhouette has pixel-derived fingers, not a bbox rectangle',()=>{
 const f=photo();
 paint(f,(x,y)=>{
  const palm=x>48&&x<111&&y>78&&y<128;
  const fingers=(x>52&&x<62&&y>47&&y<90)||
   (x>68&&x<79&&y>35&&y<90)||
   (x>84&&x<95&&y>42&&y<90)||
   (x>101&&x<111&&y>55&&y<88);
  return palm||fingers;
 });
 const s=extractPixelContour(f,[.25,.19,.48,.65]);
 assert.ok(s,'real high-contrast hand mask should be extractable');
 assert.ok(s.points.length>=18);
 assert.ok(s.points.length<=170);
 assert.ok(s.confidence>=.5);
 assert.ok(s.box[2]>.3&&s.box[3]>.45);
 const distinct=new Set(s.points.map(p=>Math.round(p[0]*160)+','+Math.round(p[1]*160)));
 assert.ok(distinct.size>15,'contour must not collapse to four bbox corners');
});
test('high-contrast asymmetric object has stable non-box edges and rotation',()=>{
 const f=photo(180,180);
 paint(f,(x,y)=>x>38&&x<132&&y>70&&y<110&&
  (x<100||Math.abs(y-90)<Math.max(2,(132-x)*.45)),[189,43,70]);
 const s=extractPixelContour(f,[.2,.32,.57,.37]);
 assert.ok(s);
 assert.ok(s.points.length>12);
 assert.ok(Math.abs(s.tilt)>.3,'horizontal long axis should rotate the origin model');
});
test('flat photo cannot produce a fake scan outline',()=>{
 const f=photo();assert.equal(extractPixelContour(f,[.2,.2,.5,.5]),null);
});
test('noisy multicolor background is rejected rather than advertised as a real contour',()=>{
 const f=photo();
 for(let y=0;y<160;y++)for(let x=0;x<160;x++)
  f.data.set([x%2?230:20,y%2?20:231,(x+y)%3?35:245,255],(y*160+x)*4);
 assert.equal(extractPixelContour(f,[.2,.2,.5,.5]),null);
});
test('retarget and stage crop preserve actual geometry (not the detector rectangle)',()=>{
 const f=photo();
 paint(f,(x,y)=>x>=45&&x<110&&y>=55&&y<112);
 const shape=extractPixelContour(f,[.22,.29,.53,.46]);
 assert.ok(shape);
 const shifted=relocateContour(shape,[.22,.29,.53,.46],[.28,.24,.53,.46]);
 assert.ok(shifted);assert.ok(shifted.box[0]>shape.box[0]+.04);
 const projected=projectPixelContour(shifted,{x:0,y:0,width:160,height:160},
   {x:24,y:0,width:112,height:160});
 assert.ok(projected);assert.ok(projected.box[2]>shifted.box[2]);
 assert.ok(projected.points.every(p=>p.every(Number.isFinite)));
});
