"""One-shot explicit source edit on the named feature branch only.
No deployment, private data access, secrets or database effects.
"""
from pathlib import Path
ROOT = Path.cwd()
def edit(path, old, new, count=1):
    p=ROOT/path; s=p.read_text()
    assert s.count(old)==count, (path, old[:90], s.count(old), count)
    p.write_text(s.replace(old,new))

p='backend/vision_catalog.py'
edit(p,'from pymongo import ReturnDocument','from pymongo import ReturnDocument\nfrom vision_seed_library import common_recipes, canonical_key, model_metadata')
edit(p,'    ]\n\n\nclass CatalogLimit', '    ] + [Manifest.model_validate(row["manifest"]) for row in common_recipes()]\n\n\nclass CatalogLimit')
edit(p,'await self._store(manifest, "shared", "seed", insert_only=True)','await self.install_seed(manifest)')
edit(p,'    async def read(self, model_id, *, scope):', '''    async def install_seed(self, manifest):
        """Promote only a generated public head via CAS; keep old versions and tombstones."""
        stored = await self._store(manifest, "shared", "seed", insert_only=True)
        if not stored or stored["source_type"] != "generated":
            return
        body = manifest.model_dump(mode="json")
        revision = "vxv_" + digest(stored["model_id"] + json.dumps(body, sort_keys=True, separators=(",", ":")))
        await self.db[MODELS].update_one({
            "_id": stored["model_id"], "scope": "shared", "status": "published",
            "source_type": "generated", "current_version": stored["version_id"],
        }, {"$set": {"current_version": revision, "source_type": "seed",
                     "title": manifest.title, "updated_at": now()}})

    async def read(self, model_id, *, scope):''')
edit(p,'"source_type": version["source_type"], "shared": scope == "shared"}', '''"source_type": version["source_type"], "shared": scope == "shared",
                "sources": model_metadata(manifest["canonical_key"])["sources"] if version["source_type"] == "seed" else []}''')
edit(p,'    async def find(self, key, user_id):\n        for scope', '    async def find(self, key, user_id):\n        key = canonical_key(key)\n        for scope')
edit(p,'.sort("canonical_key", 1).limit(100).to_list(100)', '.sort([("source_type", -1), ("canonical_key", 1)]).limit(500).to_list(500)')
edit(p,'"shared": r["scope"] == "shared"} for r in rows]', '''"shared": r["scope"] == "shared", "category": model_metadata(r["canonical_key"])["category"],
                 "aliases": model_metadata(r["canonical_key"])["aliases"]} for r in rows]''')
edit(p,'        await self.initialize()\n        if not re.fullmatch', '        await self.initialize()\n        key = canonical_key(key)\n        if not re.fullmatch')
p='backend/vision_xray.py'
edit(p,'from vision_catalog import CatalogLimit, CatalogService, Manifest, SHAPES, seeds','from vision_catalog import CatalogLimit, CatalogService, Manifest, SHAPES, seeds\nfrom vision_seed_library import canonical_key, recognition_hint, PACK_VERSION')
edit(p,'Famiglie già supportate: remote_control, click_pen, water_bottle,\ncomputer_mouse, flashlight. Se non è una di queste, usa il nome comune più', 'Famiglie già supportate elencate di seguito. Se non è una di queste, usa il nome comune più')
edit(p,'Non confondere un\'immagine stampata o uno schermo con l\'oggetto reale.\n"""', '''Non confondere un'immagine stampata o uno schermo con l'oggetto reale.
Non assimilare una tastiera meccanica a una a membrana, una penna a cappuccio a
una a scatto, cuffie cablate ad auricolari wireless, una borraccia semplice a
una termica o una bomboletta pressurizzata a uno spruzzatore manuale. Quando la
variante non è determinabile, dichiara il limite; le corrispondenze sono di
famiglia, mai di marca. Nomi ambigui come notebook non indicano per forza un PC.
""" + "\\nCatalogo di famiglie: " + recognition_hint()''')
edit(p,'key = str(raw.get("canonical_key", ""))', 'key = canonical_key(raw.get("canonical_key", ""))')
edit(p,'"seed_count": len(seeds()),', '"seed_count": len(seeds()), "catalog_pack": PACK_VERSION,')
p='backend/vision_tests/test_catalog.py'
s=(ROOT/p).read_text().replace('"stapler"','"test_widget"')
s=s.replace('== 5\n','== len(seeds())\n').replace('== 4\n','== len(seeds()) - 1\n')
(ROOT/p).write_text(s)

