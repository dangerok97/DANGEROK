"""One-shot integration patch. Runs only on the explicitly selected feature head.
No production credentials, user data, network requests or auth bypasses.
The preparation workflow/script never enter the release branch.
"""
from pathlib import Path
root=Path.cwd()
def patch(file,old,new):
 p=root/file;raw=p.read_text();assert raw.count(old)==1,(file,old[:100],raw.count(old));p.write_text(raw.replace(old,new))
P='frontend/src/vision-xray/'
patch(P+'catalogApi.ts','  model_id?: string; version_id?: string; manifest?: Manifest;','  model_id?: string; version_id?: string; manifest?: Manifest;\n  source_type?: \'seed\' | \'generated\' | \'source_based\';')
patch(P+'presentation.ts',"import { geometry, type Manifest, type Part, type Vec3 } from './scene';","import { geometry, type Manifest, type Part, type Vec3, type Box } from './scene';\nimport type { TourStep } from './walkthrough';")
patch(P+'presentation.ts','focus: number; zoom: number };','focus: number; zoom: number; origin?: {box:Box; mix:number}; tour?: {step:TourStep; phase:number} };')
patch(P+'presentation.ts','    const cx=w/2,cy=top+available*.48;','''    const cx=w/2,cy=top+available*.48;
    const highlighted=new Set(opts.tour?.step.parts||[]);''')
patch(P+'presentation.ts','    this.projected=this.meshes.map((mesh,i)=>{','''    // Map the compact assembled representation to the observed region, then move
    // smoothly into study space. A bounding box is not an exact object silhouette.
    const assembledEnvelope:Point[]=[];
    this.manifest.parts.forEach((p,i)=>{const offset=rotate(p.assembled,opts.yaw,opts.pitch);rotated[i].forEach(v=>assembledEnvelope.push([v[0]+offset[0],v[1]+offset[1]]));});
    const [al,at,ar,ab]=bounds(assembledEnvelope);
    const origin=opts.origin;
    const originScale=origin?Math.min(origin.box[2]*w/Math.max(1,ar-al),origin.box[3]*h/Math.max(1,ab-at)):s;
    const originMix=origin?Math.max(0,Math.min(1,origin.mix)):1;
    this.projected=this.meshes.map((mesh,i)=>{''')
patch(P+'presentation.ts','''        const base:Point=[cx+x*zoom,cy+y*zoom];''','''        const study:Point=[cx+x*zoom,cy+y*zoom];
        const source:Point=origin?[(origin.box[0]+origin.box[2]/2)*w+(v[0]+pos[0]-(al+ar)/2)*originScale,
          (origin.box[1]+origin.box[3]/2)*h-(v[1]+pos[1]-(at+ab)/2)*originScale]:study;
        const base:Point=[lerp(source[0],study[0],originMix),lerp(source[1],study[1],originMix)];''')
patch(P+'presentation.ts',"alpha:active?1:lerp(1,.2,focus),selected:active", "alpha:opts.tour?(highlighted.has(part.key)?1:.33):(active?1:lerp(1,.2,focus)),selected:active||highlighted.has(part.key)")
patch(P+'presentation.ts','''    if(focus>.5){''','''    // Relationships are symbolic, never measured wiring, pressure or electrical flow.
    if(opts.tour){
      ctx.globalAlpha=1;ctx.strokeStyle='#ffca91';ctx.fillStyle='#ffe2b9';ctx.lineWidth=1.7;
      const center=(key:string):Point|null=>{const p=this.projected.find(p=>p.key===key);return p?[(p.bounds[0]+p.bounds[2])/2,(p.bounds[1]+p.bounds[3])/2]:null;};
      for(const [from,to] of opts.tour.step.links){
        const a=center(from),b=center(to);if(!a||!b)continue;
        const control:Point=[(a[0]+b[0])/2,Math.min(a[1],b[1])-Math.min(48,available*.12)];
        ctx.setLineDash([4,6]);ctx.beginPath();ctx.moveTo(...a);ctx.quadraticCurveTo(...control,...b);ctx.stroke();ctx.setLineDash([]);
        // Slow single pulse per segment, not flashing lights.
        const t=opts.tour.phase,u=1-t,x=u*u*a[0]+2*u*t*control[0]+t*t*b[0],y=u*u*a[1]+2*u*t*control[1]+t*t*b[1];
        ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.fill();
      }
      for(const key of opts.tour.step.parts){const p=this.projected.find(p=>p.key===key);if(!p)continue;
        const [l,t,r,b]=p.bounds;ctx.strokeStyle='rgba(255,201,137,.48)';ctx.lineWidth=1;
        ctx.strokeRect(l-5,t-5,r-l+10,b-t+10);
      }
    }
    if(focus>.5){''')
