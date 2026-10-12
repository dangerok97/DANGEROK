/** Educational focus framing over original atlas geometry (never body measurements). */
import {regionsFor, type AtlasLayer, type AnatomyRegion, type AnatomyVariant} from './anatomyAtlas';
export type BodyRegion = 'full_body'|'face'|'hand'|'arm'|'torso'|'abdomen'|'leg';
export const BODY_LABEL:Record<BodyRegion,string>={
 full_body:'CORPO UMANO',face:'TESTA E VOLTO',hand:'MANO E POLSO',
 arm:'ARTO SUPERIORE',torso:'TORACE',abdomen:'ADDOME E BACINO',leg:'ARTO INFERIORE'};
const VIEWS:Record<BodyRegion,string>={
 full_body:'0 10 320 586',face:'112 19 96 102',hand:'32 340 78 130',
 arm:'50 125 90 320',torso:'110 115 101 250',abdomen:'112 205 96 167',leg:'112 310 100 270'};
const FILTER:Partial<Record<BodyRegion,Partial<Record<AtlasLayer,string[]>>>>={
 face:{skin:['epidermis'],muscles:['mimetic_muscles'],nerves:['brain','facial_nerve'],
       organs:['eyes'],bones:['skull']},
 hand:{skin:['hand_skin'],muscles:['hand_tendons'],nerves:['median_nerve'],
       organs:['hand_vessels'],bones:['finger_bones','carpal_bones']},
 arm:{skin:['arm_skin'],muscles:['shoulder','biceps','forearm'],nerves:['brachial','radial'],
      organs:['arm_artery'],bones:['humerus','forearm_bones']},
 torso:{skin:['torso_skin'],muscles:['pectorals','abdominals'],nerves:['spinal'],
       organs:['lungs','heart','liver','stomach','kidneys'],bones:['ribs','spine']},
 abdomen:{skin:['torso_skin'],muscles:['abdominals'],nerves:['spinal'],
          organs:['stomach','liver','intestine','kidneys','bladder'],bones:['pelvis','spine']},
 leg:{skin:['leg_skin'],muscles:['quadriceps','calves'],nerves:['sciatic'],
      organs:['leg_artery'],bones:['femur','lower_leg']},
};
const extra=(id:string,label:string,detail:string,d:string):AnatomyRegion=>({id,label,detail,d});
const EXTRAS:Record<string,AnatomyRegion>={
 mimetic_muscles:extra('mimetic_muscles','Muscoli mimici',
 'I muscoli mimici partecipano alle espressioni del volto. La loro disposizione qui è semplificata.',
 'M141 64 Q160 75 179 64 L177 87 Q160 100 143 87 Z'),
 facial_nerve:extra('facial_nerve','Nervo facciale (VII)',
 'Il nervo facciale contribuisce al movimento dei muscoli del volto. Non è la mappa nervosa della persona inquadrata.',
 'M153 67 Q135 71 142 92 M167 67 Q185 71 178 92'),
 eyes:extra('eyes','Occhi',
 'Occhio, retina e nervo ottico trasformano la luce in segnali visivi. Il modello è didattico.',
 'M141 65 Q148 58 156 65 Q148 72 141 65 Z M164 65 Q172 58 179 65 Q172 72 164 65 Z'),
 hand_tendons:extra('hand_tendons','Tendini della mano',
 'I tendini trasmettono ai segmenti delle dita la forza dei muscoli dell’avambraccio.',
 'M61 386 Q61 413 50 438 M65 390 Q69 420 65 447 M70 395 Q77 420 76 432'),
 median_nerve:extra('median_nerve','Nervo mediano',
 'Attraversa il tunnel carpale ed è importante per sensibilità e controllo di parte della mano.',
 'M69 369 Q67 386 64 403 L59 434'),
 hand_vessels:extra('hand_vessels','Vasi sanguigni della mano',
 'Arterie, vene e capillari trasportano sangue nella mano. Posizione e calibro reali non sono ricavati dalla foto.',
 'M69 374 Q73 395 60 420 M69 397 Q78 410 76 427'),
 carpal_bones:extra('carpal_bones','Ossa carpali',
 'Le piccole ossa del carpo formano il polso e contribuiscono alla mobilità e stabilità della mano.',
 'M57 390 L76 396 72 410 54 407 Z'),
 finger_bones:extra('finger_bones','Falangi',
 'Le falangi sono segmenti ossei delle dita, con articolazioni che consentono presa e movimento.',
 'M53 407 L59 436 55 453 49 447 Z M63 408 L69 428 67 451 61 451 Z M73 406 L79 435 76 443 Z'),
 arm_artery:extra('arm_artery','Vasi del braccio',
 'Il sistema arterioso e venoso irrora i tessuti dell’arto superiore. La traiettoria disegnata è indicativa.',
 'M112 165 Q98 225 99 270 L72 386'),
 leg_artery:extra('leg_artery','Vasi della gamba',
 'Le arterie e le vene degli arti inferiori trasportano sangue da e verso i tessuti. Lo schema non è una mappatura personale.',
 'M140 347 Q132 428 136 469 L138 555 M180 347 Q190 428 183 469 L183 555')
};
export function viewFor(region:BodyRegion){return VIEWS[region];}
export function focusedRegions(region:BodyRegion,layer:AtlasLayer,variant:AnatomyVariant):AnatomyRegion[]{
 const original=regionsFor(layer,variant);
 if(region==='full_body')return original;
 // Reproductive organs appear only when the pelvic area is included in the view.
 if(layer==='reproductive' && !['abdomen','torso'].includes(region))return [];
 const ids=FILTER[region]?.[layer];
 if(!ids)return original.filter(p=>region==='abdomen' && layer==='reproductive' ? true:false);
 const found=ids.map(id=>original.find(p=>p.id===id)||EXTRAS[id]).filter((p):p is AnatomyRegion=>Boolean(p));
 if(layer==='reproductive')return original;
 return found;
}
export const BODY_REGIONS:Object=BODY_LABEL;
