/** Conservative pixel-derived contour for ORA Vision.
 * This is NOT foundation-model segmentation, depth estimation, 3D scanning,
 * or a claim that hidden components match the photographed object.
 * Returns null on low-contrast/ambiguous backgrounds instead of inventing edges.
 * Everything is processed in the user's browser; no image bytes are persisted.
 */
export type ScanBox=[number,number,number,number];
export type ScanPoint=[number,number];
export type PixelFrame={data:Uint8ClampedArray|Uint8Array;width:number;height:number};
export type ScanCrop={x:number;y:number;width:number;height:number};
export type PixelContour={points:ScanPoint[];box:ScanBox;tilt:number;confidence:number};
const clamp=(n:number,min:number,max:number)=>Math.max(min,Math.min(max,n));
const sq=(a:number)=>a*a;
const distance=(a:number[],b:number[])=>Math.sqrt(sq(a[0]-b[0])+sq(a[1]-b[1])+sq(a[2]-b[2]));
function validBox(box:ScanBox):boolean{
 return box.length===4&&box.every(Number.isFinite)&&box[0]>=0&&box[1]>=0&&
  box[2]>=.045&&box[3]>=.045&&box[0]+box[2]<=1.015&&box[1]+box[3]<=1.015;
}
function pointColor(frame:PixelFrame,x:number,y:number):number[]{
 const i=(y*frame.width+x)*4;return [frame.data[i],frame.data[i+1],frame.data[i+2]];
}
function mean(frame:PixelFrame,samples:ScanPoint[]):number[]{
 const values=[0,0,0];
 for(const [x,y] of samples){const p=pointColor(frame,x,y);for(let k=0;k<3;k++)values[k]+=p[k];}
 return values.map(v=>v/Math.max(1,samples.length));
}
function polygonArea(points:ScanPoint[]):number{
 let s=0;
 for(let i=0;i<points.length;i++){const a=points[i],b=points[(i+1)%points.length];s+=a[0]*b[1]-a[1]*b[0];}
 return Math.abs(s)/2;
}
function outerRing(frame:PixelFrame,x0:number,y0:number,x1:number,y1:number):ScanPoint[]{
 const out:ScanPoint[]=[];
 const step=Math.max(1,Math.floor(Math.min(frame.width,frame.height)/96));
 const pad=Math.max(4,Math.round(Math.max(x1-x0,y1-y0)*.22));
 for(let y=Math.max(0,y0-pad);y<=Math.min(frame.height-1,y1+pad);y+=step)
  for(let x=Math.max(0,x0-pad);x<=Math.min(frame.width-1,x1+pad);x+=step){
   if(x<x0-1||x>x1+1||y<y0-1||y>y1+1)out.push([x,y]);
  }
 return out;
}
function interior(frame:PixelFrame,x0:number,y0:number,x1:number,y1:number):ScanPoint[]{
 const out:ScanPoint[]=[];
 const cx=(x0+x1)/2,cy=(y0+y1)/2;
 const dx=(x1-x0)*.18,dy=(y1-y0)*.18;
 for(let y=Math.ceil(cy-dy);y<=Math.floor(cy+dy);y+=2)
  for(let x=Math.ceil(cx-dx);x<=Math.floor(cx+dx);x+=2)
   if(x>=0&&x<frame.width&&y>=0&&y<frame.height)out.push([x,y]);
 return out;
}
/** Largest 4-connected component, with holes preserved as background. */
function component(binary:Uint8Array,width:number,height:number,seedX:number,seedY:number){
 const seen=new Uint8Array(binary.length);
 let best:number[]=[];
 let bestScore=-Infinity;
 const offsets=[1,-1,width,-width];
 for(let i=0;i<binary.length;i++){
  if(binary[i]===0||seen[i])continue;
  const queue=[i];seen[i]=1;
  let sumX=0,sumY=0;
  for(let read=0;read<queue.length;read++){
   const cur=queue[read],x=cur%width,y=Math.floor(cur/width);
   sumX+=x;sumY+=y;
   for(const off of offsets){
    const next=cur+off;
    if(next<0||next>=binary.length||seen[next]||!binary[next])continue;
    if(off===1&&x===width-1||off===-1&&x===0)continue;
    seen[next]=1;queue.push(next);
   }
  }
  const cx=sumX/queue.length,cy=sumY/queue.length;
  const radius=Math.hypot((cx-seedX)/Math.max(1,width),(cy-seedY)/Math.max(1,height));
  const score=queue.length/(1+radius*2.5);
  if(score>bestScore){best=queue;bestScore=score;}
 }
 const result=new Uint8Array(binary.length);
 for(const i of best)result[i]=1;
 return {pixels:best,mask:result};
}
/** Trace exposed edges of real foreground pixels, selecting the outer loop. */
function boundary(mask:Uint8Array,w:number,h:number):ScanPoint[]{
 const adj=new Map<number,number[]>();
 const edge=(ax:number,ay:number,bx:number,by:number)=>{
  const a=ay*(w+1)+ax,b=by*(w+1)+bx;
  let targets=adj.get(a);if(!targets){targets=[];adj.set(a,targets);}targets.push(b);
 };
 for(let y=0;y<h;y++)for(let x=0;x<w;x++){
  const i=y*w+x;if(!mask[i])continue;
  if(y===0||!mask[i-w])edge(x,y,x+1,y);
  if(x===w-1||!mask[i+1])edge(x+1,y,x+1,y+1);
  if(y===h-1||!mask[i+w])edge(x+1,y+1,x,y+1);
  if(x===0||!mask[i-1])edge(x,y+1,x,y);
 }
 let winner:ScanPoint[]=[];let maxArea=0;
 while(adj.size){
  const first=adj.keys().next().value as number;
  let node=first,loop:ScanPoint[]=[];
  for(let steps=0;steps<mask.length*5;steps++){
   loop.push([node%(w+1),Math.floor(node/(w+1))]);
   const nexts=adj.get(node);
   if(!nexts?.length){adj.delete(node);break;}
   const next=nexts.pop()!;
   if(!nexts.length)adj.delete(node);
   node=next;
   if(node===first)break;
  }
  const area=polygonArea(loop);
  if(area>maxArea){winner=loop;maxArea=area;}
 }
 return winner;
}
/**
 * Local three-by-three majority cleanup. Unlike morphological dilation, this
 * never fabricates wide foreground in gaps between individual fingers.
 * Runs only in the already bounded detection region, not on the live video.
 */
