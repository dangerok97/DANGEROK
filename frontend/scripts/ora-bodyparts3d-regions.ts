/** Semantic + bounded spatial selection for a generic BodyParts3D reference.
 * We never cut, invent, rescale or identify geometry belonging to a photographed
 * person: only source mesh IDs are shown/hidden. Original FMA IDs are preserved.
 */
import type {Atlas,Part,Concept} from './anatomy';

export type StudyRegion='full_body'|'face'|'hand'|'wrist'|'forearm'|'arm'|'elbow'|'shoulder'|
 'neck'|'torso'|'abdomen'|'back'|'pelvis'|'leg'|'knee'|'foot';
export type ModelSide='left'|'right'|'unknown';
export const STUDY_LABEL:Record<StudyRegion,string>={
 full_body:'Corpo intero',face:'Testa e volto',hand:'Mano',wrist:'Polso',
 forearm:'Avambraccio',arm:'Braccio',elbow:'Gomito',shoulder:'Spalla',
 neck:'Collo',torso:'Torace',abdomen:'Addome',back:'Schiena',pelvis:'Bacino',
 leg:'Gamba',knee:'Ginocchio',foot:'Piede'
};
export const FOLLOW_UP:Partial<Record<StudyRegion,StudyRegion>>={
 hand:'arm',wrist:'arm',elbow:'arm',forearm:'arm',shoulder:'arm',arm:'full_body',
 foot:'leg',knee:'leg',leg:'full_body',face:'full_body',neck:'torso',
 torso:'full_body',abdomen:'torso',pelvis:'full_body',back:'full_body'
};
const SPEC:Record<Exclude<StudyRegion,'full_body'>,{name:string[];factors:[number,number];location:[number,number,number,number];min:number}>={
 // location = normalized [x0,x1,y0,y1], relative to full skeletal extents.
 // These are conservative fallbacks only if FMA concepts have no usable anchors.
 face:{name:['head','skull','cranium','face'],factors:[.10,.12],location:[.30,.70,.81,1],min:5},
 hand:{name:['hand','metacarpus','palm','carpus'],factors:[.15,.18],location:[.0,.32,.36,.63],min:8},
 wrist:{name:['wrist','carpus'],factors:[.15,.18],location:[.0,.32,.47,.69],min:4},
 forearm:{name:['forearm','antebrachium'],factors:[.14,.10],location:[.0,.36,.52,.78],min:8},
 arm:{name:['upper limb','arm','brachium'],factors:[.10,.08],location:[.0,.42,.43,.86],min:12},
 elbow:{name:['elbow','cubital region'],factors:[.18,.21],location:[.06,.43,.62,.79],min:4},
 shoulder:{name:['shoulder','pectoral girdle'],factors:[.18,.16],location:[.1,.48,.75,.89],min:5},
 neck:{name:['neck','cervical region'],factors:[.15,.17],location:[.32,.68,.74,.91],min:4},
 torso:{name:['thorax','thoracic region','chest','rib cage'],factors:[.06,.08],location:[.24,.76,.52,.83],min:10},
 abdomen:{name:['abdomen','abdominal region','abdominal cavity'],factors:[.09,.10],location:[.27,.73,.38,.63],min:8},
 back:{name:['back','dorsum of trunk'],factors:[.08,.12],location:[.24,.76,.47,.85],min:8},
 pelvis:{name:['pelvis','pelvic region'],factors:[.09,.12],location:[.26,.74,.37,.58],min:8},
 leg:{name:['lower limb','leg','thigh'],factors:[.08,.10],location:[.25,.49,.07,.58],min:10},
 knee:{name:['knee','patella'],factors:[.20,.24],location:[.28,.50,.30,.45],min:5},
 foot:{name:['foot','tarsus'],factors:[.15,.22],location:[.22,.48,0,.16],min:8}
};
type Bounds=[number,number,number,number,number,number];
const clean=(s:string)=>s.toLowerCase().trim().replace(/[^a-z0-9 ]+/g,' ').replace(/\s+/g,' ');
const bounds=(parts:Part[]):Bounds=>{
 let x0=Infinity,x1=-Infinity,y0=Infinity,y1=-Infinity,z0=Infinity,z1=-Infinity;
 for(const part of parts){
  const b=part.bounds;if(!b||b.length!==2||b.some(v=>v.length!==3||v.some(n=>!Number.isFinite(n))))continue;
  x0=Math.min(x0,b[0][0]);x1=Math.max(x1,b[1][0]);
  y0=Math.min(y0,b[0][1]);y1=Math.max(y1,b[1][1]);
  z0=Math.min(z0,b[0][2]);z1=Math.max(z1,b[1][2]);
 }
 return Number.isFinite(x0)?[x0,x1,y0,y1,z0,z1]:[0,1,0,1,0,1];
};
const area=(b:Bounds)=>(b[1]-b[0])*(b[3]-b[2]);
const volume=(b:Bounds)=>(b[1]-b[0])*(b[3]-b[2])*(b[5]-b[4]);
const center=(p:Part)=>[(p.bounds[0][0]+p.bounds[1][0])/2,(p.bounds[0][1]+p.bounds[1][1])/2,(p.bounds[0][2]+p.bounds[1][2])/2] as const;
const normalizedROI=(full:Bounds,loc:[number,number,number,number]):Bounds=>[
 full[0]+(full[1]-full[0])*loc[0],full[0]+(full[1]-full[0])*loc[1],
 full[2]+(full[3]-full[2])*loc[2],full[2]+(full[3]-full[2])*loc[3],
 full[4],full[5]
];
const within=(p:Part,region:Bounds)=>{const c=center(p);
 return c[0]>=region[0]&&c[0]<=region[1]&&
  c[1]>=region[2]&&c[1]<=region[3]&&
  c[2]>=region[4]&&c[2]<=region[5];
};
const extend=(local:Bounds,full:Bounds,xFactor:number,yFactor:number):Bounds=>{
 const x=Math.max((local[1]-local[0])*xFactor,(full[1]-full[0])*.009);
 const y=Math.max((local[3]-local[2])*yFactor,(full[3]-full[2])*.013);
 const z=Math.max((local[5]-local[4])*.20,(full[5]-full[4])*.025);
 return [local[0]-x,local[1]+x,local[2]-y,local[3]+y,local[4]-z,local[5]+z];
};
const isSided=(region:StudyRegion)=>['hand','wrist','forearm','arm','elbow','shoulder','leg','knee','foot'].includes(region);
function conceptAnchor(atlas:Atlas,region:Exclude<StudyRegion,'full_body'>,side:ModelSide,full:Bounds):Part[] {
 const choices=SPEC[region].name;
 const partById=new Map(atlas.parts.map(p=>[p.id,p]));
 const concepts=atlas.concepts.filter(c=>{
  const name=clean(c.originalName||c.name);
  return choices.some(word=>name===word||name===side+' '+word||name===word+' of '+side+' side');
 });
 // Prefer the precise source concept (e.g. right hand) to whole-limb parent groups.
 concepts.sort((a,b)=>{
  const score=(c:Concept)=>{
   const n=clean(c.originalName||c.name);
   return (isSided(region)&&n.startsWith((side==='unknown'?'right':side)+' ')?0:2)+
     (choices.findIndex(name=>n.includes(name))+1)/10;
  };
  return score(a)-score(b);
 });
 for(const concept of concepts){
  const parts=concept.elements.map(id=>partById.get(id)).filter((p):p is Part=>!!p);
  if(parts.length===0)continue;
  const b=bounds(parts);
  // Reject a parent whose bounds include most of the entire adult reference.
  if((b[3]-b[2])/(full[3]-full[2])>.76&&region!=='leg'&&region!=='arm')continue;
  if(area(b)>area(full)*.8)continue;
  return parts;
 }
 const sideName=side==='unknown'?'right':side;
 const named=atlas.parts.filter(part=>{
  const name=clean(part.originalName||part.name);
  return choices.some(word=>name.includes(word))&&
   (!isSided(region)||name.includes(sideName)||!/(?:^| )left |(?:^| )right /.test(name));
 });
 return named.length>0&&named.length<500?named:[];
}
export type RegionSubset={
 region:StudyRegion;side:ModelSide;ids:string[];bounds:Bounds;label:string;
 source:'source-concept'|'fallback';available:boolean;
};
/** Return ONLY source mesh IDs in the detected body part, not the whole body. */
export function anatomicalRegion(atlas:Atlas,requested:StudyRegion,side:ModelSide='unknown'):RegionSubset{
 const region=requested in STUDY_LABEL?requested:'full_body';
 const all=atlas.parts;
 if(region==='full_body'){
  return {region,side,ids:all.map(p=>p.id),bounds:bounds(all),label:STUDY_LABEL[region],
   source:'source-concept',available:all.length>0};
 }
 const full=bounds(all);
 const spec=SPEC[region];
 const preferredSide=side==='unknown'?'right':side;
 const seed=conceptAnchor(atlas,region,preferredSide,full);
 let roi:Bounds,source:'source-concept'|'fallback';
 const expected=normalizedROI(full,spec.location);
 const seedBox=seed.length?bounds(seed):null;
 const local=seedBox?extend(seedBox,full,...spec.factors):null;
 const expectedWidth=(expected[1]-expected[0]),expectedHeight=(expected[3]-expected[2]);
 const localEnough=local&&
   (local[1]-local[0])<expectedWidth*1.27&&
   (local[3]-local[2])<expectedHeight*1.27;
 if(localEnough&&local){
  roi=local;
  source='source-concept';
 } else {
  roi=normalizedROI(full,spec.location);
  if(isSided(region)&&preferredSide==='left'){
   const centerX=(full[0]+full[1])/2;
   roi=[2*centerX-roi[1],2*centerX-roi[0],roi[2],roi[3],roi[4],roi[5]];
  }
  source='fallback';
 }
 // A spatial bounding box cannot identify laterality. If a mesh is
 // explicitly labelled for the opposite side, NEVER include it, even if
 // its bounds overlap the selected hand or limb.
 const contralateral=(p:Part):boolean=>{
  if(!isSided(region))return false;
  const sourceName=clean(p.originalName||p.name);
  return preferredSide==='right'?/(?:^| )left(?: |$)/.test(sourceName):
   /(?:^| )right(?: |$)/.test(sourceName);
 };
 // Center-in-volume test avoids keeping huge unrelated body structures.
 const candidates=(area:Bounds)=>{
  const spatial=all.filter(p=>{
   if(contralateral(p))return false;
   const b=p.bounds,spanY=b[1][1]-b[0][1],spanX=b[1][0]-b[0][0];
   // Avoid huge whole-body surfaces and structures spanning multiple limbs.
   if(spanY>(area[3]-area[2])*1.70||spanX>(area[1]-area[0])*2.5)return false;
   return within(p,area);
  });
  return Array.from(new Set([...seed.filter(p=>within(p,area)&&!contralateral(p)).map(p=>p.id),
   ...spatial.map(p=>p.id)]));
 };
 let ids=candidates(roi);
 // A source concept such as 'knee' may be only the patella itself. Expand to
 // its actual body region, never to the entire body, for useful local context.
 if(ids.length<spec.min&&source==='source-concept'){
  const backup=normalizedROI(full,spec.location);
  if(isSided(region)&&preferredSide==='left'){
   const mid=(full[0]+full[1])/2;
   backup[0]=2*mid-expected[1];backup[1]=2*mid-expected[0];
  }
  const alternate=candidates(backup);
  if(alternate.length>ids.length){ids=alternate;roi=backup;source='fallback';}
 }
 // Fail closed (never silently replace a hand with the full body).
 const available=ids.length>=spec.min&&ids.length<all.length*.87;
 return {region,side,ids:available?ids:[],bounds:roi,label:STUDY_LABEL[region],
  source,available};
}
export function expansion(region:StudyRegion):StudyRegion{return FOLLOW_UP[region]||'full_body';}
