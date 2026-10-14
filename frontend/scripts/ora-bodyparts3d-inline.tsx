import React,{useEffect,useMemo,useState} from 'react';
import AnatomyScene from './scene';
import {DEFAULT_VISIBLE,SYSTEMS,EXPLANATIONS,type Atlas,type Concept,type SystemId,type SceneState} from './anatomy';
import {italianAtlas} from './ora-locale-it';
import {systemExplanation} from './ora-anatomy-terminology-it';
import {anatomicalRegion,STUDY_LABEL,expansion,type StudyRegion,type ModelSide} from './ora-regions';
import './ora-overlay.css';

/** Transparent 3D teaching model. Never a reconstruction of the scanned person. */
const PRESETS:{key:string;label:string;systems:SystemId[]}[]=[
 {key:'all',label:'Tutto',systems:DEFAULT_VISIBLE},
 {key:'bones',label:'Ossa',systems:['skeletal']},
 {key:'muscles',label:'Muscoli',systems:['muscular']},
 {key:'organs',label:'Organi',systems:['cardiac','digestive','respiratory','urinary','endocrine']},
 {key:'nerves',label:'Nervi',systems:['nervous']},
 {key:'vessels',label:'Vasi',systems:['arterial','venous']},
];
const INITIAL_SYSTEMS:SystemId[]=['skeletal','cardiac','respiratory','digestive'];
// Responsive subsets preserve actual source mesh IDs while keeping visible parts large.
const pageSizeFor=(width:number)=>width<650?8:width<1000?10:12;
// Enter structured pagination before large anatomical systems overlap.
const EXPLODED_PAGE_THRESHOLD=.50;
const initial=():SceneState=>({
 explode:0,visible:[...INITIAL_SYSTEMS],selected:[],isolate:false,view:'front',rotate:false,reset:0
});
const normalized=(v:string)=>v.toLocaleLowerCase('it').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim();
const SIDED=new Set<StudyRegion>(['hand','wrist','forearm','arm','elbow','shoulder','leg','knee','foot']);
// Compact regions display source bone geometry first; other systems remain
// available through the existing Ossa, Muscoli and Organi controls.
const BONE_FIRST=new Set<StudyRegion>(['hand','wrist','forearm','elbow','knee','foot']);
const REGION_SYSTEMS:Partial<Record<StudyRegion,SystemId[]>>={
 hand:['skeletal'],wrist:['skeletal'],forearm:['skeletal'],
 arm:['skeletal','muscular'],elbow:['skeletal'],shoulder:['skeletal','muscular'],
 foot:['skeletal'],knee:['skeletal'],leg:['skeletal','muscular'],
 face:['skeletal','sensory','nervous'],neck:['skeletal','muscular','nervous'],
 torso:['skeletal','cardiac','respiratory'],abdomen:['digestive','urinary','skeletal'],
 back:['muscular','skeletal'],pelvis:['skeletal','urinary']
};
const visibleFor=(region:StudyRegion):SystemId[]=>[...(REGION_SYSTEMS[region]||INITIAL_SYSTEMS)];
export default function OraOverlay(){
 const [atlas,setAtlas]=useState<Atlas|null>(null);
 const [state,setState]=useState<SceneState>(initial);
 const [progress,setProgress]=useState(0);
 const [error,setError]=useState('');
 const [query,setQuery]=useState('');
 const [searchOpen,setSearchOpen]=useState(false);
 const [systemsOpen,setSystemsOpen]=useState(false);
 const [aboutOpen,setAboutOpen]=useState(false);
 const [chosen,setChosen]=useState<Concept|null>(null);
 const [piecePage,setPiecePage]=useState(0);
 const [pageSize,setPageSize]=useState(()=>pageSizeFor(window.innerWidth));
 useEffect(()=>{
  const onResize=()=>setPageSize(pageSizeFor(window.innerWidth));
  window.addEventListener('resize',onResize);
  return()=>window.removeEventListener('resize',onResize);
 },[]);
 const [beforeInspect,setBeforeInspect]=useState<{explode:number;page:number;view:SceneState['view']}|null>(null);
 const [detailZoom,setDetailZoom]=useState(1);
 const [explodedZoom,setExplodedZoom]=useState(1);
 const [studyMode,setStudyMode]=useState(new URLSearchParams(window.location.search).get('study')==='1');
 const [studyZoom,setStudyZoom]=useState(1);
 const params=useMemo(()=>new URLSearchParams(window.location.search),[]);
 const requested=params.get('region')||'full_body';
 const detected:StudyRegion=(requested in STUDY_LABEL?requested:'full_body') as StudyRegion;
 const [focusRegion,setFocusRegion]=useState<StudyRegion>(detected);
 // Reference-side control, never guessed from a mirror image.
 const observedSide=params.get('side');
 const [modelSide,setModelSide]=useState<ModelSide>(observedSide==='left'?'left':'right');
 // 2D camera rectangle: values from the one photographed body region only.
 const value=(name:string)=>{const raw=params.get(name);return raw===null?NaN:Number(raw);};
 const sourceCenter=value('cx'),sourceY=value('cy'),sourceWidth=value('bw'),sourceHeight=value('bh');
 const anchor=useMemo(()=>{
  if(![sourceCenter,sourceY,sourceWidth,sourceHeight].every(Number.isFinite)||
     sourceCenter<0||sourceCenter>1||sourceY<0||sourceY>1||
     sourceWidth<.03||sourceWidth>1||sourceHeight<.03||sourceHeight>1)return null;
  return {cx:sourceCenter,cy:sourceY,width:sourceWidth,height:sourceHeight};
 },[sourceCenter,sourceY,sourceWidth,sourceHeight]);
 const subset=useMemo(()=>atlas?anatomicalRegion(atlas,focusRegion,modelSide):null,
  [atlas,focusRegion,modelSide]);
 const permittedIds=useMemo(()=>new Set(subset?.ids||[]),[subset]);
 const availabilityWarning=!!subset&&!subset.available;
 // An exploded skull may contain hundreds of tiny mesh fragments. Show at most
 // fourteen selectable source parts per page so each can be inspected.
 const exploded=state.explode>=EXPLODED_PAGE_THRESHOLD&&!state.isolate;
 const eligiblePieces=useMemo(()=>{
  if(!atlas)return[];
  const visible=new Set(state.visible);
  return atlas.parts.filter(p=>permittedIds.has(p.id)&&visible.has(p.system))
   .sort((a,b)=>{
    const span=(p:typeof a)=>{
     const x=p.bounds[1][0]-p.bounds[0][0],y=p.bounds[1][1]-p.bounds[0][1];
     const z=p.bounds[1][2]-p.bounds[0][2];
     return Math.max(x,y,z);
    };
    return span(b)-span(a)||a.name.localeCompare(b.name,'it');
   });
 },[atlas,permittedIds,state.visible]);
 const pageCount=Math.max(1,Math.ceil(eligiblePieces.length/pageSize));
 const displayedPage=Math.min(piecePage,pageCount-1);
 const currentPieces=useMemo(()=>
  eligiblePieces.slice(displayedPage*pageSize,(displayedPage+1)*pageSize),
  [eligiblePieces,displayedPage,pageSize]);
 const renderedIds=useMemo(()=>state.isolate?state.selected:
  exploded?currentPieces.map(p=>p.id):subset?.ids||[],
  [state.isolate,state.selected,exploded,currentPieces,subset?.ids]);
 useEffect(()=>{
  document.documentElement.lang='it';
  const controller=new AbortController();
  fetch('/bodyparts3d/models/atlas.json',{signal:controller.signal,cache:'force-cache'})
   .then(response=>{if(!response.ok)throw new Error('Non riesco a caricare il modello anatomico.');return response.json();})
   .then((source:unknown)=>{
    const atlasSource=source as Atlas;
    if(controller.signal.aborted)return;
    if(atlasSource.version!=='BodyParts3D 4.0'||atlasSource.parts.length!==2234||atlasSource.concepts.length!==3432)
     throw new Error('Il modello anatomico non corrisponde alla versione verificata.');
    const next=italianAtlas(atlasSource);
    setAtlas(next);
    setState(s=>({...s,visible:visibleFor(detected),selected:[],isolate:false,
      explode:0,reset:s.reset+1}));
   })
   .catch(e=>{if(!controller.signal.aborted)setError(String(e?.message||'Atlante non disponibile.'));});
  return()=>{controller.abort();};
 },[detected]);
 const byId=useMemo(()=>new Map(atlas?.parts.map(p=>[p.id,p])),[atlas]);
 const active=state.selected.filter(id=>permittedIds.has(id)).map(id=>byId.get(id)).filter((part)=>!!part);
 const selected=active[0];
 const selectedSystem=SYSTEMS.find(s=>s.id===selected?.system);
 const results=useMemo(()=>{
  if(!atlas)return[];
  const term=normalized(query);
  const visibleConcepts=atlas.concepts.map(c=>({...c,elements:c.elements.filter(id=>permittedIds.has(id))}))
    .filter(c=>c.elements.length>0);
  if(!term)return ['cuore','fegato','encefalo','stomaco','pancreas','aorta','mano','femore']
   .map(v=>visibleConcepts.find(c=>normalized(c.name)===v))
   .filter((v):v is Concept=>!!v).slice(0,15);
  return visibleConcepts.filter(c=>
   normalized(c.name).includes(term)||
   normalized(c.originalName||'').includes(term)||
   normalized(c.id).includes(term)
  ).slice(0,60);
 },[atlas,query,permittedIds]);
 const inspect=(part:Concept,onlyId?:string)=>{
  const localElements=part.elements.filter(id=>permittedIds.has(id)&&(!onlyId||id===onlyId));
  if(!localElements.length)return;
  if(!state.isolate)setBeforeInspect({explode:state.explode,page:displayedPage,view:state.view});
  setDetailZoom(1.12);
  setChosen({...part,elements:localElements});
  // Isolate FIRST, then frame that structure. Do not reassemble the whole skull.
  setState(s=>({...s,selected:localElements,isolate:true,explode:0,
    rotate:false,reset:s.reset+1}));
  setSearchOpen(false);setSystemsOpen(false);
 };
 const choose=(part:Concept)=>inspect(part);
 const choosePart=(id:string)=>{
  const p=byId.get(id);if(!p)return;
  inspect({id:p.conceptId,name:p.name,originalName:p.originalName,elements:[id]},id);
 };
 const returnToExplosion=()=>{
  const previous=beforeInspect;
  setState(s=>({...s,selected:[],isolate:false,explode:previous?.explode??0,
    view:previous?.view||s.view,rotate:false,reset:s.reset+1}));
  if(previous)setPiecePage(previous.page);
  setChosen(null);setBeforeInspect(null);setDetailZoom(1);
 };
 const changePreset=(systems:SystemId[])=>{
  setState(s=>({...s,visible:[...systems],selected:[],isolate:false,explode:0,reset:s.reset+1}));
  setChosen(null);setBeforeInspect(null);setPiecePage(0);setExplodedZoom(1);setSystemsOpen(false);
 };
 const setOpening=(percent:number)=>{setPiecePage(0);setExplodedZoom(1);setState(s=>({...s,explode:Math.max(0,Math.min(1,percent/100)),rotate:false}));};
 const reset=()=>{setState(s=>({...s,visible:visibleFor(focusRegion),selected:[],
  explode:0,isolate:false,view:'front',rotate:false,reset:s.reset+1}));
  setChosen(null);setBeforeInspect(null);setPiecePage(0);setExplodedZoom(1);
  setQuery('');setSearchOpen(false);setSystemsOpen(false);
 };
 const setRegion=(next:StudyRegion)=>{
  if(next===focusRegion)return;
  setFocusRegion(next);setState(s=>({...s,visible:visibleFor(next),selected:[],
    explode:0,isolate:false,view:'front',rotate:false,reset:s.reset+1}));
  setChosen(null);setBeforeInspect(null);setPiecePage(0);setExplodedZoom(1);setSearchOpen(false);setSystemsOpen(false);setQuery('');
 };
 const changeSide=(side:ModelSide)=>{
  setModelSide(side);setState(s=>({...s,selected:[],explode:0,isolate:false,reset:s.reset+1}));
  setChosen(null);setBeforeInspect(null);setPiecePage(0);setExplodedZoom(1);
 };
 const title=chosen?.name||'Anatomia di riferimento';
 const sceneAnchor=!studyMode&&focusRegion===detected?anchor:null;
 const meshAnnounced=React.useRef(false);
 const reportProgress=(value:number)=>{
  setProgress(value);
  if(value>0&&!meshAnnounced.current&&window.parent!==window){
   meshAnnounced.current=true;
   window.parent.postMessage({type:'ora:anatomy-mesh-ready',version:1},'*');
  }
 };
 const reportError=(value:string)=>{
  setError(value);
  if(window.parent!==window)window.parent.postMessage({type:'ora:anatomy-error',version:1},'*');
 };
 const displayedExplosion=state.isolate&&beforeInspect?beforeInspect.explode:state.explode;
 return <main className={'ora-overlay'+(studyMode?' ora-overlay-study':'')}
   data-testid="ora-bodyparts-inline" data-view-mode={studyMode?'study':'approximate-overlay'}
   aria-label="Atlante anatomico 3D didattico">
   {studyMode&&<div className="ora-overlay-study-backdrop" aria-hidden="true"/>}
   {atlas&&subset?.available&&<AnatomyScene atlas={atlas} state={{...state,allowed:renderedIds,detailZoom,explodedZoom,studyZoom,anchor:sceneAnchor,inspectorOpen:Boolean(chosen)}} onSelect={choosePart}
     onProgress={reportProgress} onError={reportError}/>}
   <div className="ora-overlay-header">
    <div className="ora-overlay-label"><strong>ORA · {STUDY_LABEL[focusRegion].toLocaleUpperCase('it')} 3D</strong>
     <span data-testid="ora-inline-region-label">{studyMode?(BONE_FIRST.has(focusRegion)&&state.visible.length===1&&state.visible[0]==='skeletal'?
     'VISTA STUDIO · OSSA IN EVIDENZA':'VISTA STUDIO · MODELLO DI RIFERIMENTO'):
    focusRegion===detected?'POSIZIONE INDICATIVA · NON SOVRAPPOSIZIONE ESATTA':'VISTA AMPLIATA · MODELLO DIDATTICO'}</span></div>
    <button type="button" data-testid="ora-inline-search-toggle" aria-expanded={searchOpen} onClick={()=>{setSearchOpen(v=>!v);setSystemsOpen(false);}}>⌕ <span>Cerca</span></button>
    <button type="button" data-testid="ora-inline-systems-toggle" aria-expanded={systemsOpen} onClick={()=>{setSystemsOpen(v=>!v);setSearchOpen(false);}}>☷ <span>Sistemi</span></button>
   </div>
   <div className="ora-overlay-context" role="group" aria-label="Regione del modello anatomico">
    <strong data-testid="ora-inline-active-region">{STUDY_LABEL[focusRegion]}</strong>
    {SIDED.has(focusRegion)&&<div className="ora-overlay-side" aria-label="Lato del modello di riferimento">
      <button type="button" data-testid="ora-inline-side-right" aria-pressed={modelSide==='right'} onClick={()=>changeSide('right')}>Destra</button>
      <button type="button" data-testid="ora-inline-side-left" aria-pressed={modelSide==='left'} onClick={()=>changeSide('left')}>Sinistra</button>
    </div>}
    {focusRegion!=='full_body'&&<button type="button" data-testid="ora-inline-expand"
     onClick={()=>setRegion(expansion(focusRegion))}>
     Espandi: {STUDY_LABEL[expansion(focusRegion)]} ↗
    </button>}
    {focusRegion!==detected&&<button type="button" data-testid="ora-inline-back-to-part"
     onClick={()=>setRegion(detected)}>Torna a {STUDY_LABEL[detected].toLowerCase()}</button>}
   </div>
   <div className="ora-overlay-presets" role="group" aria-label="Strutture anatomiche da mostrare">
    {PRESETS.map(p=><button type="button" key={p.key} data-testid={'ora-inline-preset-'+p.key}
      aria-pressed={!state.isolate&&p.systems.length===state.visible.length&&p.systems.every(sys=>state.visible.includes(sys))}
      onClick={()=>changePreset(p.systems)}>{p.label}</button>)}
   </div>
   {systemsOpen&&<div className="ora-overlay-panel ora-overlay-systems" role="group" aria-label="Apparati anatomici">
    {SYSTEMS.map(sys=><label key={sys.id}>
      <input type="checkbox" checked={state.visible.includes(sys.id)} onChange={e=>{
       setState(s=>({...s,visible:e.target.checked?[...s.visible,sys.id]:s.visible.filter(x=>x!==sys.id),selected:[],isolate:false}));
       setChosen(null);
      }}/>{sys.name}</label>)}
   </div>}
   {searchOpen&&<section className="ora-overlay-panel ora-overlay-search" aria-label="Cerca una struttura anatomica">
    <input type="search" autoFocus value={query} onChange={e=>setQuery(e.target.value)}
      data-testid="ora-inline-search" placeholder="Cerca: cuore, fegato, femore…" aria-label="Cerca struttura anatomica"/>
    <div className="ora-overlay-search-results">{results.map(c=><button type="button" key={c.id}
      onClick={()=>choose(c)}>{c.name}<small>{c.elements.length} parti</small></button>)}
      {results.length===0&&<p>Nessuna struttura nella zona corrente. Per cercare altrove usa «Espandi».</p>}
    </div>
   </section>}
   {chosen&&selected&&<aside className="ora-overlay-detail ora-overlay-inspector"
      data-testid="ora-inline-detail" aria-label="Esamina il componente anatomico">
    <div className="ora-overlay-detail-top">
     <div>
      <small>{selectedSystem?.name||'Struttura anatomica'} · MODELLO 3D INGRANDITO</small>
      <strong data-testid="ora-inline-selected-name">{title}</strong>
     </div>
     <button type="button" aria-label="Torna alla vista precedente"
      onClick={returnToExplosion}>×</button>
    </div>
    <p data-testid="ora-inline-explanation">{EXPLANATIONS[(chosen.originalName||'').toLowerCase()]||EXPLANATIONS[chosen.name.toLowerCase()]||
      systemExplanation(selected.system,title)}</p>
    <div className="ora-inline-terminology">
     <strong>Denominazione anatomica</strong>
     <span>{selected.translationReviewed===false?'Termine originale da verificare':'Nome italiano'}</span>
     <small data-testid="ora-inline-original-name">{chosen.originalName||selected.originalName||'Nome originale non disponibile'}</small>
     <small>Riferimento BodyParts3D: {chosen.id||selected.conceptId}</small>
    </div>
    <div className="ora-overlay-detail-actions" role="group" aria-label="Ingrandimento componente">
     <button type="button" data-testid="ora-inline-zoom-out" disabled={detailZoom<=1}
      onClick={()=>setDetailZoom(v=>Math.max(1,+(v-.35).toFixed(2)))}>−</button>
     <span data-testid="ora-inline-zoom-level">{Math.round(detailZoom*100)}%</span>
     <button type="button" data-testid="ora-inline-zoom-in"
      disabled={detailZoom>=3} onClick={()=>setDetailZoom(v=>Math.min(3,+(v+.35).toFixed(2)))}>+ Ingrandisci</button>
    </div>
    <button className="ora-inline-return" type="button" data-testid="ora-inline-return-explosion"
     onClick={returnToExplosion}>
     {beforeInspect?.explode&&beforeInspect.explode>=EXPLODED_PAGE_THRESHOLD?
      '← Torna ai pezzi esplosi':'← Torna alla vista anatomica'}
    </button>
   </aside>}
   {!chosen&&!exploded&&<div className="ora-overlay-study-controls"
     role="group" aria-label="Visualizzazione e ingrandimento anatomico"
     data-testid="ora-inline-study-controls">
     <button type="button" data-testid="ora-inline-study-mode"
      title={studyMode?'Mostra la posizione 2D indicativa sulla foto':'Ingrandisci la regione per studiarla'}
      aria-pressed={studyMode}
      onClick={()=>{setStudyMode(previous=>!previous);setStudyZoom(1);}}>
      {studyMode?'Sulla foto · indicativo':'Vista studio'}
     </button>
     <button type="button" data-testid="ora-inline-study-zoom-out"
      aria-label="Riduci il modello anatomico" disabled={studyZoom<=1}
      onClick={()=>setStudyZoom(z=>Math.max(1,+(z-.15).toFixed(2)))}>−</button>
     <output data-testid="ora-inline-study-zoom-value">{studyZoom.toFixed(2)}×</output>
     <button type="button" data-testid="ora-inline-study-zoom-in"
      aria-label="Ingrandisci il modello anatomico" disabled={studyZoom>=2.5}
      onClick={()=>setStudyZoom(z=>Math.min(2.5,+(z+.15).toFixed(2)))}>+</button>
    </div>}
    {exploded&&!chosen&&eligiblePieces.length>0&&<div className="ora-overlay-explode-zoom"
    role="group" aria-label="Ingrandisci i componenti esplosi" data-testid="ora-inline-page-zoom">
    <button type="button" data-testid="ora-inline-page-zoom-out" aria-label="Riduci i pezzi"
     disabled={explodedZoom<=1} onClick={()=>setExplodedZoom(v=>Math.max(1,+(v-.25).toFixed(2)))}>−</button>
    <span data-testid="ora-inline-page-zoom-value">{explodedZoom.toFixed(2)}×</span>
    <button type="button" data-testid="ora-inline-page-zoom-in" aria-label="Ingrandisci i pezzi"
     disabled={explodedZoom>=3} onClick={()=>setExplodedZoom(v=>Math.min(3,+(v+.25).toFixed(2)))}>+</button>
    <button type="button" data-testid="ora-inline-page-recenter" aria-label="Centra e adatta i pezzi"
     onClick={()=>{setExplodedZoom(1);setState(s=>({...s,reset:s.reset+1}));}}>Centra</button>
   </div>}
   {exploded&&!chosen&&eligiblePieces.length>0&&<section className="ora-overlay-pager"
    data-testid="ora-inline-explosion-pager" aria-label="Esplora i componenti anatomici">
    <div className="ora-overlay-pager-top">
     <strong>Componenti ingranditi</strong>
     <span data-testid="ora-inline-parts-count">Pezzi {displayedPage*pageSize+1}–
       {Math.min(eligiblePieces.length,(displayedPage+1)*pageSize)} di {eligiblePieces.length}</span>
     <button type="button" data-testid="ora-inline-prev-page" disabled={displayedPage===0}
      aria-label="Pagina precedente" onClick={()=>{setPiecePage(p=>Math.max(0,p-1));setExplodedZoom(1);}}>‹</button>
     <span data-testid="ora-inline-page-number">{displayedPage+1}/{pageCount}</span>
     <button type="button" data-testid="ora-inline-next-page" disabled={displayedPage>=pageCount-1}
      aria-label="Pagina successiva" onClick={()=>{setPiecePage(p=>Math.min(pageCount-1,p+1));setExplodedZoom(1);}}>›</button>
    </div>
    <div className="ora-overlay-page-parts" role="list" aria-label="Tocca una struttura per esaminarla">
     {currentPieces.map(part=><button role="listitem" type="button" key={part.id}
      data-testid={'ora-inline-piece-'+part.id} onClick={()=>choosePart(part.id)}
      title={part.name} aria-label={'Esamina '+part.name}>{part.name}</button>)}
    </div>
   </section>}
   <div className="ora-overlay-footer">
    <div className="ora-overlay-opening">
     <label htmlFor="ora-inline-explode">Scomponi {chosen?'· posizione salvata':''} <strong data-testid="ora-inline-explode-percentage">{Math.round(displayedExplosion*100)}%</strong></label>
     <input id="ora-inline-explode" data-testid="ora-inline-explode" type="range" min="0" max="100" step="1"
      value={Math.round(displayedExplosion*100)} disabled={Boolean(chosen)}
      title={chosen?'Scomposizione salvata. Torna ai pezzi esplosi per modificarla.':'Trascina per scomporre'}
      onChange={e=>setOpening(Number(e.target.value))}/>
    </div>
    <button type="button" onClick={reset} data-testid="ora-inline-reset">Ricomponi</button>
    <button type="button" onClick={()=>setAboutOpen(v=>!v)} aria-expanded={aboutOpen} aria-label="Informazioni e licenza">ⓘ</button>
   </div>
   {progress<100&&!error&&<div className="ora-overlay-streaming" role="status"
     data-testid="ora-inline-loading">{progress>0?'Completo le strutture anatomiche…':'Preparo le mesh del riferimento…'}</div>}
   {availabilityWarning&&<div role="status" className="ora-overlay-loading ora-overlay-error"
    data-testid="ora-inline-region-unavailable">
    Non trovo sufficienti componenti BodyParts3D per questa zona. Puoi espandere la visualizzazione.
   </div>}
   {error&&<div role="alert" className="ora-overlay-loading ora-overlay-error" data-testid="ora-inline-error">{error}</div>}
   {aboutOpen&&<aside className="ora-overlay-about">
     <p>Questa è una <b>ricostruzione didattica generica di adulto maschio</b>. La fotocamera non vede organi interni e il modello non è una radiografia né uno strumento diagnostico.</p>
     <p>Ruota con un dito, usa due dita per ingrandire, seleziona un componente o sposta il cursore per scomporre.</p>
     <a href="/bodyparts3d/ATTRIBUTION.md" target="_blank" rel="noopener noreferrer">Fonte e attribuzione BodyParts3D (CC BY 4.0) ↗</a>
   </aside>}
  </main>;
}
