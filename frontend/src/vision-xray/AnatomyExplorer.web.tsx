import React from 'react';
import {LAYERS, regionsFor, silhouettePath, type AtlasLayer, type AnatomyRegion, type AnatomyVariant} from './anatomyAtlas';
import {ANATOMY_STYLES} from './anatomyStyle';

/** Atlas in the camera: educational, never a scan or an identity inference. */
export function AnatomyExplorer({onClose}:{onClose:()=>void}){
 const [layer,setLayer]=React.useState<AtlasLayer>('skin');
 const [variant,setVariant]=React.useState<AnatomyVariant>('neutral');
 const [selected,setSelected]=React.useState('');
 const [zoom,setZoom]=React.useState(1);
 const [expanded,setExpanded]=React.useState(true);
 const regions=regionsFor(layer,variant);
 const chosen=regions.find(part=>part.id===selected)||regions[0];
 const color=LAYERS.find(item=>item.key===layer)!.color;
 const changeLayer=(next:AtlasLayer)=>{setLayer(next);setSelected('');setExpanded(true);};
 const changeVariant=(next:AnatomyVariant)=>{setVariant(next);setSelected('');};
 const focus=(part:AnatomyRegion)=>{setSelected(part.id);setExpanded(true);};
 return <div className="vx-anatomy" data-testid="vision-anatomy" role="region" aria-label="Atlante anatomico illustrativo">
  <style>{ANATOMY_STYLES}</style>
  <header className="vx-anatomy-head">
   <div><small>ORA VISION · ATLANTE ANATOMICO</small><strong>Il corpo umano, livello per livello</strong><span>Modello didattico generico, non una scansione della persona</span></div>
   <button aria-label="Chiudi l'atlante e scansiona altro" data-testid="vision-anatomy-close" onClick={onClose}>×</button>
  </header>
  <div className="vx-anatomy-layers" role="group" aria-label="Livello anatomico">
   {LAYERS.map(item=><button key={item.key} type="button" data-testid={'vision-anatomy-layer-'+item.key}
    aria-pressed={layer===item.key} onClick={()=>changeLayer(item.key)}><span style={{background:item.color}}/> {item.label}</button>)}
  </div>
  {layer==='reproductive'&&<div className="vx-anatomy-variants" role="group" aria-label="Variante anatomica riproduttiva">
   {(['neutral','female','male'] as AnatomyVariant[]).map(v=><button type="button" key={v}
    aria-pressed={variant===v} onClick={()=>changeVariant(v)} data-testid={'vision-anatomy-variant-'+v}>
    {v==='neutral'?'Generale':v==='female'?'Anatomia femminile':'Anatomia maschile'}</button>)}
  </div>}
  <div className="vx-anatomy-body">
   <div className="vx-anatomy-art">
    <svg viewBox="0 10 320 586" preserveAspectRatio="xMidYMid meet" role="img"
     style={{transform:'scale('+zoom+')'}}
     aria-label="Figura anatomica frontale stilizzata, parti selezionabili">
     <defs>
      <linearGradient id="vx-anatomy-outline" x1="0" x2="1" y1="0" y2="1">
       <stop stopColor="#64d6ed" stopOpacity=".20"/><stop offset="1" stopColor="#123447" stopOpacity=".58"/>
      </linearGradient>
      <filter id="vx-anatomy-glow" x="-50%" y="-50%" width="200%" height="200%">
       <feGaussianBlur stdDeviation="1.8" result="g"/><feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
     </defs>
     <path d={silhouettePath} fill="url(#vx-anatomy-outline)" stroke="#83b3c6" strokeWidth="1.3"/>
     <g opacity=".22" fill="none" stroke="#84deed" strokeDasharray="2 5">
      <path d="M160 118 L160 568 M103 149 L217 149 M112 317 L208 317"/>
     </g>
     {regions.map((part)=><path key={part.id} d={part.d} fill={selected===part.id?color+'cc':color+'4a'}
      stroke={selected===part.id?'#ffb473':color} strokeWidth={selected===part.id?2.6:1.45}
      filter={selected===part.id?'url(#vx-anatomy-glow)':undefined}
      strokeLinecap="round" strokeLinejoin="round" fillRule="evenodd"
      role="button" tabIndex={0} aria-label={part.label}
      data-testid={'vision-anatomy-part-'+part.id}
      onClick={()=>focus(part)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();focus(part);}}}
      style={{cursor:'pointer',pointerEvents:'visiblePainted'}} />)}
    </svg>
   </div>
   <div className="vx-anatomy-parts">
    <div className="vx-anatomy-tools">
     <span>{regions.length} elementi · vista frontale</span>
     <button aria-label="Riduci l'ingrandimento" onClick={()=>setZoom(z=>Math.max(.8,z-.2))}>−</button>
     <button aria-label="Aumenta l'ingrandimento" onClick={()=>setZoom(z=>Math.min(1.9,z+.2))}>+</button>
    </div>
    <div className="vx-anatomy-list" aria-label="Parti anatomiche selezionabili">
     {regions.map(part=><button key={part.id} type="button" onClick={()=>focus(part)}
      data-testid={'vision-anatomy-select-'+part.id} aria-pressed={chosen?.id===part.id}>
      <span style={{background:chosen?.id===part.id?'#ffb473':color}}/> {part.label}</button>)}
    </div>
    {chosen&&<div className="vx-anatomy-info" data-testid="vision-anatomy-description">
     <button type="button" onClick={()=>setExpanded(x=>!x)} aria-expanded={expanded}>
      <b>{chosen.label}</b><span>{expanded?'−':'+'}</span></button>
     {expanded&&<p>{chosen.detail}</p>}
    </div>}
   </div>
  </div>
  <div className="vx-anatomy-note">La fotocamera non vede sotto la pelle e non determina sesso biologico o identità di genere.
   Le varianti anatomiche sono selezioni didattiche, non caratteristiche accertate della persona inquadrata.</div>
 </div>;
}
