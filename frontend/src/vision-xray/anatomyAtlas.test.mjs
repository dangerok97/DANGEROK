import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
import ts from 'typescript';
const root=dirname(fileURLToPath(import.meta.url));
const compile=(filename,modules={})=>{
 const source=readFileSync(resolve(root,filename),'utf8');
 const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const module={exports:{}};
 vm.runInNewContext(output,{module,exports:module.exports,require:(name)=>{
  if(!(name in modules))throw new Error('Unexpected import: '+name);
  return modules[name];
 }});
 return module.exports;
};
const detail=compile('anatomyDetail.ts');
const atlas=compile('anatomyAtlas.ts',{'./anatomyDetail':detail});
const focus=compile('anatomyFocus.ts',{'./anatomyAtlas':atlas});

test('all seven anatomy layers expose actual geometry and unique selectable IDs',()=>{
 assert.equal(atlas.LAYERS.length,7);
 for(const {key} of atlas.LAYERS){
  const regions=atlas.regionsFor(key,'neutral');
  assert.ok(regions.length>=(key==='reproductive'?1:3),'missing atlas parts for '+key);
  const ids=regions.map(r=>r.id);
  assert.equal(new Set(ids).size,ids.length,'duplicate structure ID in '+key);
  for(const part of regions){
   assert.ok(part.label.length>=3&&part.detail.length>=20);
   assert.ok(/^M[0-9 -]/.test(part.d),'expected an original SVG path');
  }
 }
});
test('vascular circuits have eight distinct generic study networks and no personal data',()=>{
 const vessels=atlas.regionsFor('vessels','neutral');
 assert.equal(vessels.length,8);
 for(const part of vessels)assert.match(part.detail,/^(?!.*fotografata.*ricostruita)/i);
 assert.ok(vessels.find(p=>p.id==='aorta'));
 assert.ok(vessels.find(p=>p.id==='vena_cava'));
});
test('focus navigation includes both classic and more detailed anatomy in each zone',()=>{
 const faces=focus.focusedRegions('face','bones','neutral');
 assert.ok(faces.some(p=>p.id==='mandible'));
 const thorax=focus.focusedRegions('torso','organs','neutral');
 assert.ok(thorax.some(p=>p.id==='trachea'));
 const abdomen=focus.focusedRegions('abdomen','organs','neutral');
 assert.ok(abdomen.some(p=>p.id==='pancreas'));
 const legs=focus.focusedRegions('leg','muscles','neutral');
 assert.ok(legs.some(p=>p.id==='tibialis'));
 for(const zone of ['face','hand','arm','torso','abdomen','leg']){
  assert.ok(focus.focusedRegions(zone,'vessels','neutral').length>0,zone+' lacks vessel context');
 }
});
test('sex-related variation is manual, never guessed from the photographed person',()=>{
 const neutral=atlas.regionsFor('reproductive','neutral');
 assert.ok(!neutral.some(p=>p.id==='uterus'||p.id==='testes'));
 assert.ok(atlas.regionsFor('reproductive','female').some(p=>p.id==='uterus'));
 assert.ok(atlas.regionsFor('reproductive','male').some(p=>p.id==='testes'));
});
