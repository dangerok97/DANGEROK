"""One-shot source patch. Exact preimages; only Vision files; no production data migration."""
from pathlib import Path
import hashlib

ROOT = Path.cwd()
EXPECTED = {
    'frontend/src/vision-xray/LiveExplorer.web.tsx': '0f4ffcbab186a9b84204368b0e4e6aa825dee905',
    'frontend/src/vision-xray/catalogApi.ts': '564c3b6cfadf1886044ba2f1236cda8785ed6b93',
    'backend/vision_catalog.py': '5bc8fb716ab23cbf21384fb9a440ddbb607828e5',
    'backend/vision_xray.py': 'e44c8c5a78635305b9c6b22ca594c1c674dae26b',
    'backend/vision_tests/test_catalog.py': '4213820ea2472c793e50eabe2f4a0605fa5852b0',
}
for rel, expected in EXPECTED.items():
    data = (ROOT / rel).read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if actual != expected:
        raise SystemExit('Preimage changed; reconcile instead of overwriting: ' + rel)


def replace(text, old, new):
    if old not in text:
        raise RuntimeError('Missing source fragment: ' + repr(old[:100]))
    return text.replace(old, new)


path = ROOT / 'frontend/src/vision-xray/LiveExplorer.web.tsx'
s = path.read_text()
s = replace(s, "import { ObjectTracker, grayFrame, type GrayFrame }", "import { grayFrame, type GrayFrame }")
s = replace(s, "type Mode = 'idle' | 'opening' | 'live' | 'photo' | 'catalog';", "type Mode = 'idle' | 'opening' | 'live' | 'photo' | 'catalog';\n// The acquired diagram stays on screen, independently of the physical object.\nconst STUDY_BOX: Box = [.15, .03, .70, .66];")
for old in [
    "  const [contribute, setContribute] = useState(false);\n",
    "  const [trackingOk, setTrackingOk] = useState(false);\n",
    "  const lastScan = useRef(0);\n",
    "  const tracker = useRef<ObjectTracker | null>(null);\n",
    "  const tracked = useRef(false);\n",
    "  const lostSince = useRef(0);\n",
    "  const contributeRef = useRef(false);\n  contributeRef.current = contribute;\n",
]:
    s = replace(s, old, '')
s = replace(s, 'tracker.current = null; scene.current = null;', 'scene.current = null;')
s = replace(s, 'tracked.current = false; scanReference.current = null;', 'scanReference.current = null;')
s = replace(s, ' setTrackingOk(false);', '')
s = replace(s, 'const apply = useCallback((value: CatalogResult, reference: GrayFrame | null)', 'const apply = useCallback((value: CatalogResult)')
a = s.index("    if (modeRef.current === 'live' && reference && value.identification) {")
b = s.index('\n  }, []);', a)
s = s[:a] + '''    // Acquisition is complete: preserve model, selection and rotation until explicit dismissal.
    setStage(modeRef.current === 'catalog' ? 'Anteprima catalogo · non è un riconoscimento' : 'Schema fissato · esplora le parti');
    nextScan.current = Infinity;
    void catalogApi.list().then(data => { if (alive.current) setEntries(data.models); }).catch(() => {});''' + s[b:]
s = replace(s, "if (busyRef.current || !['live','photo'].includes(modeRef.current)) return;", "if (busyRef.current || scene.current || !['live','photo'].includes(modeRef.current)) return;")
s = replace(s, 'scanReference.current=reference; lastScan.current=performance.now();', 'scanReference.current=reference;')
s = replace(s, 'catalogApi.scan(dataURI,frameId,contributeRef.current,controller.signal)', 'catalogApi.scan(dataURI,frameId,controller.signal)')
s = replace(s, 'apply(value,reference)', 'apply(value)')
s = replace(s, 'apply(value,null)', 'apply(value)')
s = replace(s, 'scene.current=null; tracker.current=null;', 'scene.current=null;')
a = s.index('  const pickPhoto = async')
s = s[:a] + '''  const newObject = () => {
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

''' + s[a:]
s = replace(s, 'let raf=0,lastTrack=0;', 'let raf=0,lastSample=0;')
s = replace(s, 'if(live&&v?.videoWidth&&pixels&&time-lastTrack>100){', 'if(live&&!scene.current&&v?.videoWidth&&pixels&&time-lastSample>200){')
s = replace(s, 'lastTrack=time;', 'lastSample=time;')
a = s.index('        if(tracker.current){')
b = s.index('\n      if(hasScene){', a)
s = s[:a] + '''        if(!busyRef.current&&time>=nextScan.current){
          const changed=difference(scanReference.current,latestGray.current)>.13;
          if(!scanReference.current||changed){nextScan.current=time+6000;void captureScan();}
        }
      }
      const hasScene=scene.current;
      node.dataset.sceneState=hasScene?'held':'acquiring';''' + s[b:]
