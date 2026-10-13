/** Educational Canvas2D-projected meshes: contour lenses, curved nerve/vessel tubes,
 * and ellipsoids where source geometry is too schematic for contour meshing.
 * These shapes are NOT measured human anatomy and never describe the scanned person.
 * No external model, recording, clinical inference, or runtime provider call.
 */
import type {AnatomyRegion, AtlasLayer} from './anatomyAtlas';
import type {BodyRegion} from './anatomyFocus';

export type VolumePose = { tilt: number; horizontal: number; reliability: 'approximate'|'neutral' };
export type VolumeOptions = {yaw:number; pitch:number; zoom:number; selected:string; explode:number; pose?:VolumePose};
export type VolumeHit = {id:string; label:string; x:number; y:number; radius:number; depth:number; path?:{x:number;y:number}[]};
type P3=[number,number,number];
type Trace = {points:{x:number;y:number}[];closed:boolean};
type Cluster={id:string;label:string;cx:number;cy:number;rx:number;ry:number;rz:number;sub:number;shape:'tube'|'contour'|'ellipsoid';trace?:Trace};
type Triangle={p:[number,number][];z:number;shade:number;part:string;active:boolean;cluster:number};
const SEGMENTS=11,RINGS=8;
const DEPTH:Record<AtlasLayer,number>={skin:.33,muscles:.18,nerves:.22,vessels:.24,organs:.09,bones:-.04,reproductive:.13};
/** Sample the actual M/L/Q/C paths instead of treating Bézier control points as anatomy. */
export function tracePath(path:string):Trace[]{
 const tokens=path.match(/[MLQCHVZmlqchvz]|-?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?/gi)||[];
 const result:Trace[]=[];let i=0,cmd='',x=0,y=0,points:{x:number;y:number}[]=[];
 const flush=(closed:boolean)=>{if(points.length>=2)result.push({points,closed});points=[];};
 const num=():number|null=>{
  if(i>=tokens.length||/^[a-z]$/i.test(tokens[i]))return null;
  const value=Number(tokens[i++]);return Number.isFinite(value)?value:null;
 };
 const add=(nx:number,ny:number)=>{
  if(Number.isFinite(nx)&&Number.isFinite(ny)&&points.length<240){
   x=nx;y=ny;points.push({x,y});
  }
 };
 let operations=0;
 while(i<tokens.length&&operations++<1200){
  if(/^[a-z]$/i.test(tokens[i])){
   cmd=tokens[i++].toUpperCase();
   if(cmd==='Z'){flush(true);cmd='';continue;}
  }
  const previous=i;
  if(cmd==='M'){
   const nx=num(),ny=num();if(nx===null||ny===null)break;
   flush(false);add(nx,ny);cmd='L';
  }else if(cmd==='L'){
   const nx=num(),ny=num();if(nx===null||ny===null)break;add(nx,ny);
  }else if(cmd==='H'){
   const nx=num();if(nx===null)break;add(nx,y);
  }else if(cmd==='V'){
   const ny=num();if(ny===null)break;add(x,ny);
  }else if(cmd==='Q'){
   const ax=num(),ay=num(),bx=num(),by=num();
   if(ax===null||ay===null||bx===null||by===null)break;
   const ox=x,oy=y;
   for(let step=1;step<=6;step++){
    const t=step/6,back=1-t;
    add(back*back*ox+2*back*t*ax+t*t*bx,back*back*oy+2*back*t*ay+t*t*by);
   }
  }else if(cmd==='C'){
   const ax=num(),ay=num(),bx=num(),by=num(),cx=num(),cy=num();
   if(ax===null||ay===null||bx===null||by===null||cx===null||cy===null)break;
   const ox=x,oy=y;
   for(let step=1;step<=8;step++){
    const t=step/8,back=1-t;
    add(back*back*back*ox+3*back*back*t*ax+3*back*t*t*bx+t*t*t*cx,
        back*back*back*oy+3*back*back*t*ay+3*back*t*t*by+t*t*t*cy);
   }
  }else break;
  if(i===previous)break;
 }
 flush(false);
 return result;
}
export function boundsForPath(path:string):{x:number;y:number;w:number;h:number}[]{
 return tracePath(path).map(trace=>{
  const xs=trace.points.map(p=>p.x),ys=trace.points.map(p=>p.y);
  const minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys);
  return {x:minx,y:miny,w:Math.max(5,maxx-minx),h:Math.max(7,maxy-miny)};
 });
}
export function volumeClusters(regions:AnatomyRegion[],layer:AtlasLayer):Cluster[]{
 const all:Cluster[]=[];
 for(const region of regions){
  tracePath(region.d).slice(0,6).forEach((trace,sub)=>{
   const xs=trace.points.map(p=>p.x),ys=trace.points.map(p=>p.y);
   const minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys);
   const width=Math.max(5,maxx-minx),height=Math.max(7,maxy-miny);
   let rx=Math.max(2,width/2),ry=Math.max(4,height/2);
   const longBone=layer==='bones'&&['humerus','forearm_bones','femur','lower_leg','spine'].includes(region.id);
   const shape:'tube'|'contour'|'ellipsoid'=
    (layer==='nerves'||layer==='vessels')&&!trace.closed?'tube':
    trace.closed&&(['organs','muscles','reproductive'].includes(layer)||
     (layer==='bones'&&!longBone))?'contour':'ellipsoid';
   const rz=shape==='tube'?Math.max(2.5,Math.min(5,rx*.4)):
    layer==='organs'?Math.max(7,rx*.48):Math.max(4,rx*.27);
   if(shape==='tube')rx=Math.max(3,Math.min(rx,8));
   all.push({id:region.id,label:region.label,cx:(minx+maxx)/2,cy:(miny+maxy)/2,
    rx,ry,rz,sub,shape,trace:shape==='ellipsoid'?undefined:trace});
  });
 }
 return all.slice(0,60);
}
export function poseFromLandmarks(points?:Record<string,[number,number]>|null):VolumePose{
 if(!points)return {tilt:0,horizontal:0,reliability:'neutral'};
 const left=points.left_shoulder,right=points.right_shoulder;
 if(!left||!right)return {tilt:0,horizontal:0,reliability:'neutral'};
 const dx=right[0]-left[0],dy=right[1]-left[1];
 if(Math.abs(dx)<=.06||Math.abs(dx)>.9||Math.abs(dy)>.45)return {tilt:0,horizontal:0,reliability:'neutral'};
 return {
  tilt:Math.max(-.35,Math.min(.35,Math.atan2(dy,Math.abs(dx))*(dx>0?1:-1))),
  horizontal:Math.max(-.18,Math.min(.18,(left[0]+right[0])/2-.5)),
  reliability:'approximate'
 };
}
const rotate=(point:P3,yaw:number,pitch:number,tilt:number):P3=>{
 let [x,y,z]=point;
 const ct=Math.cos(tilt),st=Math.sin(tilt);
 [x,y]=[x*ct-y*st,x*st+y*ct];
 const cy=Math.cos(yaw),sy=Math.sin(yaw);
 [x,z]=[x*cy+z*sy,-x*sy+z*cy];
 const cp=Math.cos(pitch),sp=Math.sin(pitch);
 return [x,y*cp-z*sp,y*sp+z*cp];
};
const transform=(point:P3,cx:number,cy:number,scale:number,options:VolumeOptions):[number,number,number]=>{
 const [x,y,z]=rotate(point,options.yaw,options.pitch,options.pose?.tilt||0);
 const perspective=2.8/(2.8+z*.5);
 return [cx+x*scale*perspective,cy-y*scale*perspective,z];
};
/** Mesh the sampled outline into a shallow convex lens, or sweep a round tube along a nerve. */
function mesh(cluster:Cluster,layer:AtlasLayer,options:VolumeOptions,view:number[],index:number):P3[][]{
 const [vx,vy,vw,vh]=view;
 const basis=Math.max(vw,vh*.57),centerX=vx+vw/2,centerY=vy+vh/2;
 const toXY=(p:{x:number;y:number}):[number,number]=>[
  (p.x-centerX)/basis*2,-(p.y-centerY)/basis*2];
 const depth=DEPTH[layer]+options.explode*Math.min(index,12)*.16;
 const tris:P3[][]=[];
 if(cluster.shape==='tube'&&cluster.trace){
  const points=cluster.trace.points.filter((_,i)=>i%2===0||i===cluster.trace!.points.length-1);
  const radius=Math.max(2.3,Math.min(4.2,cluster.rz))/basis*2;
  const ringCount=8;
  for(let n=0;n<points.length-1;n++){
   const [ax,ay]=toXY(points[n]),[bx,by]=toXY(points[n+1]);
   const dx=bx-ax,dy=by-ay,length=Math.hypot(dx,dy);
   if(length<.00001)continue;
   const normalX=-dy/length,normalY=dx/length;
   for(let k=0;k<ringCount;k++){
    const a=k/ringCount*Math.PI*2,b=(k+1)/ringCount*Math.PI*2;
    const vertex=(px:number,py:number,theta:number):P3=>[
     px+normalX*radius*Math.cos(theta),
     py+normalY*radius*Math.cos(theta),
     depth+radius*Math.sin(theta)];
    const p1=vertex(ax,ay,a),p2=vertex(bx,by,a),p3=vertex(bx,by,b),p4=vertex(ax,ay,b);
    tris.push([p1,p2,p3],[p1,p3,p4]);
   }
  }
  return tris;
 }
 if(cluster.shape==='contour'&&cluster.trace){
  const original=cluster.trace.points;
  const steps=Math.min(30,original.length);
  const outline=Array.from({length:steps},(_,i)=>original[Math.floor(i*original.length/steps)]);
  const center={x:outline.reduce((n,p)=>n+p.x,0)/outline.length,
                y:outline.reduce((n,p)=>n+p.y,0)/outline.length};
  const thick=Math.min(cluster.rz/basis*2,.17);
  const surface=(p:{x:number;y:number},radius:number,side:number):P3=>{
   const [xx,yy]=toXY({x:center.x+(p.x-center.x)*radius,y:center.y+(p.y-center.y)*radius});
   return [xx,yy,depth+side*thick*Math.sqrt(Math.max(0,1-radius*radius))];
  };
  // Separate front and rear domes create a solid silhouette with curved thickness.
  for(const side of [-1,1]){
   for(let ring=0;ring<3;ring++){
    const inner=ring/3,outer=(ring+1)/3;
    for(let i=0;i<outline.length;i++){
     const a=outline[i],b=outline[(i+1)%outline.length];
     const p1=surface(a,inner,side),p2=surface(a,outer,side);
     const p3=surface(b,outer,side),p4=surface(b,inner,side);
     if(side>0)tris.push([p1,p2,p3],[p1,p3,p4]);
     else tris.push([p1,p3,p2],[p1,p4,p3]);
    }
   }
  }
  return tris;
 }
 const cx=(cluster.cx-centerX)/basis*2,cy=-(cluster.cy-centerY)/basis*2;
 const radiusX=cluster.rx/basis*2,radiusY=cluster.ry/basis*2,radiusZ=cluster.rz/basis*2;
 const ellipsoid=(ring:number,seg:number):P3=>{
  const phi=ring/RINGS*Math.PI,theta=seg/SEGMENTS*Math.PI*2;
  const head=layer==='bones'?(0.77+.23*Math.pow(Math.abs(Math.cos(phi)),2)):1;
  const width=cluster.id==='lungs'?1-.26*Math.cos(phi):
    cluster.id==='heart'?1+.24*Math.cos(phi):head;
  return [cx+radiusX*width*Math.sin(phi)*Math.cos(theta),
          cy+radiusY*Math.cos(phi),
          depth+radiusZ*Math.sin(phi)*Math.sin(theta)];
 };
 for(let j=0;j<RINGS;j++)for(let i=0;i<SEGMENTS;i++){
  const a=ellipsoid(j,i),b=ellipsoid(j+1,i),c=ellipsoid(j+1,i+1),d=ellipsoid(j,i+1);
  tris.push([a,b,c],[a,c,d]);
 }
 return tris;
}
/** Unified blueprint palette for the local fallback anatomy, aligned with ORA 3D. */
function colorLayer(layer:AtlasLayer):[number,number,number]{
 return {
  skin:[139,191,206],muscles:[119,176,201],nerves:[140,210,231],
  vessels:[117,193,224],organs:[138,194,213],bones:[176,220,234],
  reproductive:[135,187,208]
 }[layer] as [number,number,number];
}
function colorPart(layer:AtlasLayer,id:string):[number,number,number]{
 // No artificial red/purple organ surfaces: functional differentiation comes
 // from labels/selection and softly varying blue technical materials.
 const base=colorLayer(layer);
 if(layer==='organs')return /heart|lung|kidney|liver/.test(id)
  ?[148,206,228]:[123,181,205];
 if(layer==='vessels')return /vein|vena|portal/i.test(id)
  ?[109,174,209]:[120,210,237];
 return base;
}

