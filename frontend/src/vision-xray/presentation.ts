/** Vision V2 presentation. Reuses the versioned catalog; no new hardware claims.
 * The model remains screen-anchored, never dependent on continued camera tracking.
 * Geometry is built once. No bitmap-generated fake parts, eval or external assets.
 */
import { geometry, type Manifest, type Part, type Vec3, type Box } from './scene';
import type { TourStep } from './walkthrough';
export type Point = [number, number];
type Mesh = ReturnType<typeof geometry>;
type Face = { points: Point[]; depth: number; light: number };
type Projected = { key: string; index: number; points: Point[]; faces: Face[]; mesh: Mesh; depth: number; alpha: number; selected: boolean; bounds: [number,number,number,number]; badge?: Point };
export type PresentationOptions = { progress: number; yaw: number; pitch: number; selected: string; focus: number; zoom: number; origin?: {box:Box; mix:number;rotation?:number}; tour?: {step:TourStep; phase:number}; visibleKeys?:readonly string[] };
const lerp = (a: number, b: number, t: number) => a+(b-a)*t;
function ring(m: Mesh, points: Vec3[]) {
  const start=m.v.length; m.v.push(...points);
  points.forEach((_,i)=>m.e.push([start+i,start+(i+1)%points.length]));
  return points.map((_,i)=>start+i);
}
function rounded(w:number,h:number,z:number,cx=0,cy=0):Vec3[] {
  const r=Math.min(w*.20,h*.12);const points:Vec3[]=[];
  const centers=[[w/2-r,h/2-r],[-w/2+r,h/2-r],[-w/2+r,-h/2+r],[w/2-r,-h/2+r]];
  centers.forEach(([x,y],c)=>{for(let k=0;k<=5;k++){const a=c*Math.PI/2+k*Math.PI/10;points.push([cx+x+r*Math.cos(a),cy+y+r*Math.sin(a),z]);}});
  return points;
}
function walls(m:Mesh,a:number[],b:number[]) {
  for(let i=0;i<a.length;i++){const j=(i+1)%a.length;m.faces.push([a[i],a[j],b[j],b[i]]);if(i%6===0)m.e.push([a[i],b[i]]);}
}
function pad(m:Mesh,w:number,h:number,depth:number,cx:number,cy:number,z:number) {
  const a=ring(m,rounded(w,h,z,cx,cy));const b=ring(m,rounded(w*.91,h*.96,z+depth,cx,cy));
  walls(m,a,b);m.faces.push(b);
}