p='frontend/src/vision-xray/catalogApi.ts'
edit(p,"shared: boolean };", "shared: boolean; category?: string; aliases?: string[] };")
edit(p,"  status: 'family' | 'building' | 'unknown';", "  status: 'family' | 'building' | 'unknown';\n  sources?: {title:string;url:string}[];")

p='frontend/src/vision-xray/LiveExplorer.web.tsx'
edit(p,"import type {Box} from './scene';", "import type {Box} from './scene';\nimport {CameraTorch, type TorchState, TORCH_UNAVAILABLE, cameraCrop, sameCrop, drawCameraCrop, clampCameraZoom} from './cameraControls';\nimport {filterCatalog} from './catalogSearch';")
edit(p,"  const [libraryOpen,setLibraryOpen]=useState(false);", """  const [libraryOpen,setLibraryOpen]=useState(false);
  const [catalogQuery,setCatalogQuery]=useState('');
  const [catalogCategory,setCatalogCategory]=useState('Tutti');
  const [cameraZoom,setCameraZoomUI]=useState(1);
  const [cameraPanel,setCameraPanel]=useState(false);
  const [torchUI,setTorchUI]=useState<TorchState>({supported:false,on:false,busy:false,message:TORCH_UNAVAILABLE});
  const cameraZoomRef=useRef(1);
  const torch=useRef<CameraTorch|null>(null);
  const stageElement=useRef<HTMLElement|null>(null);""")
edit(p,"    stream.current?.getTracks().forEach(t=>t.stop());stream.current=null;", "    torch.current?.dispose();torch.current=null;cameraZoomRef.current=1;\n    stream.current?.getTracks().forEach(t=>t.stop());stream.current=null;")
edit(p,"if(alive.current){setMode('idle');setBusy(false);setResult(null);setPhotoURL(null);setInfoOpen(false);}", "if(alive.current){setMode('idle');setBusy(false);setResult(null);setPhotoURL(null);setInfoOpen(false);setCameraZoomUI(1);setCameraPanel(false);setTorchUI({supported:false,on:false,busy:false,message:TORCH_UNAVAILABLE});}")
edit(p,"  const captureScan=useCallback(async()=>{", """  const changeCameraZoom=useCallback((requested:number)=>{
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

  const captureScan=useCallback(async()=>{""")
edit(p,"""    const sw=source instanceof HTMLVideoElement?source.videoWidth:source.naturalWidth;
    const sh=source instanceof HTMLVideoElement?source.videoHeight:source.naturalHeight;if(!sw||!sh)return;
    const snapshot=document.createElement('canvas'),scale=Math.min(1,960/Math.max(sw,sh));""", """    const rawWidth=source instanceof HTMLVideoElement?source.videoWidth:source.naturalWidth;
    const rawHeight=source instanceof HTMLVideoElement?source.videoHeight:source.naturalHeight;if(!rawWidth||!rawHeight)return;
    const liveCapture=modeRef.current==='live';
    const rect=stageElement.current?.getBoundingClientRect();
    const crop=liveCapture?cameraCrop(rawWidth,rawHeight,rect?.width||rawWidth,rect?.height||rawHeight,cameraZoomRef.current):{x:0,y:0,width:rawWidth,height:rawHeight};
    const sw=crop.width,sh=crop.height;
    const snapshot=document.createElement('canvas'),scale=Math.min(1,960/Math.max(sw,sh));""")