const safe=(v:number)=>Math.max(0,Math.min(255,Math.round(v)));
export function drawVolume(
 ctx:CanvasRenderingContext2D,w:number,h:number,regions:AnatomyRegion[],
 layer:AtlasLayer,region:BodyRegion,options:VolumeOptions,viewBox:string
):VolumeHit[]{
 const view=viewBox.split(/\s+/).map(Number);
 if(view.length!==4||view.some(x=>!Number.isFinite(x)))return [];
 const cs=volumeClusters(regions,layer);
 const cx=w/2+(options.pose?.horizontal||0)*w*.13,cy=h*.49;
 const scale=Math.min(w*.52,h*.78)*Math.max(.85,Math.min(2.2,options.zoom));
 const triangles:Triangle[]=[];
 const hits:VolumeHit[]=[];
 ctx.save();
 // local artificial depth cues, not an image-derived scan
 const aura=ctx.createRadialGradient(cx,cy,6,cx,cy,Math.max(w,h)*.58);
 aura.addColorStop(0,'rgba(28,103,123,0.12)');aura.addColorStop(1,'rgba(0,8,19,0)');
 ctx.fillStyle=aura;ctx.fillRect(0,0,w,h);
 cs.forEach((part,partIndex)=>{
  const center: P3=[(part.cx-(view[0]+view[2]/2))/Math.max(view[2],view[3]*.57)*2,
   -(part.cy-(view[1]+view[3]/2))/Math.max(view[2],view[3]*.57)*2,
   DEPTH[layer]+options.explode*Math.min(partIndex,12)*.16];
  const projected=transform(center,cx,cy,scale,options);
  const rad=Math.max(10,Math.min(90,Math.max(part.rx,part.ry)/Math.max(view[2],view[3]*.57)*scale*2));
  const projectedPath=part.shape==='tube'&&part.trace?part.trace.points.map(p=>{
   const basis=Math.max(view[2],view[3]*.57);
   const local:P3=[(p.x-(view[0]+view[2]/2))/basis*2,
     -(p.y-(view[1]+view[3]/2))/basis*2,center[2]];
   const projectedPoint=transform(local,cx,cy,scale,options);
   return {x:projectedPoint[0],y:projectedPoint[1]};
  }):undefined;
  hits.push({id:part.id,label:part.label,x:projected[0],y:projected[1],radius:rad,depth:projected[2],path:projectedPath});
  const surfaces=mesh(part,layer,options,view,partIndex);
  for(const points of surfaces){
   const pa=transform(points[0],cx,cy,scale,options),pb=transform(points[1],cx,cy,scale,options),pc=transform(points[2],cx,cy,scale,options);
   const ux=points[1][0]-points[0][0],uy=points[1][1]-points[0][1],uz=points[1][2]-points[0][2];
   const vx=points[2][0]-points[0][0],vy=points[2][1]-points[0][1],vz=points[2][2]-points[0][2];
   const nx=uy*vz-uz*vy,ny=uz*vx-ux*vz,nz=ux*vy-uy*vx;
   const magnitude=Math.hypot(nx,ny,nz)||1;
   const shade=Math.max(.16,Math.min(1,(nx*.16+ny*.42+nz*.8)/magnitude*.55+.50));
   triangles.push({p:[[pa[0],pa[1]],[pb[0],pb[1]],[pc[0],pc[1]]],z:(pa[2]+pb[2]+pc[2])/3,shade,
      part:part.id,active:options.selected===part.id,cluster:partIndex});
  }
 });
 triangles.sort((a,b)=>b.z-a.z);
 for(const t of triangles){
  const factor=(.36+t.shade*.76)*(t.active?1.15:1);
  const [r,g,b]=t.active?[172,243,255]:colorPart(layer,t.part);
  ctx.beginPath();ctx.moveTo(t.p[0][0],t.p[0][1]);ctx.lineTo(t.p[1][0],t.p[1][1]);ctx.lineTo(t.p[2][0],t.p[2][1]);ctx.closePath();
  ctx.fillStyle='rgba('+safe(r*factor)+','+safe(g*factor)+','+safe(b*factor)+','+(t.active ? .92 : .75)+')';
  ctx.fill();
  ctx.strokeStyle=t.active?'rgba(145,239,255,.79)':'rgba(68,198,238,.36)';
  ctx.lineWidth=t.active ? 1.2 : .49;ctx.stroke();
 }
 // HUD markers remain clickable and correspond to the 3D geometry above.
 hits.forEach(hit=>{
  if(hit.x<0||hit.x>w||hit.y<0||hit.y>h)return;
  const active=hit.id===options.selected;
  ctx.beginPath();ctx.arc(hit.x,hit.y,active?4.7:2.7,0,2*Math.PI);
  ctx.fillStyle=active?'#b4f5ff':'#64d3f2';ctx.fill();
  if(active){
   ctx.strokeStyle='rgba(83,214,250,.92)';ctx.lineWidth=1;
   ctx.beginPath();ctx.arc(hit.x,hit.y,10.5,0,Math.PI*2);ctx.stroke();
  }
 });
 ctx.restore();return hits;
}
/** Select the closest visible primitive, including thin curved nerves. */
export function hitVolume(hits:VolumeHit[],x:number,y:number):string|null{
 const distance=(hit:VolumeHit)=>{
  if(!hit.path||hit.path.length<2)return Math.hypot(x-hit.x,y-hit.y);
  let best=Infinity;
  for(let i=1;i<hit.path.length;i++){
   const a=hit.path[i-1],b=hit.path[i],dx=b.x-a.x,dy=b.y-a.y;
   const t=Math.max(0,Math.min(1,((x-a.x)*dx+(y-a.y)*dy)/(dx*dx+dy*dy||1)));
   best=Math.min(best,Math.hypot(x-(a.x+t*dx),y-(a.y+t*dy)));
  }
  return best;
 };
 const matches=hits.map(hit=>({hit,d:distance(hit)}))
  .filter(row=>row.d<(row.hit.path?14:Math.max(13,Math.min(60,row.hit.radius))))
  .sort((a,b)=>a.d-b.d);
 return matches[0]?.hit.id||null;
}
