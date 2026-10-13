import React from 'react';
import {SCAN_CINEMATIC_STYLES} from './scanCinematicStyle';
import type {PixelContour,ScanBox,ScanPoint} from './pixelContour';

const clamp=(value:number,min:number,max:number)=>Math.max(min,Math.min(max,value));
const svgPoint=([x,y]:ScanPoint)=>[(x*1000),(y*1000)] as const;
const fmt=(x:number)=>x.toFixed(2);
function closedPath(points:ScanPoint[]){
 return points.map((point,i)=>{
  const [x,y]=svgPoint(point);return (i?'L':'M')+fmt(x)+' '+fmt(y);
 }).join(' ')+' Z';
}
function boxPath(box:ScanBox){
 const [x,y,w,h]=box.map(n=>n*1000);
 return 'M'+fmt(x)+' '+fmt(y)+' H'+fmt(x+w)+' V'+fmt(y+h)+
  ' H'+fmt(x)+' Z';
}
/** Positions decorative tracking nodes on the REAL captured contour rather than
 * falsely claiming eye joints, finger tips or other anatomical landmarks. */
function perimeterNodes(points:ScanPoint[],count=9):ScanPoint[]{
 if(points.length<8)return [];
 const spans=points.map((p,i)=>{
  const q=points[(i+1)%points.length];return Math.hypot(q[0]-p[0],q[1]-p[1]);
 });
 const perimeter=spans.reduce((a,b)=>a+b,0);
 if(perimeter<.05)return [];
 const result:ScanPoint[]=[];
 for(let k=0;k<count;k++){
  const at=(k+.4)*perimeter/count;let walked=0;
  for(let i=0;i<points.length;i++){
   if(walked+spans[i]>=at){
    const a=points[i],b=points[(i+1)%points.length];
    const fraction=(at-walked)/Math.max(1e-7,spans[i]);
    result.push([a[0]+(b[0]-a[0])*fraction,a[1]+(b[1]-a[1])*fraction]);
    break;
   }
   walked+=spans[i];
  }
 }
 return result;
}
/** ORA SCAN 2 — premium motion design over pixel-derived, source-backed geometry.
 * A cinematic overlay is allowed; fake segmentation, real-world dimensions or
 * non-existent anatomical landmarks are not. CSS respects reduced motion. */