F=P+'LiveExplorer.web.tsx'
patch(F,"import { visualStyle } from './visualStyle';", """import { visualStyle } from './visualStyle';
import {walkthroughFor,TourClock,type Walkthrough} from './walkthrough';
import {arrivalAt,currentBox,originInView} from './arrival';
import type {Box} from './scene';""")
patch(F,"  const [photoURL,setPhotoURL]=useState<string|null>(null);", """  const [photoURL,setPhotoURL]=useState<string|null>(null);
  const [tourUI,setTourUI]=useState<{index:number;playing:boolean;done:boolean}|null>(null);
  const [tourSources,setTourSources]=useState(false);""")
patch(F,"  const gestures=useRef(new VisionGestures());", """  const gestures=useRef(new VisionGestures());
  const arrival=useRef<{elapsed:number;box:Box|null;sw:number;sh:number}|null>(null);
  const tour=useRef<{definition:Walkthrough;clock:TourClock;before:typeof view.current}|null>(null);
  const finishArrival=useCallback(()=>{if(arrival.current){arrival.current=null;view.current.progress=1;}},[]);
  const endTour=useCallback((restore=true)=>{
    const active=tour.current;if(active){active.clock.stop();if(restore)Object.assign(view.current,active.before);}
    tour.current=null;if(alive.current){setTourUI(null);setTourSources(false);}
  },[]);""")
patch(F,"    gestures.current.clear();selectedRef.current='';", "    endTour(false);arrival.current=null;gestures.current.clear();selectedRef.current='';")
patch(F,"  },[]);\n  const choose=", "  },[endTour]);\n  const choose=")
patch(F,"    if(!heldResult.current?.manifest?.parts.some(p=>p.key===key))return;", "    if(!heldResult.current?.manifest?.parts.some(p=>p.key===key))return;\n    endTour();finishArrival();")
patch(F,"  },[]);\n  const overview=", "  },[endTour,finishArrival]);\n  const overview=")
patch(F,"    view.current.focusTarget=0;view.current.zoom=1;setFocused(false);setMoreDetail(false);", "    endTour();finishArrival();view.current.focusTarget=0;view.current.zoom=1;setFocused(false);setMoreDetail(false);")
patch(F,"  },[]);\n  const stop=", "  },[endTour,finishArrival]);\n  const stop=")
patch(F,"  const apply=useCallback((value:CatalogResult)=>{", "  const apply=useCallback((value:CatalogResult,origin?:{box:Box;sw:number;sh:number}|null)=>{")
patch(F,"    heldResult.current=value;setResult(value);", "    if(modeRef.current!=='catalog')arrival.current={elapsed:0,box:origin?.box||null,sw:origin?.sw||1,sh:origin?.sh||1};\n    heldResult.current=value;setResult(value);")
patch(F,"      if(value.status==='family'&&value.manifest)apply(value);", """      if(value.status==='family'&&value.manifest){
        // The AI replied about an earlier capture. Check position once, never
        // make the held model depend on tracking after acquisition.
        let box:Box|null=null;
        if(value.identification?.bbox){
          if(modeRef.current==='photo')box=value.identification.bbox;
          else if(video.current?.videoWidth&&sc){
            sc.drawImage(video.current,0,0,small.width,small.height);
            box=currentBox(scanReference.current,grayFrame(sc.getImageData(0,0,small.width,small.height)),value.identification.bbox);
          }
        }
        apply(value,box?{box,sw,sh}:null);
      }""")
