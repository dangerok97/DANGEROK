import React from 'react';
import {LAYERS, silhouettePath, type AtlasLayer, type AnatomyRegion, type AnatomyVariant} from './anatomyAtlas';
import {BODY_LABEL, focusedRegions, viewFor, type BodyRegion} from './anatomyFocus';
import {ANATOMY_STYLES} from './anatomyStyle';
import {AnatomyVolume,type VisiblePosePoints} from './AnatomyVolume.web';

/** Contextual educational atlas in the live camera, not an X-ray of this person. */
export function AnatomyExplorer({onClose,region='full_body',posePoints}: {onClose:()=>void;region?:BodyRegion;posePoints?:VisiblePosePoints|null}){
 const [layer,setLayer]=React.useState<AtlasLayer>('skin');
 const [viewRegion,setViewRegion]=React.useState<BodyRegion>(region);
 const [search,setSearch]=React.useState('');
 React.useEffect(()=>{setViewRegion(region);setSelected('');setZoom(1);setSearch('');},[region]);
 const [variant,setVariant]=React.useState<AnatomyVariant>('neutral');
 const [selected,setSelected]=React.useState('');
 const [zoom,setZoom]=React.useState(1);
 const [viewMode,setViewMode]=React.useState<'volume'|'flat'>('volume');
 const [expanded,setExpanded]=React.useState(true);
 const [info,setInfo]=React.useState(false);
 const [bp3dStatus,setBp3dStatus]=React.useState<'checking'|'ready'|'unavailable'>('checking');
 const [bp3dActive,setBp3dActive]=React.useState(false);
 React.useEffect(()=>{
  let active=true;
  const controller=new AbortController();
  void fetch('/bodyparts3d/ora-integrated.json',{signal:controller.signal,cache:'no-store'})
   .then(response=>{
    if(!response.ok||!response.headers.get('content-type')?.includes('application/json'))
     throw new Error('Atlas assets unavailable');
    return response.json();
   })
   .then(data=>{
    if(!active)return;
    if(data?.provider!=='BodyParts3D'||data?.dataset_version!=='4.0'||
       data?.reference!=='adult male'||data?.model_is_person_specific!==false||
       data?.parts!==2234||data?.concepts!==3432)throw new Error('Atlas provenance invalid');
    setBp3dStatus('ready');setBp3dActive(true);
   })
   .catch(()=>{if(active){setBp3dStatus('unavailable');setBp3dActive(false);}});
  return()=>{active=false;controller.abort();};
 },[]);
 const regions=focusedRegions(viewRegion,layer,variant);
 const visibleRegions=regions.filter(part=>part.label.toLocaleLowerCase('it').includes(search.toLocaleLowerCase('it').trim()));
 const chosen=regions.find(part=>part.id===selected)||regions[0];
 const color=LAYERS.find(item=>item.key===layer)!.color;
 const viewBox=viewFor(viewRegion);
 const changeLayer=(next:AtlasLayer)=>{setLayer(next);setSelected('');setSearch('');setExpanded(true);};
 const changeRegion=(next:BodyRegion)=>{setViewRegion(next);setSelected('');setSearch('');setZoom(1);setExpanded(true);};
 const changeVariant=(next:AnatomyVariant)=>{setVariant(next);setSelected('');};
 const focus=(part:AnatomyRegion)=>{setSelected(part.id);setExpanded(true);};
 return <div className="vx-anatomy" data-testid="vision-anatomy" data-region={viewRegion} role="region" aria-label="Atlante anatomico contestuale, illustrativo">
  <style>{ANATOMY_STYLES}</style>
  <div aria-hidden="true" className="vx-anatomy-grid"/>
  <div aria-hidden="true" className="vx-anatomy-scan"/>
  <header className="vx-anatomy-head">
   <div className="vx-anatomy-identity">
    <span className="vx-anatomy-kicker"><i/> ORA / HUMAN ATLAS <b>01</b></span>
    <strong>{BODY_LABEL[viewRegion]}</strong>
    <span className="vx-anatomy-context">RICOSTRUZIONE ANATOMICA · MODELLO DIDATTICO</span>
   </div>
   <button aria-label="Chiudi l'atlante e scansiona altro" data-testid="vision-anatomy-close" className="vx-anatomy-close" onClick={onClose}>×</button>
  </header>
  <div className="vx-anatomy-region-tabs" role="group" aria-label="Esplora una zona del corpo senza effettuare una nuova scansione">
   {([['full_body','Intero'],['face','Testa'],['torso','Torace'],['abdomen','Addome'],['arm','Braccia'],['hand','Mani'],['leg','Gambe']] as [BodyRegion,string][]).map(([key,label])=>
    <button type="button" key={key} data-testid={'vision-anatomy-region-'+key} aria-pressed={viewRegion===key}
     onClick={()=>changeRegion(key)}>{label}</button>)}
  </div>
  <div className="vx-anatomy-source-tabs" role="group" aria-label="Motore anatomico">
   <button type="button" data-testid="vision-bp3d-toggle" aria-pressed={bp3dActive&&bp3dStatus==='ready'}
    disabled={bp3dStatus!=='ready'} onClick={()=>setBp3dActive(true)}>BodyParts3D · 3D {bp3dStatus==='checking'?'…':''}</button>
   <button type="button" data-testid="vision-bp3d-fallback" aria-pressed={!bp3dActive||bp3dStatus!=='ready'}
    onClick={()=>setBp3dActive(false)}>Schema ORA</button>
   {bp3dStatus==='ready'&&<a href="/bodyparts3d/ATTRIBUTION.md" target="_blank" rel="noopener noreferrer">
    Fonti e licenza</a>}
  </div>
  {bp3dActive&&bp3dStatus==='ready'?<section className="vx-bp3d-panel" aria-label="Atlante anatomico 3D BodyParts3D">
   <iframe data-testid="vision-bp3d-frame" title="BodyParts3D: atlante anatomico tridimensionale di riferimento"
    src="/bodyparts3d/index.html" sandbox="allow-scripts" referrerPolicy="no-referrer" loading="eager"
    onError={()=>setBp3dActive(false)} />
   <div className="vx-bp3d-caption">
    Modello 3D di riferimento maschile adulto · 2.234 mesh · non rappresenta la persona inquadrata
   </div>
  </section>:<div className="vx-anatomy-shell">
   <nav className="vx-anatomy-layers" role="group" aria-label="Livello anatomico">
    {LAYERS.map((item,i)=><button type="button" key={item.key} data-testid={'vision-anatomy-layer-'+item.key}
     aria-pressed={layer===item.key} onClick={()=>changeLayer(item.key)} title={item.label}>
     <span className="vx-anatomy-layer-index">{String(i+1).padStart(2,'0')}</span>
     <span className="vx-anatomy-layer-dot" style={{background:item.color}}/>
     <span className="vx-anatomy-layer-name">{item.label}</span>
    </button>)}
   </nav>
   <div className="vx-anatomy-core">
    <div className="vx-anatomy-art" data-testid="vision-anatomy-visual" data-renderer={viewMode}>
     {viewMode==='volume'&&<AnatomyVolume regions={regions} layer={layer} region={viewRegion} selected={chosen?.id||''} onSelect={key=>{const item=regions.find(x=>x.id===key);if(item)focus(item);}} zoom={zoom} onZoom={setZoom} viewBox={viewBox} posePoints={posePoints}/>}
     <div className="vx-anatomy-view-mode" role="group" aria-label="Modalità visuale"><button type="button" data-testid="vision-anatomy-view-volume" aria-pressed={viewMode==='volume'} onClick={()=>setViewMode('volume')}>3D</button><button type="button" data-testid="vision-anatomy-view-flat" aria-pressed={viewMode==='flat'} onClick={()=>setViewMode('flat')}>2D</button></div>
     <div className="vx-anatomy-coordinate vx-anatomy-coordinate-top">FIG. {viewRegion==='full_body'?'01':'02'} / {LAYERS.findIndex(x=>x.key===layer)+1} · {BODY_LABEL[viewRegion]}</div>
     <div aria-hidden="true" className="vx-anatomy-halo vx-anatomy-halo-a"/>
     <div aria-hidden="true" className="vx-anatomy-halo vx-anatomy-halo-b"/>
     <svg viewBox={viewBox} preserveAspectRatio="xMidYMid meet" role="img"
      style={{display:viewMode==='volume'?'none':undefined,transform:'scale('+zoom+')'}}
      data-testid="vision-anatomy-svg"
      aria-label={'Atlante anatomico stilizzato: '+BODY_LABEL[viewRegion]+', livello '+LAYERS.find(x=>x.key===layer)?.label}>
      <defs>
       <linearGradient id="vx-anatomy-shell-fill" x1="0" y1="0" x2="1" y2="1">
        <stop stopColor="#3af0ee" stopOpacity=".15"/><stop offset=".5" stopColor="#176079" stopOpacity=".065"/><stop offset="1" stopColor="#163c63" stopOpacity=".28"/>
       </linearGradient>
       <filter id="vx-anatomy-glow" x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation="2.5" result="g"/><feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge>
       </filter>
       <pattern id="vx-anatomy-points" width="8" height="8" patternUnits="userSpaceOnUse">
        <circle cx="1" cy="1" r=".65" fill="#8fdee9" fillOpacity=".34"/>
       </pattern>
      </defs>
      <path d={silhouettePath} fill="url(#vx-anatomy-shell-fill)" stroke="#70bbd6" strokeOpacity=".75" strokeWidth="1.5"/>
      <path d={silhouettePath} fill="url(#vx-anatomy-points)" stroke="#9be7eb" strokeOpacity=".2" strokeWidth=".55"/>
      <g fill="none" opacity=".3" stroke="#88e9f4" strokeWidth=".8">
       <path d="M160 118 L160 560 M101 159 L220 159 M118 319 L202 319" strokeDasharray="2 6"/>
      </g>
      <g key={layer+'-'+region+'-'+variant} className="vx-anatomy-reveal">
       {regions.map((part,i)=><path key={part.id} d={part.d}
         fill={(layer==='nerves'||layer==='vessels')&&!part.d.includes('Z')?'none':chosen?.id===part.id?color+'bb':color+'4b'}
         stroke={chosen?.id===part.id?'#ffc18b':color}
         strokeWidth={chosen?.id===part.id?((layer==='nerves'||layer==='vessels')?3.6:2.5):((layer==='nerves'||layer==='vessels')?2.2:1.4)}
         filter={chosen?.id===part.id?'url(#vx-anatomy-glow)':undefined}
         strokeLinecap="round" strokeLinejoin="round" fillRule="evenodd"
         role="button" tabIndex={0} aria-label={part.label}
         data-testid={'vision-anatomy-part-'+part.id}
         onClick={()=>focus(part)}
         onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();focus(part);}}}
         style={{cursor:'pointer',pointerEvents:'visiblePainted',animationDelay:Math.min(i*60,540)+'ms'}}/>)}
      </g>
     </svg>
     <div className="vx-anatomy-zoom" role="group" aria-label="Zoom dell'atlante">
      <button aria-label="Riduci l'ingrandimento" onClick={()=>setZoom(z=>Math.max(.85,+(z-.2).toFixed(2)))}>−</button>
      <span>{zoom.toFixed(1)}×</span>
      <button aria-label="Aumenta l'ingrandimento" onClick={()=>setZoom(z=>Math.min(2,+(z+.2).toFixed(2)))}>+</button>
     </div>
     <div className="vx-anatomy-coordinate vx-anatomy-coordinate-bottom">VISUALIZZAZIONE ILLUSTRATIVA / NON MEDICA</div>
    </div>
    <aside className="vx-anatomy-inspector">
     <div className="vx-anatomy-inspector-head">
      <small>STRUTTURE SELEZIONABILI</small>
      <b>{String(regions.length).padStart(2,'0')}</b>
     </div>
     {layer==='reproductive'&&<div className="vx-anatomy-variants" role="group" aria-label="Variante anatomica riproduttiva">
      {(['neutral','female','male'] as AnatomyVariant[]).map(v=><button type="button" key={v}
       aria-pressed={variant===v} onClick={()=>changeVariant(v)} data-testid={'vision-anatomy-variant-'+v}>
       {v==='neutral'?'Generale':v==='female'?'Femminile':'Maschile'}</button>)}
     </div>}
     <input type="search" className="vx-anatomy-search" data-testid="vision-anatomy-search"
      aria-label="Cerca una struttura anatomica" placeholder="Cerca organo, nervo, osso…" value={search} onChange={e=>setSearch(e.target.value)}/>
     <div className="vx-anatomy-list" aria-label="Parti anatomiche selezionabili">
      {visibleRegions.map((part,i)=><button type="button" key={part.id} onClick={()=>focus(part)}
       data-testid={'vision-anatomy-select-'+part.id} aria-pressed={chosen?.id===part.id}>
       <span className="vx-anatomy-list-index">{String(i+1).padStart(2,'0')}</span>
       <span className="vx-anatomy-list-dot" style={{background:chosen?.id===part.id?'#ffb473':color}}/>
       <span className="vx-anatomy-list-label">{part.label}</span><span className="vx-anatomy-arrow">›</span></button>)}
      {!visibleRegions.length&&<p className="vx-anatomy-not-applicable">Nessuna struttura corrisponde alla ricerca in questa zona. Cambia termine, livello o zona del corpo.</p>}
     </div>
     {chosen&&<div className="vx-anatomy-info" data-testid="vision-anatomy-description">
      <button type="button" onClick={()=>setExpanded(x=>!x)} aria-expanded={expanded}>
       <small>DETTAGLIO ANATOMICO</small><b>{chosen.label}</b><span>{expanded?'−':'+'}</span></button>
      {expanded&&<p>{chosen.detail}</p>}
     </div>}
    </aside>
   </div>
  </div>}
  <footer className="vx-anatomy-foot">
   <div><span className="vx-anatomy-indicator"/> MODELLO ANATOMICO GENERICO</div>
   <button type="button" data-testid="vision-anatomy-disclaimer" onClick={()=>setInfo(x=>!x)} aria-expanded={info}>Che cosa sto vedendo? <span>{info?'−':'+'}</span></button>
  </footer>
  {bp3dStatus==='unavailable'&&<p className="vx-anatomy-note" data-testid="vision-bp3d-unavailable">BodyParts3D non è disponibile su questa versione del sito; lo schema ORA resta utilizzabile.</p>}
  {info&&<p className="vx-anatomy-note">I livelli illustrano anatomia umana tipica; la fotocamera non rileva ossa, nervi, organi interni, sesso biologico o identità di genere della persona inquadrata. BodyParts3D mostra esclusivamente un riferimento generico maschile adulto, mentre le varianti nello schema ORA sono selezionate dall’utente. Non è uno strumento diagnostico.</p>}
 </div>;
}