function denoiseMask(mask:Uint8Array,w:number,h:number,loX:number,loY:number,hiX:number,hiY:number):Uint8Array{
 const clean=mask.slice();
 for(let y=Math.max(1,loY);y<Math.min(h-1,hiY);y++)
  for(let x=Math.max(1,loX);x<Math.min(w-1,hiX);x++){
   const i=y*w+x;let count=0;
   for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++)count+=mask[i+dy*w+dx];
   // Remove a single salt pixel; close a one-pixel pinhole. Preserve narrow,
   // true extensions if at least three pixels support their connectivity.
   if(mask[i]&&count<=2)clean[i]=0;
   else if(!mask[i]&&count>=8)clean[i]=1;
  }
 return clean;
}
function perpendicular(p:ScanPoint,a:ScanPoint,b:ScanPoint):number{
 const dx=b[0]-a[0],dy=b[1]-a[1],len=dx*dx+dy*dy;
 if(len<1e-8)return Math.hypot(p[0]-a[0],p[1]-a[1]);
 const t=clamp(((p[0]-a[0])*dx+(p[1]-a[1])*dy)/len,0,1);
 return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy);
}
/** Iterative Ramer-Douglas-Peucker: keeps real high-curvature corners/fingers
 * while removing long runs of staircase raster pixels. */
function simplifyOpen(points:ScanPoint[],epsilon:number):ScanPoint[]{
 const n=points.length;
 if(n<4)return points;
 const keep=new Uint8Array(n);keep[0]=1;keep[n-1]=1;
 const stack:Array<[number,number]>=[[0,n-1]];
 while(stack.length){
  const [from,to]=stack.pop()!;
  let max=0,index=-1;
  for(let i=from+1;i<to;i++){
   const d=perpendicular(points[i],points[from],points[to]);
   if(d>max){max=d;index=i;}
  }
  if(index>=0&&max>epsilon){keep[index]=1;stack.push([from,index],[index,to]);}
 }
 return points.filter((_,i)=>keep[i]);
}
/** Bounded low-pass smoothing + curvature-aware simplification, not a generic
 * oval placeholder. Points still come exclusively from the extracted pixels. */