patch(F,"    const motion=()=>{view.current.reduceMotion=mq.matches;};", "    const motion=()=>{view.current.reduceMotion=mq.matches;if(mq.matches&&tour.current){tour.current.clock.stop();setTourUI({index:tour.current.clock.index,playing:false,done:tour.current.clock.done});}};")
patch(F,"      const settings=view.current;\n      settings.progress=approach(settings.progress,settings.target,elapsed,settings.reduceMotion);", """      const settings=view.current;
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
      }""")
patch(F,"      const signature=[w,h,dpr,modeRef.current,", "      const signature=[w,h,dpr,arrival.current?.elapsed,activeTour?.clock.index,activeTour?.clock.phase.toFixed(3),Boolean(activeTour),modeRef.current,")
patch(F,"      node.dataset.sceneState=scene.current?'held':'acquiring';", "      node.dataset.arrival=arrival.current?(origin?'from-object':'centred'):'complete';\n      node.dataset.tourStep=activeTour?String(activeTour.clock.index):'';node.dataset.tourPhase=activeTour?activeTour.clock.phase.toFixed(3):'';\n      node.dataset.sceneState=scene.current?'held':'acquiring';")
patch(F,"selected:selectedRef.current,focus:settings.focus,zoom:settings.zoom});", "selected:activeTour?'':selectedRef.current,focus:activeTour?0:settings.focus,zoom:settings.zoom,origin,tour:activeTour?{step:activeTour.definition.steps[activeTour.clock.index],phase:settings.reduceMotion?1:activeTour.clock.phase}:undefined});")
patch(F,"  const setExplosion=(percent:number)=>{const value=", "  const setExplosion=(percent:number)=>{endTour();finishArrival();const value=")
patch(F,"    if(!scene.current)return;gestures.current.down", "    if(!scene.current)return;finishArrival();gestures.current.down")
patch(F,"    if(!scene.current)return;\n    if(['ArrowLeft'", "    if(!scene.current)return;finishArrival();\n    if(['ArrowLeft'")
patch(F,"  const currentPart=result?.manifest?.parts.find(p=>p.key===selected),live=mode==='live';", """  const definition=result?.manifest?walkthroughFor(result.manifest,result.source_type):null;
  const startTour=()=>{
    if(!definition)return;
    endTour();finishArrival();
    const before={...view.current};
    const clock=new TourClock(definition.steps.length);clock.start(!view.current.reduceMotion);
    tour.current={definition,clock,before};
    Object.assign(view.current,{target:1,progress:1,zoom:1,focus:0,focusTarget:0});
    setTourUI({index:0,playing:clock.playing,done:false});setTourSources(false);setInfoOpen(false);setLibraryOpen(false);
  };
  const syncTour=()=>{const c=tour.current?.clock;if(c)setTourUI({index:c.index,playing:c.playing,done:c.done});};
  const step=tourUI&&definition?definition.steps[tourUI.index]:null;
  const currentPart=result?.manifest?.parts.find(p=>p.key===selected),live=mode==='live';""")
