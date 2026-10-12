import {useEffect,useMemo,useState} from 'react';
import AnatomyScene from './scene';
import {DEFAULT_VISIBLE,SYSTEMS,explanation,type Atlas,type Concept,type SystemId,type SceneState} from './anatomy';
import {italianAtlas} from './ora-locale-it';
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
const initial=():SceneState=>({
 explode:0,visible:[...INITIAL_SYSTEMS],selected:[],isolate:false,view:'front',rotate:false,reset:0
});
const normalized=(v:string)=>v.toLocaleLowerCase('it').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim();
const REGION_QUERY:Record<string,string>={
 face:'skull',hand:'hand',arm:'humerus',torso:'heart',abdomen:'stomach',leg:'femur'
};
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
 const params=useMemo(()=>new URLSearchParams(window.location.search),[]);
 const zone=params.get('region')||'full_body';
 const focusX=Number(params.get('cx'));
 useEffect(()=>{
  document.documentElement.lang='it';
  if(Number.isFinite(focusX)){
   const clamped=Math.min(.75,Math.max(.25,focusX));
   document.documentElement.style.setProperty('--ora-person-offset',((clamped-.5)*100).toFixed(1)+'%');
  }
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
    const name=REGION_QUERY[zone];
    if(name){
     const candidate=next.concepts.find(c=>c.originalName?.toLowerCase()===name);
     if(candidate)setState(s=>({...s,selected:candidate.elements,isolate:false}));
    }
   })
   .catch(e=>{if(!controller.signal.aborted)setError(String(e?.message||'Atlante non disponibile.'));});
  return()=>{controller.abort();document.documentElement.style.removeProperty('--ora-person-offset');};
 },[zone,focusX]);
 const byId=useMemo(()=>new Map(atlas?.parts.map(p=>[p.id,p])),[atlas]);
 const active=state.selected.map(id=>byId.get(id)).filter((part)=>!!part);
 const selected=active[0];
 const selectedSystem=SYSTEMS.find(s=>s.id===selected?.system);
 const results=useMemo(()=>{
  if(!atlas)return[];
  const term=normalized(query);
  if(!term)return ['cuore','fegato','encefalo','stomaco','pancreas','aorta'].map(v=>atlas.concepts.find(c=>normalized(c.name)===v)).filter((v):v is Concept=>!!v);
  return atlas.concepts.filter(c=>
   normalized(c.name).includes(term)||
   normalized(c.originalName||'').includes(term)||
   normalized(c.id).includes(term)
  ).slice(0,60);
 },[atlas,query]);
 const choose=(part:Concept)=>{
  setChosen(part);setState(s=>({...s,selected:part.elements,isolate:false,explode:0,reset:s.reset+1}));
  setSearchOpen(false);setSystemsOpen(false);
 };
 const choosePart=(id:string)=>{
  const p=byId.get(id);if(!p)return;
  choose({id:p.conceptId,name:p.name,originalName:p.originalName,elements:[id]});
 };
 const changePreset=(systems:SystemId[])=>{
  setState(s=>({...s,visible:[...systems],selected:[],isolate:false,explode:0,reset:s.reset+1}));
  setChosen(null);setSystemsOpen(false);
 };
 const setOpening=(percent:number)=>setState(s=>({...s,explode:Math.max(0,Math.min(1,percent/100)),rotate:false}));
 const reset=()=>{setState(initial());setChosen(null);setQuery('');setSearchOpen(false);setSystemsOpen(false);};
 const title=chosen?.name||'Anatomia di riferimento';
 return <main className="ora-overlay" data-testid="ora-bodyparts-inline" aria-label="Anatomia 3D in sovrimpressione, modello didattico">
   {atlas&&<AnatomyScene atlas={atlas} state={{...state,inspectorOpen:Boolean(chosen)}} onSelect={choosePart}
     onProgress={setProgress} onError={setError}/>}
   <div className="ora-overlay-header">
    <div className="ora-overlay-label"><strong>ORA · ANATOMIA 3D</strong><span>MODELLO DIDATTICO FISSATO ALL'INQUADRATURA</span></div>
    <button type="button" data-testid="ora-inline-search-toggle" aria-expanded={searchOpen} onClick={()=>{setSearchOpen(v=>!v);setSystemsOpen(false);}}>⌕ <span>Cerca</span></button>
    <button type="button" data-testid="ora-inline-systems-toggle" aria-expanded={systemsOpen} onClick={()=>{setSystemsOpen(v=>!v);setSearchOpen(false);}}>☷ <span>Sistemi</span></button>
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
      {results.length===0&&<p>Nessuna struttura trovata. Prova il nome scientifico originale.</p>}
    </div>
   </section>}
   {chosen&&selected&&<aside className="ora-overlay-detail" data-testid="ora-inline-detail">
    <div className="ora-overlay-detail-top">
     <div><small>{selectedSystem?.name||'Struttura anatomica'}</small><strong>{title}</strong></div>
     <button aria-label="Chiudi dettaglio" type="button" onClick={()=>{setChosen(null);setState(s=>({...s,selected:[],isolate:false}));}}>×</button>
    </div>
    <p>{explanation(chosen.name,selected.system)}</p>
    <div className="ora-overlay-detail-actions">
     <button type="button" data-testid="ora-inline-isolate" onClick={()=>setState(s=>({...s,isolate:!s.isolate,explode:0}))}>
      {state.isolate?'Mostra strutture vicine':'Isola struttura'}
     </button>
     <button type="button" onClick={()=>{setState(s=>({...s,selected:[],isolate:false}));setChosen(null);}}>Vista d’insieme</button>
    </div>
   </aside>}
   <div className="ora-overlay-footer">
    <div className="ora-overlay-opening">
     <label htmlFor="ora-inline-explode">Scomponi <strong>{Math.round(state.explode*100)}%</strong></label>
     <input id="ora-inline-explode" data-testid="ora-inline-explode" type="range" min="0" max="100" step="1"
      value={Math.round(state.explode*100)} onChange={e=>setOpening(Number(e.target.value))}/>
    </div>
    <button type="button" onClick={reset} data-testid="ora-inline-reset">Ricomponi</button>
    <button type="button" onClick={()=>setAboutOpen(v=>!v)} aria-expanded={aboutOpen} aria-label="Informazioni e licenza">ⓘ</button>
   </div>
   {progress<100&&!error&&<div className="ora-overlay-loading" role="status" data-testid="ora-inline-loading">
    <strong>Preparo il corpo umano 3D…</strong><span>{progress}%</span>
   </div>}
   {error&&<div role="alert" className="ora-overlay-loading ora-overlay-error" data-testid="ora-inline-error">{error}</div>}
   {aboutOpen&&<aside className="ora-overlay-about">
     <p>Questa è una <b>ricostruzione didattica generica di adulto maschio</b>. La fotocamera non vede organi interni e il modello non è una radiografia né uno strumento diagnostico.</p>
     <p>Ruota con un dito, usa due dita per ingrandire, seleziona un componente o sposta il cursore per scomporre.</p>
     <a href="/bodyparts3d/ATTRIBUTION.md" target="_blank" rel="noopener noreferrer">Fonte e attribuzione BodyParts3D (CC BY 4.0) ↗</a>
   </aside>}
  </main>;
}
