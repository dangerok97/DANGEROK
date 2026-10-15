import fs from 'node:fs';
import path from 'node:path';

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

const positions=[];
const normals=[];
const indices=[];
let vertexBase=0;
for(const p of parts){
  const raw=chunkBuffer(p.chunk);
  const pos=new Float32Array(raw.buffer,raw.byteOffset+p.positions,p.vertexCount*3);
  const nor=new Int16Array(raw.buffer,raw.byteOffset+p.normals,p.vertexCount*3);
  const idx=new Uint32Array(raw.buffer,raw.byteOffset+p.indices,p.indexCount);
  for(let i=0;i<p.vertexCount;i++){
    const x=(pos[i*3]-center[0])*scale;
    const y=(pos[i*3+1]-center[1])*scale;
    const z=(pos[i*3+2]-center[2])*scale;
    positions.push(
      Math.max(-32767,Math.min(32767,Math.round(x*32767))),
      Math.max(-32767,Math.min(32767,Math.round(y*32767))),
      Math.max(-32767,Math.min(32767,Math.round(z*32767)))
    );
    const nx=nor[i*3]/32767,ny=nor[i*3+1]/32767,nz=nor[i*3+2]/32767;
    const length=Math.hypot(nx,ny,nz)||1;
    normals.push(
      Math.max(-127,Math.min(127,Math.round(nx/length*127))),
      Math.max(-127,Math.min(127,Math.round(ny/length*127))),
      Math.max(-127,Math.min(127,Math.round(nz/length*127)))
    );
  }
  for(const n of idx) indices.push(vertexBase+n);
  vertexBase+=p.vertexCount;
}
if(vertexBase>=65535) throw new Error('brain asset exceeded uint16 vertex budget: '+vertexBase);
if(indices.some(n=>n>=65535)) throw new Error('brain index overflow');

const posBuf=Buffer.from(new Int16Array(positions).buffer);
const normalBuf=Buffer.from(new Int8Array(normals).buffer);
const indexBuf=Buffer.from(new Uint16Array(indices).buffer);
const asset={
  source:'BodyParts3D 4.0',
  sourceCommit:'1c38bf35c254a891200d3cedecfd57abebe83d8d',
  license:'CC BY 4.0',
  concept:'brain surface for ORA presence',
  partCount:parts.length,
  vertexCount:vertexBase,
  indexCount:indices.length,
  triangleCount:indices.length/3,
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
