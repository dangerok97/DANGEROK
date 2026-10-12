/** Original procedural anatomy volume - actual 3D ellipsoid surface meshes projected to Canvas2D.
 * Scientific fidelity is NOT implied. This is neither CT/MRI nor a person's internal geometry.
 * No shader downloads, WebGL fingerprints, photographs, external assets or AI calls.
 */
import type {AnatomyRegion, AtlasLayer} from './anatomyAtlas';
import type {BodyRegion} from './anatomyFocus';

export type VolumePose = { tilt: number; horizontal: number; reliability: 'approximate'|'neutral' };
export type VolumeOptions = {yaw:number; pitch:number; zoom:number; selected:string; explode:number; pose?:VolumePose};
export type VolumeHit = {id:string; label:string; x:number; y:number; radius:number; depth:number};
type P3=[number,number,number];
type Cluster={id:string;label:string;cx:number;cy:number;rx:number;ry:number;rz:number;sub:number};
type Triangle={p:[number,number][];z:number;shade:number;part:string;active:boolean;cluster:number};
const MAX_VERTICES=1500,SEGMENTS=11,RINGS=8;
const DEPTH:Record<AtlasLayer,number>={skin:.33,muscles:.18,nerves:.22,organs:.09,bones:-.04,reproductive:.13};
const parseCoords=(s:string):number[] => (s.match(/-?\d+(?:\.\d+)?/g)||[]).map(Number);
export function boundsForPath(path:string):{x:number;y:number;w:number;h:number}[]{
 const pieces=path.split(/(?=M\s*-?\d)/i).filter(x=>x.trim());
 return pieces.flatMap(piece=>{
  const nums=parseCoords(piece);if(nums.length<4||nums.length%2)return [];
  const xs:number[]=[],ys:number[]=[];for(let i=0;i<nums.length;i+=2){xs.push(nums[i]);ys.push(nums[i+1]);}
  const minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys);
  if(![minx,maxx,miny,maxy].every(Number.isFinite))return [];
  return [{x:minx,y:miny,w:Math.max(5,maxx-minx),h:Math.max(7,maxy-miny)}];
 });
}
export function volumeClusters(regions:AnatomyRegion[],layer:AtlasLayer):Cluster[]{
 const all:Cluster[]=[];
 for(const region of regions){
  const boxes=boundsForPath(region.d);
  boxes.slice(0,5).forEach((b,sub)=>{
   let rx=Math.max(2,b.w/2),ry=Math.max(4,b.h/2);
   // Narrow lines (nerves, tendons and long bones) become rounded tubes,
   // broad muscles and organs become volumetric ellipsoids.
   const slim=layer==='nerves'||(layer==='bones'&&rx<10);
   const rz=slim?Math.max(3,Math.min(8,rx*.5)):layer==='organs'?Math.max(8,rx*.58):Math.max(4,rx*.28);
   if(slim)rx=Math.max(3,Math.min(rx,8));
   all.push({id:region.id,label:region.label,cx:b.x+b.w/2,cy:b.y+b.h/2,rx,ry,rz,sub});
  });
 }
 return all.slice(0,60);
}
const rad=(degrees:number)=>degrees*Math.PI/180;
export function poseFromLandmarks(points?:Record<string,[number,number]>|null):VolumePose{
 if(!points)return {tilt:0,horizontal:0,reliability:'neutral'};
 const left=points.left_shoulder,right=points.right_shoulder;
 if(!left||!right)return {tilt:0,horizontal:0,reliability:'neutral'};
 const dx=right[0]-left[0],dy=right[1]-left[1];
 if(dx<=.06||dx>.9||Math.abs(dy)>.45)return {tilt:0,horizontal:0,reliability:'neutral'};
 return {
  tilt:Math.max(-.35,Math.min(.35,Math.atan2(dy,dx))),
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
function mesh(cluster:Cluster,layer:AtlasLayer,region:BodyRegion,options:VolumeOptions,view:number[]):P3[][]{
 const [vx,vy,vw,vh]=view;
 const viewCenterX=vx+vw/2,viewCenterY=vy+vh/2;
 const basis=Math.max(vw,vh*.57);
 const cx=(cluster.cx-viewCenterX)/basis*2.0;
 const cy=-(cluster.cy-viewCenterY)/basis*2.0;
 const radiusX=cluster.rx/basis*2,radiusY=cluster.ry/basis*2,radiusZ=cluster.rz/basis*2;
 const depth=DEPTH[layer] + options.explode;
 const ellipsoid=(ring:number,seg:number):P3=>{
  const phi=ring/RINGS*Math.PI,theta=seg/SEGMENTS*Math.PI*2;
  return [cx+radiusX*Math.sin(phi)*Math.cos(theta),
          cy+radiusY*Math.cos(phi),
          depth+radiusZ*Math.sin(phi)*Math.sin(theta)];
 };
 const tris:P3[][]=[];
 for(let j=0;j<RINGS;j++)for(let i=0;i<SEGMENTS;i++){
  const a=ellipsoid(j,i),b=ellipsoid(j+1,i),c=ellipsoid(j+1,i+1),d=ellipsoid(j,i+1);
  tris.push([a,b,c],[a,c,d]);
 }
 return tris;
}
function colorLayer(layer:AtlasLayer):[number,number,number]{
 return {skin:[70,209,217],muscles:[237,115,91],nerves:[246,196,99],
         organs:[201,132,233],bones:[195,231,238],reproductive:[97,204,186]}[layer] as [number,number,number];
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
 const colors=colorLayer(layer);
 ctx.save();
 // local artificial depth cues, not an image-derived scan
 const aura=ctx.createRadialGradient(cx,cy,6,cx,cy,Math.max(w,h)*.58);
 aura.addColorStop(0,'rgba(28,103,123,0.12)');aura.addColorStop(1,'rgba(0,8,19,0)');
 ctx.fillStyle=aura;ctx.fillRect(0,0,w,h);
 cs.forEach((part,partIndex)=>{
  const center: P3=[(part.cx-(view[0]+view[2]/2))/Math.max(view[2],view[3]*.57)*2,
   -(part.cy-(view[1]+view[3]/2))/Math.max(view[2],view[3]*.57)*2,
   DEPTH[layer]+options.explode];
  const projected=transform(center,cx,cy,scale,options);
  const rad=Math.max(10,Math.min(90,Math.max(part.rx,part.ry)/Math.max(view[2],view[3]*.57)*scale*2));
  hits.push({id:part.id,label:part.label,x:projected[0],y:projected[1],radius:rad,depth:projected[2]});
  const surfaces=mesh(part,layer,region,options,view);
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
  const [r,g,b]=t.active?[247,177,118]:colors;
  ctx.beginPath();ctx.moveTo(t.p[0][0],t.p[0][1]);ctx.lineTo(t.p[1][0],t.p[1][1]);ctx.lineTo(t.p[2][0],t.p[2][1]);ctx.closePath();
  ctx.fillStyle='rgba('+safe(r*factor)+','+safe(g*factor)+','+safe(b*factor)+','+(t.active?.94:.83)+')';
  ctx.fill();
  ctx.strokeStyle=t.active?'rgba(255,195,130,.45)':'rgba(155,241,244,.17)';
  ctx.lineWidth=t.active?.7:.28;ctx.stroke();
 }
 // HUD markers remain clickable and correspond to the 3D geometry above.
 hits.forEach(hit=>{
  if(hit.x<0||hit.x>w||hit.y<0||hit.y>h)return;
  const active=hit.id===options.selected;
  ctx.beginPath();ctx.arc(hit.x,hit.y,active?4.7:2.7,0,2*Math.PI);
  ctx.fillStyle=active?'#ffc18b':'#a5f4fb';ctx.fill();
  if(active){
   ctx.strokeStyle='rgba(255,196,130,.8)';ctx.lineWidth=1;
   ctx.beginPath();ctx.arc(hit.x,hit.y,10.5,0,Math.PI*2);ctx.stroke();
  }
 });
 ctx.restore();return hits;
}
export function hitVolume(hits:VolumeHit[],x:number,y:number):string|null{
 return hits.filter(p=>Math.hypot(x-p.x,y-p.y)<Math.max(13,Math.min(60,p.radius)))
   .sort((a,b)=>Math.hypot(x-a.x,y-a.y)-Math.hypot(x-b.x,y-b.y))[0]?.id||null;
}