function simplify(points:ScanPoint[],maxPoints=170):ScanPoint[]{
 if(points.length<8)return points;
 const count=points.length;
 const filtered:ScanPoint[]=points.map(([x,y],i)=>{
  const before=points[(i-1+count)%count],after=points[(i+1)%count];
  return [x*.72+(before[0]+after[0])*.14,y*.72+(before[1]+after[1])*.14];
 });
 // Choose a cut far away from the original starting point to avoid creating
 // an arbitrary straight segment at the closing seam.
 let farthest=0,dist=0;
 for(let i=1;i<count;i++){
  const d=sq(filtered[i][0]-filtered[0][0])+sq(filtered[i][1]-filtered[0][1]);
  if(d>dist){dist=d;farthest=i;}
 }
 const chain=[...filtered.slice(farthest),...filtered.slice(0,farthest),filtered[farthest]];
 let epsilon=.38,out=chain;
 for(let attempts=0;attempts<12;attempts++){
  out=simplifyOpen(chain,epsilon);
  if(out.length<=maxPoints+1)break;
  epsilon*=1.34;
 }
 out=out.slice(0,-1); // closing point is implicit in the SVG
 if(out.length<8)return filtered.filter((_,i)=>i%Math.max(1,Math.floor(count/22))===0).slice(0,maxPoints);
 const areaError=Math.abs(polygonArea(out)-polygonArea(points))/Math.max(1,polygonArea(points));
 if(areaError>.075)return filtered.filter((_,i)=>i%Math.ceil(count/maxPoints)===0).slice(0,maxPoints);
 return out.length>maxPoints?out.filter((_,i)=>i%Math.ceil(out.length/maxPoints)===0):out;
}
/** Pixel-only segmentation for distinct subjects on relatively simple backgrounds.
 * The predicted box localizes the target, but the outline is from image pixels. */
