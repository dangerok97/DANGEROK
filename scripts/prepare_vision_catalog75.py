"""One-shot source preparation, QA branch only. No production data or credentials.
Existing 25 families retain exact manifests; no history rewrite or force push.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'backend'))
from vision_catalog import seeds


def once(path, old, new):
    path = ROOT / path
    text = path.read_text()
    if text.count(old) != 1:
        raise AssertionError(f'Expected one source match in {path}: {old[:90]}')
    path.write_text(text.replace(old, new, 1))


old = seeds()
assert len(old) == 25
fingerprints = {m.canonical_key: hashlib.sha256(json.dumps(m.model_dump(mode='json'),
    ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()).hexdigest() for m in old}
fixture = ROOT / 'backend/vision_tests/fixtures/legacy25_sha256.json'
fixture.parent.mkdir(parents=True, exist_ok=True)
assert not fixture.exists()
fixture.write_text(json.dumps(fingerprints, indent=2, sort_keys=True) + '\n')

once('backend/vision_seed_library.py', 'import unicodedata',
     'import unicodedata\nfrom vision_catalog_extended import extended_recipes')
once('backend/vision_seed_library.py', 'PACK_VERSION = "common-25-v1"',
     'PACK_VERSION = "common-75-v1"')
once('backend/vision_seed_library.py', '\ndef metadata():',
     '\ndef all_recipes():\n    """Original twenty recipes plus the additive fifty-family pack."""\n    return common_recipes() + extended_recipes(recipe, p)\n\n\ndef metadata():')
once('backend/vision_seed_library.py', 'for entry in common_recipes():',
     'for entry in all_recipes():')
once('backend/vision_catalog.py',
     'from vision_seed_library import common_recipes, canonical_key, model_metadata',
     'from vision_seed_library import all_recipes, canonical_key, model_metadata')
once('backend/vision_catalog.py', 'for row in common_recipes()]', 'for row in all_recipes()]')
once('backend/vision_catalog_extended/home_desk.py', 'Grucce con gancio metallico', 'Gruccia con gancio metallico')

# Keep original 25/124 assertions scoped to their immutable baseline, not weakened.
once('backend/vision_tests/test_seed_pack.py', 'import json\n', 'import json\nfrom pathlib import Path\n')
once('backend/vision_tests/test_seed_pack.py', '    items = seeds()\n',
     "    baseline = json.loads((Path(__file__).parent / 'fixtures' / 'legacy25_sha256.json').read_text())\n    items = [m for m in seeds() if m.canonical_key in baseline]\n")
once('backend/vision_tests/test_seed_pack.py', '    assert len(rows) == 25', '    assert len(rows) == 75')

path='frontend/src/vision-xray/walkthrough.test.mjs'
once(path,'const reviewed=new Set(seeds.map(s=>s.canonical_key));',
     "const reviewed=new Set(Object.keys(JSON.parse(readFileSync(resolve(here,'../../../backend/vision_tests/fixtures/legacy25_sha256.json'),'utf8'))));\nconst authored=seeds.filter(s=>reviewed.has(s.canonical_key));")
once(path,'const extra=seeds.filter(s=>!', 'const extra=authored.filter(s=>!')
once(path,'assert.equal(seeds.length,25);assert.equal(seeds.reduce',
     'assert.equal(seeds.length,75);assert.equal(authored.length,25);assert.equal(authored.reduce')
once(path,' for(const manifest of seeds){\n  const tour=walkthroughFor',
     ' for(const manifest of authored){\n  const tour=walkthroughFor')
with (ROOT/path).open('a') as output:
    output.write("\ntest('fifty additional seed families never inherit an unauthored tour',()=>{\n const added=seeds.filter(m=>!reviewed.has(m.canonical_key));assert.equal(added.length,50);\n for(const m of added){assert.equal(walkthroughFor(m,'seed'),null);assert.equal(walkthroughFor(m,'generated'),null);}\n});\n")

path='frontend/e2e/vision-catalog-camera.spec.ts'
once(path,"import {mkdirSync} from 'node:fs';", "import {mkdirSync,readFileSync} from 'node:fs';\nconst legacy=new Set(Object.keys(JSON.parse(readFileSync('../backend/vision_tests/fixtures/legacy25_sha256.json','utf8'))));")
once(path,"toContainText('25');", "toContainText('75');")
once(path,'expect(list.models).toHaveLength(25);',
     'expect(list.models).toHaveLength(75);const originalModels=list.models.filter((m:any)=>legacy.has(m.canonical_key));expect(originalModels).toHaveLength(25);')
once(path,'for(const entry of list.models){','for(const entry of originalModels){')
once(path,"toContainText('0 di 25');", "toContainText('0 di 75');")
path='frontend/e2e/vision-walkthrough25.spec.ts'
once(path,"import {mkdirSync} from 'node:fs';", "import {mkdirSync,readFileSync} from 'node:fs';\nconst reviewed=new Set(Object.keys(JSON.parse(readFileSync('../backend/vision_tests/fixtures/legacy25_sha256.json','utf8'))));")
once(path,'list.models.filter((m:any)=>!original.has(m.canonical_key))',
     'list.models.filter((m:any)=>reviewed.has(m.canonical_key)&&!original.has(m.canonical_key))')
once('frontend/playwright.vision.config.ts',"'vision-walkthrough25.spec.ts']", "'vision-walkthrough25.spec.ts','vision-catalog75.spec.ts']")

# Evidence must contain all modules needed to reproduce the catalog.
workflow=ROOT/'.github/workflows/vision-catalog-live.yml'
s=workflow.read_text()
needle='backend/vision_catalog.py backend/vision_xray.py backend/vision_tests'
assert s.count(needle)==1
s=s.replace(needle,'backend/vision_catalog.py backend/vision_xray.py backend/vision_seed_library.py backend/vision_catalog_extended backend/vision_tests',1)
workflow.write_text(s)

# Fresh process: imports above intentionally reflect the *old* registry.
check = '''import hashlib,json
from collections import Counter
from pathlib import Path
from vision_catalog import seeds,Manifest
from vision_seed_library import METADATA,all_recipes,PACK_VERSION,canonical_key
models=seeds();assert len(models)==75
old=json.loads(Path('backend/vision_tests/fixtures/legacy25_sha256.json').read_text())
for m in models:
 if m.canonical_key in old:
  actual=hashlib.sha256(json.dumps(m.model_dump(mode='json'),ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  assert actual==old[m.canonical_key],m.canonical_key
 assert Manifest.model_validate(m.model_dump())==m
 row=METADATA[m.canonical_key]
 for alias in [m.title,*row['aliases']]:assert canonical_key(alias)==m.canonical_key,(m.canonical_key,alias)
assert len(all_recipes())==70
added=[m for m in models if m.canonical_key not in old]
counts={'families':len(models),'legacy':len(old),'added':len(added),'groups':sum(len(m.parts) for m in models),'added_groups':sum(len(m.parts) for m in added),'categories':dict(Counter(METADATA[m.canonical_key]['category'] for m in models))}
Path('.catalog75-prepare').mkdir(exist_ok=True)
Path('.catalog75-prepare/seed-counts.json').write_text(json.dumps(counts,ensure_ascii=False,indent=2))
Path('.catalog75-prepare/seeds.json').write_text(json.dumps([m.model_dump(mode='json') for m in models],ensure_ascii=False))
lines=['# ORA Vision — 75 famiglie del catalogo iniziale','', 'Pacchetto `common-75-v1`. Cinquanta aggiunte alle venticinque precedenti.','',f"Totale: {len(models)} famiglie, {counts['groups']} gruppi principali selezionabili. Le cinquanta aggiunte contengono {counts['added_groups']} gruppi.",'', 'I sinonimi, le foto e le versioni non sono contati come nuovi oggetti. Questo è il contenuto del pacchetto, non una lettura del database di un utente.','', '| Oggetto | Categoria | Gruppi | Stato |','|---|---|---:|---|']
for m in sorted(models,key=lambda m:(METADATA[m.canonical_key]['category'],m.title)):
 lines.append(f"| {m.title} | {METADATA[m.canonical_key]['category']} | {len(m.parts)} | {'Preesistente' if m.canonical_key in old else 'Nuovo'} |")
lines += ['', '## Comportamento e limiti', '', 'Ogni voce ha geometrie procedurali separabili, posizioni di apertura, identificatori stabili e spiegazioni originali. Forme, proporzioni e disposizione sono schematiche; alcuni gruppi riuniscono parti integrate o incollate. Le dimensioni sono unità grafiche e non misure reali.', '', 'I 25 modelli precedenti conservano gli stessi manifest e i 25 percorsi didattici già pubblicati. Le 50 aggiunte hanno selezione, spiegazioni, zoom, rotazione e ricomposizione, ma non ricevono un percorso animato inventato.', '', 'I riferimenti, quando presenti, documentano principi generali o esempi di costruzione: non certificano l’interno dell’esemplare inquadrato. Nessun CAD, fotografia, valore tecnico specifico o modello di marca è copiato.', '', 'Le nuove famiglie sono incluse nei nomi canonici usati dal riconoscimento, nei sinonimi e nelle categorie di ricerca. La ricerca resta distinta dalla ricostruzione di un esemplare specifico. Gli schemi originali e generati restano etichettati illustrativi.', '', 'Installazione non distruttiva tramite il servizio esistente: aggiunta di versioni, promozione controllata di eventuali precedenti versioni generate pubbliche, conservazione di versioni vecchie, voci private e voci ritirate.', '', 'Nessuna modifica ai controlli di flash, zoom della fotocamera o del modello, schema fissato e × sulla stessa traccia video. Nessuna nuova dipendenza runtime. Nessuna nuova prova fisica iPhone implicita.', '', '## Verifica', '', 'Baseline dei 25 manifest salvata come SHA-256 canonici prima dell’espansione; preflight 75 famiglie/50 aggiunte e alias validi. Gate remoti, screenshot e pubblicazione devono ancora essere verificati sul commit finale.']
Path('docs/VISION_CATALOG_75_INVENTORY.md').write_text('\\n'.join(lines)+'\\n')
print(json.dumps(counts))
'''
env={**os.environ,'PYTHONPATH':str(ROOT/'backend')}
subprocess.run([sys.executable,'-c',check],check=True,env=env)

sections={
 'PRODUCT.md':'Il catalogo iniziale Vision passa da 25 a 75 famiglie, con cinquanta nuovi oggetti di cucina, casa, scrivania, elettronica, utensili e tempo libero. Ricerca per nome, sinonimo e categoria. Le nuove voci hanno parti selezionabili e spiegazioni; i percorsi didattici restano i 25 già pubblicati. Sono gruppi illustrativi, non interni verificati.',
 'ARCHITECTURE.md':'`vision_catalog_extended` compone tre raccolte additive, 50 ricette originali in nove primitive. `common_recipes()` conserva le venti ricette storiche; `all_recipes()` le integra con la nuova raccolta. `seeds()` e `METADATA` usano lo stesso insieme. Nessuna modifica a schema dati, servizio di pubblicazione o motore grafico. I manifest dei 25 seed storici conservano il fingerprint canonico.',
 'DEVELOPMENT_STATE.md':'Preparata espansione a 75 famiglie/50 aggiunte sul ramo Vision, lasciando intatte le riparazioni della roadmap. Preflight controlla manifest, conteggi, alias e immutabilità dei 25 seed precedenti. Nuovi test Mongo e browser coprono tutte le famiglie aggiunte; rilascio e stato dei gate saranno documentati nella PR finale, non presunti completati qui.',
 'CHANGELOG_AI.md':'Aggiunte 50 ricette di oggetti quotidiani e rispettivi sinonimi/categorie. Preservati manifest e percorsi dei 25 oggetti precedenti. Aggiunti test di migrazione da 25 a 75, riuso senza generazione, isolamento delle vecchie voci private, mancata riattivazione dei ritirati e apertura/selezione delle 50 nuove famiglie su mobile e desktop.',
}
for filename,text in sections.items():
    path=ROOT/'docs'/filename
    path.write_text('## 12 ottobre 2026 — Vision: catalogo iniziale da 75 famiglie\n\n'+text+'\n\n---\n\n'+path.read_text())
print('Source integration complete; CI and deployment are still pending.')
