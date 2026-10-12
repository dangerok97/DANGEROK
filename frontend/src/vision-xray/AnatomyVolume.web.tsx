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
 const pinch=React.useRef<{distance:number;zoom:number}|null>(null);
 const pinched=React.useRef(false);
 const [yaw,setYaw]=React.useState(.34);
 const [pitch,setPitch]=React.useState(-.12);
 const [explode,setExplode]=React.useState(.03);
 const [isolated,setIsolated]=React.useState(false);
 const [toolsOpen,setToolsOpen]=React.useState(false);
 React.useEffect(()=>{setIsolated(false);setToolsOpen(false);},[layer,region]);
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
   node.dataset.zoom=zoom.toFixed(2);
  };
  const render=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(draw);};
  const observer=new ResizeObserver(render);observer.observe(node);render();
  return()=>{cancelAnimationFrame(frame);observer.disconnect();};
 },[regions,layer,region,selected,yaw,pitch,zoom,explode,pose,viewBox,isolated]);
 const down=(e:React.PointerEvent<HTMLCanvasElement>)=>{
  pointers.current.set(e.pointerId,{x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY});
  if(pointers.current.size===1){moved.current=false;pinched.current=false;pinch.current=null;}
  if(pointers.current.size===2){
   const [first,second]=[...pointers.current.values()];
   pinch.current={distance:Math.max(1,Math.hypot(first.x-second.x,first.y-second.y)),zoom};
   pinched.current=true;moved.current=true;
  }
  try{e.currentTarget.setPointerCapture(e.pointerId);}catch{/* WebKit synthetic capture */}
 };
 const move=(e:React.PointerEvent<HTMLCanvasElement>)=>{
  const prev=pointers.current.get(e.pointerId);if(!prev)return;
  const dx=e.clientX-prev.x,dy=e.clientY-prev.y;
  prev.x=e.clientX;prev.y=e.clientY;
  if(pointers.current.size>1){
   const pair=[...pointers.current.values()];
   if(pair.length===2&&pinch.current){
    const distance=Math.hypot(pair[0].x-pair[1].x,pair[0].y-pair[1].y);
    onZoom(Math.max(.85,Math.min(2.2,pinch.current.zoom*distance/pinch.current.distance)));
   }
   pinched.current=true;moved.current=true;return;
  }
  if(pinched.current)return;
  if(Math.hypot(e.clientX-prev.startX,e.clientY-prev.startY)>6)moved.current=true;
  if(moved.current){
   setYaw(v=>Math.max(-1.3,Math.min(1.3,v+dx*.012)));
   setPitch(v=>Math.max(-.85,Math.min(.85,v-dy*.012)));
  }
 };
 const up=(e:React.PointerEvent<HTMLCanvasElement>)=>{
  const prev=pointers.current.get(e.pointerId);
  pointers.current.delete(e.pointerId);
  if(pointers.current.size<2)pinch.current=null;
  if(prev&&!pinched.current&&!moved.current&&
     Math.hypot(e.clientX-prev.startX,e.clientY-prev.startY)<8){
   const box=e.currentTarget.getBoundingClientRect();
   const key=hitVolume(hits.current,e.clientX-box.left,e.clientY-box.top);
   if(key)onSelect(key);
  }
  if(pointers.current.size===0){moved.current=false;pinched.current=false;}
  try{if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}catch{/* Capture may have ended externally */}
 };
 const cancel=(e:React.PointerEvent<HTMLCanvasElement>)=>{
  pointers.current.delete(e.pointerId);
  if(pointers.current.size<2)pinch.current=null;
  if(pointers.current.size===0){moved.current=false;pinched.current=false;}
 };
 return <>
  <canvas ref={canvas} data-testid="vision-anatomy-volume" className="vx-anatomy-volume"
   role="img" tabIndex={0} aria-label="Modello anatomico 3D illustrativo: trascina per ruotare, pizzica con due dita per zoom, tocca per selezionare; frecce da tastiera per orientare"
   onPointerDown={down} onPointerMove={move} onPointerUp={up}
   onPointerCancel={cancel}
   onKeyDown={e=>{
    if(e.key==='ArrowLeft'){e.preventDefault();setYaw(v=>Math.max(-1.3,v-.16));}
    else if(e.key==='ArrowRight'){e.preventDefault();setYaw(v=>Math.min(1.3,v+.16));}
    else if(e.key==='ArrowUp'){e.preventDefault();setPitch(v=>Math.min(.85,v+.16));}
    else if(e.key==='ArrowDown'){e.preventDefault();setPitch(v=>Math.max(-.85,v-.16));}
    else if(e.key==='+'||e.key==='='){e.preventDefault();onZoom(Math.min(2.2,zoom+.2));}
    else if(e.key==='-'){e.preventDefault();onZoom(Math.max(.85,zoom-.2));}
    else if(e.key==='0'){e.preventDefault();setYaw(.34);setPitch(-.12);onZoom(1);}
    else if(e.key==='Escape'){setIsolated(false);setToolsOpen(false);}
   }}
   onWheel={e=>{
     e.preventDefault();onZoom(Math.max(.85,Math.min(2.2,zoom*Math.exp(-e.deltaY*.001))));
   }}/>
  <div className="vx-anatomy-volume-label" aria-hidden="true">
   <span>PROCEDURAL 3D</span>
   <span>{pose.reliability==='approximate'?'ORIENTAMENTO STIMATO · 1 FOTOGRAMMA':'ORIENTAMENTO ILLUSTRATIVO'}</span>
  </div>
  {toolsOpen&&<div className="vx-anatomy-tools" role="group" aria-label="Strumenti modello anatomico">
   <button type="button" data-testid="vision-anatomy-isolate" aria-pressed={isolated} disabled={!selected}
    onClick={()=>setIsolated(value=>!value)}>{isolated?'Mostra tutte le strutture':'Isola struttura selezionata'}</button>
   <label>Separa le strutture
    <input data-testid="vision-anatomy-explode" aria-label="Distanza di separazione delle strutture" type="range"
     min="0" max="0.7" step="0.05" value={explode} onChange={e=>setExplode(Number(e.target.value))}/>
   </label>
   <span>Modello illustrativo, non diagnostico</span>
  </div>}
  <div className="vx-anatomy-volume-controls" role="group" aria-label="Orientamento del modello">
   <button type="button" data-testid="vision-anatomy-turn-left" onClick={()=>setYaw(v=>Math.max(-1.3,v-.22))} aria-label="Ruota a sinistra">↶</button>
   <button type="button" data-testid="vision-anatomy-reset-orbit" onClick={()=>{setYaw(.34);setPitch(-.12);setExplode(.03);setIsolated(false);}} aria-label="Reimposta la visuale">⊙</button>
   <button type="button" data-testid="vision-anatomy-turn-right" onClick={()=>setYaw(v=>Math.min(1.3,v+.22))} aria-label="Ruota a destra">↷</button>
   <button type="button" className="vx-anatomy-more-btn" data-testid="vision-anatomy-tools"
    aria-expanded={toolsOpen} onClick={()=>setToolsOpen(value=>!value)}>Strumenti {toolsOpen?'−':'+'}</button>
  </div>
 </>;
}
