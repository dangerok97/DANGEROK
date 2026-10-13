import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'expo-router';
import { catalogApi, type CatalogEntry, type CatalogResult } from './catalogApi';
import { grayFrame, type GrayFrame } from './tracking';
import { VisionPresentation } from './presentation';
import { VisionGestures, clampZoom, approach } from './gestures';
import { visualStyle } from './visualStyle';
import { recognitionHelpStyle } from './recognitionHelpStyle';
import {walkthroughFor,sourcesForStep,TourClock,type Walkthrough} from './walkthrough';
import {arrivalAt,currentBox,originInView} from './arrival';
import type {Box} from './scene';
import {CameraTorch, type TorchState, TORCH_UNAVAILABLE, cameraCrop, sameCrop, drawCameraCrop, clampCameraZoom} from './cameraControls';
import {filterCatalog} from './catalogSearch';
import {AnatomyExplorer} from './AnatomyExplorer.web';
import {warmAnatomyReference} from './anatomyWarmup.web';
import type {BodyRegion} from './anatomyFocus';

type Mode = 'idle' | 'opening' | 'live' | 'photo' | 'catalog';
const sleep = (ms:number) => new Promise<void>(resolve=>setTimeout(resolve,ms));
function difference(a:GrayFrame|null,b:GrayFrame|null){
  if(!a||!b||a.data.length!==b.data.length)return 1;
  let d=0;for(let i=0;i<a.data.length;i+=8)d+=Math.abs(a.data[i]-b.data[i]);
  return d/Math.ceil(a.data.length/8)/255;
}

