import React,{useEffect,useRef,useState} from 'react';
import * as T from 'three';
import {OrbitControls} from 'three/examples/jsm/controls/OrbitControls.js';
import {decodeModelResponse} from './model-download';
import type {Atlas,Part} from './anatomy';
import './ora-brain.css';

const BRAIN_CONCEPT_ID='FMA50801';
const AREAS=[
 {id:'memory',label:'MEMORIA'},
 {id:'calendar',label:'IMPEGNI'},
 {id:'people',label:'PERSONE'},
 {id:'places',label:'LUOGHI'},
 {id:'home',label:'CASA'},
 {id:'documents',label:'DOCUMENTI'},
 {id:'finances',label:'FINANZE'},
 {id:'calls',label:'CHIAMATE'},
] as const;

type PresenceStar={
 id:string;area:string;kind:'node'|'branch';tentative?:boolean;temporary?:boolean;complete?:boolean
};
type PresenceOptions={
 mode?:'idle'|'listen'|'think'|'speak';paused?:boolean;reduced?:boolean;
 selectedIndex?:number|null;resetKey?:number;zoomOverride?:number;
 spotlightId?:string|null;area?:string|null;stars?:PresenceStar[];
};
type MarkerData={
 index:number;area:string;kind:'area'|'node'|'branch';id?:string;
 temporary?:boolean;tentative?:boolean;complete?:boolean;
};
type MarkerEntry={data:MarkerData;core:T.Mesh;halo:T.Mesh;label?:HTMLButtonElement};

const hash=(value:string)=>{
 let h=2166136261;
 for(let i=0;i<value.length;i++)h=Math.imul(h^value.charCodeAt(i),16777619)>>>0;
 return h>>>0;
};
const boundsCenter=(part:Part)=>new T.Vector3(
 (part.bounds[0][0]+part.bounds[1][0])/2,
 (part.bounds[0][1]+part.bounds[1][1])/2,
 (part.bounds[0][2]+part.bounds[1][2])/2,
);
const surfaceLike=(name:string)=>/(gyrus|lobe|lobule|insula|cerebellum|medulla oblongata|pons|midbrain|cerebral hemisphere)/i.test(name);
const clamp=(value:number,min:number,max:number)=>Math.max(min,Math.min(max,value));

