import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
import vm from 'node:vm';
const src=readFileSync(new URL('./objectPage.ts',import.meta.url),'utf8');
const js=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const module={exports:{}};vm.runInNewContext(js,{module,exports:module.exports});
const {objectPage,OBJECT_PARTS_PER_PAGE}=module.exports;
test('large exploded object paginates without losing or duplicating an original component',()=>{
 const parts=Array.from({length:17},(_,i)=>({key:'part_'+i}));
 const batches=Array.from({length:Math.ceil(parts.length/OBJECT_PARTS_PER_PAGE)},(_,i)=>objectPage(parts,i));
 assert.deepEqual([...batches.flatMap(b=>b.keys)],parts.map(x=>x.key));
 assert.equal(batches[0].from,0);assert.equal(batches[0].to,6);
 assert.equal(batches[2].to,17);assert.equal(batches[0].pages,3);
});
test('small models stay on one page; clamp out of range values',()=>{
 const parts=[{key:'a'},{key:'b'},{key:'c'}];
 assert.deepEqual(Array.from(objectPage(parts,-50).keys),parts.map(p=>p.key));
 assert.equal(objectPage(parts,100).page,0);
 assert.equal(objectPage([],0).keys.length,0);
 assert.equal(objectPage(parts,NaN).page,0);
});
test('pagination cannot change versioned source order',()=>{
 const parts=Array.from({length:13},(_,i)=>({key:'k'+i}));
 const original=JSON.stringify(parts);
 assert.equal(objectPage(parts,1).keys[0],'k6');
 assert.equal(JSON.stringify(parts),original);
});
