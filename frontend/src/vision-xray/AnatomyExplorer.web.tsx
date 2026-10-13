import React from 'react';
import {BODY_LABEL,type BodyRegion} from './anatomyFocus';
import {ANATOMY_STYLES} from './anatomyStyle';

type AtlasStatus='checking'|'ready'|'unavailable';
type Props={
 onClose:()=>void;
 region?:BodyRegion;
 bodySide?:'left'|'right'|'unknown';
 posePoints?:Record<string,[number,number]>|null;
 anchorBox?:[number,number,number,number]|null;
};

/** Only source-verified BodyParts3D meshes are anatomy. Never render the old
 * procedural human preview or replace a failed atlas with a fabricated body. */
export function AnatomyExplorer({onClose,region='full_body',bodySide='unknown',anchorBox}:Props){
 const [status,setStatus]=React.useState<AtlasStatus>('checking');
 const [meshReady,setMeshReady]=React.useState(false);
 const [attempt,setAttempt]=React.useState(0);
 const [failure,setFailure]=React.useState('');
 const iframe=React.useRef<HTMLIFrameElement>(null);

 React.useEffect(()=>{
  let active=true;const controller=new AbortController();
  setStatus('checking');setMeshReady(false);setFailure('');
  void fetch('/bodyparts3d/ora-integrated.json',{signal:controller.signal,cache:'no-store'})
   .then(response=>{
    if(!response.ok||!response.headers.get('content-type')?.includes('application/json'))
     throw new Error('Il riferimento BodyParts3D non è disponibile.');
    return response.json();
   })
   .then(data=>{
    if(!active)return;
    if(data?.provider!=='BodyParts3D'||data?.dataset_version!=='4.0'||
       data?.reference!=='adult male'||data?.model_is_person_specific!==false||
       data?.parts!==2234||data?.concepts!==3432)
      throw new Error('La provenienza del modello anatomico 3D non è verificata.');
    setStatus('ready');
   })
   .catch(error=>{
    if(active&&!controller.signal.aborted){
     setFailure(error instanceof Error?error.message:'Modello anatomico 3D non disponibile.');
     setStatus('unavailable');
    }
   });
  return()=>{active=false;controller.abort();};
 },[attempt]);

 React.useEffect(()=>{setMeshReady(false);},[region,bodySide]);
 React.useEffect(()=>{
  const listener=(event:MessageEvent)=>{
   // Sandboxed iframe has an opaque origin; only its window may send a status.
   if(event.source!==iframe.current?.contentWindow||
      !event.data||event.data.version!==1)return;
   if(event.data.type==='ora:anatomy-mesh-ready')setMeshReady(true);
   if(event.data.type==='ora:anatomy-error'){
    setFailure('Il visualizzatore non è riuscito ad aprire il modello anatomico 3D.');
    setStatus('unavailable');
   }
  };
  window.addEventListener('message',listener);
  return()=>window.removeEventListener('message',listener);
 },[]);

 const placement=React.useMemo(()=>{
  if(!anchorBox||anchorBox.length!==4||anchorBox.some(v=>!Number.isFinite(v)))return null;
  const [x,y,w,h]=anchorBox;
  if(x<0||y<0||w<.03||h<.03||x+w>1.01||y+h>1.01)return null;
  const clamp=(v:number,min:number,max:number)=>Math.min(max,Math.max(min,v));
  return {x,y,w,h,cx:clamp(x+w/2,.07,.93),cy:clamp(y+h/2,.07,.93),
   bw:clamp(w,.03,1),bh:clamp(h,.03,1)};
 },[anchorBox?.[0],anchorBox?.[1],anchorBox?.[2],anchorBox?.[3]]);
 const center=placement?.cx??.5;
 const dimensions=placement?'&cy='+placement.cy.toFixed(3)+
  '&bw='+placement.bw.toFixed(3)+'&bh='+placement.bh.toFixed(3):'';
 const src='/bodyparts3d/index.html?ora=inline&lang=it&region='+
  encodeURIComponent(region)+'&cx='+center.toFixed(3)+'&side='+bodySide+dimensions;
 const aiming=status==='checking'||(status==='ready'&&!meshReady);
 return <div className={'vx-anatomy vx-anatomy-inline vx-bp3d-only '+
    (status==='ready'?'vx-has-bp3d':'vx-bp3d-pending')}
  data-testid="vision-anatomy" data-visual-mode="camera-overlay"
  data-atlas-status={status} data-region={region}
  role="region" aria-label={'Anatomia 3D: '+BODY_LABEL[region]}>
  <style>{ANATOMY_STYLES}</style>
  <header className="vx-anatomy-head">
   <button type="button" className="vx-anatomy-close"
    aria-label="Chiudi l'atlante e scansiona altro"
    data-testid="vision-anatomy-close" onClick={onClose}>×</button>
  </header>
  {aiming&&<div className="vx-anatomy-inline-preview vx-anatomy-target"
    data-testid="vision-anatomy-preview" data-anchored={placement?'true':'false'}
    aria-hidden="true"
    style={placement?{left:(placement.x*100)+'%',top:(placement.y*100)+'%',
     width:(placement.w*100)+'%',height:(placement.h*100)+'%'}:undefined}>
    <span className="vx-target-corner vx-target-tl"/>
    <span className="vx-target-corner vx-target-tr"/>
    <span className="vx-target-corner vx-target-bl"/>
    <span className="vx-target-corner vx-target-br"/>
    <span className="vx-target-cross"/>
   </div>}
  {status==='ready'&&<section className="vx-bp3d-panel"
    aria-label="Atlante anatomico tridimensionale BodyParts3D">
   <iframe ref={iframe} data-testid="vision-bp3d-frame"
    title="BodyParts3D: modello 3D della zona inquadrata"
    src={src} sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
    referrerPolicy="no-referrer" loading="eager"
    onError={()=>{
     setFailure('Il visualizzatore 3D non è stato caricato.');
     setStatus('unavailable');
    }}/>
   <div className="vx-bp3d-caption">
    <span>Atlante anatomico di riferimento, non della persona ripresa</span>
    <a href="/bodyparts3d/index.html" data-testid="vision-bp3d-fullscreen"
      target="_blank" rel="noopener noreferrer">Visualizza fonte 3D ↗</a>
   </div>
  </section>}
  {aiming&&<div className="vx-anatomy-preview-status" role="status"
    data-testid="vision-anatomy-inline-pending">
    {status==='checking'?'Verifico il modello anatomico 3D…':'Appaiono i componenti 3D…'}
   </div>}
  {status==='unavailable'&&<div className="vx-bp3d-recovery"
    data-testid="vision-bp3d-unavailable" role="alert">
    <strong>Modello 3D non disponibile</strong>
    <p>{failure||'Non riesco a mostrare il modello anatomico.'} La fotocamera rimane aperta.</p>
    <button type="button" data-testid="vision-bp3d-retry"
     onClick={()=>setAttempt(value=>value+1)}>Riprova modello 3D</button>
   </div>}
 </div>;
}
