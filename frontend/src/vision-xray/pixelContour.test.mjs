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
 assert.ok(s.points.length>=12,'distinct finger silhouette must keep multiple bends');
 assert.ok(s.points.length<=170);
 const smoothed=new Set(s.points.map(p=>p.join(',')));
 assert.equal(smoothed.size,s.points.length,'no duplicate points after adaptive contour simplification');
 assert.ok(s.points.every(p=>p.every(Number.isFinite)));
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

test('small salt pixels near a real hand do not create spurious silhouette branches',()=>{
 const f=photo();
 paint(f,(x,y)=>(x>=47&&x<=109&&y>=74&&y<=125)||
   (x>=57&&x<=68&&y>=38&&y<=82)||(x>=77&&x<=88&&y>=45&&y<=83));
 for(let y=61;y<111;y+=7)for(let x=39;x<119;x+=13){
  if((x>=47&&x<=109&&y>=74&&y<=125)||
    (x>=57&&x<=68&&y>=38&&y<=82)||
    (x>=77&&x<=88&&y>=45&&y<=83))continue;
  const i=(y*f.width+x)*4;f.data.set([38,88,151,255],i);
 }
 const s=extractPixelContour(f,[.22,.18,.53,.67]);
 assert.ok(s,'visible subject must survive salt-noise cleanup');
 assert.ok(s.points.length<=170);
 assert.ok(s.box[0]>.27&&s.box[0]<.33);
 assert.ok(s.box[2]>.35&&s.box[2]<.48);
});
test('smoothing preserves a stepped asymmetric object without turning it into a rectangle',()=>{
 const f=photo(192,192);
 paint(f,(x,y)=>(x>36&&x<153&&y>65&&y<112)||
   (x>69&&x<106&&y>=111&&y<156),[28,93,145]);
 const s=extractPixelContour(f,[.17,.29,.67,.56]);
 assert.ok(s);
 // The stepped T-shape is deliberately concave. A real curved/stepped
 // contour encloses much less area than its bounding rectangle. Counting
 // extra vertices would reward the very aliasing SCAN 2 is meant to remove.
 const area=Math.abs(s.points.reduce((sum,a,i)=>{
  const b=s.points[(i+1)%s.points.length];return sum+a[0]*b[1]-b[0]*a[1];
 },0))/2;
 const fillRatio=area/(s.box[2]*s.box[3]);
 assert.ok(fillRatio>.36&&fillRatio<.86,'must preserve the nonrectangular captured profile');
 assert.ok(s.points.length>=7&&s.points.length<=170);
});