patch(F,'data-version="visual-v2">','data-version="visual-v2" data-experience="guided-v3">')
patch(F,"onClick={()=>{setInfoOpen(false);setLibraryOpen(v=>!v);}}", "onClick={()=>{if(tour.current){tour.current.clock.stop();syncTour();}setInfoOpen(false);setLibraryOpen(v=>!v);}}")
patch(F,"onClick={()=>{setLibraryOpen(false);setInfoOpen(true);}} aria-label", "onClick={()=>{if(tour.current){tour.current.clock.stop();syncTour();}setLibraryOpen(false);setInfoOpen(true);}} aria-label")
patch(F,"(focused?' is-focus':'')", "(focused&&!tourUI?' is-focus':'')")
patch(F,"{focused&&currentPart?currentPart.name:result.manifest.title}", "{focused&&!tourUI&&currentPart?currentPart.name:result.manifest.title}")
patch(F,"{focused?'COMPONENTE TIPICO':result.manifest.parts.length+' parti'}", "{tourUI?'PERCORSO DIDATTICO':focused?'COMPONENTE TIPICO':result.manifest.parts.length+' parti'}")
patch(F,'      {focused&&<button className="vx-whole"','      {focused&&!tourUI&&<button className="vx-whole"')
patch(F,'    {result?.manifest&&<section className="vx-details"', '''    {result?.manifest&&<section className={'vx-details'+(tourUI?' is-tour':'')}''')
patch(F,'      <div ref={tabs} className="vx-part-tabs"', '''      {definition&&!tourUI&&<button className="vx-how" data-testid="vision-how-it-works" onClick={startTour}>▷ Mostrami come funziona <span>3 passaggi</span></button>}
      {tourUI&&step&&definition&&<div className="vx-tour" data-testid="vision-tour">
        <div className="vx-tour-heading"><small>PERCORSO DIDATTICO · {tourUI.index+1}/{definition.steps.length}</small><button aria-label="Chiudi il percorso e torna all’esplorazione" data-testid="vision-tour-close" onClick={()=>endTour()}>×</button></div>
        <div role="status" aria-live="polite" aria-atomic="true" className="vx-tour-copy"><h2>{step.title}</h2><p>{step.text}</p></div>
        <div className="vx-tour-controls"><button aria-label="Passaggio precedente" data-testid="vision-tour-prev" disabled={tourUI.index===0} onClick={()=>{tour.current?.clock.seek(tourUI.index-1);syncTour();}}>←</button><button data-testid="vision-tour-play" onClick={()=>{tour.current?.clock.toggle();syncTour();}}>{tourUI.done?'Rivedi':tourUI.playing?'Pausa':'Riprendi'}</button><button aria-label="Passaggio successivo" data-testid="vision-tour-next" disabled={tourUI.index===definition.steps.length-1} onClick={()=>{tour.current?.clock.seek(tourUI.index+1);syncTour();}}>→</button><button className="vx-tour-source-button" aria-expanded={tourSources} data-testid="vision-tour-sources" onClick={()=>{tour.current?.clock.stop();syncTour();setTourSources(v=>!v);}}>Fonti</button></div>
        {tourSources&&<div className="vx-tour-sources">Principi generali, non verifica del tuo esemplare.{definition.sources.map(s=><a key={s.url} href={s.url} target="_blank" rel="noopener noreferrer">{s.title} ↗</a>)}</div>}
        <small className="vx-tour-note">Collegamenti illustrativi, non un circuito misurato.</small>
      </div>}
      <div ref={tabs} className={'vx-part-tabs'+(tourUI?' vx-tour-tabs':'')}''')