export default function OraBrain(){
 const host=useRef<HTMLDivElement>(null);
 const [status,setStatus]=useState<'loading'|'ready'|'error'>('loading');
 const [error,setError]=useState('');
 useEffect(()=>{
  const el=host.current;
  if(!el)return;
  let disposed=false,frame=0;
  const abort=new AbortController();
  const latest:{current:PresenceOptions}={current:{mode:'idle',paused:false,reduced:false,stars:[],zoomOverride:1,resetKey:0}};
  let renderer:T.WebGLRenderer;
  try{
   renderer=new T.WebGLRenderer({antialias:true,alpha:true,powerPreference:'high-performance'});
  }catch{
   setStatus('error');setError('WebGL non disponibile su questo dispositivo.');
   window.parent?.postMessage({type:'ora:brain-error',version:1},window.location.origin);
   return;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,el.clientWidth<700?1.5:2));
  renderer.setClearColor(0x000000,0);
  renderer.outputColorSpace=T.SRGBColorSpace;
  renderer.toneMapping=T.ACESFilmicToneMapping;
  renderer.toneMappingExposure=1.18;
  renderer.domElement.setAttribute('aria-label','Cervello tridimensionale di ORA. Trascina per ruotare e usa due dita per ingrandire.');
  el.appendChild(renderer.domElement);

  const scene=new T.Scene();
  scene.fog=new T.FogExp2(0x02070d,.16);
  const camera=new T.PerspectiveCamera(34,1,.002,50);
  const controls=new OrbitControls(camera,renderer.domElement);
  controls.enableDamping=true;controls.dampingFactor=.075;
  controls.enablePan=false;controls.minDistance=.16;controls.maxDistance=3.5;
  controls.autoRotate=true;controls.autoRotateSpeed=.34;
  controls.target.set(0,0,0);

  scene.add(new T.HemisphereLight(0xbcefff,0x07121a,1.35));
  const key=new T.DirectionalLight(0x9feaff,2.6);key.position.set(-1.5,2.2,2.5);scene.add(key);
  const rim=new T.DirectionalLight(0x1fa3d5,2.1);rim.position.set(2.5,.5,-2.4);scene.add(rim);
  const lower=new T.PointLight(0x2bc8ef,1.8,4);lower.position.set(0,-1.4,.6);scene.add(lower);

  const brain=new T.Group();scene.add(brain);
  brain.rotation.x=-.04;
  const markerGroup=new T.Group();brain.add(markerGroup);

  const surfaceMaterial=new T.MeshStandardMaterial({
   color:0x79d8ee,emissive:0x0a6f8d,emissiveIntensity:.78,
   metalness:.12,roughness:.42,transparent:true,opacity:.48,
   side:T.DoubleSide,depthWrite:true,
  });
  const innerMaterial=new T.MeshStandardMaterial({
   color:0x4fb8d5,emissive:0x063f53,emissiveIntensity:.52,
   metalness:.05,roughness:.56,transparent:true,opacity:.13,
   side:T.DoubleSide,depthWrite:false,
  });
  const wireMaterial=new T.MeshBasicMaterial({
   color:0xa7ecfb,wireframe:true,transparent:true,opacity:.075,
   depthWrite:false,blending:T.AdditiveBlending,
  });
  const geometries:T.BufferGeometry[]=[];
  const brainParts:Part[]=[];
  const partCenters:T.Vector3[]=[];
  const corticalCenters:T.Vector3[]=[];
  const markers:MarkerEntry[]=[];
  const markerGeometry=new T.SphereGeometry(1,14,10);
  const labelLayer=document.createElement('div');labelLayer.className='ora-brain-label-layer';el.appendChild(labelLayer);
  let brainCenter=new T.Vector3(),brainRadius=.1,lastReset=-1,lastZoom=1,lastSelected:number|null=null,lastSpotlight:string|null=null;

  const send=(payload:unknown)=>{
   if(window.parent&&window.parent!==window)window.parent.postMessage(payload,window.location.origin);
  };
  const markerColor=(data:MarkerData)=>{
   if(data.temporary)return 0xff565f;
   if(data.tentative)return 0xf0c978;
   if(data.kind==='branch')return 0x7ee0c6;
   return data.kind==='area'?0xc7f5ff:0x9de8f8;
  };
  const disposeMarkers=()=>{
   for(const entry of markers){
    (entry.core.material as T.Material).dispose();
    (entry.halo.material as T.Material).dispose();
    entry.label?.remove();
   }
   markers.splice(0,markers.length);
   markerGroup.clear();
  };
  const chooseCenter=(key:string,index:number)=>{
   const pool=corticalCenters.length?corticalCenters:partCenters;
   if(!pool.length)return new T.Vector3();
   const base=pool[hash(key+'|'+index)%pool.length].clone();
   const outward=base.clone().sub(brainCenter);
   if(outward.lengthSq()>.000001)base.add(outward.normalize().multiplyScalar(brainRadius*.045));
   return base;
  };
  const postSelect=(data:MarkerData)=>send({type:'ora:brain-select',version:1,node:data});
  const rebuildMarkers=()=>{
   disposeMarkers();
   if(!partCenters.length)return;
   const stars=Array.isArray(latest.current.stars)?latest.current.stars:[];
   const data:MarkerData[]=[
    ...AREAS.map((area,index)=>({index,area:area.id,kind:'area' as const})),
    ...stars.map((star,index)=>({index:index+8,area:star.area,kind:star.kind,id:star.id,
      temporary:!!star.temporary,tentative:!!star.tentative,complete:!!star.complete})),
   ];
   data.forEach((item,i)=>{
    const radius=brainRadius*(item.kind==='area' ? .025 : .016);
    const coreMat=new T.MeshBasicMaterial({color:markerColor(item),transparent:true,opacity:.97,depthWrite:false});
    const haloMat=new T.MeshBasicMaterial({color:markerColor(item),transparent:true,opacity:item.kind==='area' ? .16 : .11,depthWrite:false,blending:T.AdditiveBlending});
    const core=new T.Mesh(markerGeometry,coreMat),halo=new T.Mesh(markerGeometry,haloMat);
    const position=chooseCenter((item.id||item.area),i);
    core.position.copy(position);halo.position.copy(position);
    core.scale.setScalar(radius);halo.scale.setScalar(radius*3.2);
    core.renderOrder=20;halo.renderOrder=19;core.userData.marker=item;
    markerGroup.add(halo,core);
    const entry:MarkerEntry={data:item,core,halo};
    if(item.kind==='area'){
     const button=document.createElement('button');
     button.type='button';button.className='ora-brain-label';
     button.textContent=AREAS[item.index]?.label||item.area.toUpperCase();
     button.setAttribute('aria-label','Apri area '+button.textContent.toLowerCase());
     button.addEventListener('click',e=>{e.stopPropagation();postSelect(item);});
     labelLayer.appendChild(button);entry.label=button;
    }
    markers.push(entry);
   });
   applySelection();
  };
  const applySelection=()=>{
   const selected=latest.current.selectedIndex??null;
   const spotlight=latest.current.spotlightId??null;
   for(const entry of markers){
    const active=entry.data.index===selected||(entry.data.id&&entry.data.id===spotlight);
    const areaActive=!active&&latest.current.area&&entry.data.kind==='area'&&entry.data.area===latest.current.area;
    entry.core.scale.setScalar(brainRadius*(entry.data.kind==='area' ? .025 : .016)*(active?1.75:areaActive?1.38:1));
    entry.halo.scale.setScalar(brainRadius*(entry.data.kind==='area' ? .025 : .016)*(active?5.0:areaActive?4.0:3.2));
    (entry.halo.material as T.MeshBasicMaterial).opacity=active ? .34 : areaActive ? .24 : (entry.data.kind==='area' ? .16 : .11);
   }
   lastSelected=selected;lastSpotlight=spotlight;
  };
  const fit=()=>{
   const box=new T.Box3().setFromObject(brain);
   if(box.isEmpty())return;
   const size=box.getSize(new T.Vector3());
   const maxDim=Math.max(size.x,size.y,size.z);
   const distance=maxDim/(2*Math.tan(T.MathUtils.degToRad(camera.fov/2)))*1.34;
   controls.target.set(0,0,0);
   camera.position.set(distance*.42,distance*.12,distance);
   camera.near=Math.max(.001,distance/200);camera.far=Math.max(20,distance*20);camera.updateProjectionMatrix();
   controls.update();
  };
  const applyZoom=()=>{
   const value=clamp(Number(latest.current.zoomOverride)||1,.72,1.55);
   camera.zoom=value;camera.updateProjectionMatrix();lastZoom=value;
  };

  const load=async()=>{
   try{
    const response=await fetch('/bodyparts3d/models/atlas.json',{signal:abort.signal,cache:'force-cache'});
    if(!response.ok)throw new Error('Atlante anatomico non disponibile');
    const atlas=await response.json() as Atlas;
    if(atlas.version!=='BodyParts3D 4.0'||atlas.parts.length!==2234)throw new Error('Versione anatomica inattesa');
    const concept=atlas.concepts.find(c=>c.id===BRAIN_CONCEPT_ID&&c.name.toLowerCase()==='brain');
    if(!concept||concept.elements.length<50)throw new Error('Mesh encefalo non trovate');
    const ids=new Set(concept.elements);
    const parts=atlas.parts.filter(p=>ids.has(p.id));
    brainParts.push(...parts);
    const wantedChunks=Array.from(new Set(parts.map(p=>p.chunk))).sort((a,b)=>a-b);
    const partsByChunk=new Map<number,Part[]>();
    parts.forEach(part=>{const list=partsByChunk.get(part.chunk)||[];list.push(part);partsByChunk.set(part.chunk,list);});
    let loaded=0;
    for(const ci of wantedChunks){
     const chunk=atlas.chunks[ci];
     const compressed=!!chunk.gzip&&typeof DecompressionStream!=='undefined';
     const chunkResponse=await fetch(compressed?chunk.gzip!:chunk.url,{signal:abort.signal,cache:'force-cache'});
     const buffer=await decodeModelResponse(chunkResponse,chunk.bytes,compressed);
     if(disposed)return;
     for(const part of partsByChunk.get(ci)||[]){
      const geometry=new T.BufferGeometry();
      geometry.setAttribute('position',new T.BufferAttribute(new Float32Array(buffer,part.positions,part.vertexCount*3),3));
      geometry.setAttribute('normal',new T.BufferAttribute(new Int16Array(buffer,part.normals,part.vertexCount*3),3,true));
      geometry.setIndex(new T.BufferAttribute(new Uint32Array(buffer,part.indices,part.indexCount),1));
      geometry.computeBoundingSphere();geometries.push(geometry);
      const outer=surfaceLike(part.name);
      const mesh=new T.Mesh(geometry,outer?surfaceMaterial:innerMaterial);mesh.frustumCulled=false;brain.add(mesh);
      if(outer){const wire=new T.Mesh(geometry,wireMaterial);wire.frustumCulled=false;wire.renderOrder=4;brain.add(wire);}
      const center=boundsCenter(part);partCenters.push(center);
      if(outer)corticalCenters.push(center);
     }
     loaded++;send({type:'ora:brain-progress',version:1,progress:Math.round(loaded/wantedChunks.length*100)});
    }
    const box=new T.Box3().setFromObject(brain);
    brainCenter=box.getCenter(new T.Vector3());
    const size=box.getSize(new T.Vector3());brainRadius=Math.max(size.x,size.y,size.z)/2;
    brain.position.sub(brainCenter);
    fit();applyZoom();rebuildMarkers();
    setStatus('ready');send({type:'ora:brain-ready',version:1,meshCount:parts.length,concept:BRAIN_CONCEPT_ID});
   }catch(e){
    if(abort.signal.aborted||disposed)return;
    setStatus('error');setError(e instanceof Error?e.message:'Cervello 3D non disponibile');
    send({type:'ora:brain-error',version:1});
   }
  };

  const message=(event:MessageEvent)=>{
   if(event.source!==window.parent||event.origin!==window.location.origin)return;
   const payload=event.data;
   if(!payload||payload.type!=='ora:brain-state'||typeof payload.options!=='object')return;
   const next=payload.options as PresenceOptions;
   const starsChanged=JSON.stringify((latest.current.stars||[]).map(s=>[s.id,s.area,s.kind,!!s.temporary,!!s.tentative,!!s.complete]))!==
    JSON.stringify((next.stars||[]).map(s=>[s.id,s.area,s.kind,!!s.temporary,!!s.tentative,!!s.complete]));
   latest.current={...latest.current,...next,stars:Array.isArray(next.stars)?next.stars:latest.current.stars};
   controls.autoRotate=!(latest.current.paused||latest.current.reduced);
   controls.autoRotateSpeed=latest.current.mode==='think' ? .7 : latest.current.mode==='listen' ? .46 : .34;
   if(starsChanged&&partCenters.length)rebuildMarkers();
   if(lastSelected!==(latest.current.selectedIndex??null)||lastSpotlight!==(latest.current.spotlightId??null))applySelection();
   const zoom=clamp(Number(latest.current.zoomOverride)||1,.72,1.55);
   if(Math.abs(zoom-lastZoom)>.001)applyZoom();
   if((latest.current.resetKey??0)!==lastReset){lastReset=latest.current.resetKey??0;fit();applyZoom();}
  };
  window.addEventListener('message',message);

  let down:{x:number;y:number;id:number}|null=null;
  const pointerDown=(e:PointerEvent)=>{down={x:e.clientX,y:e.clientY,id:e.pointerId};};
  const pointerUp=(e:PointerEvent)=>{
   if(!down||down.id!==e.pointerId)return;
   const moved=Math.hypot(e.clientX-down.x,e.clientY-down.y)>8;down=null;if(moved)return;
   const rect=renderer.domElement.getBoundingClientRect();
   const pointer=new T.Vector2((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1);
   const ray=new T.Raycaster();ray.setFromCamera(pointer,camera);
   const hit=ray.intersectObjects(markers.map(m=>m.core),false)[0];
   const marker=hit?.object.userData.marker as MarkerData|undefined;
   if(marker)postSelect(marker);
  };
  renderer.domElement.addEventListener('pointerdown',pointerDown);
  renderer.domElement.addEventListener('pointerup',pointerUp);

  const resize=()=>{
   if(disposed)return;
   const w=Math.max(1,el.clientWidth),h=Math.max(1,el.clientHeight);
   renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,w<700||h<600?1.5:2));
   renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();
  };
  const observer=new ResizeObserver(resize);observer.observe(el);resize();
  const projected=new T.Vector3(),world=new T.Vector3(),clock=new T.Clock();
  const animate=()=>{
   if(disposed)return;frame=requestAnimationFrame(animate);
   const elapsed=clock.getElapsedTime(),state=latest.current;
   controls.autoRotate=!(state.paused||state.reduced);
   controls.update();
   const pulse=.5+.5*Math.sin(elapsed*(state.mode==='think'?3.1:1.55));
   surfaceMaterial.emissiveIntensity=.66+pulse*(state.mode==='think' ? .32 : .12);
   wireMaterial.opacity=.055+pulse*.035;
   markers.forEach(entry=>{
    const selected=entry.data.index===(state.selectedIndex??null)||(entry.data.id&&entry.data.id===state.spotlightId);
    const base=entry.data.kind==='area' ? .97 : .88;
    (entry.core.material as T.MeshBasicMaterial).opacity=clamp(base+pulse*(selected ? .03 : .015),0,1);
    if(entry.label){
     entry.core.getWorldPosition(world);projected.copy(world).project(camera);
     const visible=projected.z>-1&&projected.z<1;
     const x=(projected.x*.5+.5)*el.clientWidth,y=(-projected.y*.5+.5)*el.clientHeight;
     entry.label.style.transform=`translate(-50%,-50%) translate(${x.toFixed(1)}px,${y.toFixed(1)}px)`;
     entry.label.style.opacity=visible?String(clamp(.42+(1-projected.z)*.38,.35,.95)):'0';
     entry.label.style.pointerEvents=visible?'auto':'none';
     entry.label.classList.toggle('active',selected||entry.data.area===state.area);
    }
   });
   renderer.render(scene,camera);
  };
  load();animate();

  const contextLost=(event:Event)=>{event.preventDefault();setStatus('error');setError('La sessione WebGL è stata interrotta.');send({type:'ora:brain-error',version:1});};
  renderer.domElement.addEventListener('webglcontextlost',contextLost);

  return()=>{
   disposed=true;abort.abort();cancelAnimationFrame(frame);observer.disconnect();
   window.removeEventListener('message',message);
   renderer.domElement.removeEventListener('pointerdown',pointerDown);
   renderer.domElement.removeEventListener('pointerup',pointerUp);
   renderer.domElement.removeEventListener('webglcontextlost',contextLost);
   controls.dispose();disposeMarkers();markerGeometry.dispose();
   geometries.forEach(g=>g.dispose());surfaceMaterial.dispose();innerMaterial.dispose();wireMaterial.dispose();
   renderer.dispose();labelLayer.remove();renderer.domElement.remove();
  };
 },[]);

 return <main className="ora-brain-presence" data-testid="ora-brain-webgl" data-status={status}>
  <div className="ora-brain-aura" aria-hidden="true"/>
  <div className="ora-brain-host" ref={host}/>
  {status==='loading'?<div className="ora-brain-status" role="status"><span/>Preparo il cervello 3D…</div>:null}
  {status==='error'?<div className="ora-brain-status error" role="alert">{error}</div>:null}
 </main>;
}