edit(p,"context.drawImage(source,0,0,snapshot.width,snapshot.height);", "drawCameraCrop(context,source,crop,snapshot.width,snapshot.height);")
edit(p,"""            sc.drawImage(video.current,0,0,small.width,small.height);
            box=currentBox(scanReference.current,grayFrame(sc.getImageData(0,0,small.width,small.height)),value.identification.bbox);""", """            const currentRect=stageElement.current?.getBoundingClientRect();
            const fresh=cameraCrop(video.current.videoWidth,video.current.videoHeight,currentRect?.width||rawWidth,currentRect?.height||rawHeight,cameraZoomRef.current);
            if(sameCrop(crop,fresh)){
              drawCameraCrop(sc,video.current,fresh,small.width,small.height);
              box=currentBox(scanReference.current,grayFrame(sc.getImageData(0,0,small.width,small.height)),value.identification.bbox);
            }""")
edit(p,"      changeMode('live');setStage('Tieni l’oggetto al centro: lo riconosco automaticamente.');nextScan.current=performance.now()+1500;", """      const track=media.getVideoTracks()[0];
      if(track){
        const control=new CameraTorch(track,state=>{if(alive.current&&torch.current===control)setTorchUI(state);});
        torch.current=control;setTorchUI(control.snapshot());
        track.addEventListener('ended',()=>{if(alive.current&&stream.current===media){stop();setError('La fotocamera è stata disconnessa. Riaprila per continuare.');}},{once:true});
      }
      changeMode('live');setStage('Tieni l’oggetto al centro: lo riconosco automaticamente.');nextScan.current=performance.now()+1500;""")
edit(p,"setResult(null);setBusy(false);setError(null);setInfoOpen(false);setLibraryOpen(false);", "setResult(null);setBusy(false);setError(null);setInfoOpen(false);setLibraryOpen(false);setCameraPanel(false);")
edit(p,"const wheel=(e:WheelEvent)=>{if(!scene.current)return;e.preventDefault();view.current.zoom=clampZoom(view.current.zoom*Math.exp(-e.deltaY*.0015));};", "const wheel=(e:WheelEvent)=>{if(!scene.current&&modeRef.current!=='live')return;e.preventDefault();if(scene.current)view.current.zoom=clampZoom(view.current.zoom*Math.exp(-e.deltaY*.0015));else changeCameraZoom(cameraZoomRef.current*Math.exp(-e.deltaY*.0015));};")
edit(p,"""        lastSample=time;small.width=160;small.height=Math.round(160*v.videoHeight/v.videoWidth);
        pixels.drawImage(v,0,0,small.width,small.height);""", """        const rect=stageElement.current?.getBoundingClientRect();
        const crop=cameraCrop(v.videoWidth,v.videoHeight,rect?.width||w,rect?.height||h,cameraZoomRef.current);
        lastSample=time;small.width=160;small.height=Math.round(160*crop.height/crop.width);
        drawCameraCrop(pixels,v,crop,small.width,small.height);""")
edit(p,"    if(!scene.current)return;finishArrival();gestures.current.down(e.pointerId,e.clientX,e.clientY);", "    if(!scene.current&&modeRef.current!=='live')return;finishArrival();gestures.current.down(e.pointerId,e.clientX,e.clientY);")
edit(p,"""    if(!scene.current)return;
    const d=gestures.current.move(e.pointerId,e.clientX,e.clientY);
    view.current.yaw+=d.yaw;view.current.pitch=Math.max(-1.1,Math.min(1.1,view.current.pitch+d.pitch));view.current.zoom=clampZoom(view.current.zoom*d.zoomFactor);""", """    if(!scene.current&&modeRef.current!=='live')return;
    const d=gestures.current.move(e.pointerId,e.clientX,e.clientY);
    if(!scene.current){changeCameraZoom(cameraZoomRef.current*d.zoomFactor);return;}
    view.current.yaw+=d.yaw;view.current.pitch=Math.max(-1.1,Math.min(1.1,view.current.pitch+d.pitch));view.current.zoom=clampZoom(view.current.zoom*d.zoomFactor);""")
