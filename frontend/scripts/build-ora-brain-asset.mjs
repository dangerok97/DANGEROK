import fs from 'node:fs';
import path from 'node:path';
import {MeshoptSimplifier} from 'meshoptimizer';

const source=path.resolve(process.argv[2]||'');
const output=path.resolve(process.argv[3]||'');
if(!source||!output) throw new Error('usage: node build-ora-brain-asset.mjs <human-atlas-root> <output-js>');

const models=path.join(source,'public','models');
const atlas=JSON.parse(fs.readFileSync(path.join(models,'atlas.json'),'utf8'));
if(atlas.version!=='BodyParts3D 4.0') throw new Error('unexpected BodyParts3D version');

const byId=new Map(atlas.parts.map(p=>[p.id,p]));
const concept=name=>atlas.concepts.find(c=>String(c.name).toLowerCase()===name);
const left=concept('left cerebral hemisphere');
const right=concept('right cerebral hemisphere');
const cerebellum=concept('cerebellum');
const pons=concept('pons');
const medulla=concept('medulla oblongata');
if(!left||!right||!cerebellum||!pons||!medulla) throw new Error('brain concepts missing');

const corticalIds=[...left.elements,...right.elements];
const cortex=corticalIds.map(id=>byId.get(id)).filter(Boolean)
  .filter(p=>/(gyrus|lobe|lobule)$/i.test(p.name));
const support=[...cerebellum.elements,...pons.elements,...medulla.elements]
  .map(id=>byId.get(id)).filter(Boolean);
const parts=[...cortex,...support];
if(cortex.length<24||parts.length<30) throw new Error('brain surface selection unexpectedly small: '+parts.length);

const chunks=new Map();
const chunkBuffer=i=>{
  if(!chunks.has(i)){
    const file=atlas.chunks[i].url.split('/').pop();
    chunks.set(i,fs.readFileSync(path.join(models,file)));
  }
  return chunks.get(i);
};

const bounds=parts.reduce((acc,p)=>{
  for(let a=0;a<3;a++){
    acc[0][a]=Math.min(acc[0][a],p.bounds[0][a]);
    acc[1][a]=Math.max(acc[1][a],p.bounds[1][a]);
  }
  return acc;
},[[Infinity,Infinity,Infinity],[-Infinity,-Infinity,-Infinity]]);
const center=bounds[0].map((v,i)=>(v+bounds[1][i])/2);
const maxHalf=Math.max(...center.map((v,i)=>Math.max(Math.abs(bounds[0][i]-v),Math.abs(bounds[1][i]-v))));
const scale=.70/maxHalf;

const sourcePositions=[];
const sourceNormals=[];
const sourceIndices=[];
let vertexBase=0;
for(const p of parts){
  const raw=chunkBuffer(p.chunk);
  const pos=new Float32Array(raw.buffer,raw.byteOffset+p.positions,p.vertexCount*3);
  const nor=new Int16Array(raw.buffer,raw.byteOffset+p.normals,p.vertexCount*3);
  const idx=new Uint32Array(raw.buffer,raw.byteOffset+p.indices,p.indexCount);
  for(let i=0;i<p.vertexCount;i++){
    sourcePositions.push(
      (pos[i*3]-center[0])*scale,
      (pos[i*3+1]-center[1])*scale,
      (pos[i*3+2]-center[2])*scale
    );
    const nx=nor[i*3]/32767,ny=nor[i*3+1]/32767,nz=nor[i*3+2]/32767;
    const length=Math.hypot(nx,ny,nz)||1;
    sourceNormals.push(nx/length,ny/length,nz/length);
  }
  for(const n of idx) sourceIndices.push(vertexBase+n);
  vertexBase+=p.vertexCount;
}
await MeshoptSimplifier.ready;
const sourceIndexArray=Uint32Array.from(sourceIndices);
const sourcePositionArray=Float32Array.from(sourcePositions);
const target=Math.min(sourceIndexArray.length,60000);
const targetIndices=Math.floor(target/3)*3;
const [simplified,error]=MeshoptSimplifier.simplify(
  sourceIndexArray,sourcePositionArray,3,targetIndices,.0015
);
const [remap,compactCount]=MeshoptSimplifier.compactMesh(simplified);
if(compactCount>=65535) throw new Error('brain asset exceeded uint16 vertex budget: '+compactCount);
const compactPositions=new Float32Array(compactCount*3);
const compactNormals=new Float32Array(compactCount*3);
for(let oldIndex=0;oldIndex<remap.length;oldIndex++){
  const next=remap[oldIndex];
  if(next===0xffffffff) continue;
  compactPositions.set(sourcePositionArray.subarray(oldIndex*3,oldIndex*3+3),next*3);
  compactNormals.set(sourceNormals.slice(oldIndex*3,oldIndex*3+3),next*3);
}
const positions=new Int16Array(compactCount*3);
const normals=new Int8Array(compactCount*3);
for(let i=0;i<compactCount;i++){
  for(let a=0;a<3;a++) positions[i*3+a]=Math.max(-32767,Math.min(32767,Math.round(compactPositions[i*3+a]*32767)));
  const nx=compactNormals[i*3],ny=compactNormals[i*3+1],nz=compactNormals[i*3+2],length=Math.hypot(nx,ny,nz)||1;
  normals[i*3]=Math.round(nx/length*127);normals[i*3+1]=Math.round(ny/length*127);normals[i*3+2]=Math.round(nz/length*127);
}
const compactIndices=Uint16Array.from(simplified);
if([...compactIndices].some(n=>n>=compactCount)) throw new Error('brain compact index overflow');

const posBuf=Buffer.from(positions.buffer);
const normalBuf=Buffer.from(normals.buffer);
const indexBuf=Buffer.from(compactIndices.buffer);
const asset={
  source:'BodyParts3D 4.0',
  sourceCommit:'1c38bf35c254a891200d3cedecfd57abebe83d8d',
  license:'CC BY 4.0',
  concept:'brain surface for ORA presence',
  partCount:parts.length,
  vertexCount:compactCount,
  indexCount:compactIndices.length,
  triangleCount:compactIndices.length/3,
  sourceVertexCount:vertexBase,
  sourceTriangleCount:sourceIndices.length/3,
  simplificationError:error,
  positionEncoding:'int16-normalized',
  normalEncoding:'int8-normalized',
  indexEncoding:'uint16',
  positions:posBuf.toString('base64'),
  normals:normalBuf.toString('base64'),
  indices:indexBuf.toString('base64'),
  parts:parts.map(p=>({id:p.id,name:p.name}))
};
const js='/** Generated from pinned BodyParts3D 4.0. Do not hand edit. */\nexport const BRAIN_ASSET='+JSON.stringify(asset)+';\n';
fs.mkdirSync(path.dirname(output),{recursive:true});
fs.writeFileSync(output,js);
console.log(JSON.stringify({partCount:asset.partCount,vertexCount:asset.vertexCount,triangles:asset.triangleCount,bytes:posBuf.length+normalBuf.length+indexBuf.length}));
