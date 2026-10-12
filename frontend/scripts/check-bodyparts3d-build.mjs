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
assert.match(sourceFile('app/ora-overlay.tsx'),/Preparo il corpo umano 3D/);
assert.match(sourceFile('app/scene.tsx'),/alpha:oraInline/);
assert.match(sourceFile('app/scene.tsx'),/oraInline\?0:1/);
assert.match(sourceFile('app/ora-overlay.css'),/background:transparent/);
assert.match(sourceFile('app/anatomy.ts'),/SISTEMI_IT/);
const assetFiles=await import('node:fs').then(fs=>fs.readdirSync(resolve(dist,'assets')));
assert.ok(assetFiles.some(file=>file.endsWith('.js')),'No deployed 3D viewer JavaScript');

// Check region extraction using the REAL vendor geometry, not a synthetic mock.
const ts = await import('typescript'),vm=await import('node:vm');
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
 if(['hand','face','torso','abdomen','arm','leg','foot'].includes(id)){
  assert.ok(item.available,'No usable local geometry for '+id+': '+JSON.stringify(result[id]));
  assert.ok(item.ids.length<model.parts.length*.65,'Too much body geometry in '+id);
 }
}
assert.ok(!regions.anatomicalRegion(model,'hand','right').ids.includes(
 model.parts.find(p=>p.name.toLowerCase()==='heart')?.id||'__heart_missing__'
 ),'Hand cannot contain heart mesh');
assert.ok(regions.anatomicalRegion(model,'full_body','unknown').ids.length===2234);
console.log('ANATOMICAL_REGION_COUNTS '+JSON.stringify(result));

console.log(JSON.stringify({status:'PASS',parts:model.parts.length,concepts:model.concepts.length,
 chunks:model.chunks.length,rawBytes:bytes,source:provenance.distributor_commit}));