edit(p,"  const currentPart=result?.manifest?.parts.find(p=>p.key===selected),live=mode==='live';", """  const currentPart=result?.manifest?.parts.find(p=>p.key===selected),live=mode==='live';
  const visibleEntries=filterCatalog(entries,catalogQuery,catalogCategory);
  const categories=['Tutti',...Array.from(new Set(entries.map(e=>e.category||'Altri oggetti'))).sort()];""")
edit(p,'<section className="vx-stage" aria-label=', '<section ref={stageElement} className="vx-stage" aria-label=')
edit(p,'style={{opacity:live?1:0}}', 'style={{opacity:live?1:0,transform:`scale(${cameraZoom})`,transformOrigin:"center"}} data-camera-zoom={cameraZoom.toFixed(2)}')
edit(p,'tabIndex={result?0:-1}', 'tabIndex={result||live?0:-1}')
edit(p,'aria-label="Scena 3D. Trascina per ruotare, due dita per lo zoom. Con tastiera: frecce per ruotare, più e meno per zoomare. I componenti sono disponibili anche nei pulsanti sotto."', 'aria-label={result?"Scena 3D: trascina per ruotare, due dita per ingrandire i componenti.":"Fotocamera: due dita per lo zoom digitale. I comandi sono disponibili anche nei pulsanti."}')
edit(p,'      {busy&&<div className="vx-scanning"', '''      {live&&<div className="vx-camera-tools" data-testid="vision-camera-controls">
        <button className={torchUI.on?'is-on':''} data-testid="vision-torch" aria-label={torchUI.supported?(torchUI.on?'Spegni il flash':'Accendi il flash'):TORCH_UNAVAILABLE} aria-pressed={torchUI.on} disabled={!torchUI.supported||torchUI.busy} title={torchUI.message||'Luce continua della fotocamera'} onClick={()=>void torch.current?.toggle()}>{torchUI.busy?'…':torchUI.supported?(torchUI.on?'⚡ On':'⚡ Off'):'Flash n/d'}</button>
        <button data-testid="vision-camera-zoom-toggle" aria-label="Zoom della fotocamera" aria-expanded={cameraPanel} onClick={()=>setCameraPanel(v=>!v)}>◉ {cameraZoom.toFixed(1)}×</button>
        {cameraPanel&&<div className="vx-camera-zoom-panel" data-testid="vision-camera-zoom-panel"><small>ZOOM FOTOCAMERA · DIGITALE</small><div>{[1,2,3].map(z=><button key={z} data-testid={'vision-camera-zoom-'+z} aria-pressed={Math.abs(cameraZoom-z)<.05} onClick={()=>changeCameraZoom(z)}>{z}×</button>)}</div><input data-testid="vision-camera-zoom-range" aria-label="Ingrandimento della fotocamera" type="range" min="1" max="3" step="0.1" value={cameraZoom} onChange={e=>changeCameraZoom(Number(e.target.value))}/><span>{result?'Non modifica lo zoom dello schema 3D.':'ORA analizza la stessa area ingrandita.'}</span></div>}
        {torchUI.message&&torchUI.supported&&<p role="status" className="vx-camera-message">{torchUI.message}</p>}
      </div>}
      {busy&&<div className="vx-scanning"''')
edit(p,'<p>Modelli indicativi salvati, non riconoscimenti della fotocamera.</p>{entries.map(entry=>', '''<p>Modelli indicativi salvati, non riconoscimenti della fotocamera.</p><input className="vx-catalog-search" data-testid="vision-catalog-search" type="search" aria-label="Cerca un oggetto nel catalogo" placeholder="Cerca: telefono, penna, USB…" value={catalogQuery} onChange={e=>setCatalogQuery(e.target.value)}/><select className="vx-catalog-category" data-testid="vision-catalog-category" aria-label="Categoria del catalogo" value={catalogCategory} onChange={e=>setCatalogCategory(e.target.value)}>{categories.map(c=><option key={c}>{c}</option>)}</select><small role="status" data-testid="vision-catalog-count">{visibleEntries.length} di {entries.length} modelli</small>{visibleEntries.map(entry=>''')
edit(p,"{entry.shared?'Condiviso':'Privato'} · schema indicativo", "{entry.category||'Altri oggetti'} · {entry.shared?'Condiviso':'Privato'}")
edit(p,'</small></button>)}<button onClick={()=>setLibraryOpen(false)}>Chiudi catalogo</button>', '</small></button>)}{!visibleEntries.length&&<p>Nessun modello corrispondente. Prova un altro nome o inquadra l’oggetto.</p>}<button onClick={()=>setLibraryOpen(false)}>Chiudi catalogo</button>')
edit(p,'<p>I nuovi schemi generici validati vengono salvati automaticamente', '''{Boolean(result?.sources?.length)&&<div className="vx-seed-sources">Riferimenti generali, non verifica del tuo esemplare.{result!.sources!.map(s=><a key={s.url} href={s.url} target="_blank" rel="noopener noreferrer">{s.title} ↗</a>)}</div>}<p>I nuovi schemi generici validati vengono salvati automaticamente''')

