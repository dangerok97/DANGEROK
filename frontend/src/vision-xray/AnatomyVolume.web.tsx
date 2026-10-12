import React from 'react';
import type {AnatomyRegion, AtlasLayer} from './anatomyAtlas';
import type {BodyRegion} from './anatomyFocus';
import {drawVolume,hitVolume,poseFromLandmarks,type VolumeHit} from './anatomyVolume';
export type VisiblePosePoints=Record<string,[number,number]>;

/** A study-space volumetric diagram anchored to ONE captured frame, not live 6DoF pose tracking. */
export function AnatomyVolume({regions,layer,region,selected,onSelect,zoom,onZoom,viewBox,posePoints}:{
 regions:AnatomyRegion[];layer:AtlasLayer;region:BodyRegion;selected:string;
 onSelect:(id:string)=>void;zoom:number;onZoom:(z:number)=>void;viewBox:string;
 posePoints?:VisiblePosePoints|null;
}){
 const canvas=React.useRef<HTMLCanvasElement>(null);
 const hits=React.useRef<VolumeHit[]>([]);
 const pointers=React.useRef(new Map<number,{x:number;y:number;startX:number;startY:number}>());
 const moved=React.useRef(false);
 const [yaw,setYaw]=React.useState(.34);
 const [pitch,setPitch]=React.useState(-.12);
 const [explode,setExplode]=React.useState(.03);
 const [isolated,setIsolated]=React.useState(false);
 React.useEffect(()=>{setIsolated(false);},[layer,region]);
 const pose=React.useMemo(()=>poseFromLandmarks(posePoints),[posePoints]);
 React.useEffect(()=>{
  const node=canvas.current;if(!node)return;
  let frame=0;
  const draw=()=>{
   const width=node.clientWidth,height=node.clientHeight;
   if(width<1||height<1)return;
   const dpr=Math.min(2,window.devicePixelRatio||1);
   const W=Math.max(1,Math.round(width*dpr)),H=Math.max(1,Math.round(height*dpr));
   if(node.width!==W||node.height!==H){node.width=W;node.height=H;}
   const ctx=node.getContext('2d');if(!ctx)return;
   ctx.setTransform(dpr,0,0,dpr,0,0);
   ctx.clearRect(0,0,width,height);
   hits.current=drawVolume(ctx,width,height,isolated&&selected?regions.filter(part=>part.id===selected):regions,layer,region,
     {yaw,pitch,zoom,selected,explode,pose},viewBox);
   node.dataset.faceCount=String(hits.current.length);
   node.dataset.poseMode=pose.reliability;
   node.dataset.yaw=yaw.toFixed(2);
  };
  const render=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(draw);};
  const observer=new ResizeObserver(render);observer.observe(node);render();
  return()=>{cancelAnimationFrame(frame);observer.disconnect();};
 },[regions,layer,region,selected,yaw,pitch,zoom,explode,pose,viewBox,isolated]);
 const down=(e:React.PointerEvent<HTMLCanvasElement>)=>{
  pointers.current.set(e.pointerId,{x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY});
  moved.current=false;
  try{e.currentTarget.setPointerCapture(e.pointerId);}catch{/* WebKit synthetic capture */}
 };
 const move=(e:React.PointerEvent<HTMLCanvasElement>)=>{
  const prev=pointers.current.get(e.pointerId);if(!prev)return;
  const dx=e.clientX-prev.x,dy=e.clientY-prev.y;
  prev.x=e.clientX;prev.y=e.clientY;
  if(Math.hypot(e.clientX-prev.startX,e.clientY-prev.startY)>6)moved.current=true;
  if(pointers.current.size>1)return;
  if(moved.current){
   setYaw(v=>Math.max(-1.3,Math.min(1.3,v+dx*.012)));
   setPitch(v=>Math.max(-.85,Math.min(.85,v-dy*.012)));
  }
 };
 const up=(e:React.PointerEvent<HTMLCanvasElement>)=>{
  const prev=pointers.current.get(e.pointerId);
  pointers.current.delete(e.pointerId);
  if(!prev)return;
  if(!moved.current&&Math.hypot(e.clientX-prev.startX,e.clientY-prev.startY)<8){
   const box=e.currentTarget.getBoundingClientRect();
   const key=hitVolume(hits.current,e.clientX-box.left,e.clientY-box.top);
   if(key)onSelect(key);
  }
  if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);
 };
 return <>
  <canvas ref={canvas} data-testid="vision-anatomy-volume" className="vx-anatomy-volume"
   role="img" tabIndex={0} aria-label="Modello anatomico tridimensionale illustrativo, trascina per ruotare e tocca una parte per selezionarla"
   onPointerDown={down} onPointerMove={move} onPointerUp={up}
   onPointerCancel={e=>{pointers.current.delete(e.pointerId);}} onWheel={e=>{
     e.preventDefault();onZoom(Math.max(.85,Math.min(2.2,zoom*Math.exp(-e.deltaY*.001))));
   }}/>
  <div className="vx-anatomy-volume-label" aria-hidden="true">
   <span>PROCEDURAL 3D</span>
   <span>{pose.reliability==='approximate'?'ORIENTAMENTO STIMATO · 1 FOTOGRAMMA':'ORIENTAMENTO ILLUSTRATIVO'}</span>
  </div>
  <div className="vx-anatomy-volume-controls">
   <button type="button" data-testid="vision-anatomy-isolate" aria-pressed={isolated} disabled={!selected} onClick={()=>setIsolated(v=>!v)} title="Mostra solo la struttura selezionata o tutte">{isolated?'Mostra tutte':'Isola parte'}</button>
   <label style={{display:'flex',alignItems:'center',gap:5,fontSize:11,color:'#d7edf0'}}>Separa <input data-testid="vision-anatomy-explode" aria-label="Distanza di separazione anatomica" type="range" min="0" max="0.7" step="0.05" value={explode} onChange={e=>setExplode(Number(e.target.value))}/></label>
   <button type="button" data-testid="vision-anatomy-turn-left" onClick={()=>setYaw(v=>Math.max(-1.3,v-.22))} aria-label="Ruota a sinistra">↶</button>
   <button type="button" data-testid="vision-anatomy-reset-orbit" onClick={()=>{setYaw(.34);setPitch(-.12);setExplode(.03);}} aria-label="Reimposta la visuale">⊙</button>
   <button type="button" data-testid="vision-anatomy-turn-right" onClick={()=>setYaw(v=>Math.min(1.3,v+.22))} aria-label="Ruota a destra">↷</button>
  </div>
 </>;
}