patch(F,'{focused&&currentPart&&(detailOpen?', '{!tourUI&&focused&&currentPart&&(detailOpen?')
patch(F,"onClick={()=>{setLibraryOpen(false);setInfoOpen(true);}}>Info", "onClick={()=>{if(tour.current){tour.current.clock.stop();syncTour();}setLibraryOpen(false);setInfoOpen(true);}}>Info")
patch(P+'visualStyle.ts',"\n`;", """
.vx-how{display:flex;align-items:center;justify-content:center;gap:12px;width:100%;min-height:42px;background:#102a34;color:#dcf4ef!important;border:0;border-bottom:1px solid #30434b;font-size:12px!important}.vx-how span{font:9px ui-monospace,monospace;color:#90b7c5}
.vx-tour{width:100%;padding:5px 16px 8px;background:linear-gradient(125deg,#122a34,#142129);max-height:240px;overflow:auto}.vx-tour-heading{display:flex;align-items:center;justify-content:space-between}.vx-tour-heading small{font:9px ui-monospace,monospace;letter-spacing:1px;color:#edbf8c}.vx-tour-heading button{border:0;background:transparent;border-radius:9px;font-size:23px!important;min-width:40px;min-height:36px}.vx-tour-copy h2{font-size:17px;font-weight:500;margin:0 0 6px;line-height:1.2}.vx-tour-copy p{font-size:12px;line-height:18px;color:#bed3dd;max-width:720px;margin:0 0 8px}.vx-tour-controls{display:flex;align-items:center;gap:8px}.vx-tour-controls button{min-width:42px;min-height:36px;padding:5px 12px;border:1px solid #52616c;border-radius:10px;background:#102934;font-size:12px!important}.vx-tour-controls button:nth-child(2){min-width:86px;background:#423325;border-color:#ac855d;color:#ffddae}.vx-tour-controls button.vx-tour-source-button{margin-left:auto;background:transparent}.vx-tour-note{display:block;font-size:9px;color:#94afb9;padding-top:7px}.vx-tour-sources{font-size:10px;line-height:17px;color:#aac7d2;padding:10px 0}.vx-tour-sources a{color:#bde9fa;display:block;text-decoration:underline;padding:7px 0;min-height:30px}.vx-tour-tabs{max-height:0!important;padding-block:0!important;overflow:hidden!important;visibility:hidden}
@media(min-width:900px){.vx-tour{max-width:850px;max-height:255px;padding-inline:28px}.vx-how{max-width:850px}}
@media(max-height:680px){.vx-how{min-height:36px}.vx-tour{max-height:210px;padding:3px 12px 5px}.vx-tour-copy h2{font-size:15px}.vx-tour-copy p{font-size:11px;line-height:16px}.vx-tour-heading button{min-height:32px}.vx-tour-note{padding-top:4px}}
@media(orientation:landscape) and (max-height:540px){.vx-tour{max-height:none}.vx-details.is-tour{top:62px;max-height:calc(100% - 140px)}.vx-tour-controls{gap:4px}.vx-tour-controls button{padding-inline:7px;min-width:34px}.vx-tour-controls button:nth-child(2){min-width:72px}}
`;""")
patch('frontend/playwright.vision.config.ts',"'vision-visual-v2.spec.ts']", "'vision-visual-v2.spec.ts','vision-guided-v3.spec.ts']")
workflow=root/'.github/workflows/vision-catalog-live.yml'
s=workflow.read_text();assert 'src/vision-xray/presentation.test.mjs' in s
s=s.replace('src/vision-xray/presentation.test.mjs','src/vision-xray/presentation.test.mjs src/vision-xray/walkthrough.test.mjs');workflow.write_text(s)
summary='''\n\n## Vision guided V3 — implementation\nCamera acquisition can animate a generic assembly from a once-revalidated detection box into the held study view. If position is stale or unclear it falls back to the centre. This is not segmentation, exact silhouette extraction or world-anchored AR.\nAuthored three-step tours for five seed families show functional links and consulted sources, with pause/manual steps/replay and explicit final stop. No fabricated guided tour for generated or incompatible models. No additional AI requests during exploration; held diagram, focus/zoom and X-to-rescan on the same MediaStream remain. New tutorial tests cover these contracts.\nNo backend, database, runtime dependency or provider-credential changes. Full CI and deployed status must be checked before reporting a release; physical iPhone camera is not tested by the synthetic browser suite.\n'''
for name in ['PRODUCT.md','ARCHITECTURE.md','DEVELOPMENT_STATE.md','CHANGELOG_AI.md']:
 p=root/'docs'/name
 if p.exists():p.write_text(p.read_text()+summary)
(root/'docs/VISION_GUIDED_V3.md').write_text('# Vision guided V3\n'+summary+'\nTechnical sources are stored with each authored walkthrough in frontend/src/vision-xray/walkthrough.ts. They support generic educational principles, not a specific device. All catalogue evidence levels remain unchanged.\n')
print('Applied V3 source, tests and documentation edits. No deployment was performed.')