p='frontend/src/vision-xray/visualStyle.ts'
edit(p,'`;','''
.vx-camera-tools{position:absolute;z-index:6;bottom:48px;left:14px;display:flex;gap:7px;align-items:center;max-width:calc(100% - 28px)}
.vx-camera-tools>button{background:#0c2533ed;border:1px solid #537080;border-radius:12px;min-height:44px;min-width:52px;font-size:12px!important;padding:8px 12px}.vx-camera-tools>button.is-on{color:#ffe1a6;background:#4a3721;border-color:#d5ac6d}.vx-camera-tools>button:disabled{opacity:.65;cursor:default}
.vx-camera-zoom-panel{position:absolute;bottom:54px;left:0;width:230px;max-width:calc(100vw - 32px);border:1px solid #4b6879;background:#0c2331f5;box-shadow:0 5px 20px #0008;border-radius:14px;padding:12px;display:flex;flex-direction:column;gap:9px}
.vx-camera-zoom-panel small{font:9px monospace;color:#b1d6e5}.vx-camera-zoom-panel div{display:flex;gap:8px}.vx-camera-zoom-panel button{flex:1;border:1px solid #3c5f70;border-radius:10px;background:#143747;min-height:40px}.vx-camera-zoom-panel button[aria-pressed=true]{background:#4d3b28;color:#ffdaad;border-color:#ac865c}.vx-camera-zoom-panel input{width:100%;height:34px;accent-color:#b0e4f2}.vx-camera-zoom-panel span{font-size:10px;line-height:15px;color:#a0bdcd}
.vx-camera-message{position:absolute;left:0;bottom:49px;width:230px;background:#382b21;color:#ffdfc2;font-size:11px;padding:10px;border-radius:8px}.vx-catalog-search,.vx-catalog-category{width:100%;min-height:44px;border:1px solid #587381;border-radius:10px;color:#e0f3f8;background:#122c3b;padding:10px;margin-bottom:9px;font-size:14px}.vx-catalog-search::placeholder{color:#97b2c1}.vx-seed-sources{font-size:11px;line-height:17px;color:#a9c9d8}.vx-seed-sources a{display:block;color:#c6edff;min-height:36px;padding:8px 0}
@media(max-height:540px) and (orientation:landscape){.vx-camera-tools{bottom:12px;left:14px}.vx-camera-zoom-panel{bottom:50px;width:210px;gap:5px;padding:8px}.vx-root.has-model .vx-camera-tools{left:auto;right:14px;bottom:10px}}
`;''')

p='frontend/src/vision-xray/walkthrough.test.mjs'
edit(p,'for(const manifest of seeds)test(',"const reviewed=new Set(['remote_control','click_pen','water_bottle','computer_mouse','flashlight']);\nfor(const manifest of seeds.filter(s=>reviewed.has(s.canonical_key)))test(")
p=ROOT/p
p.write_text(p.read_text()+"\nfor(const manifest of seeds.filter(s=>!reviewed.has(s.canonical_key)))test('new catalog family has no invented tour: '+manifest.canonical_key,()=>{assert.equal(walkthroughFor(manifest,'seed'),null);});\n")
edit('frontend/playwright.vision.config.ts',"'vision-guided-v3.spec.ts']", "'vision-guided-v3.spec.ts','vision-catalog-camera.spec.ts']")
p='frontend/e2e/vision-catalog-camera.spec.ts'
edit(p,"await page.getByTestId('vision-zoom-in').click();const modelZoom=", "await page.getByTestId('vision-zoom-in').click();await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-zoom','1.250');const modelZoom=")

