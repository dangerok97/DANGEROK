/** Offline verification of the exact deployable third-party anatomy reference. */
import {readFileSync,existsSync,statSync} from 'node:fs';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';

const dist=resolve(process.argv[2]||'./.vendor-bodyparts3d/dist');
const read=(p)=>readFileSync(resolve(dist,p),'utf8');
const model=JSON.parse(read('models/atlas.json'));
const provenance=JSON.parse(read('ora-integrated.json'));
assert.equal(model.version,'BodyParts3D 4.0');
assert.equal(model.parts.length,2234);
assert.equal(model.concepts.length,3432);
assert.ok(model.chunks.length>=10);
assert.equal(provenance.provider,'BodyParts3D');
assert.equal(provenance.dataset_version,'4.0');
assert.equal(provenance.license,'CC BY 4.0');
assert.equal(provenance.reference,'adult male');
assert.equal(provenance.model_is_person_specific,false);
assert.equal(provenance.distributor_commit,'1c38bf35c254a891200d3cedecfd57abebe83d8d');
assert.ok(read('ATTRIBUTION.md').includes(
 'BodyParts3D, © The Database Center for Life Science licensed under CC Attribution 4.0 International'
));
assert.ok(read('UPSTREAM_MIT_LICENSE.txt').includes('MIT License'));
assert.match(read('index.html'),/\/bodyparts3d\/assets\//);
for(const entry of model.parts){
 assert.ok(Number.isInteger(entry.chunk)&&entry.chunk>=0&&entry.chunk<model.chunks.length);
 assert.ok(entry.vertexCount>0&&entry.indexCount>=3&&entry.indexCount%3===0);
}
let bytes=0;
for(const chunk of model.chunks){
 assert.match(chunk.url,/^\/bodyparts3d\/models\/body-\d+\.bin$/);
 const raw=chunk.url.slice('/bodyparts3d/'.length);
 assert.ok(existsSync(resolve(dist,raw)));
 assert.equal(statSync(resolve(dist,raw)).size,chunk.bytes);
 bytes+=chunk.bytes;
 if(chunk.gzip){
  assert.match(chunk.gzip,/^\/bodyparts3d\/models\/body-\d+\.bin\.gz$/);
  assert.ok(existsSync(resolve(dist,chunk.gzip.slice('/bodyparts3d/'.length))));
 }
}
const concepts=new Set(model.concepts.map(p=>p.id));
const sources=new Set(model.parts.map(p=>p.id));
assert.equal(sources.size,model.parts.length);
assert.equal(concepts.size,model.concepts.length);
// The distributed build must contain BOTH language adaptation and alpha WebGL mode.
const vendorRoot=resolve(dist,'..');
const sourceFile=(p)=>readFileSync(resolve(vendorRoot,p),'utf8');
assert.match(read('index.html'),/lang="it"/);
assert.match(read('index.html'),/ORA · Anatomia 3D/);
assert.match(sourceFile('app/page.tsx'),/Atlante umano/);
assert.match(sourceFile('app/ora-overlay.tsx'),/ORA · \{STUDY_LABEL\[focusRegion\]/);
assert.match(sourceFile('app/ora-overlay.tsx'),/Scomponi/);
assert.match(sourceFile('app/ora-overlay.tsx'),/Dettagli anatomici in arrivo/);
assert.match(sourceFile('app/ora-overlay.tsx'),/ora:anatomy-mesh-ready/);
assert.match(sourceFile('app/ora-overlay.tsx'),/anchor:sceneAnchor/);
assert.match(sourceFile('app/scene.tsx'),/alpha:oraInline/);
assert.match(sourceFile('app/scene.tsx'),/oraInline\?0:1/);
assert.match(sourceFile('app/ora-overlay.css'),/background:transparent/);
assert.match(sourceFile('app/anatomy.ts'),/SISTEMI_IT/);
const assetFiles=await import('node:fs').then(fs=>fs.readdirSync(resolve(dist,'assets')));
assert.ok(assetFiles.some(file=>file.endsWith('.js')),'No deployed 3D viewer JavaScript');

// Check region extraction using the REAL vendor geometry, not a synthetic mock.
const tsModule=await import((await import('node:url')).pathToFileURL(resolve(dist,'../node_modules/typescript/lib/typescript.js')).href);
const ts=tsModule.default||tsModule,vm=await import('node:vm');
const source=readFileSync(resolve('scripts/ora-bodyparts3d-regions.ts'),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{
 module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022
}}).outputText;
const module={exports:{}};
vm.runInNewContext(js,{module,exports:module.exports,require(name){throw Error('Unexpected dependency '+name);}});
const result={};
const regions=module.exports;
for(const id of ['hand','face','torso','abdomen','arm','leg','foot','wrist','knee']){
 const item=regions.anatomicalRegion(model,id,'right');
 result[id]={count:item.ids.length,source:item.source,available:item.available,
   ratio:+(item.ids.length/model.parts.length).toFixed(3)};
 console.log('REGION_SAMPLE '+id+' '+JSON.stringify(result[id]));
 if(['hand','face','torso','abdomen','arm','leg','foot','wrist','knee'].includes(id)){
  assert.ok(item.available,'No usable local geometry for '+id+': '+JSON.stringify(result[id]));
  assert.ok(item.ids.length<model.parts.length*.65,'Too much body geometry in '+id);
 }
}
assert.ok(!regions.anatomicalRegion(model,'hand','right').ids.includes(
 model.parts.find(p=>p.name.toLowerCase()==='heart')?.id||'__heart_missing__'
 ),'Hand cannot contain heart mesh');
const rightHand=regions.anatomicalRegion(model,'hand','right');
const leftHand=regions.anatomicalRegion(model,'hand','left');
const sharedHands=rightHand.ids.filter(id=>leftHand.ids.includes(id)).length;
console.log('REGION_HAND_SIDES '+JSON.stringify({
 right:rightHand.ids.length,left:leftHand.ids.length,shared:sharedHands
}));
assert.ok(leftHand.available,'Left-hand reference mesh is missing');
assert.ok(sharedHands<Math.min(rightHand.ids.length,leftHand.ids.length)*.45,
 'Both hand options cannot display the same anatomical reference');
assert.ok(regions.anatomicalRegion(model,'full_body','unknown').ids.length===2234);
console.log('ANATOMICAL_REGION_COUNTS '+JSON.stringify(result));

// The Italian nomenclature must be dependable: no half-Italian hybrids.
const terminologySource=sourceFile('app/ora-anatomy-terminology-it.ts');
const terminologyJs=ts.transpileModule(terminologySource,{compilerOptions:{
 module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022
}}).outputText;
const terminologyModule={exports:{}};
vm.runInNewContext(terminologyJs,{module:terminologyModule,exports:terminologyModule.exports});
const it=terminologyModule.exports;
for(const [en,expected] of [
 ['Right anterior temporal artery','Arteria temporale anteriore destra'],
 ['Left inferior frontal gyrus','Giro frontale inferiore sinistro'],
 ['Gingiva of upper jaw','Gengiva della mascella superiore'],
 ['Left lower first secondary molar tooth','Primo molare permanente inferiore sinistro'],
 ['Left lower central secondary incisor tooth','Incisivo centrale permanente inferiore sinistro'],
 ['Left lateral nasal cartilage','Cartilagine nasale laterale sinistra'],
 ['Left frontal nerve','Nervo frontale sinistro'],
 ['Left supra-orbital nerve','Nervo sovraorbitario sinistro'],
 ['Right common carotid artery','Arteria carotide comune destra'],
 ['Left choroid','Coroide sinistra'],
 ['External ear','Orecchio esterno'],
 ['Right external ear','Orecchio esterno destro'],
 ['Left lacrimal sac','Sacco lacrimale sinistro'],
 ['White matter of right cerebral hemisphere','Sostanza bianca dell’emisfero cerebrale destro']
]){
 const got=it.anatomyNameIt(en);
 assert.equal(got.name,expected,'Incorrect Italian term for '+en);
 assert.equal(got.reviewed,true);
}
assert.deepEqual(Object.keys(it.anatomyNameIt('Unlisted mysterious tissue of foobar')).sort(),['name','reviewed']);
assert.equal(it.anatomyNameIt('Unlisted mysterious tissue of foobar').reviewed,false);
assert.match(it.systemExplanation('sensory','Orecchio esterno'),/padiglione auricolare/);
assert.match(it.systemExplanation('skeletal','Osso frontale'),/volta cranica/);
assert.match(it.systemExplanation('nervous','Sostanza bianca'),/fibre nervose/);
const candidates=[...model.parts,...model.concepts];
const translated=candidates.filter(p=>it.anatomyNameIt(p.name).reviewed);
const untranslated=candidates.filter(p=>!it.anatomyNameIt(p.name).reviewed);
console.log('ANATOMY_ITALIAN_TERMINOLOGY '+JSON.stringify({
 covered:translated.length,total:candidates.length,
 percentage:+(translated.length/candidates.length*100).toFixed(1),
 originalTerms:untranslated.slice(0,18).map(p=>p.name)
}));
assert.ok(translated.length/candidates.length>.80,
 'Medical Italian terminology coverage regressed unexpectedly');
// Ensure exploded meshes do not collapse into hundreds of unreadable fragments,
// and tapping an individual piece isolates it while remembering the prior page.
const oraOverlay=sourceFile('app/ora-overlay.tsx');
assert.match(oraOverlay,/const EXPLODED_PAGE_SIZE=14/);
assert.match(oraOverlay,/const EXPLODED_PAGE_THRESHOLD=\.50/);
assert.match(oraOverlay,/data-testid="ora-inline-explosion-pager"/);
assert.match(oraOverlay,/data-testid="ora-inline-return-explosion"/);
assert.match(oraOverlay,/isolate:true,explode:0/);
assert.match(oraOverlay,/setState\(s=>\(\{\.\.\.s,selected:\[\],isolate:false,explode:previous\?\.explode/);
assert.match(oraOverlay,/data-testid="ora-inline-zoom-in"/);
assert.match(oraOverlay,/const displayedExplosion=state.isolate&&beforeInspect\?beforeInspect.explode:state.explode/);
assert.match(oraOverlay,/data-testid="ora-inline-explode-percentage"/);
assert.match(oraOverlay,/value=\{Math.round\(displayedExplosion\*100\)\} disabled=\{Boolean\(chosen\)\}/);
assert.doesNotMatch(oraOverlay,/title=\{part.originalName\|\|part.name\}/);
assert.match(sourceFile('app/scene.tsx'),/detailZoom\|\|1/);

// ORA technical blueprint: real cyan 3D edges, subdued blue anatomical system
// colors and a bounded per-page GPU edge cache, not colored textbook solids.
const technicalScene=sourceFile('app/scene.tsx');
const technicalAtlas=sourceFile('app/anatomy.ts');
const blueprintSource=readFileSync(resolve('scripts/ora-bodyparts3d-blueprint.mjs'),'utf8');
assert.match(technicalScene,/technicalColor\(system\)/);
assert.match(technicalScene,/vec3\(0\.25, 0\.76, 0\.99\)/);
assert.match(technicalScene,/new T\.EdgesGeometry\(mesh\.geometry,32\)/);
assert.match(technicalScene,/const EDGE_LIMIT=20,EDGE_CACHE_LIMIT=42/);
assert.match(technicalScene,/syncBlueprintEdges\(s,amount\)/);
assert.match(technicalScene,/blueprintEdges\.forEach\(line=>\{scene\.remove\(line\)/);
assert.match(technicalScene,/partVisible < 0\.5/);
assert.match(technicalScene,/partSelected/);
assert.doesNotMatch(technicalScene,/color:SYSTEMS\.find\(s=>s\.id===system\)/);
assert.match(technicalAtlas,/const ORA_SYSTEM_BLUE/);
assert.match(technicalAtlas,/system\.color=ORA_SYSTEM_BLUE/);
assert.match(blueprintSource,/const EDGE_LIMIT=20,EDGE_CACHE_LIMIT=42/);
assert.match(technicalScene,/const explodedPage=oraInline&&latest\.current\.explode>=\.50/);
assert.match(technicalScene,/const requestedIds=new Set\(latest\.current\.allowed\|\|\[\]\)/);
assert.match(technicalScene,/const preferredSystems=new Set\(latest\.current\.visible\)/);
assert.match(technicalScene,/scores\[b\]-scores\[a\]/);
assert.match(technicalScene,/camera\.setViewOffset\(w,h,w\/2-centerX\*w,h\/2-centerY\*h,w,h\)/);
assert.match(technicalScene,/const positionMix=T\.MathUtils\.smoothstep\(amount,\.16,\.86\)/);
assert.match(technicalScene,/visibleIds\.has\(part\.id\)&&data\[i\*4\+3\]>/);
assert.match(technicalScene,/area\.union\(bounds\[i\]\.clone\(\)\.translate\(/);
assert.match(technicalScene,/lastOverviewZoom=s\.explodedZoom/);
assert.match(technicalScene,/s\.explode>=\.50&&!s\.isolate&&!moving\)fit\(s\.view/);
assert.match(technicalScene,/camera\.setViewOffset\(w,h/);
assert.match(oraOverlay,/data-testid="ora-inline-page-zoom-in"/);
assert.match(oraOverlay,/data-testid="ora-inline-page-zoom-out"/);
assert.match(oraOverlay,/data-testid="ora-inline-page-recenter"/);
assert.match(oraOverlay,/explodedZoom,inspectorOpen:Boolean\(chosen\)/);
console.log('ORA_BLUEPRINT_RENDERER '+JSON.stringify({
 style:'ORA blue technical',edges:'real THREE.EdgesGeometry',
 maximumVisibleOutlinedParts:20,maximumCachedOutlinedParts:42,
 defaultSystemColors:'cyan spectrum',personSpecific:false
}));

console.log(JSON.stringify({status:'PASS',parts:model.parts.length,concepts:model.concepts.length,
 chunks:model.chunks.length,rawBytes:bytes,source:provenance.distributor_commit}));
