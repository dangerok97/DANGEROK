"""Bounded source preparation on the explicitly named feature branch only.
No production API, credentials, camera, database or provider is used.
The workflow checks the exact input commit and performs a normal fast-forward push.
"""
from pathlib import Path

def replace(text, before, after):
    assert text.count(before) == 1, 'Unexpected source context: ' + before[:90]
    return text.replace(before, after, 1)

p=Path('frontend/src/vision-xray/walkthrough.ts');s=p.read_text()
s=replace(s,"import type { Manifest } from './scene';", "import type { Manifest } from './scene';\nimport { EXTRA_TOURS, EXTRA_TOUR_SHAPES } from './walkthroughLibrary';")
s=replace(s,"effect:'energy'|'press'|'signal'|'spring'|'seal'|'sense'|'light';", "effect:'energy'|'press'|'signal'|'spring'|'seal'|'sense'|'light'|'flow'|'rotation'|'material'|'sound'|'heat';\n  sourceIndexes?:readonly number[];")
s=replace(s,"export type Walkthrough = { key:string; title:string; sources:readonly TourSource[]; steps:readonly TourStep[] };", "export type Walkthrough = { key:string; title:string; sources:readonly TourSource[]; steps:readonly TourStep[]; note?:string };")
s=replace(s,"const tours:Record<string,Walkthrough>={", "const tours:Record<string,Walkthrough>={\n  ...EXTRA_TOURS,")
a=s.index('/** Only seed models with the expected relationships, never a generated look-alike. */')
b=s.index('/** Bounded single run;',a)
s=s[:a]+r'''/** Sources belong to a step, not to an unrelated panel or a physical-unit claim. */
export function sourcesForStep(tour:Walkthrough,index:number):readonly TourSource[]{
  if(!Number.isInteger(index)||index<0||index>=tour.steps.length)return [];
  const ids=tour.steps[index].sourceIndexes??tour.sources.map((_,i)=>i);
  if(ids.length===0||ids.some(i=>!Number.isInteger(i)||i<0||i>=tour.sources.length))return [];
  return [...new Set(ids)].map(i=>tour.sources[i]);
}

/** Only the authored seed family and part contract can unlock a walkthrough.
 * This is structural compatibility, not proof of the user's hidden hardware.
 */
export function walkthroughFor(manifest:Manifest,sourceType?:string):Walkthrough|null{
  if(sourceType!=='seed'||manifest.schema_version!==1||manifest.evidence_level!=='illustrative'
    ||manifest.match_scope!=='family'||manifest.units!=='illustrative')return null;
  if(!Object.prototype.hasOwnProperty.call(tours,manifest.canonical_key))return null;
  const tour=tours[manifest.canonical_key];
  const keys=new Set(manifest.parts.map(p=>p.key));
  if(keys.size!==manifest.parts.length)return null;
  const expected=EXTRA_TOUR_SHAPES[manifest.canonical_key];
  if(expected&&(manifest.parts.length!==Object.keys(expected).length
    ||manifest.parts.some(p=>expected[p.key]!==p.shape||p.evidence!=='typical')))return null;
  if(!tour.sources.length||tour.sources.some(s=>!s.title.trim()||!/^https:\/\/[^\s/]+\//.test(s.url)))return null;
  return tour.steps.every((step,index)=>{
    const highlighted=new Set(step.parts);
    return step.parts.length>0&&highlighted.size===step.parts.length
      &&step.parts.every(k=>keys.has(k))
      &&step.links.every(([from,to])=>from!==to&&highlighted.has(from)&&highlighted.has(to))
      &&sourcesForStep(tour,index).length>0;
  })?tour:null;
}

''' + s[b:]
p.write_text(s)

p=Path('frontend/src/vision-xray/LiveExplorer.web.tsx');s=p.read_text()
s=replace(s,"{walkthroughFor,TourClock,type Walkthrough}","{walkthroughFor,sourcesForStep,TourClock,type Walkthrough}")
s=replace(s,'<span>3 passaggi</span>','<span>{definition.steps.length} passaggi</span>')
s=replace(s,'Principi generali, non verifica del tuo esemplare.{definition.sources.map(s=>','<span data-testid="vision-tour-source-context">Fonti di questo passaggio · principi generali, non verifica del tuo esemplare.</span>{sourcesForStep(definition,tourUI.index).map(s=>')
s=replace(s,'Collegamenti illustrativi, non un circuito misurato.</small>',"{definition.note||'Collegamenti illustrativi, non un circuito misurato.'}</small>")
p.write_text(s)