s = replace(s, 'if(live&&v?.videoWidth)box=coverBox(box,v.videoWidth,v.videoHeight,w,h);', 'if(live)box=STUDY_BOX;')
s = replace(s, "      if(live){\n        const b=tracker.current&&tracked.current?coverBox(boxRef.current,v!.videoWidth,v!.videoHeight,w,h):[.26,.20,.48,.60] as Box;", "      if(live&&!hasScene){\n        const b: Box=[.26,.20,.48,.60];")
s = replace(s, "ctx.strokeStyle=tracked.current?'rgba(125,246,207,.7)':'rgba(124,228,240,.45)';", "ctx.strokeStyle='rgba(124,228,240,.45)';")
s = replace(s, "&&scene.current&&(modeRef.current!=='live'||tracked.current)", '&&scene.current')
s = replace(s, "  const statusLine=live&&result&&!trackingOk&&!busy?'Riaggancio l’oggetto · lo schema è nascosto finché non lo ritrovo':stage;\n", '')
s = replace(s, '{statusLine}', '{stage}')
s = replace(s, "{live?'● LIVE':", "{live?(result?'● LIVE · SCHEMA FISSATO':'● LIVE'):")
s = replace(s, '      {busy&&<div className="vx-scanning"', '''      {result?.manifest&&<button className="vx-close-model" data-testid="vision-close-model" aria-label="Chiudi la scomposizione e scansiona un altro oggetto" title="Scansiona un altro oggetto" onClick={newObject}>×</button>}
      {busy&&<div className="vx-scanning"''')
s = replace(s, "{mode!=='idle'&&mode!=='opening'&&<button onClick={()=>void openCamera()}", "{!result&&mode!=='idle'&&mode!=='opening'&&<button onClick={newObject}")
s = replace(s, '{live&&<button onClick={()=>void captureScan()}', '{live&&!result&&<button onClick={()=>void captureScan()}')
a = s.index('      <label className="vx-consent">')
b = s.index('\n    </footer>', a)
s = s[:a] + '''      <p className="vx-catalog-note" data-testid="vision-catalog-policy">I nuovi schemi generici vengono salvati automaticamente nel catalogo comune.</p>
      <p className="vx-privacy">Invio fotogrammi all’AI per riconoscere l’oggetto; dopo l’acquisizione l’analisi si ferma. Non registro il video e non salvo foto o dati personali nel catalogo. Le parti interne sono indicative. {result?'Trascina per ruotare · tocca un pezzo · × per scansionare altro.':'Gli oggetti nuovi richiedono più tempo.'}</p>''' + s[b:]
s = replace(s, '.vx-consent{display:flex;justify-content:center;align-items:center;gap:8px;font-size:10px;color:#9fbcc5;margin-top:11px;min-height:26px}.vx-consent input{accent-color:#79dfe7;width:16px;height:16px}', '.vx-catalog-note{text-align:center;font-size:10px;line-height:15px;color:#9fbcc5;margin:11px auto 0;max-width:730px}')
s = replace(s, '.vx-consent{font-size:9px}', '.vx-catalog-note{font-size:9px}')
s = replace(s, '.vx-scanning{position:absolute;', '.vx-close-model{position:absolute;top:55px;right:16px;z-index:4;width:46px;height:46px;display:flex;align-items:center;justify-content:center;border:1px solid #84d9e4;border-radius:50%;background:#041920e8;color:#e5ffff;font-size:31px!important;line-height:1;box-shadow:0 4px 18px #0008}.vx-close-model:hover{background:#153d48}.vx-scanning{position:absolute;')
assert 'contribute' not in s and 'tracker.current' not in s and 'tracked.current' not in s
path.write_text(s)

path = ROOT / 'frontend/src/vision-xray/catalogApi.ts'
s = replace(path.read_text(), 'frameId: string, contribute: boolean, signal?: AbortSignal', 'frameId: string, signal?: AbortSignal')
s = replace(s, 'allow_generation: true, contribute,', 'allow_generation: true,')
path.write_text(s)

path = ROOT / 'backend/vision_catalog.py'
s = replace(path.read_text(), 'scope = "shared" if contribute else self.private_scope(user_id)', '''# Generated recipes are generic shared knowledge. Legacy client flags do not control this.
        # Do not republish previously-private records; existing owner isolation remains intact.
        scope = "shared"''')
path.write_text(s)

