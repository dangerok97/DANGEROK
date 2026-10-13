import React from 'react';
import type {PixelContour,ScanBox} from './pixelContour';

/** Screen-space contour from captured pixels, not a reusable stock silhouette.
 * Weak segmentation is explicitly presented as a rectangular detection area. */
export function ScanOutline({contour,box,label}:{
 contour?:PixelContour|null;box?:ScanBox|null;label?:string;
}){
 const bounds=contour?.box||box;
 if(!bounds||bounds.some(n=>!Number.isFinite(n))||bounds[2]<=0||bounds[3]<=0)return null;
 const real=!!contour&&contour.points.length>7&&contour.confidence>=.5;
 const outline=real?contour!.points.map(([x,y],i)=>
  (i===0?'M':'L')+(x*1000).toFixed(1)+' '+(y*1000).toFixed(1)).join(' ')+' Z':'';
 const rect='M'+(bounds[0]*1000).toFixed(1)+' '+(bounds[1]*1000).toFixed(1)+
  ' h'+(bounds[2]*1000).toFixed(1)+' v'+(bounds[3]*1000).toFixed(1)+
  ' h'+(-bounds[2]*1000).toFixed(1)+' Z';
 const caption=real?'Bordo ricavato dall’immagine':'Area stimata · bordo non verificato';
 return <div className="vx-scan-surface" data-testid="vision-scan-overlay"
  data-mode={real?'pixels':'box'} role="status" aria-label={caption}>
  <svg viewBox="0 0 1000 1000" preserveAspectRatio="none"
   aria-hidden="true" className="vx-scan-surface-svg">
   <path className={'vx-scan-trace '+(real?'is-pixel':'is-box')} d={real?outline:rect}/>
   {real&&<path className="vx-scan-halo" d={outline}/>}
  </svg>
  <div className="vx-scan-chip"
   style={{left:Math.min(.76,Math.max(.04,bounds[0]))*100+'%',
    top:Math.min(.81,Math.max(.10,bounds[1]+bounds[3]))*100+'%'}}>
    <span className="vx-scan-dot"/> {label||'SCAN'} · {real?'contorno rilevato':'aggancio indicativo'}
  </div>
 </div>;
}