export function extractPixelContour(frame:PixelFrame,box:ScanBox):PixelContour|null{
 const {width:w,height:h,data}=frame;
 if(!validBox(box)||w<48||h<48||w*h>150_000||data.length!==w*h*4)return null;
 const x0=Math.floor(box[0]*w),y0=Math.floor(box[1]*h);
 const x1=Math.min(w-1,Math.ceil((box[0]+box[2])*w));
 const y1=Math.min(h-1,Math.ceil((box[1]+box[3])*h));
 const bw=x1-x0,bh=y1-y0;
 if(bw<10||bh<10)return null;
 const fgSamples=interior(frame,x0,y0,x1,y1);
 const bgSamples=outerRing(frame,x0,y0,x1,y1);
 if(fgSamples.length<10||bgSamples.length<12)return null;
 const fg=mean(frame,fgSamples),bg=mean(frame,bgSamples);
 const contrast=distance(fg,bg);
 if(contrast<48)return null;
 // Reject checkerboard / highly inconsistent backgrounds before tracing:
 // they yield attractive but false outlines.
 const backgroundDeviation=bgSamples.reduce((s,[x,y])=>s+sq(distance(pointColor(frame,x,y),bg)),0)/bgSamples.length;
 if(Math.sqrt(backgroundDeviation)>72)return null;
 const padX=Math.max(3,Math.round(bw*.13)),padY=Math.max(3,Math.round(bh*.13));
 const loX=clamp(x0-padX,0,w-1),hiX=clamp(x1+padX,0,w-1);
 const loY=clamp(y0-padY,0,h-1),hiY=clamp(y1+padY,0,h-1);
 const mask=new Uint8Array(w*h);
 for(let y=loY;y<=hiY;y++)for(let x=loX;x<=hiX;x++){
  const color=pointColor(frame,x,y),dF=distance(color,fg),dB=distance(color,bg);
  if(dF*1.12+7<dB&&dF<Math.max(38,contrast*1.25))mask[y*w+x]=1;
 }
 // Discard isolated image noise using a 4-connected foreground component.
 const clean=denoiseMask(mask,w,h,loX,loY,hiX,hiY);
 const result=component(clean,w,h,x0+bw/2,y0+bh/2);
 if(!result.pixels.length)return null;
 const pixels=result.pixels;
 const area=pixels.length,relativeArea=area/(bw*bh);
 if(relativeArea<.22||relativeArea>1.32)return null;
 let minX=w,maxX=0,minY=h,maxY=0,sumX=0,sumY=0;
 for(const i of pixels){const x=i%w,y=Math.floor(i/w);
  minX=Math.min(minX,x);maxX=Math.max(maxX,x);
  minY=Math.min(minY,y);maxY=Math.max(maxY,y);sumX+=x;sumY+=y;
 }
 const fw=maxX-minX+1,fh=maxY-minY+1;
 if(fw<bw*.47||fh<bh*.47)return null;
 if(Math.abs(sumX/area-(x0+x1)/2)>bw*.24||Math.abs(sumY/area-(y0+y1)/2)>bh*.24)return null;
 let perimeterAtCrop=0,boundaryCount=0;
 for(const i of pixels){const x=i%w,y=Math.floor(i/w);
  if(x===loX||x===hiX||y===loY||y===hiY)perimeterAtCrop++;
  if(x===0||y===0||x===w-1||y===h-1)boundaryCount++;
 }
 if(perimeterAtCrop>Math.max(6,area*.055)||boundaryCount>area*.18)return null;
 const outline=boundary(result.mask,w,h);
 if(outline.length<12||polygonArea(outline)<bw*bh*.16)return null;
 const compact=simplify(outline);
 let xx=0,yy=0,xy=0;
 const cx=sumX/area,cy=sumY/area;
 for(const i of pixels){const dx=i%w-cx,dy=Math.floor(i/w)-cy;xx+=dx*dx;yy+=dy*dy;xy+=dx*dy;}
 xx/=area;yy/=area;xy/=area;
 // A symmetric image does not provide a trustworthy principal orientation.
 const discriminant=Math.sqrt(sq(xx-yy)+4*xy*xy),total=xx+yy;
 const axis=total>0&&discriminant/total>.23?.5*Math.atan2(2*xy,xx-yy):Math.PI/2;
 const tilt=clamp(axis-Math.PI/2,-Math.PI/2,Math.PI/2);
 const quality=clamp(.50+.25*(contrast-48)/115+.16*Math.min(1,relativeArea)+
  .08*(1-Math.sqrt(backgroundDeviation)/72),.50,.98);
 return {
  points:compact.map(([x,y])=>[clamp(x/w,0,1),clamp(y/h,0,1)]),
  box:[minX/w,minY/h,fw/w,fh/h],
  tilt:Number.isFinite(tilt)?tilt:0,
  confidence:quality
 };
}
export function relocateContour(shape:PixelContour,from:ScanBox,to:ScanBox):PixelContour|null{
 if(!validBox(from)||!validBox(to))return null;
 const remap=([x,y]:ScanPoint):ScanPoint=>[
  to[0]+(x-from[0])*to[2]/from[2],to[1]+(y-from[1])*to[3]/from[3]];
 const mapped=shape.points.map(remap);
 const ax=to[0]+(shape.box[0]-from[0])*to[2]/from[2];
 const ay=to[1]+(shape.box[1]-from[1])*to[3]/from[3];
 const bw=shape.box[2]*to[2]/from[2],bh=shape.box[3]*to[3]/from[3];
 return {...shape,points:mapped,box:[ax,ay,bw,bh]};
}
export function projectPixelContour(shape:PixelContour,source:ScanCrop,viewport:ScanCrop):PixelContour|null{
 if([source.x,source.y,source.width,source.height,viewport.x,viewport.y,viewport.width,viewport.height]
  .some(n=>!Number.isFinite(n))||source.width<=0||source.height<=0||viewport.width<=0||viewport.height<=0)return null;
 const map=([x,y]:ScanPoint):ScanPoint=>[
  (source.x+x*source.width-viewport.x)/viewport.width,
  (source.y+y*source.height-viewport.y)/viewport.height];
 const points=shape.points.map(map);
 const rect=shape.box;const origin=map([rect[0],rect[1]]);
 const bw=rect[2]*source.width/viewport.width,bh=rect[3]*source.height/viewport.height;
 const left=clamp(origin[0],0,1),top=clamp(origin[1],0,1);
 const right=clamp(origin[0]+bw,0,1),bottom=clamp(origin[1]+bh,0,1);
 if(right-left<.035||bottom-top<.035)return null;
 return {...shape,points,box:[left,top,right-left,bottom-top]};
}