path = ROOT / 'backend/vision_xray.py'
s = replace(path.read_text(), '    contribute: bool = False', '    # Compatibility with cached clients only; the server always shares new generic recipes.\n    contribute: bool | None = Field(default=None, exclude=True, deprecated=True)')
s = replace(s, 'user_id=user["user_id"], generator=generator,\n                                       contribute=body.contribute)', 'user_id=user["user_id"], generator=generator)')
s = replace(s, '"schema_version": 1, "verified_3d": False, "catalog_persistent": True}', '"schema_version": 1, "verified_3d": False, "catalog_persistent": True,\n            "catalog_policy": "automatic_generic_shared", "exploration_mode": "hold_after_acquisition"}')
path.write_text(s)

path = ROOT / 'backend/vision_tests/test_catalog.py'
s = path.read_text()
s = replace(s, 'second = await CatalogService(database).resolve(key="stapler", title="", user_id="alice", generator=generate)', 'second = await CatalogService(database).resolve(key="stapler", title="", user_id="bob", generator=generate)')
s = replace(s, 'assert not first["shared"]', 'assert first["shared"] and second["shared"]')
a = s.index('async def test_private_model_cannot_be_read_by_another_user')
b = s.index('\n\n@pytest.mark.asyncio', a)
s = s[:a] + '''async def test_legacy_private_model_is_not_republished(database):
    service = CatalogService(database)
    await service.initialize()
    scope = service.private_scope("alice")
    first = await service._store(Manifest.model_validate(generated_fixture()), scope, "generated")
    await database[JOBS].insert_one({"_id":"legacy-private-job", "model_id":first["model_id"],
                                    "scope":scope, "state":"ready"})
    assert await service.find("stapler", "bob") is None
    assert await service.read(first["model_id"], scope=service.private_scope("bob")) is None
    assert await service.job_result("legacy-private-job", "bob") is None
    await CatalogService(database).initialize()
    assert (await service.find("stapler", "alice"))["shared"] is False
    assert await database[MODELS].count_documents({"canonical_key":"stapler", "scope":"shared"}) == 0
''' + s[b:]
s = replace(s, 'async def test_opted_in_generic_model_is_reused_by_another_user(database):', '@pytest.mark.parametrize("legacy_flag", [None, False, True])\nasync def test_generic_model_is_shared_automatically(database, legacy_flag):')
s = replace(s, 'a = await service.resolve(key="stapler", title="", user_id="alice", generator=generate, contribute=True)', 'a = await service.resolve(key="stapler", title="", user_id="alice", generator=generate, contribute=legacy_flag)')
s = replace(s, 'generator=generate, contribute=True) for u in ("alice", "bob")', 'generator=generate) for u in ("alice", "bob")')
s = replace(s, 'scope = service.private_scope("alice"); model_id = service.model_id("stapler", scope)', 'scope = "shared"; model_id = service.model_id("stapler", scope)')
s += '''

@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_flag", [None, False, True])
async def test_api_shares_generic_recipe_without_client_opt_in(api_module, monkeypatch, database, legacy_flag):
    monkeypatch.setattr(api_module, "can_see", lambda: True)
    async def recognize(*args, **kwargs):
        return {"recognized":True, "canonical_key":"stapler", "object_name":"Pinzatrice",
                "confidence":"high", "bbox":[100,200,900,600], "safe_to_generate":True}
    calls = []
    async def generate(key):
        calls.append(key)
        return generated_fixture(key)
    monkeypatch.setattr(api_module, "ask_json", recognize)
    monkeypatch.setattr(api_module, "generate_family", generate)
    app = FastAPI(); app.include_router(api_module.router, prefix="/api")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        body = {"mime_type":"image/jpeg", "image_base64":jpeg(), "allow_generation":True}
        if legacy_flag is not None: body["contribute"] = legacy_flag
        response = await client.post("/api/vision-xray/scan", json=body,
                                     headers={"Authorization":"Bearer vision-test-alice"})
        assert response.status_code == 200, response.text
        first = response.json()
        assert first["shared"] is True and first["generation_used"] is True
        second = await client.get("/api/vision-xray/catalog/" + first["model_id"],
                                  headers={"Authorization":"Bearer vision-test-bob"})
        assert second.status_code == 200
        assert second.json()["version_id"] == first["version_id"]
        assert second.json()["cache_hit"] and not second.json()["generation_used"]
        available = await client.get("/api/vision-xray/available",
                                     headers={"Authorization":"Bearer vision-test-alice"})
        assert available.json()["catalog_policy"] == "automatic_generic_shared"
    assert calls == ["stapler"]
    for collection in (MODELS, VERSIONS, JOBS):
        text = json.dumps(await database[collection].find({}).to_list(100), default=str)
        assert "image_base64" not in text and "private-metadata-never-persist" not in text
'''
path.write_text(s)