export default function LiveExplorer(){
  const router=useRouter();
  const [mode,setMode]=useState<Mode>('idle');
  const [anatomyActive,setAnatomyActive]=useState(false);
  const [anatomyRegion,setAnatomyRegion]=useState<BodyRegion>('full_body');
  const [anatomySide,setAnatomySide]=useState<'left'|'right'|'unknown'>('unknown');
  const [anatomyBox,setAnatomyBox]=useState<Box|null>(null);
  const [anatomyPosePoints,setAnatomyPosePoints]=useState<Record<string,[number,number]>|null>(null);
  const anatomyActiveRef=useRef(false);
  const [stage,setStage]=useState('Inquadra. Esplora. Capisci.');
  const [error,setError]=useState<string|null>(null);
  const [busy,setBusy]=useState(false);
  const [canHint,setCanHint]=useState(false);
  const [objectHint,setObjectHint]=useState('');
  const objectHintRef=useRef('');
  const [result,setResult]=useState<CatalogResult|null>(null);
  const [selected,setSelected]=useState('');
  const [focused,setFocused]=useState(false);
  const [detailOpen,setDetailOpen]=useState(true);
  const [moreDetail,setMoreDetail]=useState(false);
  const [expanded,setExpanded]=useState(true);
  const [opening,setOpening]=useState(100);
  const [entries,setEntries]=useState<CatalogEntry[]>([]);
  const [libraryOpen,setLibraryOpen]=useState(false);
  const [catalogQuery,setCatalogQuery]=useState('');
  const [catalogCategory,setCatalogCategory]=useState('Tutti');
  const [cameraZoom,setCameraZoomUI]=useState(1);
  const [cameraPanel,setCameraPanel]=useState(false);
  const [torchUI,setTorchUI]=useState<TorchState>({supported:false,on:false,busy:false,message:TORCH_UNAVAILABLE});
  const cameraZoomRef=useRef(1);
  const torch=useRef<CameraTorch|null>(null);
  const stageElement=useRef<HTMLElement|null>(null);
  const [infoOpen,setInfoOpen]=useState(false);
  const [photoURL,setPhotoURL]=useState<string|null>(null);
  const [tourUI,setTourUI]=useState<{index:number;playing:boolean;done:boolean}|null>(null);
  const [tourSources,setTourSources]=useState(false);
  const video=useRef<HTMLVideoElement>(null);
  const canvas=useRef<HTMLCanvasElement>(null);
  const picker=useRef<HTMLInputElement>(null);
  const tabs=useRef<HTMLDivElement>(null);
  const stream=useRef<MediaStream|null>(null);
  const photo=useRef<HTMLImageElement|null>(null);
  const photoObjectURL=useRef<string|null>(null);
  const modeRef=useRef<Mode>('idle');
  const epoch=useRef(0),alive=useRef(true);
  const request=useRef<AbortController|null>(null);
  const busyRef=useRef(false),nextScan=useRef(Infinity);
  const scanReference=useRef<GrayFrame|null>(null);
  const scene=useRef<VisionPresentation|null>(null);
  const heldResult=useRef<CatalogResult|null>(null);
  const selectedRef=useRef('');
  const view=useRef({progress:0,target:1,yaw:.46,pitch:-.22,zoom:1,focus:0,focusTarget:0,reduceMotion:false});
  const gestures=useRef(new VisionGestures());
  const arrival=useRef<{elapsed:number;box:Box|null;sw:number;sh:number}|null>(null);
  const tour=useRef<{definition:Walkthrough;clock:TourClock;before:typeof view.current}|null>(null);
  const finishArrival=useCallback(()=>{if(arrival.current){arrival.current=null;view.current.progress=1;}},[]);
  const endTour=useCallback((restore=true)=>{
    const active=tour.current;if(active){active.clock.stop();if(restore){const reduced=view.current.reduceMotion;Object.assign(view.current,active.before,{reduceMotion:reduced});if(alive.current){setOpening(Math.round(view.current.target*100));setExpanded(view.current.target>.5);}}}
    tour.current=null;if(alive.current){setTourUI(null);setTourSources(false);}
  },[]);

  const changeMode=(m:Mode)=>{modeRef.current=m;if(alive.current)setMode(m);};
  const resetView=useCallback(()=>{
    endTour(false);arrival.current=null;gestures.current.clear();selectedRef.current='';
    Object.assign(view.current,{yaw:.46,pitch:-.22,zoom:1,focus:0,focusTarget:0,progress:0,target:1});
    if(alive.current){setSelected('');setFocused(false);setDetailOpen(true);setMoreDetail(false);setOpening(100);setExpanded(true);}
  },[endTour]);
  const choose=useCallback((key:string)=>{
    if(!heldResult.current?.manifest?.parts.some(p=>p.key===key))return;
    endTour();finishArrival();
    if(selectedRef.current!==key)view.current.focus=0;
    selectedRef.current=key;view.current.focusTarget=1;view.current.zoom=1;
    setSelected(key);setFocused(true);setDetailOpen(true);setMoreDetail(false);
    const button=tabs.current?.querySelector<HTMLButtonElement>('[data-testid="vision-part-'+key+'"]');
    button?.scrollIntoView({block:'nearest',inline:'nearest',behavior:'auto'});
  },[endTour,finishArrival]);
  const overview=useCallback(()=>{
    endTour();finishArrival();view.current.focusTarget=0;view.current.zoom=1;setFocused(false);setMoreDetail(false);
  },[endTour,finishArrival]);
  const stop=useCallback(()=>{
    epoch.current++;request.current?.abort();request.current=null;
    torch.current?.dispose();torch.current=null;cameraZoomRef.current=1;
    stream.current?.getTracks().forEach(t=>t.stop());stream.current=null;
    if(video.current)video.current.srcObject=null;
    if(photoObjectURL.current)URL.revokeObjectURL(photoObjectURL.current);
    photoObjectURL.current=null;photo.current=null;modeRef.current='idle';
    busyRef.current=false;nextScan.current=Infinity;scene.current=null;heldResult.current=null;scanReference.current=null;
    resetView();objectHintRef.current='';
    anatomyActiveRef.current=false;
    if(alive.current){setAnatomyActive(false);setAnatomyRegion('full_body');setAnatomyBox(null);setAnatomyPosePoints(null);setAnatomyPosePoints(null);setCanHint(false);setObjectHint('');setMode('idle');setBusy(false);setResult(null);setPhotoURL(null);setInfoOpen(false);setAnatomyBox(null);setCameraZoomUI(1);setCameraPanel(false);setTorchUI({supported:false,on:false,busy:false,message:TORCH_UNAVAILABLE});}
  },[resetView]);
  const apply=useCallback((value:CatalogResult,origin?:{box:Box;sw:number;sh:number}|null)=>{
    if(!value.manifest||!value.version_id)return;
    if(heldResult.current?.version_id!==value.version_id){
      scene.current=new VisionPresentation(value.manifest);resetView();
      view.current.progress=view.current.reduceMotion?1:0;
    }
    if(modeRef.current!=='catalog')arrival.current={elapsed:0,box:origin?.box||null,sw:origin?.sw||1,sh:origin?.sh||1};
    heldResult.current=value;setResult(value);setCanHint(false);
    setStage(modeRef.current==='catalog'?'Anteprima catalogo · non è un riconoscimento':'Schema fissato · tocca una parte');
    nextScan.current=Infinity;
    const ticket=epoch.current;
    void catalogApi.list().then(data=>{if(alive.current&&epoch.current===ticket)setEntries(data.models);}).catch(()=>{});
  },[resetView]);

  const changeCameraZoom=useCallback((requested:number)=>{
    if(modeRef.current!=='live')return;
    const zoom=clampCameraZoom(requested);
    if(Math.abs(zoom-cameraZoomRef.current)<.002)return;
    cameraZoomRef.current=zoom;setCameraZoomUI(zoom);
    // Old replies cannot describe the new crop. Held models never trigger new AI.
    if(!scene.current){
      epoch.current++;request.current?.abort();request.current=null;busyRef.current=false;
      scanReference.current=null;setBusy(false);setError(null);
      setStage('Inquadra con lo zoom: analizzo la zona visibile.');
      nextScan.current=performance.now()+700;
    }
  },[]);

  const captureScan=useCallback(async(hintOverride?:string)=>{
    if(busyRef.current||scene.current||anatomyActiveRef.current||!['live','photo'].includes(modeRef.current))return;
    const source=modeRef.current==='live'?video.current:photo.current;if(!source)return;
    const rawWidth=source instanceof HTMLVideoElement?source.videoWidth:source.naturalWidth;
    const rawHeight=source instanceof HTMLVideoElement?source.videoHeight:source.naturalHeight;if(!rawWidth||!rawHeight)return;
    const liveCapture=modeRef.current==='live';
    const rect=stageElement.current?.getBoundingClientRect();
    const crop=liveCapture?cameraCrop(rawWidth,rawHeight,rect?.width||rawWidth,rect?.height||rawHeight,cameraZoomRef.current):{x:0,y:0,width:rawWidth,height:rawHeight};
    const sw=crop.width,sh=crop.height;
    const snapshot=document.createElement('canvas'),scale=Math.min(1,960/Math.max(sw,sh));
    snapshot.width=Math.round(sw*scale);snapshot.height=Math.round(sh*scale);
    const context=snapshot.getContext('2d');if(!context)return;
    drawCameraCrop(context,source,crop,snapshot.width,snapshot.height);
    const small=document.createElement('canvas');small.width=160;small.height=Math.round(160*sh/sw);
    const sc=small.getContext('2d',{willReadFrequently:true});if(!sc)return;
    sc.drawImage(snapshot,0,0,small.width,small.height);scanReference.current=grayFrame(sc.getImageData(0,0,small.width,small.height));
    const dataURI=snapshot.toDataURL('image/jpeg',.78),ticket=epoch.current;
    const controller=new AbortController();request.current=controller;
    busyRef.current=true;setBusy(true);setError(null);setStage('Riconosco e cerco nel catalogo…');
    try{
      let value=await catalogApi.scan(dataURI,String(ticket)+'-'+Date.now(),controller.signal,hintOverride??objectHintRef.current);
      const identification=value.identification;
      if(value.status==='anatomy'){
        // Live capture is already cropped to the visible stage. Only map photo
        // coordinates through CSS cover when the photo has a different aspect.
        const recognizedBox=value.identification?.bbox||null;
        const stageRect=stageElement.current?.getBoundingClientRect();
        const mappedBox=recognizedBox&&modeRef.current==='photo'&&stageRect
          ?originInView(recognizedBox,sw,sh,stageRect.width,stageRect.height)
          :recognizedBox;
        if(epoch.current===ticket&&alive.current) activateAtlas(value.body_region||value.identification?.body_region||'full_body',value.identification?.pose_points||null,mappedBox,value.identification?.body_side||value.body_side||'unknown');
        return;
      }
      for(let attempt=0;value.status==='building'&&attempt<12;attempt++){
        if(epoch.current!==ticket||controller.signal.aborted)return;
        setStage('Un nuovo schema è in preparazione…');await sleep(4000);
        if(!value.job_id||epoch.current!==ticket||controller.signal.aborted)return;
        value={...await catalogApi.job(value.job_id,controller.signal),identification};
      }
      if(epoch.current!==ticket||!alive.current)return;
      if(value.status==='family'&&value.manifest){
        // Check the earlier capture once; never tie a held model to tracking.
        let box:Box|null=null;
        if(value.identification?.bbox){
          if(modeRef.current==='photo')box=value.identification.bbox;
          else if(video.current?.videoWidth&&sc){
            const currentRect=stageElement.current?.getBoundingClientRect();
            const fresh=cameraCrop(video.current.videoWidth,video.current.videoHeight,currentRect?.width||rawWidth,currentRect?.height||rawHeight,cameraZoomRef.current);
            if(sameCrop(crop,fresh)){
              drawCameraCrop(sc,video.current,fresh,small.width,small.height);
              box=currentBox(scanReference.current,grayFrame(sc.getImageData(0,0,small.width,small.height)),value.identification.bbox);
            }
          }
        }
        apply(value,box?{box,sw,sh}:null);
      }
      else{scene.current=null;heldResult.current=null;setResult(null);setCanHint(value.can_hint===true||value.error_code==='object_uncertain');setStage(value.reason||'Ricostruzione in corso. Premi Riprova per verificarla.');nextScan.current=performance.now()+6000;}
    }catch(e:any){
      if(epoch.current!==ticket||!alive.current)return;
      setError(e?.name==='AbortError'?'Analisi scaduta. Il video non è stato interrotto.':String(e?.message||'Analisi non disponibile.'));
      setCanHint(false);setStage('Analisi non completata · il catalogo e la fotocamera restano disponibili.');nextScan.current=performance.now()+30000;
    }finally{if(epoch.current===ticket){busyRef.current=false;request.current=null;if(alive.current)setBusy(false);}}
  },[apply]);

  const openCamera=useCallback(async()=>{
    void warmAnatomyReference();
    stop();setLibraryOpen(false);setError(null);changeMode('opening');setStage('Consenti l’accesso alla fotocamera…');
    const ticket=epoch.current;
    try{
      if(!navigator.mediaDevices?.getUserMedia||!window.isSecureContext)throw new Error('Apri ORA in un browser HTTPS per usare la fotocamera.');
      const media=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:'environment'},width:{ideal:1280},frameRate:{ideal:24,max:30}}});
      if(epoch.current!==ticket||!alive.current){media.getTracks().forEach(t=>t.stop());return;}
      stream.current=media;if(!video.current){media.getTracks().forEach(t=>t.stop());return;}
      video.current.srcObject=media;await video.current.play();
      if(epoch.current!==ticket||!alive.current)return;
      const track=media.getVideoTracks()[0];
      if(track){
        const control=new CameraTorch(track,state=>{if(alive.current&&torch.current===control)setTorchUI(state);});
        torch.current=control;setTorchUI(control.snapshot());
        track.addEventListener('ended',()=>{if(alive.current&&stream.current===media){stop();setError('La fotocamera è stata disconnessa. Riaprila per continuare.');}},{once:true});
      }
      changeMode('live');setStage('Tieni l’oggetto al centro: lo riconosco automaticamente.');nextScan.current=performance.now()+1500;
    }catch(e:any){
      if(epoch.current!==ticket||!alive.current)return;
      stop();setError(e?.name==='NotAllowedError'?'Permesso negato. Abilita la fotocamera nelle impostazioni del sito.':String(e?.message||'Fotocamera non disponibile.'));
    }
  },[stop]);
  const activateAtlas=(region:BodyRegion='full_body',posePoints:Record<string,[number,number]>|null=null,box:Box|null=null,bodySide:'left'|'right'|'unknown'='unknown')=>{
    setAnatomyRegion(region);setAnatomySide(bodySide);setAnatomyPosePoints(posePoints);
    setAnatomyBox(box&&box.length===4&&box.every(n=>Number.isFinite(n))&&box[2]>.03&&box[3]>.03?box:null);
    epoch.current++;request.current?.abort();request.current=null;busyRef.current=false;
    anatomyActiveRef.current=true;setAnatomyActive(true);scene.current=null;
    heldResult.current=null;scanReference.current=null;resetView();setResult(null);
    setBusy(false);setError(null);setCanHint(false);setLibraryOpen(false);setInfoOpen(false);
    setStage('Persona riconosciuta · modello anatomico 3D fissato sull’immagine.');
    nextScan.current=Infinity;
  };
  const newObject=()=>{
    if(modeRef.current!=='live'){void openCamera();return;}
    // Dismiss only the model. Keep the stream and invalidate every old AI reply.
    epoch.current++;request.current?.abort();request.current=null;busyRef.current=false;
    scene.current=null;heldResult.current=null;scanReference.current=null;resetView();
    anatomyActiveRef.current=false;setAnatomyActive(false);setAnatomyRegion('full_body');
    objectHintRef.current='';setObjectHint('');setCanHint(false);
    setResult(null);setBusy(false);setError(null);setInfoOpen(false);setLibraryOpen(false);setCameraPanel(false);
    setStage('Inquadra il nuovo oggetto: lo riconosco automaticamente.');nextScan.current=performance.now()+300;
  };
  const closeAtlas=()=>{
    // Opening the reference from idle never acquires a camera, and X must not ask for one.
    if(modeRef.current==='idle'&&!stream.current){
      stop();setStage('Inquadra. Esplora. Capisci.');return;
    }
    newObject();
  };
  const pickPhoto=async(event:React.ChangeEvent<HTMLInputElement>)=>{
    void warmAnatomyReference();
    const file=event.target.files?.[0];event.target.value='';if(!file)return;
    stop();setLibraryOpen(false);setError(null);
    if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>12*1024*1024){setError('Scegli JPEG, PNG o WebP inferiore a 12 MB.');return;}
    const ticket=epoch.current,url=URL.createObjectURL(file);photoObjectURL.current=url;
    const img=new window.Image();img.src=url;
    try{await img.decode();if(epoch.current!==ticket)return;photo.current=img;setPhotoURL(url);changeMode('photo');await captureScan();}
    catch{if(epoch.current===ticket)setError('Questa foto non è leggibile.');}
  };
  const loadModel=async(entry:CatalogEntry)=>{
    stop();setLibraryOpen(false);setError(null);changeMode('catalog');setStage('Carico il modello salvato…');
    const ticket=epoch.current,ctrl=new AbortController();request.current=ctrl;setBusy(true);busyRef.current=true;
    try{const value=await catalogApi.model(entry.model_id,ctrl.signal);if(epoch.current===ticket)apply(value);}
    catch(e:any){if(epoch.current===ticket)setError(String(e?.message||'Modello non disponibile.'));}
    finally{if(epoch.current===ticket){setBusy(false);busyRef.current=false;request.current=null;}}
  };

  useEffect(()=>{
    alive.current=true;
    void catalogApi.list().then(data=>{if(alive.current)setEntries(data.models);}).catch(e=>{if(alive.current)setError(e.message);});
    const mq=window.matchMedia('(prefers-reduced-motion: reduce)');view.current.reduceMotion=mq.matches;
    const motion=()=>{view.current.reduceMotion=mq.matches;if(mq.matches&&tour.current){tour.current.clock.stop();setTourUI({index:tour.current.clock.index,playing:false,done:tour.current.clock.done});}};mq.addEventListener?.('change',motion);
    const hidden=()=>{if(document.hidden){stop();setStage('Fotocamera fermata quando ORA è passata in secondo piano.');}};
    document.addEventListener('visibilitychange',hidden);window.addEventListener('pagehide',stop);
    return()=>{alive.current=false;stop();document.removeEventListener('visibilitychange',hidden);window.removeEventListener('pagehide',stop);mq.removeEventListener?.('change',motion);};
  },[stop]);
  useEffect(()=>{
    const node=canvas.current;if(!node)return;
    const wheel=(e:WheelEvent)=>{if(!scene.current&&modeRef.current!=='live')return;e.preventDefault();if(scene.current)view.current.zoom=clampZoom(view.current.zoom*Math.exp(-e.deltaY*.0015));else changeCameraZoom(cameraZoomRef.current*Math.exp(-e.deltaY*.0015));};
    node.addEventListener('wheel',wheel,{passive:false});return()=>node.removeEventListener('wheel',wheel);
  },[]);
  useEffect(()=>{
    let raf=0,lastSample=0,lastFrame=0,lastSignature='';
    const small=document.createElement('canvas'),pixels=small.getContext('2d',{willReadFrequently:true});
    const paint=(time:number)=>{
      raf=requestAnimationFrame(paint);
      if(document.hidden||time-lastFrame<30)return;
      const elapsed=Math.min(80,time-lastFrame);lastFrame=time;
      const node=canvas.current;if(!node)return;const ctx=node.getContext('2d');if(!ctx)return;
      const w=node.clientWidth,h=node.clientHeight,dpr=Math.min(2,window.devicePixelRatio||1);if(!w||!h)return;
      const live=modeRef.current==='live',v=video.current;
      if(live&&!scene.current&&!anatomyActiveRef.current&&v?.videoWidth&&pixels&&time-lastSample>120){
        const rect=stageElement.current?.getBoundingClientRect();
        const crop=cameraCrop(v.videoWidth,v.videoHeight,rect?.width||w,rect?.height||h,cameraZoomRef.current);
        lastSample=time;small.width=160;small.height=Math.round(160*crop.height/crop.width);
        drawCameraCrop(pixels,v,crop,small.width,small.height);
        if(!busyRef.current&&time>=nextScan.current){
          const changed=difference(scanReference.current,grayFrame(pixels.getImageData(0,0,small.width,small.height)))>.13;
          if(!scanReference.current||changed){nextScan.current=time+6000;void captureScan();}
        }
      }
      const settings=view.current;
      let origin:{box:Box;mix:number}|undefined;
      if(arrival.current){
        arrival.current.elapsed+=elapsed;
        const state=arrivalAt(arrival.current.elapsed,settings.reduceMotion);
        settings.progress=state.progress;
        const box=arrival.current.box?originInView(arrival.current.box,arrival.current.sw,arrival.current.sh,w,h):null;
        if(box&&state.active)origin={box,mix:state.mix};
        if(!state.active)arrival.current=null;
      }else settings.progress=approach(settings.progress,settings.target,elapsed,settings.reduceMotion);
      const activeTour=tour.current;
      if(activeTour){
        const previous=[activeTour.clock.index,activeTour.clock.playing,activeTour.clock.done].join('|');
        activeTour.clock.tick(elapsed);
        if(previous!==[activeTour.clock.index,activeTour.clock.playing,activeTour.clock.done].join('|'))
          setTourUI({index:activeTour.clock.index,playing:activeTour.clock.playing,done:activeTour.clock.done});
      }
      settings.focus=approach(settings.focus,settings.focusTarget,elapsed,settings.reduceMotion);
      const signature=[w,h,dpr,arrival.current?.elapsed,activeTour?.clock.index,activeTour?.clock.phase.toFixed(3),Boolean(activeTour),modeRef.current,heldResult.current?.version_id,selectedRef.current,settings.progress.toFixed(3),settings.focus.toFixed(3),settings.yaw.toFixed(3),settings.pitch.toFixed(3),settings.zoom.toFixed(3)].join('|');
      if(signature===lastSignature)return;lastSignature=signature;
      if(node.width!==Math.round(w*dpr)||node.height!==Math.round(h*dpr)){node.width=Math.round(w*dpr);node.height=Math.round(h*dpr);}
      ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
      node.dataset.arrival=arrival.current?(origin?'from-object':'centred'):'complete';
      node.dataset.tourStep=activeTour?String(activeTour.clock.index):'';node.dataset.tourPhase=activeTour?activeTour.clock.phase.toFixed(3):'';
      node.dataset.sceneState=anatomyActiveRef.current?'anatomy':scene.current?'held':'acquiring';node.dataset.focusedPart=settings.focusTarget?selectedRef.current:'';
      node.dataset.zoom=settings.zoom.toFixed(3);node.dataset.yaw=settings.yaw.toFixed(3);
      if(scene.current){
        scene.current.draw(ctx,w,h,{progress:settings.progress,yaw:settings.yaw,pitch:settings.pitch,selected:activeTour?'':selectedRef.current,focus:activeTour?0:settings.focus,zoom:settings.zoom,origin,tour:activeTour?{step:activeTour.definition.steps[activeTour.clock.index],phase:settings.reduceMotion?1:activeTour.clock.phase}:undefined});
        node.dataset.partCount=String(scene.current.manifest.parts.length);node.dataset.selectedPart=selectedRef.current;
      }else{node.dataset.partCount='0';node.dataset.selectedPart='';}
      if(live&&!scene.current){
        const x=w*.26,y=h*.22,bw=w*.48,bh=h*.55;
        ctx.strokeStyle='rgba(144,221,237,.65)';ctx.lineWidth=1.3;
        for(const [xx,yy,sx,sy] of [[x,y,1,1],[x+bw,y,-1,1],[x,y+bh,1,-1],[x+bw,y+bh,-1,-1]]){
          ctx.beginPath();ctx.moveTo(xx+sx*17,yy);ctx.lineTo(xx,yy);ctx.lineTo(xx,yy+sy*17);ctx.stroke();
        }
      }
    };raf=requestAnimationFrame(paint);return()=>cancelAnimationFrame(raf);
  },[captureScan]);

  const setExplosion=(percent:number)=>{endTour();finishArrival();const value=Math.max(0,Math.min(100,percent));view.current.target=value/100;setOpening(value);setExpanded(value>50);};
  const toggleExpansion=()=>setExplosion(view.current.target>.5?0:100);
  const onDown=(e:React.PointerEvent<HTMLCanvasElement>)=>{
    if(!scene.current&&modeRef.current!=='live')return;finishArrival();gestures.current.down(e.pointerId,e.clientX,e.clientY);
    try{e.currentTarget.setPointerCapture(e.pointerId);}catch{/* Synthetic pointer tests do not create native capture. */}
  };
  const onMove=(e:React.PointerEvent<HTMLCanvasElement>)=>{
    if(!scene.current&&modeRef.current!=='live')return;
    const d=gestures.current.move(e.pointerId,e.clientX,e.clientY);
    if(!scene.current){changeCameraZoom(cameraZoomRef.current*d.zoomFactor);return;}
    view.current.yaw+=d.yaw;view.current.pitch=Math.max(-1.1,Math.min(1.1,view.current.pitch+d.pitch));view.current.zoom=clampZoom(view.current.zoom*d.zoomFactor);
  };
  const onUp=(e:React.PointerEvent<HTMLCanvasElement>,cancelled=false)=>{
    const tap=gestures.current.up(e.pointerId,e.clientX,e.clientY,cancelled);
    if(tap&&scene.current){const r=e.currentTarget.getBoundingClientRect(),key=scene.current.hit(e.clientX-r.left,e.clientY-r.top);if(key)choose(key);}
    if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);
  };
  const keyboard=(e:React.KeyboardEvent<HTMLCanvasElement>)=>{
    if(!scene.current)return;finishArrival();
    if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','-','=','0','Escape'].includes(e.key))e.preventDefault();
    if(e.key==='ArrowLeft')view.current.yaw-=.12;if(e.key==='ArrowRight')view.current.yaw+=.12;
    if(e.key==='ArrowUp')view.current.pitch=Math.max(-1.1,view.current.pitch-.1);
    if(e.key==='ArrowDown')view.current.pitch=Math.min(1.1,view.current.pitch+.1);
    if(e.key==='+'||e.key==='=')view.current.zoom=clampZoom(view.current.zoom*1.2);
    if(e.key==='-')view.current.zoom=clampZoom(view.current.zoom/1.2);
    if(e.key==='0')view.current.zoom=1;if(e.key==='Escape')overview();
  };
  const definition=result?.manifest?walkthroughFor(result.manifest,result.source_type):null;
  const startTour=()=>{
    if(!definition)return;
    endTour();finishArrival();
    const before={...view.current};
    const clock=new TourClock(definition.steps.length);clock.start(!view.current.reduceMotion);
    tour.current={definition,clock,before};
    Object.assign(view.current,{target:1,progress:1,zoom:1,focus:0,focusTarget:0});
    setOpening(100);setExpanded(true);setTourUI({index:0,playing:clock.playing,done:false});setTourSources(false);setInfoOpen(false);setLibraryOpen(false);
  };
  const syncTour=()=>{const c=tour.current?.clock;if(c)setTourUI({index:c.index,playing:c.playing,done:c.done});};
  const step=tourUI&&definition?definition.steps[tourUI.index]:null;
  const currentPart=result?.manifest?.parts.find(p=>p.key===selected),live=mode==='live';
  const visibleEntries=filterCatalog(entries,catalogQuery,catalogCategory);
  const categories=['Tutti',...Array.from(new Set(entries.map(e=>e.category||'Altri oggetti'))).sort()];

  return <div className={'vx-root'+(result?' has-model':'')+(anatomyActive?' has-anatomy':'')} data-testid="vision-live-explorer" data-version="visual-v2" data-experience="guided-v3" data-recognition="body-region-v4">
    <style>{visualStyle+recognitionHelpStyle}</style>
    <header className="vx-header">
      <button aria-label="Torna a ORA" className="vx-back" onClick={()=>{stop();if(router.canGoBack())router.back();else router.replace('/ora');}}>←</button>
      <div className="vx-brand">ORA <span>VISION</span><small className="vx-version">ESPLORA L’ESSENZIALE</small></div>
      <button className="vx-catalog" data-testid="vision-catalog-toggle" aria-expanded={libraryOpen} onClick={()=>{if(tour.current){tour.current.clock.stop();syncTour();}setInfoOpen(false);setLibraryOpen(v=>!v);}}>Catalogo <span>{entries.length}</span></button>
    </header>
    <section ref={stageElement} className="vx-stage" aria-label="Fotocamera e scomposizione interattiva" data-testid="vision-stage">
      <video ref={video} autoPlay playsInline muted data-testid="vision-camera-video" aria-label="Video live della fotocamera" style={{opacity:live?1:0,transform:`scale(${cameraZoom})`,transformOrigin:"center"}} data-camera-zoom={cameraZoom.toFixed(2)}/>
      {photoURL&&<img src={photoURL} alt="Foto scelta per l’analisi" className="vx-photo"/>}
      <div className={'vx-shade '+(result?'vx-shade-result':anatomyActive?'vx-shade-anatomy':'')}/>
      <canvas ref={canvas} className="vx-canvas" data-testid="vision-scene" tabIndex={result||live?0:-1} aria-label={result?"Scena 3D: trascina per ruotare, due dita per ingrandire i componenti.":"Fotocamera: due dita per lo zoom digitale. I comandi sono disponibili anche nei pulsanti."} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={e=>onUp(e,true)} onLostPointerCapture={e=>{gestures.current.up(e.pointerId,e.clientX,e.clientY,true);}} onKeyDown={keyboard}/>
      {anatomyActive&&<AnatomyExplorer region={anatomyRegion} bodySide={anatomySide} posePoints={anatomyPosePoints} anchorBox={anatomyBox} onClose={closeAtlas}/>}
      <div className="vx-topline"><span className={'vx-tag '+(live?'vx-tag-live':'')}>{live?'● LIVE':mode==='photo'?'FOTO':mode==='catalog'?'CATALOGO':'VISION X-RAY'}</span><button className="vx-evidence" onClick={()=>{if(tour.current){tour.current.clock.stop();syncTour();}setLibraryOpen(false);setInfoOpen(true);}} aria-label="Informazioni sullo schema indicativo">Schema indicativo ⓘ</button></div>
      {(mode==='idle'||mode==='opening')&&!result&&!anatomyActive&&<div className="vx-empty"><div className="vx-reticle">⌖</div><h1>Guarda più da vicino.<br/>Scopri come è fatto.</h1><p>Inquadra un oggetto. Esplora i suoi componenti.<br/>Tocca una parte per portarla davanti a te.</p>{mode==='idle'&&<><button className="vx-main" data-testid="vision-open-camera" onClick={()=>void openCamera()}>Apri fotocamera</button><button className="vx-minor" onClick={()=>picker.current?.click()}>Scegli una foto</button></>}</div>}
      {result?.manifest&&<><button className="vx-close-model" data-testid="vision-close-model" aria-label="Chiudi la scomposizione e scansiona un altro oggetto" title="Scansiona un altro oggetto" onClick={newObject}>×</button><div className={'vx-object-title'+(focused&&!tourUI?' is-focus':'')}><strong>{focused&&!tourUI&&currentPart?currentPart.name:result.manifest.title}</strong><small>{tourUI?'PERCORSO DIDATTICO':focused?'COMPONENTE TIPICO':result.manifest.parts.length+' parti'}</small></div><div className="vx-zoom" aria-label="Zoom della scomposizione"><button aria-label="Riduci lo zoom" data-testid="vision-zoom-out" onClick={()=>{view.current.zoom=clampZoom(view.current.zoom/1.25);}}>−</button><button aria-label="Aumenta lo zoom" data-testid="vision-zoom-in" onClick={()=>{view.current.zoom=clampZoom(view.current.zoom*1.25);}}>+</button></div></>}
      {focused&&!tourUI&&<button className="vx-whole" data-testid="vision-overview" onClick={overview}>← Vista d’insieme</button>}
      {live&&<div className="vx-camera-tools" data-testid="vision-camera-controls">
        <button className={torchUI.on?'is-on':''} data-testid="vision-torch" aria-label={torchUI.supported?(torchUI.on?'Spegni il flash':'Accendi il flash'):TORCH_UNAVAILABLE} aria-pressed={torchUI.on} disabled={!torchUI.supported||torchUI.busy} title={torchUI.message||'Luce continua della fotocamera'} onClick={()=>void torch.current?.toggle()}>{torchUI.busy?'…':torchUI.supported?(torchUI.on?'⚡ On':'⚡ Off'):'Flash non disponibile'}</button>
        <button data-testid="vision-camera-zoom-toggle" aria-label="Zoom della fotocamera" aria-expanded={cameraPanel} onClick={()=>setCameraPanel(v=>!v)}>◉ {cameraZoom.toFixed(1)}×</button>
        {cameraPanel&&<div className="vx-camera-zoom-panel" data-testid="vision-camera-zoom-panel"><small>ZOOM FOTOCAMERA · DIGITALE</small><div>{[1,2,3].map(z=><button key={z} data-testid={'vision-camera-zoom-'+z} aria-pressed={Math.abs(cameraZoom-z)<.05} onClick={()=>changeCameraZoom(z)}>{z}×</button>)}</div><input data-testid="vision-camera-zoom-range" aria-label="Ingrandimento della fotocamera" type="range" min="1" max="3" step="0.1" value={cameraZoom} onChange={e=>changeCameraZoom(Number(e.target.value))}/><span>{result?'Non modifica lo zoom dello schema 3D.':'ORA analizza la stessa area ingrandita.'}</span></div>}
        {torchUI.message&&torchUI.supported&&<p role="status" className="vx-camera-message">{torchUI.message}</p>}
      </div>}
      {busy&&<div className="vx-scanning" aria-hidden="true"/>}
      <div className={'vx-status'+(result?' vx-status-held':'')} role="status" data-testid="vision-status"><span className={busy?'vx-pulse':''}>{busy?'◌':'◇'}</span>{stage}</div>
      {libraryOpen&&<aside className="vx-library" data-testid="vision-catalog" aria-label="Catalogo delle scomposizioni"><h2>Esplora il catalogo</h2><p>Modelli indicativi salvati, non riconoscimenti della fotocamera.</p><input className="vx-catalog-search" data-testid="vision-catalog-search" type="search" aria-label="Cerca un oggetto nel catalogo" placeholder="Cerca: telefono, penna, USB…" value={catalogQuery} onChange={e=>setCatalogQuery(e.target.value)}/><select className="vx-catalog-category" data-testid="vision-catalog-category" aria-label="Categoria del catalogo" value={catalogCategory} onChange={e=>setCatalogCategory(e.target.value)}>{categories.map(c=><option key={c}>{c}</option>)}</select><small role="status" data-testid="vision-catalog-count">{visibleEntries.length} di {entries.length} modelli</small>{visibleEntries.map(entry=><button key={entry.model_id} data-testid={'vision-catalog-'+entry.canonical_key} onClick={()=>void loadModel(entry)}><span>{entry.title}</span><small>{entry.category||'Altri oggetti'} · {entry.shared?'Condiviso':'Privato'}</small></button>)}{!visibleEntries.length&&<p>Nessun modello corrispondente. Prova un altro nome o inquadra l’oggetto.</p>}<button onClick={()=>setLibraryOpen(false)}>Chiudi catalogo</button></aside>}
      {infoOpen&&<aside className="vx-info" data-testid="vision-information" aria-label="Informazioni su Vision"><h2>Uno schema, non una radiografia</h2><p>{result?.manifest?.limitations||'Le forme e le parti interne sono indicative della famiglia di oggetti, non verificate sul tuo esemplare.'}</p><p>Per riconoscere l’oggetto invio fotogrammi all’AI. Dopo l’acquisizione l’analisi si ferma. Non registro il video e non salvo le foto nel catalogo.</p>{Boolean(result?.sources?.length)&&<div className="vx-seed-sources">Riferimenti generali, non verifica del tuo esemplare.{result!.sources!.map(s=><a key={s.url} href={s.url} target="_blank" rel="noopener noreferrer">{s.title} ↗</a>)}</div>}<p>I nuovi schemi generici validati vengono salvati automaticamente nel catalogo comune. Le precedenti voci private restano private.</p><button onClick={()=>setInfoOpen(false)}>Torna all’oggetto</button></aside>}
    </section>
    {error&&<div className="vx-error" role="alert" data-testid="vision-error">{error}</div>}
    {result?.manifest&&<section className={'vx-details'+(tourUI?' is-tour':'')} aria-label="Componenti dell’oggetto">
      {definition&&!tourUI&&<button className="vx-how" data-testid="vision-how-it-works" onClick={startTour}>▷ Mostrami come funziona <span>{definition.steps.length} passaggi</span></button>}
      {tourUI&&step&&definition&&<div className="vx-tour" data-testid="vision-tour">
        <div className="vx-tour-heading"><small>PERCORSO DIDATTICO · {tourUI.index+1}/{definition.steps.length}</small><button aria-label="Chiudi il percorso e torna all’esplorazione" data-testid="vision-tour-close" onClick={()=>endTour()}>×</button></div>
        <div role="status" aria-live="polite" aria-atomic="true" className="vx-tour-copy"><h2>{step.title}</h2><p>{step.text}</p></div>
        <div className="vx-tour-controls"><button aria-label="Passaggio precedente" data-testid="vision-tour-prev" disabled={tourUI.index===0} onClick={()=>{tour.current?.clock.seek(tourUI.index-1);syncTour();}}>←</button><button data-testid="vision-tour-play" onClick={()=>{tour.current?.clock.toggle();syncTour();}}>{tourUI.done?'Rivedi':tourUI.playing?'Pausa':'Riprendi'}</button><button aria-label="Passaggio successivo" data-testid="vision-tour-next" disabled={tourUI.index===definition.steps.length-1} onClick={()=>{tour.current?.clock.seek(tourUI.index+1);syncTour();}}>→</button><button className="vx-tour-source-button" aria-expanded={tourSources} data-testid="vision-tour-sources" onClick={()=>{tour.current?.clock.stop();syncTour();setTourSources(v=>!v);}}>Fonti</button></div>
        {tourSources&&<div className="vx-tour-sources"><span data-testid="vision-tour-source-context">Fonti di questo passaggio · principi generali, non verifica del tuo esemplare.</span>{sourcesForStep(definition,tourUI.index).map(s=><a key={s.url} href={s.url} target="_blank" rel="noopener noreferrer">{s.title} ↗</a>)}</div>}
        <small className="vx-tour-note">{definition.note||'Collegamenti illustrativi, non un circuito misurato.'}</small>
      </div>}
      <div ref={tabs} className={'vx-part-tabs'+(tourUI?' vx-tour-tabs':'')} aria-label="Seleziona un componente">{result.manifest.parts.map((p,i)=><button key={p.key} data-testid={'vision-part-'+p.key} aria-pressed={p.key===selected&&focused} onClick={()=>choose(p.key)}>{String(i+1).padStart(2,'0')} {p.name}</button>)}</div>
      {!tourUI&&focused&&currentPart&&(detailOpen?<div className="vx-part-info" data-testid="vision-part-detail"><button className="vx-collapse" data-testid="vision-collapse-detail" aria-label="Riduci la spiegazione" onClick={()=>setDetailOpen(false)}>⌄</button><small>COMPONENTE TIPICO</small><h2>{currentPart.name}</h2><p><b>A cosa serve.</b> {currentPart.function}</p>{moreDetail?<p><b>Come funziona.</b> {currentPart.how_it_works}</p>:<button className="vx-detail-more" data-testid="vision-more-detail" onClick={()=>setMoreDetail(true)}>Come funziona →</button>}</div>:<div className="vx-mini-detail" data-testid="vision-detail-collapsed">{currentPart.name}<button data-testid="vision-expand-detail" onClick={()=>setDetailOpen(true)}>Spiegazione ↑</button></div>)}
    </section>}
    <footer className="vx-footer">
      {canHint&&!result&&<form className="vx-recognition-help" data-testid="vision-recognition-help" onSubmit={e=>{e.preventDefault();void captureScan(objectHintRef.current);}}>
        <label htmlFor="vision-object-hint">Come si chiama l’oggetto? <span>Il nome aiuta: ORA lo confronterà con l’immagine.</span></label>
        <div><input id="vision-object-hint" data-testid="vision-object-hint" value={objectHint} maxLength={80} autoComplete="off" placeholder="Es. pattumiera con coperchio" disabled={busy} onChange={e=>{const value=e.target.value.slice(0,80);objectHintRef.current=value;setObjectHint(value);nextScan.current=Infinity;}}/>
          <button type="submit" data-testid="vision-hint-submit" disabled={busy||!objectHint.trim()}>{busy?'Analizzo…':'Analizza'}</button></div>
      </form>}
      <div className="vx-controls">
        {result?.manifest&&<><button onClick={toggleExpansion} data-testid="vision-toggle-explode">{expanded?'Ricomponi':'Scomponi'}</button><label className="vx-opening"><span>APERTURA</span><input aria-label="Apertura della scomposizione" data-testid="vision-explode-range" type="range" min="0" max="100" value={opening} onChange={e=>setExplosion(Number(e.target.value))}/></label></>}
        {!result&&!anatomyActive&&(live||mode==='photo')&&<><button onClick={()=>void captureScan()} disabled={busy} data-testid="vision-retry">{busy?'Analizzo…':'Riprova'}</button><button onClick={()=>picker.current?.click()} disabled={busy}>Scegli foto</button></>}
        {!live&&result&&<button onClick={newObject} data-testid="vision-new-object">Fotocamera</button>}
        {(live||mode==='opening')&&<button className="vx-off" onClick={()=>{stop();setStage('Fotocamera spenta.');}} data-testid="vision-stop-camera">Spegni</button>}
      </div>
      <input ref={picker} type="file" accept="image/jpeg,image/png,image/webp" style={{display:'none'}} onChange={e=>void pickPhoto(e)}/>
      <p className="vx-catalog-note" data-testid="vision-catalog-policy">Schemi generici salvati automaticamente. <button className="vx-policy-info" onClick={()=>{if(tour.current){tour.current.clock.stop();syncTour();}setLibraryOpen(false);setInfoOpen(true);}}>Info</button></p>
      {!result&&!anatomyActive&&<p className="vx-privacy-start">Invio fotogrammi all’AI solo durante l’analisi. Non registro il video e non salvo le foto nel catalogo.</p>}
    </footer>
  </div>;
}