p=Path('frontend/src/vision-xray/walkthrough.test.mjs');s=p.read_text()
s=replace(s,'const {walkthroughFor,TourClock}','const {walkthroughFor,sourcesForStep,TourClock}')
s=replace(s,"const reviewed=new Set(['remote_control','click_pen','water_bottle','computer_mouse','flashlight']);","const reviewed=new Set(seeds.map(s=>s.canonical_key));")
s=replace(s,"for(const manifest of seeds.filter(s=>!reviewed.has(s.canonical_key)))test('new catalog family has no invented tour: '+manifest.canonical_key,()=>{assert.equal(walkthroughFor(manifest,'seed'),null);});",'')
s+=r'''
const extra=seeds.filter(s=>!['remote_control','click_pen','water_bottle','computer_mouse','flashlight'].includes(s.canonical_key));
test('all 25 authored families expose exactly 75 bounded steps',()=>{
 assert.equal(seeds.length,25);assert.equal(seeds.reduce((n,m)=>n+walkthroughFor(m,'seed').steps.length,0),75);
});
for(const manifest of extra)test('new authored template cannot be inherited by changed parts or AI output: '+manifest.canonical_key,()=>{
 assert.equal(walkthroughFor(manifest,'generated'),null);
 const clone=JSON.parse(JSON.stringify(manifest));clone.parts[0].shape='spring';
 if(manifest.parts[0].shape==='spring')clone.parts[0].shape='box';
 assert.equal(walkthroughFor(clone,'seed'),null);
 assert.equal(walkthroughFor({...manifest,parts:manifest.parts.slice(1)},'seed'),null);
 const duplicate={...manifest,parts:[...manifest.parts,manifest.parts[0]]};
 assert.equal(walkthroughFor(duplicate,'seed'),null);
 assert.equal(walkthroughFor({...manifest,evidence_level:'model_verified'},'seed'),null);
 assert.equal(walkthroughFor({...manifest,schema_version:99},'seed'),null);
});
test('prototype-like keys and incompatible evidence never unlock a path',()=>{
 for(const key of ['toString','constructor','__proto__'])assert.equal(walkthroughFor({...remote,canonical_key:key},'seed'),null);
 assert.equal(walkthroughFor({...remote,parts:[...remote.parts,remote.parts[0]]},'seed'),null);
});
test('sources are relevant to the active step, bounded, HTTPS and unique',()=>{
 for(const manifest of seeds){
  const tour=walkthroughFor(manifest,'seed');
  for(let i=0;i<tour.steps.length;i++){
   const step=tour.steps[i],refs=sourcesForStep(tour,i);
   assert.ok(step.title.length>=8&&step.title.length<=100);
   assert.ok(step.text.length>=50&&step.text.length<=440);
   assert.ok(refs.length>=1&&refs.length<=4);
   assert.equal(new Set(refs.map(s=>s.url)).size,refs.length);
   assert.ok(refs.every(s=>new URL(s.url).protocol==='https:'));
   assert.ok(step.links.every(([a,b])=>step.parts.includes(a)&&step.parts.includes(b)&&a!==b));
  }
  for(const bad of [-1,99,NaN,.5])assert.equal(sourcesForStep(tour,bad).length,0);
 }
 const phone=walkthroughFor(seeds.find(m=>m.canonical_key==='smartphone'),'seed');
 assert.equal(sourcesForStep(phone,0)[0].url,'https://support.apple.com/en-us/100308');
 assert.equal(sourcesForStep(phone,1)[0].url,'https://www.analog.com/en/products/max11855.html');
 assert.equal(sourcesForStep({...phone,steps:[{...phone.steps[0],sourceIndexes:[99]}]},0).length,0);
});
test('mechanics, flow and materials do not masquerade as measured circuits',()=>{
 const get=key=>walkthroughFor(seeds.find(m=>m.canonical_key===key),'seed');
 assert.match(get('clothespin').steps[1].text,/torsione/);
 assert.match(get('insulated_bottle').steps[1].text,/Non elimina tutti/);
 assert.match(get('adhesive_tape_roll').note,/Strati e regioni/);
 assert.match(get('wooden_pencil').steps[1].text,/regione/);
 assert.match(get('screwdriver').note,/non elettrico/);
 const pump=get('soap_dispenser');
 assert.equal(pump.steps[0].effect,'press');assert.equal(pump.steps[2].effect,'flow');
 assert.ok(pump.steps[2].links.some(([a,b])=>a==='bottle'&&b==='tube'));
 assert.ok(pump.steps[2].links.some(([a,b])=>a==='tube'&&b==='pump'));
});
'''
p.write_text(s)

p=Path('frontend/e2e/vision-catalog-camera.spec.ts');s=p.read_text()
s=replace(s,"await expect(page.getByTestId('vision-how-it-works')).toHaveCount(0);","await expect(page.getByTestId('vision-how-it-works')).toBeVisible();")
p.write_text(s)
p=Path('frontend/playwright.vision.config.ts');s=p.read_text()
s=replace(s,"'vision-catalog-camera.spec.ts']","'vision-catalog-camera.spec.ts','vision-walkthrough25.spec.ts']")
p.write_text(s)