# Modify the existing tested browser suite rather than silently retaining the old loss expectation.
path = ROOT / 'frontend/e2e/vision-live.spec.ts'
s = path.read_text()
s = replace(s, 'offset:0,blank:false,frames:0,stream:null', 'offset:0,blank:false,frames:0,stream:null,openings:0')
s = replace(s, "const getUserMedia=async()=>{\n      const c=", "const getUserMedia=async()=>{\n      state.openings++;\n      const c=")
s = replace(s, "await expect(page.getByTestId('vision-live-explorer')).toBeVisible();", "await expect(page.getByTestId('vision-live-explorer')).toBeVisible();\n  await expect(page.getByRole('checkbox')).toHaveCount(0);\n  await expect(page.getByTestId('vision-catalog-policy')).toContainText('automaticamente');")
s = replace(s, "video remains live during analysis and exploded view, hides on loss, stops on command", "held diagram survives loss, remains interactive, X restarts scanning without reopening camera")
s = replace(s, "await session(page);await virtualCamera(page);await page.goto('/vision-xray');", "await session(page);await virtualCamera(page);\n  const scans:any[]=[];\n  page.on('request',r=>{if(r.url().endsWith('/api/vision-xray/scan'))scans.push(r.postDataJSON());});\n  await page.goto('/vision-xray');")
s = replace(s, "  await expect(page.getByTestId('vision-status')).toContainText('Riconosco');", "  await expect(page.getByTestId('vision-status')).toContainText('Riconosco');\n  await expect(page.getByRole('checkbox')).toHaveCount(0);")
s = replace(s, "  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count','0');\n  await expect(page.getByTestId('vision-status')).toContainText('Riaggancio');", """  // Exceed both old 12s and 15s automatic scan thresholds with the object absent.
  await page.waitForTimeout(17_000);
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count','8');
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-scene-state','held');
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-selected-part','pcb');
  await expect(page.getByTestId('vision-status')).toContainText('Schema fissato');
  expect(scans).toHaveLength(1);expect(scans[0]).not.toHaveProperty('contribute');
  await expect(page.getByTestId('vision-retry')).toHaveCount(0);
  await page.getByTestId('vision-part-battery_a').click();
  await expect(page.getByTestId('vision-part-detail')).toContainText('Prima pila');
  await page.getByTestId('vision-toggle-explode').click();
  await expect(page.getByTestId('vision-toggle-explode')).toHaveText('Scomponi');
  await page.getByTestId('vision-toggle-explode').click();
  await page.screenshot({path:'../.vision-evidence/vision-held-without-object-'+info.project.name+'.png',fullPage:true});
  const close=page.getByTestId('vision-close-model');
  await expect(close).toBeVisible();
  const size=await close.boundingBox();expect(size!.width).toBeGreaterThanOrEqual(44);expect(size!.height).toBeGreaterThanOrEqual(44);
  await page.evaluate(()=>{(window as any).__visionFixture.blank=false;});
  await close.click();
  await expect.poll(()=>scans.length).toBe(2);
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count','8');
  expect(await page.evaluate(()=>(window as any).__visionFixture.openings)).toBe(1);
  expect(await page.getByTestId('vision-camera-video').evaluate((v:HTMLVideoElement)=>(v.srcObject as MediaStream).getTracks()[0].readyState)).toBe('live');""")
path.write_text(s)

path = ROOT / 'docs/VISION_HOLD_SHARED_20261011.md'
path.write_text('''# Vision: schema persistente, X e catalogo automatico

Requisiti del feedback del 11 ottobre 2026.

Dopo un riconoscimento riuscito il modello rimane fissato nello spazio dello schermo.
Perdita di aggancio, spostamento della fotocamera e oggetto fuori scena non lo nascondono.
Scansioni automatiche sospese mentre si esplora: selezione, rotazione e ricomposizione restano disponibili.
La X visibile (46px, etichetta accessibile) chiude il modello e riavvia il riconoscimento
senza chiudere il MediaStream. Risposte tardive sono invalidate. Dall'anteprima catalogo
la X apre la fotocamera su richiesta esplicita. Spegni e uscita fermano ancora la fotocamera.

Non esiste più una casella per contribuire. Il server salva automaticamente i nuovi schemi
generici validati nel catalogo comune; anche i vecchi client che inviano contribute=false
non creano nuovi schemi privati. Il generatore continua a ricevere la sola famiglia generica,
non foto, identità, seriali o contesto privato. Le foto non vengono archiviate nel catalogo.
Le vecchie voci private non vengono ripubblicate o migrate. Non è addestramento dei pesi AI.

Test aggiornati: schema ancora visibile dopo 17 secondi senza oggetto, assenza di nuove
scansioni finché non si preme X, X senza nuova richiesta getUserMedia, schemi condivisi
anche con flag vecchi false/null, riuso da secondo utente e isolamento delle vecchie voci.
I test con MediaStream sintetico non sostituiscono la prova di fotocamera fisica iPhone.
''')
print('Patched Vision source and regression tests. No deployment or production data mutation performed by this script.')
