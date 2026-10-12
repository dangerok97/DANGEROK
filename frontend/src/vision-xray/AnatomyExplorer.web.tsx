import React from 'react';
import {LAYERS, silhouettePath, type AtlasLayer, type AnatomyRegion, type AnatomyVariant} from './anatomyAtlas';
import {BODY_LABEL, focusedRegions, viewFor, type BodyRegion} from './anatomyFocus';
import {ANATOMY_STYLES} from './anatomyStyle';

/** Contextual educational atlas in the live camera, not an X-ray of this person. */
export function AnatomyExplorer({onClose,region='full_body'}:{onClose:()=>void;region?:BodyRegion}){
 const [layer,setLayer]=React.useState<AtlasLayer>('skin');
 const [variant,setVariant]=React.useState<AnatomyVariant>('neutral');
 const [selected,setSelected]=React.useState('');
 const [zoom,setZoom]=React.useState(1);
 const [expanded,setExpanded]=React.useState(true);
 const [info,setInfo]=React.useState(false);
 const regions=focusedRegions(region,layer,variant);
 const chosen=regions.find(part=>part.id===selected)||regions[0];
 const color=LAYERS.find(item=>item.key===layer)!.color;
 const viewBox=viewFor(region);
 const changeLayer=(next:AtlasLayer)=>{setLayer(next);setSelected('');setExpanded(true);};
 const changeVariant=(next:AnatomyVariant)=>{setVariant(next);setSelected('');};
 const focus=(part:AnatomyRegion)=>{setSelected(part.id);setExpanded(true);};
 return <div className="vx-anatomy" data-testid="vision-anatomy" data-region={region} role="region" aria-label="Atlante anatomico contestuale, illustrativo">
  <style>{ANATOMY_STYLES}</style>
  <div aria-hidden="true" className="vx-anatomy-grid"/>
  <div aria-hidden="true" className="vx-anatomy-scan"/>
  <header className="vx-anatomy-head">
   <div className="vx-anatomy-identity">
    <span className="vx-anatomy-kicker"><i/> ORA / HUMAN ATLAS <b>01</b></span>
    <strong>{BODY_LABEL[region]}</strong>
    <span className="vx-anatomy-context">RICOSTRUZIONE ANATOMICA · MODELLO DIDATTICO</span>
   </div>
   <button aria-label="Chiudi l'atlante e scansiona altro" data-testid="vision-anatomy-close" className="vx-anatomy-close" onClick={onClose}>×</button>
  </header>
  <div className="vx-anatomy-shell">
   <nav className="vx-anatomy-layers" role="group" aria-label="Livello anatomico">
    {LAYERS.map((item,i)=><button type="button" key={item.key} data-testid={'vision-anatomy-layer-'+item.key}
     aria-pressed={layer===item.key} onClick={()=>changeLayer(item.key)} title={item.label}>
     <span className="vx-anatomy-layer-index">{String(i+1).padStart(2,'0')}</span>
     <span className="vx-anatomy-layer-dot" style={{background:item.color}}/>
     <span className="vx-anatomy-layer-name">{item.label}</span>
    </button>)}
   </nav>
   <div className="vx-anatomy-core">
    <div className="vx-anatomy-art" data-testid="vision-anatomy-visual">
     <div className="vx-anatomy-coordinate vx-anatomy-coordinate-top">FIG. {region==='full_body'?'01':'02'} / {LAYERS.findIndex(x=>x.key===layer)+1} · {BODY_LABEL[region]}</div>
     <div aria-hidden="true" className="vx-anatomy-halo vx-anatomy-halo-a"/>
     <div aria-hidden="true" className="vx-anatomy-halo vx-anatomy-halo-b"/>
     <svg viewBox={viewBox} preserveAspectRatio="xMidYMid meet" role="img"
      data-testid="vision-anatomy-svg"
      style={{transform:'scale('+zoom+')'}}
      aria-label={'Atlante anatomico stilizzato: '+BODY_LABEL[region]+', livello '+LAYERS.find(x=>x.key===layer)?.label}>
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
         fill={chosen?.id===part.id?color+'bb':color+'4b'}
         stroke={chosen?.id===part.id?'#ffc18b':color}
         strokeWidth={chosen?.id===part.id?2.5:1.4}
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
     <div className="vx-anatomy-list" aria-label="Parti anatomiche selezionabili">
      {regions.map((part,i)=><button type="button" key={part.id} onClick={()=>focus(part)}
       data-testid={'vision-anatomy-select-'+part.id} aria-pressed={chosen?.id===part.id}>
       <span className="vx-anatomy-list-index">{String(i+1).padStart(2,'0')}</span>
       <span className="vx-anatomy-list-dot" style={{background:chosen?.id===part.id?'#ffb473':color}}/>
       <span className="vx-anatomy-list-label">{part.label}</span><span className="vx-anatomy-arrow">›</span></button>)}
      {!regions.length&&<p className="vx-anatomy-not-applicable">Questo livello non mostra strutture in questa zona. Seleziona un altro livello o inquadra una zona diversa.</p>}
     </div>
     {chosen&&<div className="vx-anatomy-info" data-testid="vision-anatomy-description">
      <button type="button" onClick={()=>setExpanded(x=>!x)} aria-expanded={expanded}>
       <small>DETTAGLIO ANATOMICO</small><b>{chosen.label}</b><span>{expanded?'−':'+'}</span></button>
      {expanded&&<p>{chosen.detail}</p>}
     </div>}
    </aside>
   </div>
  </div>
  <footer className="vx-anatomy-foot">
   <div><span className="vx-anatomy-indicator"/> MODELLO ANATOMICO GENERICO</div>
   <button type="button" data-testid="vision-anatomy-disclaimer" onClick={()=>setInfo(x=>!x)} aria-expanded={info}>Che cosa sto vedendo? <span>{info?'−':'+'}</span></button>
  </footer>
  {info&&<p className="vx-anatomy-note">I livelli illustrano anatomia umana tipica; la fotocamera non rileva ossa, nervi, organi interni, sesso biologico o identità di genere della persona inquadrata. Le varianti sono rappresentazioni selezionate dall’utente. Non è uno strumento diagnostico.</p>}
 </div>;
}