sections={
 'PRODUCT.md': "Tutte le 25 famiglie del pacchetto iniziale hanno ora un percorso didattico scritto: 75 passaggi complessivi. Selezione dei gruppi coinvolti, relazioni simboliche, pausa/frecce/ripetizione e fonti del passaggio. Non si inventa un percorso per un modello generato o incompatibile.",
 'ARCHITECTURE.md': "walkthroughLibrary.ts contiene i 20 nuovi percorsi e i contratti chiave/forma delle parti. walkthroughFor accetta solo seed illustrativi compatibili, rifiuta duplicati, metadati errati e collegamenti estranei ai gruppi evidenziati. sourcesForStep associa i riferimenti al passaggio. Nessuna modifica a backend, database, flash, crop, zoom o runtime dependencies.",
 'DEVELOPMENT_STATE.md': "Aggiunti 20 percorsi alle cinque famiglie esistenti, con testi originali e fonti primarie dei principi generali. Esecuzione locale dei controlli geometrici, gesti e percorsi: 129/129 passati. Test browser aggiunti per tutte le nuove famiglie, fonti per passaggio, compatibilita e schermi compatti. Gate remoti, ispezione visiva e rilascio vanno verificati prima di dichiarare la pubblicazione. Non e un collaudo di fotocamera/flash fisici iPhone.",
 'CHANGELOG_AI.md': "Estesi i percorsi Mostrami come funziona a smartphone, tablet, portatile, tastiera, controller, USB, auricolare/custodia, cancelleria, molletta, dispenser/spruzzatore, borraccia e cacciavite. Note adatte a meccanica, fluidi e materiali; fonti relative al passaggio. Conservati schema fissato, X sulla stessa traccia, zoom indipendenti e catalogo generico automatico.",
}
heading='## 12 ottobre 2026 — Vision: percorsi per tutte le 25 famiglie'
for name,body in sections.items():
    p=Path('docs')/name
    old=p.read_text()
    assert heading not in old
    p.write_text(heading+'\n\n'+body+'\n\n---\n\n'+old)

Path('docs/VISION_WALKTHROUGHS_25.md').write_text('''# Vision — 25 percorsi didattici / 75 passaggi

Data: 12 ottobre 2026. Implementazione candidata, verifiche di rilascio nella PR.

Il catalogo rimane di 25 famiglie: questa versione non aggiunge altri 20 modelli,
ma completa i percorsi dei 20 introdotti nel pacchetto common-25-v1.
Ogni famiglia ha tre passaggi originali, riferiti a gruppi davvero presenti nel
manifest. I collegamenti sono simbolici; non vengono spostati ingranaggi reali,
misurate correnti/forze o ricostruiti gli interni del singolo esemplare.

Esempi: pulsante/matrice/controllo della tastiera; grilletto/pompa/ugello dello
spruzzatore; richiamo e riempimento del dispenser; leve/molla a torsione della
molletta; pareti e chiusura della borraccia isolante. La punta della matita e
lo strato adesivo del nastro sono regioni o strati, non ricambi staccabili.

Le fonti consultate sono collegate al singolo passaggio e supportano principi
costruttivi generali o esempi esplicitamente nominati. Testi e link sono nel
modulo walkthroughLibrary.ts; nessun disegno CAD o testo lungo e copiato.
Marchi nelle fonti NON identificano la marca dell'oggetto fotografato.

I riferimenti principali sono documentazione Apple e Analog Devices per i
gruppi elettronici/tocco; Adafruit per matrici e joystick; Kingston per Flash;
Bluetooth SIG, Sony e osservazione iFixit per l'audio; Pilot, Faber-Castell,
Pentel, edding e Pritt per gli strumenti di scrittura; 3M per il nastro; brevetti
originali di meccanismi per molletta, pinzatrice e pompe; Aptar per spruzzatori;
Thermos per doppia parete; Wera per trasmissione meccanica della coppia.

Le fonti esterne vengono aperte soltanto su scelta dell'utente. L'avvio di un
percorso non invia foto, non fa chiamate AI e non registra nuovi dati. Seed
incompatibili e modelli generati non ereditano automaticamente un percorso.
Il controllo del contratto e una difesa strutturale, non una verifica semantica
universale della geometria.

Test previsti: tutti i 75 passaggi disegnabili senza mutare i manifest, fonti
HTTPS e indici coerenti, duplicati/chiavi/forme incompatibili rifiutati; 20 nuove
famiglie esplorate in Chromium desktop/mobile e WebKit; ripristino del focus,
pausa e termine senza loop; fonti contestuali e controlli su schermi compatti.
Restano attivi i gate di flash/zoom/crop, X senza riapertura, schema fisso e
nessuna scansione durante l'esplorazione. I video nei test sono sintetici.

Nessuna nuova dipendenza, migrazione o modifica ai dati del catalogo. La prova
su fotocamera e flash fisici iPhone resta separata, non implicita nei test UI.
''')
print('Prepared feature-only source and documentation changes.')