export function ScanOutline({contour,box,label}:{
 contour?:PixelContour|null;box?:ScanBox|null;label?:string;
}){
 const bounds=contour?.box||box;
 const uid=React.useId().replace(/:/g,'');
 const clipId='vxclip'+uid,fillId='vxfill'+uid,gridId='vxgrid'+uid;
 const sweepId='vxsweep'+uid,glowId='vxglow'+uid;
 const valid=!!bounds&&bounds.length===4&&bounds.every(Number.isFinite)&&
  bounds[2]>.015&&bounds[3]>.015;
 const real=!!contour&&contour.points.length>=8&&contour.confidence>=.5;
 const path=real?closedPath(contour!.points):valid?boxPath(bounds!):'';
 const nodes=real?perimeterNodes(contour!.points):[];
 if(!valid)return null;
 const [x,y,w,h]=bounds!;
 const left=x*1000,top=y*1000,width=w*1000,height=h*1000;
 const cx=left+width/2,cy=top+height/2;
 const bracket=Math.max(14,Math.min(28,Math.min(width,height)*.11));
 const arm=Math.max(15,Math.min(29,Math.min(width,height)*.10));
 const status=real?'Contorno ricavato dai pixel del fotogramma, non una misura 3D':
  'Area stimata dal riconoscitore: contorno reale non verificato';
 const readoutX=clamp(x,.045,.67)*100;
 const readoutY=clamp(y+h+.022,.12,.84)*100;
 const travel=(height+200).toFixed(0)+'px';
 const cornerPaths=[
  'M'+fmt(left)+' '+fmt(top+bracket)+'V'+fmt(top)+'H'+fmt(left+bracket),
  'M'+fmt(left+width-bracket)+' '+fmt(top)+'H'+fmt(left+width)+'V'+fmt(top+bracket),
  'M'+fmt(left)+' '+fmt(top+height-bracket)+'V'+fmt(top+height)+'H'+fmt(left+bracket),
  'M'+fmt(left+width-bracket)+' '+fmt(top+height)+'H'+fmt(left+width)+'V'+fmt(top+height-bracket)
 ];
 const radial=Math.max(18,Math.min(42,Math.min(width,height)*.11));
 return <div className={'vx-scan-surface vx-scan-cinematic '+(real?'vx-scan-detected':'vx-scan-estimated')}
   data-testid="vision-scan-overlay" data-mode={real?'pixels':'box'}
   data-scan-style="cinematic-v2" role="status" aria-label={status}>
   <style>{SCAN_CINEMATIC_STYLES}</style>
   <svg className="vx-scan-surface-svg" viewBox="0 0 1000 1000"
    preserveAspectRatio="none" aria-hidden="true" focusable="false">
    <defs>
     <linearGradient id={fillId} x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stopColor="#38c8fc" stopOpacity=".09"/>
      <stop offset="48%" stopColor="#66ffff" stopOpacity=".025"/>
      <stop offset="100%" stopColor="#5b8bff" stopOpacity=".11"/>
     </linearGradient>
     <pattern id={gridId} width="18" height="18" patternUnits="userSpaceOnUse">
      <path d="M18 0H0V18" fill="none" stroke="#96ebff" strokeWidth=".33" opacity=".19"/>
      <circle cx="0" cy="0" r="1" fill="#c1fbff" opacity=".35"/>
     </pattern>
     <linearGradient id={sweepId} x1="0" x2="0" y1="0" y2="1">
      <stop offset="0%" stopColor="#8affff" stopOpacity="0"/>
      <stop offset="35%" stopColor="#47dafa" stopOpacity=".12"/>
      <stop offset="82%" stopColor="#8efaff" stopOpacity=".25"/>
      <stop offset="100%" stopColor="#b5fbff" stopOpacity="0"/>
     </linearGradient>
     <filter id={glowId} x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="3.5"/>
     </filter>
     {real&&<clipPath id={clipId} clipPathUnits="userSpaceOnUse">
      <path d={path}/>
     </clipPath>}
    </defs>
    {real&&<>
     <path className="vx-hud-fill" d={path} fill={'url(#'+fillId+')'}/>
     <rect x="0" y="0" width="1000" height="1000"
      fill={'url(#'+gridId+')'} clipPath={'url(#'+clipId+')'}
      className="vx-hud-grid"/>
     <path d={path} className="vx-hud-glow"
      filter={'url(#'+glowId+')'}/>
     <rect x="0" y={top-150} width="1000" height="150"
      fill={'url(#'+sweepId+')'} clipPath={'url(#'+clipId+')'}
      className="vx-hud-sweep"
      style={{'--vx-scan-travel':travel} as React.CSSProperties}/>
    </>}
    <path className={'vx-scan-trace '+(real?'is-pixel':'is-box')}
     d={path} pathLength={1000}/>
    {real&&<path className="vx-hud-tracer" d={path} pathLength={1000}/>}
    <g className="vx-hud-corners">
     {cornerPaths.map((d,i)=><path key={i} d={d}/>)}
    </g>
    {real&&<>
     <g className="vx-hud-nodes">
      {nodes.map(([px,py],i)=><g key={i} transform={'translate('+fmt(px*1000)+' '+fmt(py*1000)+')'}>
        <circle className="vx-hud-node-ring" r={i%3===0?6.5:4.6}/>
        <circle className="vx-hud-node-core" r={i%3===0?2.15:1.6}/>
       </g>)}
     </g>
     <g className="vx-hud-reticle">
      <circle cx={cx} cy={cy} r={radial} className="vx-hud-radial"/>
      <path d={'M'+fmt(cx-arm)+' '+fmt(cy)+'h'+fmt(arm*.55)+
        ' M'+fmt(cx+arm*.45)+' '+fmt(cy)+'h'+fmt(arm*.55)+
        ' M'+fmt(cx)+' '+fmt(cy-arm)+'v'+fmt(arm*.55)+
        ' M'+fmt(cx)+' '+fmt(cy+arm*.45)+'v'+fmt(arm*.55)}/>
      <circle cx={cx} cy={cy} r="2.4" className="vx-hud-center"/>
     </g>
    </>}
    {real&&<path className="vx-hud-leader"
      d={'M'+fmt(left+width*.89)+' '+fmt(top+height*.12)+
       ' L'+fmt(left+width*.89+Math.min(42,Math.max(6,(1000-left-width)*.42)))+
       ' '+fmt(top+height*.12-29)}/>}
   </svg>
   <div className="vx-scan-readout"
    style={{left:readoutX+'%',top:readoutY+'%'}}>
    <div className="vx-scan-readout-top"><span className="vx-scan-readout-led"/>
     <span>ORA <b>VISION</b> / SCAN</span>
     <span className="vx-scan-readout-bars" aria-hidden="true"><i/><i/><i/><i/></span>
    </div>
    <div className="vx-scan-readout-divider"/>
    <strong>{real?'PROFILO ACQUISITO':'AREA INDIVIDUATA'}</strong>
    <small>{real?'Bordo 2D · immagine acquisita':'Contorno non verificato'}</small>
    <span className="vx-scan-readout-category">{label||'OGGETTO'}</span>
   </div>
 </div>;
}
