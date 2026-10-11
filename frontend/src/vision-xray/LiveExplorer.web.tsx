import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'expo-router';
import { catalogApi, type CatalogEntry, type CatalogResult } from './catalogApi';
import { ExplodedScene, coverBox, type Box } from './scene';
import { grayFrame, type GrayFrame } from './tracking';

type Mode = 'idle' | 'opening' | 'live' | 'photo' | 'catalog';
// The acquired diagram stays on screen, independently of the physical object.
const STUDY_BOX: Box = [.15, .03, .70, .66];
const sleep = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));
function difference(a: GrayFrame | null, b: GrayFrame | null) {
  if (!a || !b || a.data.length !== b.data.length) return 1;
  let d = 0; for (let i=0;i<a.data.length;i+=8) d += Math.abs(a.data[i]-b.data[i]);
  return d / Math.ceil(a.data.length/8) / 255;
}

export default function LiveExplorer() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>('idle');
  const [stage, setStage] = useState('Inquadra. Esplora. Capisci.');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CatalogResult | null>(null);
  const [selected, setSelected] = useState('');
  const [expanded, setExpanded] = useState(true);
  const [entries, setEntries] = useState<CatalogEntry[]>([]);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [photoURL, setPhotoURL] = useState<string | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const photo = useRef<HTMLImageElement | null>(null);
  const photoObjectURL = useRef<string | null>(null);
  const modeRef = useRef<Mode>('idle');
  const epoch = useRef(0);
  const alive = useRef(true);
  const request = useRef<AbortController | null>(null);
  const busyRef = useRef(false);
  const nextScan = useRef(Infinity);
  const scanReference = useRef<GrayFrame | null>(null);
  const latestGray = useRef<GrayFrame | null>(null);
  const scene = useRef<ExplodedScene | null>(null);
  const heldResult = useRef<CatalogResult | null>(null);
  const selectedRef = useRef('');
  const boxRef = useRef<Box>([.2,.15,.6,.7]);
  const view = useRef({ progress: 0, target: 1, yaw: .40, pitch: -.18, reduceMotion: false });
  const drag = useRef<{x:number;y:number;startX:number;startY:number} | null>(null);

  const changeMode = (value: Mode) => { modeRef.current = value; if (alive.current) setMode(value); };
  const choose = useCallback((key: string) => { selectedRef.current = key; setSelected(key); }, []);
  const stop = useCallback(() => {
    epoch.current++; request.current?.abort(); request.current = null;
    stream.current?.getTracks().forEach(track => track.stop()); stream.current = null;
    if (video.current) video.current.srcObject = null;
    if (photoObjectURL.current) URL.revokeObjectURL(photoObjectURL.current);
    photoObjectURL.current = null; photo.current = null;
    modeRef.current = 'idle'; busyRef.current = false; nextScan.current = Infinity;
    scene.current = null; heldResult.current = null;
    scanReference.current = null; latestGray.current = null;
    if (alive.current) { setMode('idle'); setBusy(false); setResult(null); setPhotoURL(null); }
  }, []);

  const apply = useCallback((value: CatalogResult) => {
    if (!value.manifest || !value.version_id) return;
    if (heldResult.current?.version_id !== value.version_id) {
      scene.current = new ExplodedScene(value.manifest);
      view.current.progress = view.current.reduceMotion ? 1 : 0;
      view.current.target = 1; setExpanded(true);
      const first = value.manifest.parts[0].key; selectedRef.current = first; setSelected(first);
    }
    heldResult.current = value; setResult(value);
    const bbox = value.identification?.bbox || [.2,.15,.6,.7] as Box;
    boxRef.current = bbox;
    // Acquisition is complete: preserve model, selection and rotation until explicit dismissal.
    setStage(modeRef.current === 'catalog' ? 'Anteprima catalogo · non è un riconoscimento' : 'Schema fissato · esplora le parti');
    nextScan.current = Infinity;
    void catalogApi.list().then(data => { if (alive.current) setEntries(data.models); }).catch(() => {});
  }, []);

  const captureScan = useCallback(async () => {
    if (busyRef.current || scene.current || !['live','photo'].includes(modeRef.current)) return;
    const source = modeRef.current === 'live' ? video.current : photo.current;
    if (!source) return;
    const sw = source instanceof HTMLVideoElement ? source.videoWidth : source.naturalWidth;
    const sh = source instanceof HTMLVideoElement ? source.videoHeight : source.naturalHeight;
    if (!sw || !sh) return;
    const snapshot = document.createElement('canvas');
    const scale = Math.min(1, 960 / Math.max(sw,sh));
    snapshot.width = Math.round(sw*scale); snapshot.height = Math.round(sh*scale);
    const context = snapshot.getContext('2d'); if (!context) return;
    context.drawImage(source,0,0,snapshot.width,snapshot.height);
    const small = document.createElement('canvas'); small.width=160; small.height=Math.round(160*sh/sw);
    const sc = small.getContext('2d', {willReadFrequently:true}); if (!sc) return;
    sc.drawImage(snapshot,0,0,small.width,small.height);
    const reference = grayFrame(sc.getImageData(0,0,small.width,small.height));
    scanReference.current=reference;
    const dataURI=snapshot.toDataURL('image/jpeg',.78);
    const currentEpoch=epoch.current, frameId=String(currentEpoch)+'-'+String(Date.now());
    const controller=new AbortController(); request.current=controller;
    busyRef.current=true; setBusy(true); setError(null); setStage('Riconosco e cerco nel catalogo…');
    try {
      let value=await catalogApi.scan(dataURI,frameId,controller.signal);
      const identification=value.identification;
      for (let attempt=0; value.status==='building' && attempt<12; attempt++) {
        if (epoch.current!==currentEpoch || controller.signal.aborted) return;
        setStage('Un nuovo schema è in preparazione…'); await sleep(4000);
        if (!value.job_id || epoch.current!==currentEpoch) return;
        value={...await catalogApi.job(value.job_id,controller.signal), identification};
      }
      if (epoch.current!==currentEpoch || !alive.current) return;
      if (value.status==='family' && value.manifest) apply(value);
      else {
        scene.current=null; heldResult.current=null; setResult(null);
        setStage(value.reason || 'Ricostruzione in corso. Premi Riprova per verificarla.');
        nextScan.current=performance.now()+6000;
      }
    } catch (e: any) {
      if (epoch.current!==currentEpoch || !alive.current) return;
      setError(e?.name==='AbortError' ? 'Analisi scaduta. Il video non è stato interrotto.' : String(e?.message || 'Analisi non disponibile.'));
      setStage('La fotocamera resta aperta. Puoi riprovare.'); nextScan.current=performance.now()+30_000;
    } finally {
      if (epoch.current===currentEpoch) { busyRef.current=false; request.current=null; if(alive.current) setBusy(false); }
    }
  }, [apply]);

  const openCamera = useCallback(async () => {
    stop(); setLibraryOpen(false); setError(null); changeMode('opening');
    setStage('Consenti l’accesso alla fotocamera…'); const ticket=epoch.current;
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.isSecureContext) throw new Error('Apri ORA in un browser HTTPS per usare la fotocamera.');
      const media=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:'environment'},width:{ideal:1280},frameRate:{ideal:24,max:30}}});
      if (epoch.current!==ticket || !alive.current) { media.getTracks().forEach(t=>t.stop()); return; }
      stream.current=media;
      if (!video.current) { media.getTracks().forEach(t=>t.stop()); return; }
      video.current.srcObject=media; await video.current.play();
      if (epoch.current!==ticket || !alive.current) return;
      changeMode('live'); setStage('Tieni l’oggetto al centro: lo riconosco automaticamente.');
      nextScan.current=performance.now()+1500;
    } catch(e:any) {
      if (epoch.current!==ticket || !alive.current) return;
      stop(); setError(e?.name==='NotAllowedError' ? 'Permesso negato. Abilita la fotocamera nelle impostazioni del sito.' : String(e?.message || 'Fotocamera non disponibile.'));
    }
  }, [stop]);

  const newObject = () => {
    if (modeRef.current !== 'live') { void openCamera(); return; }
    // X resets recognition, not the MediaStream. Late replies cannot restore the dismissed model.
    epoch.current++; request.current?.abort(); request.current = null;
    busyRef.current = false; scene.current = null; heldResult.current = null;
    scanReference.current = null; latestGray.current = null;
    boxRef.current = [.2,.15,.6,.7]; selectedRef.current = '';
    view.current.yaw = .40; view.current.pitch = -.18;
    setResult(null); setSelected(''); setBusy(false); setError(null);
    setStage('Inquadra il nuovo oggetto: lo riconosco automaticamente.');
    nextScan.current = performance.now() + 300;
  };

  const pickPhoto = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file=event.target.files?.[0]; event.target.value=''; if(!file) return;
    stop(); setLibraryOpen(false); setError(null);
    if (!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size>12*1024*1024) { setError('Scegli JPEG, PNG o WebP inferiore a 12 MB.'); return; }
    const ticket=epoch.current, url=URL.createObjectURL(file); photoObjectURL.current=url;
    const img=new window.Image(); img.src=url;
    try { await img.decode(); if(epoch.current!==ticket) return; photo.current=img; setPhotoURL(url); changeMode('photo'); await captureScan(); }
    catch { if(epoch.current===ticket) setError('Questa foto non è leggibile.'); }
  };

  const loadModel = async (entry: CatalogEntry) => {
    stop(); setLibraryOpen(false); setError(null); changeMode('catalog');
    setStage('Carico il modello salvato…'); const ticket=epoch.current;
    const ctrl=new AbortController(); request.current=ctrl; setBusy(true); busyRef.current=true;
    try { const value=await catalogApi.model(entry.model_id,ctrl.signal); if(epoch.current===ticket) apply(value); }
    catch(e:any) { if(epoch.current===ticket) setError(String(e?.message||'Modello non disponibile.')); }
    finally { if(epoch.current===ticket) {setBusy(false);busyRef.current=false;} }
  };

  useEffect(() => {
    alive.current=true;
    void catalogApi.list().then(data=>{if(alive.current)setEntries(data.models);}).catch(e=>{if(alive.current)setError(e.message);});
    const mq=window.matchMedia('(prefers-reduced-motion: reduce)'); view.current.reduceMotion=mq.matches;
    const motion=()=>{view.current.reduceMotion=mq.matches;}; mq.addEventListener?.('change',motion);
    const hidden=()=>{if(document.hidden){stop();setStage('Fotocamera fermata quando ORA è passata in secondo piano.');}};
    document.addEventListener('visibilitychange',hidden); window.addEventListener('pagehide',stop);
    return()=>{alive.current=false;stop();document.removeEventListener('visibilitychange',hidden);window.removeEventListener('pagehide',stop);mq.removeEventListener?.('change',motion);};
  }, [stop]);

  useEffect(() => {
    let raf=0,lastSample=0; const small=document.createElement('canvas');
    const pixels=small.getContext('2d',{willReadFrequently:true});
    const paint=(time:number)=>{
      raf=requestAnimationFrame(paint); const node=canvas.current; if(!node)return;
      const ctx=node.getContext('2d'); if(!ctx)return;
      const w=node.clientWidth,h=node.clientHeight,dpr=Math.min(2,window.devicePixelRatio||1);
      if(node.width!==Math.round(w*dpr)||node.height!==Math.round(h*dpr)){node.width=Math.round(w*dpr);node.height=Math.round(h*dpr);}
      ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
      const live=modeRef.current==='live', v=video.current;
      if(live&&!scene.current&&v?.videoWidth&&pixels&&time-lastSample>200){
        lastSample=time;small.width=160;small.height=Math.round(160*v.videoHeight/v.videoWidth);
        pixels.drawImage(v,0,0,small.width,small.height);latestGray.current=grayFrame(pixels.getImageData(0,0,small.width,small.height));
        if(!busyRef.current&&time>=nextScan.current){
          const changed=difference(scanReference.current,latestGray.current)>.13;
          if(!scanReference.current||changed){nextScan.current=time+6000;void captureScan();}
        }
      }
      const hasScene=scene.current;
      node.dataset.sceneState=hasScene?'held':'acquiring';
      if(hasScene){
        const settings=view.current;
        settings.progress=settings.reduceMotion?settings.target:settings.progress+(settings.target-settings.progress)*.08;
        let box=boxRef.current;
        if(live)box=STUDY_BOX;
        else if(modeRef.current==='photo'&&photo.current)box=coverBox(box,photo.current.naturalWidth,photo.current.naturalHeight,w,h);
        scene.current!.draw(ctx,w,h,{box,progress:settings.progress,yaw:settings.yaw,pitch:settings.pitch,selected:selectedRef.current,time});
        node.dataset.partCount=String(scene.current!.manifest.parts.length);node.dataset.selectedPart=selectedRef.current;
      } else { node.dataset.partCount='0'; }
      if(live&&!hasScene){
        const b: Box=[.26,.20,.48,.60];
        const x=b[0]*w,y=b[1]*h,bw=b[2]*w,bh=b[3]*h;
        ctx.strokeStyle='rgba(124,228,240,.45)';ctx.lineWidth=1.3;
        for(const [xx,yy,sx,sy] of [[x,y,1,1],[x+bw,y,-1,1],[x,y+bh,1,-1],[x+bw,y+bh,-1,-1]]){
          ctx.beginPath();ctx.moveTo(xx+sx*16,yy);ctx.lineTo(xx,yy);ctx.lineTo(xx,yy+sy*16);ctx.stroke();
        }
      }
    };raf=requestAnimationFrame(paint);return()=>cancelAnimationFrame(raf);
  },[captureScan]);

  const toggleExpansion=()=>{view.current.target=view.current.target>.5?0:1;setExpanded(view.current.target===1);};
  const onDown=(e:React.PointerEvent<HTMLCanvasElement>)=>{drag.current={x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY};e.currentTarget.setPointerCapture(e.pointerId);};
  const onMove=(e:React.PointerEvent<HTMLCanvasElement>)=>{
    const d=drag.current;if(!d)return;
    if(Math.hypot(e.clientX-d.startX,e.clientY-d.startY)>5){view.current.yaw+=(e.clientX-d.x)*.006;view.current.pitch=Math.max(-1,Math.min(1,view.current.pitch+(e.clientY-d.y)*.005));}
    d.x=e.clientX;d.y=e.clientY;
  };
  const onUp=(e:React.PointerEvent<HTMLCanvasElement>)=>{
    const d=drag.current;drag.current=null;
    if(d&&Math.hypot(e.clientX-d.startX,e.clientY-d.startY)<6&&scene.current){
      const r=e.currentTarget.getBoundingClientRect();const key=scene.current.hit(e.clientX-r.left,e.clientY-r.top);if(key)choose(key);
    }
    if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);
  };
  const currentPart=result?.manifest?.parts.find(p=>p.key===selected);
  const live=mode==='live';

  return <div className="vx-root" data-testid="vision-live-explorer">
    <style>{CSS}</style>
    <header className="vx-header">
      <button aria-label="Torna a ORA" className="vx-back" onClick={()=>{stop();if(router.canGoBack())router.back();else router.replace('/ora');}}>←</button>
      <div><div className="vx-brand">ORA <span>VISION</span></div><div className="vx-eyebrow">OLTRE LA SUPERFICIE</div></div>
      <button className="vx-catalog" data-testid="vision-catalog-toggle" onClick={()=>setLibraryOpen(v=>!v)}>Catalogo <span>{entries.length}</span></button>
    </header>
    <section className="vx-stage" aria-label="Fotocamera e scomposizione interattiva">
      <video ref={video} autoPlay playsInline muted data-testid="vision-camera-video" aria-label="Video live della fotocamera" style={{opacity:live?1:0}} />
      {photoURL&&<img src={photoURL} alt="Foto scelta per l’analisi" className="vx-photo"/>}
      <div className={'vx-shade '+(result?'vx-shade-result':'')} />
      <canvas ref={canvas} className="vx-canvas" data-testid="vision-scene" aria-label="Oggetto virtuale: usa anche i pulsanti delle parti sotto la visuale" onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={()=>{drag.current=null;}} />
      <div className="vx-topline"><span className={'vx-tag '+(live?'vx-tag-live':'')}>{live?(result?'● LIVE · SCHEMA FISSATO':'● LIVE'):mode==='photo'?'FOTO':mode==='catalog'?'ANTEPRIMA CATALOGO':'VISION X-RAY'}</span><span className="vx-tag">BETA · SCHEMA TIPICO</span></div>
      {(mode==='idle'||mode==='opening')&&!result&&<div className="vx-empty"><div className="vx-reticle">⌖</div><h1>Ogni oggetto<br/>ha una storia dentro.</h1><p>Apri la fotocamera. ORA riconosce l’oggetto<br/>e ne separa virtualmente le parti.</p>{mode==='idle'&&<button className="vx-main" data-testid="vision-open-camera" onClick={()=>void openCamera()}>Apri fotocamera</button>}</div>}
      {result?.manifest&&<button className="vx-close-model" data-testid="vision-close-model" aria-label="Chiudi la scomposizione e scansiona un altro oggetto" title="Scansiona un altro oggetto" onClick={newObject}>×</button>}
      {busy&&<div className="vx-scanning" aria-hidden="true"/>}
      <div className="vx-status" role="status" data-testid="vision-status"><span className={busy?'vx-pulse':''}>{busy?'◌':'◇'}</span>{stage}</div>
      {result?.manifest&&<div className="vx-object-title"><small>{mode==='catalog'?'ESPLORA IL MODELLO SALVATO':result.identification?.object_name||'OGGETTO'}</small><strong>{result.manifest.title}</strong><span>{result.manifest.parts.length} parti · {result.cache_hit?'recuperato dal catalogo':'nuovo schema salvato'}{result.shared?'':' · privato'}</span></div>}
      {libraryOpen&&<aside className="vx-library" data-testid="vision-catalog"><h2>Modelli disponibili</h2><p>Anteprime degli schemi salvati, non riconoscimenti della fotocamera.</p>{entries.map(entry=><button key={entry.model_id} data-testid={'vision-catalog-'+entry.canonical_key} onClick={()=>void loadModel(entry)}><span>{entry.title}</span><small>{entry.shared?'Condiviso':'Privato'} · indicativo</small></button>)}<button onClick={()=>setLibraryOpen(false)}>Chiudi</button></aside>}
    </section>
    {error&&<div className="vx-error" role="alert" data-testid="vision-error">{error}</div>}
    {result?.manifest&&<section className="vx-details">
      <div className="vx-part-tabs" aria-label="Seleziona un componente">{result.manifest.parts.map((p,i)=><button key={p.key} data-testid={'vision-part-'+p.key} aria-pressed={p.key===selected} onClick={()=>choose(p.key)}>{String(i+1).padStart(2,'0')} {p.name}</button>)}</div>
      {currentPart&&<div className="vx-part-info" data-testid="vision-part-detail"><div><small>COMPONENTE TIPICO · NON VERIFICATO SUL TUO ESEMPLARE</small><h2>{currentPart.name}</h2></div><p><b>A cosa serve.</b> {currentPart.function}</p><p><b>Come funziona.</b> {currentPart.how_it_works}</p></div>}
    </section>}
    <footer className="vx-footer">
      <div className="vx-controls">
        {!result&&mode!=='idle'&&mode!=='opening'&&<button onClick={newObject} data-testid="vision-new-object">{live?'Nuovo oggetto':'Fotocamera'}</button>}
        {live&&!result&&<button onClick={()=>void captureScan()} disabled={busy} data-testid="vision-retry">Riprova</button>}
        <button onClick={()=>picker.current?.click()} disabled={busy}>Scegli foto</button>
        {result?.manifest&&<button onClick={toggleExpansion} data-testid="vision-toggle-explode">{expanded?'Ricomponi':'Scomponi'}</button>}
        {(live||mode==='opening')&&<button onClick={()=>{stop();setStage('Fotocamera spenta.');}} data-testid="vision-stop-camera">Spegni</button>}
      </div>
      <input ref={picker} type="file" accept="image/jpeg,image/png,image/webp" style={{display:'none'}} onChange={e=>void pickPhoto(e)}/>
      <p className="vx-catalog-note" data-testid="vision-catalog-policy">I nuovi schemi generici vengono salvati automaticamente nel catalogo comune.</p>
      <p className="vx-privacy">Invio fotogrammi all’AI per riconoscere l’oggetto; dopo l’acquisizione l’analisi si ferma. Non registro il video e non salvo foto o dati personali nel catalogo. Le parti interne sono indicative. {result?'Trascina per ruotare · tocca un pezzo · × per scansionare altro.':'Gli oggetti nuovi richiedono più tempo.'}</p>
    </footer>
  </div>;
}