# The fixture recogniser must return coordinates in the image it actually receives
# now that the application correctly sends the visible crop instead of the full sensor.
p='scripts/vision_test_server.py'
edit(p,'import asyncio\n', 'import asyncio\nimport io\nfrom PIL import Image\n')
edit(p,'    await asyncio.sleep(1.1)\n    return {"recognized":True', '''    box = [146,406,854,578]
    with Image.open(io.BytesIO(image)) as frame:
        frame = frame.convert("RGB"); frame.thumbnail((160,160))
        points = [(x,y) for y in range(frame.height) for x in range(frame.width)
                  if (lambda rgb: rgb[0]<85 and rgb[1]<110 and rgb[2]<125)(frame.getpixel((x,y)))]
        if points:
            x0=min(x for x,y in points); y0=min(y for x,y in points)
            x1=max(x for x,y in points)+1; y1=max(y for x,y in points)+1
            box=[y0/frame.height*1000,x0/frame.width*1000,y1/frame.height*1000,x1/frame.width*1000]
    await asyncio.sleep(1.1)
    return {"recognized":True''')
edit(p,'"confidence":"high","bbox":[146,406,854,578]', '"confidence":"high","bbox":box')

note='''\n\n## Vision catalog 25 + fotocamera (2026-10-12)\n\nCatalogo iniziale ampliato a 25 famiglie / 124 gruppi separabili. Nuovi seed in\n`backend/vision_seed_library.py`; nomi canonici e sinonimi condivisi con il\nriconoscimento. Ricerca per testo e categoria. Modelli illustrativi, non interni\nverificati. I 20 nuovi modelli non ricevono un percorso didattico inventato.\nLe cinque famiglie precedenti mantengono il proprio percorso.\n\nFlash/torcia tramite getCapabilities/applyConstraints/getSettings della traccia.\nIndicatore acceso solo dopo conferma; indisponibilità esplicita; rilascio della\ntraccia e richiesta di spegnimento all'uscita. Zoom FOTOCAMERA digitale 1–3x\nindipendente dallo zoom 3D: stesso ritaglio per preview, fotogramma AI e\nconferma della posizione. Zoom durante riconoscimento invalida risposte vecchie;\nzoom mentre si esplora non riavvia l'AI. Nessuna registrazione video.\n\nInstallazione seed idempotente: aggiunge versioni e promuove tramite confronto\ndella versione solo precedenti modelli generati pubblici. Mantiene versioni\nvecchie, voci private e modelli ritirati. Nessuna nuova dipendenza runtime.\nTest aggiunti per 25 famiglie, sinonimi, riuso, migrazione non distruttiva, flash\nsupportato/non supportato/ignorato, crop dei pixel e indipendenza dei due zoom.\nI dispositivi nei test browser sono simulati; il flash fisico su iPhone deve\nancora essere verificato. Non dichiarare supporto del flash universale.\n\nRiferimenti API: https://www.w3.org/TR/image-capture/ e\nhttps://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/getCapabilities\nLo zoom qui è digitale, non un comando hardware o zoom ottico. Le sorgenti\ngenerali per i seed sono elencate nel modulo; nessun CAD o immagine è copiato.\n'''
for name in ['PRODUCT','ARCHITECTURE','DEVELOPMENT_STATE','CHANGELOG_AI']:
    path=ROOT/'docs'/f'{name}.md'
    path.write_text((path.read_text() if path.exists() else '# ORA\n')+note)
(ROOT/'docs'/'VISION_CATALOG_CAMERA_V4.md').write_text('# Vision — catalogo e comandi fotocamera\n'+note)