/** Enrich the same schematic primitives, without changing their semantic part IDs. */
export function presentationGeometry(part:Part):Mesh {
  const [w,h,d]=part.size;
  if(part.shape==='shell'){
    const m:Mesh={v:[],e:[],faces:[],dots:[]};
    const bottom=ring(m,rounded(w*.94,h*.985,-d/2));
    const lip=ring(m,rounded(w,h,d/2));
    const inside=ring(m,rounded(w*.84,h*.955,d/2-.15));
    const floor=ring(m,rounded(w*.82,h*.94,-d/2+Math.min(d*.35,1.2)));
    walls(m,bottom,lip);walls(m,lip,inside);walls(m,inside,floor);m.faces.push(floor);
    // Stylized mounting bosses; not exact fasteners of the photographed unit.
    for(const x of [-w*.32,w*.32])for(const y of [-h*.38,h*.38]){
      const z=-d/2+Math.min(d*.45,1.5),r=Math.min(w,h)*.035;
      const a=ring(m,Array.from({length:12},(_,i)=>[x+r*Math.cos(i*Math.PI/6),y+r*Math.sin(i*Math.PI/6),z] as Vec3));
      const b=ring(m,Array.from({length:12},(_,i)=>[x+r*Math.cos(i*Math.PI/6),y+r*Math.sin(i*Math.PI/6),d/2] as Vec3));walls(m,a,b);
    }
    return m;
  }
  const m=geometry(part);
  if(part.shape==='keypad'){
    // The base membrane has individual raised, shaded controls instead of flat dots.
    for(let row=0;row<7;row++)for(let col=0;col<3;col++){
      const y=h*(.38-row*.115),x=(col-1)*w*.28;
      pad(m,w*.205,h*.066,Math.min(2,w*.055),x,y,d/2+.3);
    }
  } else if(part.shape==='board') {
    // Conductive edge pads and package bodies: schematic, never a claimed circuit layout.
    for(let k=0;k<12;k++){
      const y=h*(.39-k*.071);
      pad(m,w*.09,h*.025,.5,-w*.43,y,d/2+.3);
      pad(m,w*.09,h*.025,.5,w*.43,y,d/2+.3);
    }
  }
  return m;
}
function rotate([x,y,z]:Vec3,yaw:number,pitch:number):Vec3 {
  const xx=x*Math.cos(yaw)+z*Math.sin(yaw),zz=-x*Math.sin(yaw)+z*Math.cos(yaw);
  return [xx,y*Math.cos(pitch)-zz*Math.sin(pitch),y*Math.sin(pitch)+zz*Math.cos(pitch)];
}
function bounds(points:Point[]):[number,number,number,number] {
  let l=Infinity,t=Infinity,r=-Infinity,b=-Infinity;
  for(const [x,y] of points){l=Math.min(l,x);r=Math.max(r,x);t=Math.min(t,y);b=Math.max(b,y);}
  return [l,t,r,b];
}
export function inPolygon(x:number,y:number,points:Point[]):boolean {
  let inside=false;
  for(let i=0,j=points.length-1;i<points.length;j=i++){
    const [xi,yi]=points[i],[xj,yj]=points[j];
    if((yi>y)!==(yj>y)&&x<(xj-xi)*(y-yi)/(yj-yi)+xi)inside=!inside;
  }
  return inside;
}
export function edgeDistance(x:number,y:number,a:Point,b:Point) {
  const dx=b[0]-a[0],dy=b[1]-a[1],den=dx*dx+dy*dy;
  const t=den?Math.min(1,Math.max(0,((x-a[0])*dx+(y-a[1])*dy)/den)):0;
  return Math.hypot(x-a[0]-t*dx,y-a[1]-t*dy);
}
function illumination(vertices:Vec3[],face:number[]) {
  if(face.length<3)return .6;
  const a=vertices[face[0]],b=vertices[face[1]],c=vertices[face[2]];
  const u=b.map((v,i)=>v-a[i]),v=c.map((n,i)=>n-a[i]);
  const n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];
  const len=Math.hypot(...n)||1;
  return .25+.75*Math.abs((n[0]*-.35+n[1]*.5+n[2]*.79)/len);
}
function path(ctx:CanvasRenderingContext2D,points:Point[]){
  ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();
}

export class VisionPresentation {
  private meshes:Mesh[];
  private projected:Projected[]=[];
  constructor(public manifest:Manifest){this.meshes=manifest.parts.map(presentationGeometry);}

  /** Matching visible faces/edges, not the empty rectangle around an object. */
  hit(x:number,y:number):string|null {
    const badges=this.projected.filter(p=>p.badge&&Math.hypot(x-p.badge[0],y-p.badge[1])<=20)
      .sort((a,b)=>Math.hypot(x-a.badge![0],y-a.badge![1])-Math.hypot(x-b.badge![0],y-b.badge![1]));
    if(badges.length)return badges[0].key;
    for(const p of [...this.projected].reverse()){
      if(p.alpha<.3)continue;
      const [l,t,r,b]=p.bounds;if(x<l-8||x>r+8||y<t-8||y>b+8)continue;
      if(p.faces.some(f=>inPolygon(x,y,f.points)))return p.key;
      if(p.mesh.e.some(([a,b])=>edgeDistance(x,y,p.points[a],p.points[b])<=7))return p.key;
    }
    return null;
  }
  /** Useful for regression assertions without exposing page globals or user data. */
  partBounds(key:string){return this.projected.find(p=>p.key===key)?.bounds;}