const CSS=`
.vx-root{box-sizing:border-box;height:100dvh;min-height:600px;display:flex;flex-direction:column;background:#030d12;color:#dff7fa;font-family:system-ui,-apple-system,sans-serif;overflow:auto;position:relative}
.vx-root *{box-sizing:border-box}.vx-root button{font:inherit;cursor:pointer}.vx-root button:focus-visible{outline:2px solid #f4b278;outline-offset:3px}.vx-root button:disabled{opacity:.4;cursor:wait}
.vx-header{height:76px;flex-shrink:0;display:flex;align-items:center;gap:16px;padding:12px 22px;border-bottom:1px solid #16343d;background:#041116}
.vx-back{color:#b5eaf1;border:1px solid #23505c;border-radius:12px;background:transparent;font-size:24px!important;width:44px;height:44px}.vx-brand{font-size:22px;letter-spacing:6px;font-weight:300}.vx-brand span{font-size:12px;letter-spacing:3px;color:#6fbbc6;margin-left:8px}.vx-eyebrow{font:9px monospace;letter-spacing:2px;color:#70a4af;margin-top:5px}.vx-catalog{margin-left:auto;background:#0a222b;border:1px solid #28505d;color:#caeff4;border-radius:12px;padding:11px 14px;font-size:13px!important}.vx-catalog span{color:#f3bb83;margin-left:6px}
.vx-stage{position:relative;flex:1;min-height:275px;overflow:hidden;background:radial-gradient(ellipse at 50% 42%,#10313a 0%,#041318 55%,#030b10 100%)}
.vx-stage video,.vx-photo{position:absolute;width:100%;height:100%;object-fit:cover;inset:0}.vx-shade{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,14,19,.35),transparent 25%,rgba(0,12,17,.32) 65%,#041116 100%);pointer-events:none}.vx-shade-result{background:linear-gradient(180deg,rgba(0,13,18,.45),rgba(0,12,18,.48) 35%,rgba(0,12,18,.60) 70%,#041116 100%)}
.vx-canvas{position:absolute;width:100%;height:100%;inset:0;touch-action:none}.vx-topline{position:absolute;top:15px;left:20px;right:20px;display:flex;justify-content:space-between;gap:10px;pointer-events:none}.vx-tag{font:9px monospace;letter-spacing:1.3px;color:#8dd1db;padding:6px 9px;background:#05181ecc;border:1px solid #204650;border-radius:4px}.vx-tag-live{color:#a0f5cb}
.vx-empty{position:absolute;inset:35px 0 40px;display:flex;align-items:center;justify-content:center;flex-direction:column;text-align:center;pointer-events:none}.vx-empty button{pointer-events:auto}.vx-reticle{font-size:60px;line-height:70px;color:#77e6ed;font-weight:200}.vx-empty h1{font-weight:300;font-size:30px;line-height:1.15;letter-spacing:-.7px;margin:8px 0 12px}.vx-empty p{font-size:13px;line-height:1.6;color:#96bdc6;margin:0 0 20px}.vx-main{background:#9ceaf0;color:#05242c;font-weight:650!important;border:none;border-radius:12px;padding:14px 22px;min-height:48px}
.vx-status{position:absolute;left:20px;right:20px;bottom:14px;display:flex;gap:10px;align-items:center;font-size:12px;line-height:18px;color:#a3d6dc;pointer-events:none}.vx-status>span{font-size:20px;color:#8ee7e9}.vx-pulse{animation:vx-spin 2s linear infinite}.vx-object-title{position:absolute;left:24px;right:24px;bottom:52px;display:flex;flex-direction:column;gap:4px;pointer-events:none;text-shadow:0 2px 7px #000}.vx-object-title small{font:10px monospace;letter-spacing:2px;color:#76bbc5}.vx-object-title strong{font-size:24px;font-weight:350;letter-spacing:-.3px}.vx-object-title span{font:11px monospace;color:#b2cfce}
.vx-close-model{position:absolute;top:55px;right:16px;z-index:4;width:46px;height:46px;display:flex;align-items:center;justify-content:center;border:1px solid #84d9e4;border-radius:50%;background:#041920e8;color:#e5ffff;font-size:31px!important;line-height:1;box-shadow:0 4px 18px #0008}.vx-close-model:hover{background:#153d48}.vx-scanning{position:absolute;left:25%;right:25%;top:23%;height:1px;box-shadow:0 0 18px 2px #6fe6e977;background:#8aeff0;animation:vx-scan 3s ease-in-out infinite;pointer-events:none}
.vx-library{position:absolute;right:12px;top:54px;z-index:9;width:min(340px,calc(100% - 24px));max-height:calc(100% - 64px);overflow:auto;background:#071b23f5;border:1px solid #386370;border-radius:16px;padding:18px;box-shadow:0 20px 60px #0009}.vx-library h2{margin:0;font-size:18px;font-weight:500}.vx-library p{font-size:11px;line-height:17px;color:#9fbcc5}.vx-library button{width:100%;border:1px solid #284753;background:#0e2933;border-radius:9px;margin-top:8px;color:#cceef1;min-height:48px;text-align:left;padding:10px 12px;display:flex;flex-direction:column;gap:4px}.vx-library small{font-size:10px;color:#8ab1bc}
.vx-error{background:#371c1a;border-top:1px solid #84503c;color:#ffd2b6;padding:10px 20px;font-size:12px;line-height:17px}
.vx-details{background:#07171e;border-top:1px solid #1e414d;flex-shrink:0}.vx-part-tabs{display:flex;gap:7px;padding:10px 18px;overflow-x:auto;border-bottom:1px solid #15313c}.vx-part-tabs button{background:#0e252f;color:#9fcbd4;border:1px solid #254754;border-radius:7px;white-space:nowrap;min-height:36px;padding:7px 10px;font-size:11px!important}.vx-part-tabs button[aria-pressed=true]{background:#35291f;border-color:#b78454;color:#ffd2a4}
.vx-part-info{padding:12px 22px 14px;max-height:175px;overflow-y:auto}.vx-part-info small{font:8px monospace;letter-spacing:1.2px;color:#ca9a70}.vx-part-info h2{margin:5px 0 8px;font-size:18px;font-weight:500}.vx-part-info p{font-size:12px;line-height:18px;margin:5px 0;color:#b8d3da}.vx-part-info b{color:#d7eaee;font-weight:550}
.vx-footer{padding:12px 20px max(13px,env(safe-area-inset-bottom));background:#061319;border-top:1px solid #1c3641;flex-shrink:0}.vx-controls{display:flex;gap:8px;flex-wrap:wrap;justify-content:center}.vx-controls button{background:#0d2832;color:#c0ebef;border:1px solid #285563;border-radius:9px;min-height:44px;padding:9px 13px;font-size:12px!important}.vx-catalog-note{text-align:center;font-size:10px;line-height:15px;color:#9fbcc5;margin:11px auto 0;max-width:730px}.vx-privacy{text-align:center;font-size:9px;line-height:14px;color:#7d9faa;margin:5px auto 0;max-width:730px}
@keyframes vx-spin{to{transform:rotate(360deg)}}@keyframes vx-scan{0%,100%{top:23%;opacity:.2}50%{top:63%;opacity:.8}}
@media(min-width:800px){.vx-part-info{max-width:950px;margin:auto;max-height:160px}.vx-stage{min-height:400px}.vx-object-title{left:40px;bottom:60px}.vx-object-title strong{font-size:30px}.vx-empty h1{font-size:43px}.vx-empty p{font-size:15px}.vx-controls{gap:14px}.vx-header{padding-left:30px;padding-right:30px}}
@media(max-width:420px){.vx-header{height:66px;padding:10px 13px;gap:12px}.vx-brand{font-size:20px;letter-spacing:4px}.vx-tag{font-size:8px;letter-spacing:.5px}.vx-topline{left:12px;right:12px}.vx-footer{padding-left:12px;padding-right:12px}.vx-controls{gap:5px}.vx-controls button{font-size:11px!important;padding:8px 9px}.vx-part-info{padding:10px 14px;max-height:159px}.vx-object-title{left:15px}.vx-object-title strong{font-size:22px}.vx-stage{min-height:260px}.vx-catalog-note{font-size:9px}}
@media(prefers-reduced-motion:reduce){.vx-scanning,.vx-pulse{animation:none}}
`;