  draw(ctx:CanvasRenderingContext2D,w:number,h:number,opts:PresentationOptions){
    const progress=Math.max(0,Math.min(1,opts.progress));
    const selectedIndex=this.manifest.parts.findIndex(p=>p.key===opts.selected);
    const focus=selectedIndex<0?0:Math.max(0,Math.min(1,opts.focus));
    // Only zoom a crowded object when the caller explicitly opens a page.
    // Keep the original geometry/version/part identifiers untouched.
    const allowed=opts.visibleKeys?.length&&focus<.2&&!opts.tour
      ?new Set(opts.visibleKeys):null;
    const displayed=this.manifest.parts.map((_,i)=>i)
      .filter(i=>!allowed||allowed.has(this.manifest.parts[i].key));
    const indices=displayed.length?displayed:this.manifest.parts.map((_,i)=>i);
    // The page controls live above the opening footer; do not draw pieces under them.
    const top=h<310?65:82,bottom=allowed?111:48,available=Math.max(90,h-top-bottom);
    const cx=w/2,cy=top+available*.48;
    const highlighted=new Set(opts.tour?.step.parts||[]);
    const rotated=this.meshes.map(m=>m.v.map(v=>rotate(v,opts.yaw,opts.pitch)));
    const positions=this.manifest.parts.map(p=>rotate(p.assembled.map((n,j)=>lerp(n,p.exploded[j],progress)) as Vec3,opts.yaw,opts.pitch));
    // Fit against the entire exploded envelope to avoid a zoom-pump on recomposition.
    const envelope:Point[]=[];let nearestDepth=0;
    for(const i of indices){const p=this.manifest.parts[i],offset=rotate(p.exploded,opts.yaw,opts.pitch);
      rotated[i].forEach(v=>{envelope.push([v[0]+offset[0],v[1]+offset[1]]);
        nearestDepth=Math.max(nearestDepth,v[2]+offset[2]);});}
    const [l,t,r,b]=bounds(envelope),midX=(l+r)/2,midY=(t+b)/2;
    const flatScale=Math.min(w*.84/Math.max(1,r-l),available*.83/Math.max(1,b-t));
    // Bound the maximum perspective magnification before fitting, so wide or
    // deep families do not clip at zoom 1. User-requested zoom may still crop.
    const s=flatScale*(850-Math.min(350,nearestDepth*flatScale))/850;
    const zoom=Math.min(3.2,Math.max(.65,opts.zoom));
    const selectedBounds=selectedIndex<0?[0,0,1,1]:bounds(rotated[selectedIndex].map(v=>[v[0],v[1]]));
    const flatFocusScale=selectedIndex<0?s:Math.min(w*.72/Math.max(1,selectedBounds[2]-selectedBounds[0]),available*.72/Math.max(1,selectedBounds[3]-selectedBounds[1]));
    const nearestFocusDepth=selectedIndex<0?0:Math.max(0,...rotated[selectedIndex].map(v=>v[2]));
    const focusScale=flatFocusScale*(1000-Math.min(350,nearestFocusDepth*flatFocusScale))/1000;
    const fcx=(selectedBounds[0]+selectedBounds[2])/2,fcy=(selectedBounds[1]+selectedBounds[3])/2;
    const focusCenterY=top+available*.37;
    // Map the compact assembled representation to the observed region, then move
    // smoothly into study space. A bounding box is not an exact object silhouette.
    const assembledEnvelope:Point[]=[];
    for(const i of indices){const p=this.manifest.parts[i],offset=rotate(p.assembled,opts.yaw,opts.pitch);
      rotated[i].forEach(v=>assembledEnvelope.push([v[0]+offset[0],v[1]+offset[1]]));}
    const [al,at,ar,ab]=bounds(assembledEnvelope);
    const origin=opts.origin;
    // Initial assembled drawing follows the major axis of the real pixel mask,
    // but the parts remain schematic. No 3D pose or camera depth is inferred.
    const originAngle=origin?.rotation||0;
    const sin=Math.sin(originAngle),cos=Math.cos(originAngle);
    const rotatedAssembly=assembledEnvelope.map(([x,y]):Point=>{
      const dx=x-(al+ar)/2,dy=-(y-(at+ab)/2);
      return [dx*cos-dy*sin,dx*sin+dy*cos];
    });
    const [oL,oT,oR,oB]=bounds(rotatedAssembly);
    const originScale=origin?Math.min(origin.box[2]*w*.89/Math.max(1,oR-oL),
      origin.box[3]*h*.89/Math.max(1,oB-oT)):s;
    const originMix=origin?Math.max(0,Math.min(1,origin.mix)):1;
    this.projected=indices.map(i=>{const mesh=this.meshes[i];
      const part=this.manifest.parts[i],active=i===selectedIndex,pos=positions[i];
      const transform=(v:Vec3):Point=>{
        // Mild perspective creates depth without unstable camera clipping.
        const perspective=850/(850-Math.min(350,Math.max(-350,(v[2]+pos[2])*s)));
        const x=(v[0]+pos[0]-midX)*s*perspective,y=-(v[1]+pos[1]-midY)*s*perspective;
        const study:Point=[cx+x*zoom,cy+y*zoom];
        const dx=v[0]+pos[0]-(al+ar)/2,dy=-(v[1]+pos[1]-(at+ab)/2);
        const source:Point=origin?[(origin.box[0]+origin.box[2]/2)*w+
             (dx*cos-dy*sin)*originScale,
          (origin.box[1]+origin.box[3]/2)*h+(dx*sin+dy*cos)*originScale]:study;
        const base:Point=[lerp(source[0],study[0],originMix),lerp(source[1],study[1],originMix)];
        if(active){
          const k=1000/(1000-Math.min(350,Math.max(-350,v[2]*focusScale)));
          return [lerp(base[0],cx+(v[0]-fcx)*focusScale*zoom*k,focus),lerp(base[1],focusCenterY-(v[1]-fcy)*focusScale*zoom*k,focus)];
        }
        return [lerp(base[0],cx+x*.56,focus),lerp(base[1],top+available*.83+y*.30,focus)];
      };
      const points=rotated[i].map(transform);
      const faces=mesh.faces.map(face=>({points:face.map(index=>points[index]),depth:face.reduce((total,index)=>total+rotated[i][index][2],0)/face.length,light:illumination(rotated[i],face)})).sort((a,b)=>a.depth-b.depth);
      return {key:part.key,index:i,points,faces,mesh,depth:pos[2]+(active?focus*2000:0),alpha:opts.tour?(highlighted.has(part.key)?1:.33):(active?1:lerp(1,.2,focus)),selected:active||highlighted.has(part.key),bounds:bounds(points)};
    }).sort((a,b)=>a.depth-b.depth);
    ctx.save();ctx.lineJoin='round';ctx.lineCap='round';
    // Static orientation rings. Nothing runs endlessly when the viewer is at rest.
    ctx.strokeStyle='rgba(102,207,221,.11)';ctx.lineWidth=1;
    for(const radius of [.85,1]){ctx.beginPath();ctx.ellipse(cx,cy,w*.44*radius,available*.44*radius,-.06,.08,Math.PI*1.88);ctx.stroke();}
    for(const p of this.projected){
      const shape=this.manifest.parts[p.index].shape;
      const rgb=p.selected?[237,171,109]:shape==='board'?[89,194,177]:[98,203,222];
      ctx.globalAlpha=p.alpha;
      for(const face of p.faces){
        path(ctx,face.points);
        const brightness=.12+.20*face.light;
        ctx.fillStyle=`rgba(${Math.round(rgb[0]*brightness)},${Math.round(rgb[1]*brightness)},${Math.round(rgb[2]*brightness)},.91)`;ctx.fill();
      }
      ctx.strokeStyle=p.selected?'rgba(255,191,123,.90)':'rgba(143,228,240,.76)';
      ctx.lineWidth=p.selected?1.15:.8;
      ctx.shadowColor=p.selected?'#ffb56d':'#60cfe0';ctx.shadowBlur=p.selected?4:0;
      ctx.beginPath();for(const [a,b] of p.mesh.e){ctx.moveTo(...p.points[a]);ctx.lineTo(...p.points[b]);}ctx.stroke();ctx.shadowBlur=0;
      // Crisp point accents, not a dense layer of visual noise.
      ctx.fillStyle=p.selected?'#ffe0b6':'#c2f7ff';
      for(let j=0;j<p.points.length;j+=19){const [x,y]=p.points[j];ctx.fillRect(x-.6,y-.6,1.2,1.2);}
    }
    // Selected object index is a readable callout; other badges remain useful tap targets.
    const used:Point[]=[];
    if(progress>.6&&focus<.5){
      for(const p of [...this.projected].sort((a,b)=>a.index-b.index)){
        const [left,upper,right,lower]=p.bounds;
        let x=Math.min(w-27,Math.max(27,(left+right)/2));
        let y=Math.min(h-35,lower+22);
        for(let tries=0;tries<5&&used.some(([xx,yy])=>Math.hypot(x-xx,y-yy)<31);tries++)y=Math.max(top, y-32);
        used.push([x,y]);p.badge=[x,y];
        ctx.globalAlpha=1;ctx.strokeStyle=p.selected?'#ffc087':'rgba(127,215,230,.6)';ctx.lineWidth=.8;
        ctx.beginPath();ctx.moveTo((left+right)/2,lower);ctx.lineTo(x,y-12);ctx.stroke();
        ctx.beginPath();ctx.arc(x,y,12,0,Math.PI*2);ctx.fillStyle='#071c24';ctx.fill();ctx.stroke();
        ctx.fillStyle=p.selected?'#ffcc92':'#caf0f5';ctx.font='10px ui-monospace,monospace';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(String(p.index+1).padStart(2,'0'),x,y+.5);
      }
    }
    // Relationships are symbolic, never measured wiring, pressure or electrical flow.
    if(opts.tour){
      ctx.globalAlpha=1;ctx.strokeStyle='#ffca91';ctx.fillStyle='#ffe2b9';ctx.lineWidth=1.7;
      const center=(key:string):Point|null=>{const p=this.projected.find(p=>p.key===key);return p?[(p.bounds[0]+p.bounds[2])/2,(p.bounds[1]+p.bounds[3])/2]:null;};
      for(const [from,to] of opts.tour.step.links){
        const a=center(from),b=center(to);if(!a||!b)continue;
        const control:Point=[(a[0]+b[0])/2,Math.min(a[1],b[1])-Math.min(48,available*.12)];
        ctx.setLineDash([4,6]);ctx.beginPath();ctx.moveTo(...a);ctx.quadraticCurveTo(...control,...b);ctx.stroke();ctx.setLineDash([]);
        // Slow single pulse per segment, not flashing lights.
        const t=opts.tour.phase,u=1-t,x=u*u*a[0]+2*u*t*control[0]+t*t*b[0],y=u*u*a[1]+2*u*t*control[1]+t*t*b[1];
        ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.fill();
      }
      for(const key of opts.tour.step.parts){const p=this.projected.find(p=>p.key===key);if(!p)continue;
        const [l,t,r,b]=p.bounds;ctx.strokeStyle='rgba(255,201,137,.48)';ctx.lineWidth=1;
        ctx.strokeRect(l-5,t-5,r-l+10,b-t+10);
      }
    }
    if(focus>.5){
      ctx.globalAlpha=.62;ctx.textAlign='center';ctx.fillStyle='#9bbfc8';ctx.font='10px ui-monospace,monospace';
      ctx.fillText('CONTEXTE DE L’OBJET'.replace('CONTEXTE DE L’OBJET','NEL TUO OGGETTO'),cx,top+available*.96);
    }
    ctx.restore();
  }
}
