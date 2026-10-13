/** Deterministic adaptation of pinned BodyParts3D. No changes to geometry or ids. */
import {readFileSync,writeFileSync,copyFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {applyOraBlueprint} from './ora-bodyparts3d-blueprint.mjs';
const root=resolve(process.argv[2]||'.'),source=resolve(process.argv[3]||'.');
const read=file=>readFileSync(join(root,file),'utf8');
const save=(file,body)=>writeFileSync(join(root,file),body);
const once=(body,from,to)=>{
 if(!body.includes(from))throw new Error('Pinned BodyParts3D source changed: '+from.slice(0,90));
 return body.replace(from,to);
};
for(const [from,to] of [
 ['ora-bodyparts3d-inline.tsx','app/ora-overlay.tsx'],
 ['ora-bodyparts3d-inline.css','app/ora-overlay.css'],
 ['ora-bodyparts3d-locale-it.ts','app/ora-locale-it.ts'],
 ['ora-bodyparts3d-regions.ts','app/ora-regions.ts'],
 ['ora-anatomy-terminology-it.ts','app/ora-anatomy-terminology-it.ts']
])copyFileSync(join(source,from),join(root,to));

let anatomy=read('app/anatomy.ts');
anatomy=once(anatomy,'export interface Part {id:string;name:string;conceptId:string;',
 'export interface Part {id:string;name:string;originalName?:string;conceptId:string;');
anatomy=once(anatomy,'export interface Concept {id:string;name:string;elements:string[]}',
 'export interface Concept {id:string;name:string;originalName?:string;elements:string[]}');
anatomy=once(anatomy,
 'export interface Part {id:string;name:string;originalName?:string;conceptId:string;',
 'export interface Part {id:string;name:string;originalName?:string;translationReviewed?:boolean;conceptId:string;');
anatomy=once(anatomy,
 'export interface Concept {id:string;name:string;originalName?:string;elements:string[]}',
 'export interface Concept {id:string;name:string;originalName?:string;translationReviewed?:boolean;elements:string[]}');
anatomy=once(anatomy,'export interface SceneState {inspectorOpen?:boolean;explode:number;',
 'export interface SceneState {inspectorOpen?:boolean;allowed?:string[]|null;detailZoom?:number;explode:number;');
anatomy="import {SISTEMI_IT,SPIEGAZIONI_IT} from './ora-locale-it';\n"+anatomy;
anatomy+="\nconst ORA_SYSTEM_BLUE:Record<string,string>={skeletal:'#b9e7f6',muscular:'#83c7df',arterial:'#7fcde8',venous:'#77bddc',nervous:'#a6e3f0',digestive:'#8ac6dd',respiratory:'#8ed5e8',urinary:'#88c9e2',cardiac:'#8fc9dd',sensory:'#acddea',endocrine:'#8ec9de',lymphatic:'#8bd1e5',integumentary:'#93c4d3',connective:'#a0cfdf',reproductive:'#8ac5da'};\nfor(const system of SYSTEMS){const it=SISTEMI_IT[system.id];if(!it)throw Error('Lingua italiana mancante');system.name=it.name;system.description=it.description;system.color=ORA_SYSTEM_BLUE[system.id]||'#81cfe9';}\nObject.assign(EXPLANATIONS,SPIEGAZIONI_IT);\n";
save('app/anatomy.ts',anatomy);

let scene=read('app/scene.tsx');
scene=once(scene,'export default function AnatomyScene({atlas,state,onSelect,onProgress,onError}:Props){',
 "export default function AnatomyScene({atlas,state,onSelect,onProgress,onError}:Props){\n const oraInline=new URLSearchParams(window.location.search).get('ora')==='inline';");
scene=once(scene,"new T.WebGLRenderer({antialias:true,alpha:false,powerPreference:'high-performance'})",
 "new T.WebGLRenderer({antialias:true,alpha:oraInline,powerPreference:'high-performance'})");
scene=once(scene,"renderer.setClearColor('#f2f3f3');",
 "renderer.setClearColor(oraInline?'#000000':'#f2f3f3',oraInline?0:1);");
scene=once(scene,"const changed=lastState?.visible!==s.visible||lastState?.selected!==s.selected||lastState?.isolate!==s.isolate;","const changed=lastState?.visible!==s.visible||lastState?.selected!==s.selected||lastState?.isolate!==s.isolate||lastState?.allowed!==s.allowed;");
scene=once(scene,"const visible=new Set(s.visible),selection=new Set(s.selected);","const visible=new Set(s.visible),selection=new Set(s.selected),permitted=s.allowed?new Set(s.allowed):null;");
scene=once(scene,"const visibleParts=atlas.parts.filter(p=>s.isolate?selection.has(p.id):visible.has(p.system)||selection.has(p.id));","const visibleParts=atlas.parts.filter(p=>(!permitted||permitted.has(p.id))&&(s.isolate?selection.has(p.id):visible.has(p.system)||selection.has(p.id)));");
scene=once(scene,"(s.isolate?selected:visible.has(p.system)||selected)?1:0","(!permitted||permitted.has(p.id))&&(s.isolate?selected:visible.has(p.system)||selected)?1:0");
scene=once(scene,"const fit=(view:string,extent=0)=>{","const fit=(view:string,extent=0)=>{\n   const selectedRegion=latest.current.allowed;\n   if(selectedRegion?.length&&extent<.4&&!latest.current.isolate){\n    const regionIds=new Set(selectedRegion),area=new T.Box3();\n    const shownSystems=new Set(latest.current.visible);\n    atlas.parts.forEach((part,i)=>{if(regionIds.has(part.id)&&shownSystems.has(part.system))area.union(bounds[i]);});\n    if(area.isEmpty())atlas.parts.forEach((part,i)=>{if(regionIds.has(part.id))area.union(bounds[i]);});\n    if(!area.isEmpty()){\n     const c=area.getCenter(new T.Vector3()),dim=area.getSize(new T.Vector3());\n     const w=Math.max(1,el.clientWidth),h=Math.max(1,el.clientHeight);\n     const useW=Math.max(125,w*(w<670?.75:.84)),useH=Math.max(140,h*(h<700?.50:.61));\n     const fov=2*Math.tan(T.MathUtils.degToRad(camera.fov/2));\n     const distance=Math.max(.12,dim.y*h/(useH*fov),dim.x*w/(useW*fov*camera.aspect),dim.z*2.0)*1.30;\n     const direction=view==='back'?new T.Vector3(0,.02,-1):\n       view==='side'?new T.Vector3(1,.02,0):\n       view==='three-quarter'?new T.Vector3(.3,.03,1).normalize():\n       new T.Vector3(0,.02,1);\n     camera.clearViewOffset();controls.target.copy(c);\n     camera.position.copy(c).addScaledVector(direction,distance);\n     controls.update();dirty=true;return;\n    }\n   }");
scene=once(scene,'ground.visible=platform.visible=ring.visible=innerRing.visible=amount<.5&&!s.isolate;',
 'ground.visible=platform.visible=ring.visible=innerRing.visible=amount<.5&&!s.isolate&&!oraInline;');
scene=scene.replace('Interactive human anatomy. Drag to orbit, pinch or scroll to zoom, and tap a structure to inspect it.',
 'Anatomia 3D: trascina per ruotare, pizzica per ingrandire e tocca una parte per selezionarla.');
scene=scene.replace('The 3D session was paused by your device. Reload to continue.',
 'La sessione 3D è stata interrotta dal dispositivo. Riaprila per continuare.');
scene=scene.replace('This browser could not start the 3D viewer. Please try a browser with WebGL enabled.',
 'Questo browser non riesce ad avviare la visualizzazione 3D. Usa un browser con WebGL.');
scene=once(scene,"const distance=T.MathUtils.lerp(normalDistance,Math.max(.2,atlasDistance),extent);if(extent>.8)view='front';","const distance=T.MathUtils.lerp(normalDistance,Math.max(.2,atlasDistance),extent)*(oraInline&&extent>.4?.82:1);if(extent>.8)view='front';");
scene=once(scene,"const isolateKey=s.isolate?s.selected.join(',')+':'+s.reset+':'+s.inspectorOpen+':'+camera.aspect:'';","const isolateKey=s.isolate?s.selected.join(',')+':'+s.reset+':'+s.inspectorOpen+':'+camera.aspect+':'+(s.detailZoom||1):'';");
scene=once(scene,"if(s.inspectorOpen){if(landscape){right=w-335;top=100;bottom=h-125;}","if(oraInline){left=15;right=w>900?w-365:w-15;top=w<768?95:110;bottom=h-(w<768?220:100);}\n     else if(s.inspectorOpen){if(landscape){right=w-335;top=100;bottom=h-125;}");
scene=once(scene,"const distance=Math.max(.07,Math.max(size.y*h/availableHeight,size.x*w/availableWidth/camera.aspect,size.z)/(2*Math.tan(T.MathUtils.degToRad(camera.fov/2)))*1.35);","const distance=Math.max(.07,Math.max(size.y*h/availableHeight,size.x*w/availableWidth/camera.aspect,size.z)/(2*Math.tan(T.MathUtils.degToRad(camera.fov/2)))*1.35)/(oraInline?Math.max(1,Math.min(3,s.detailZoom||1)):1);");
scene=applyOraBlueprint(scene);
save('app/scene.tsx',scene);

let page=read('app/page.tsx');
page="import OraOverlay from './ora-overlay';\nimport {italianAtlas} from './ora-locale-it';\n"+page;
page=once(page,'export default function Home(){','function FullAtlas(){');
page=once(page,'.then(data=>setAtlas(data as Atlas))','.then(data=>setAtlas(italianAtlas(data as Atlas)))');
page=once(page,"['heart','brain','liver','stomach','spleen','pancreas','urinary bladder','trachea']",
 "['cuore','encefalo','fegato','stomaco','milza','pancreas','vescica urinaria','trachea']");
page=once(page,'c.name.toLowerCase().includes(term)||c.id.toLowerCase().includes(term)',
 'c.name.toLowerCase().includes(term)||c.originalName?.toLowerCase().includes(term)||c.id.toLowerCase().includes(term)');
const words=[
 ['INTERACTIVE ANATOMY','ANATOMIA INTERATTIVA'],['Human Atlas','Atlante umano'],
 ['modeled pieces','componenti anatomici'],['Find a structure','Cerca una struttura'],
 ['Search anatomy','Cerca strutture anatomiche'],['About this atlas','Informazioni sull’atlante'],
 ['Anatomical layers','Sistemi anatomici'],['Close systems','Chiudi sistemi'],
 ['Systems','Sistemi'],['Skeleton','Scheletro'],['Organs','Organi'],
 ['Hide all','Nascondi tutto'],['pieces visible','parti visibili'],
 ['Find anatomy','Cerca nell’atlante'],['Close search','Chiudi ricerca'],
 ['Heart, femur, cranial nerve…','Cuore, femore, nervo cranico…'],
 ['No structures match your search.','Nessuna struttura trovata.'],
 ['Showing up to 80 matches. Refine your search to find smaller structures.','Fino a 80 risultati: specifica meglio il nome per trovare strutture più piccole.'],
 ['Start with a major organ, or search every named structure.','Parti da un organo oppure cerca qualsiasi struttura anatomica.'],
 ['Camera controls','Comandi visuale'],['three-quarter view','Visuale tre quarti'],
 ['front view','Visuale anteriore'],['side view','Visuale laterale'],['back view','Visuale posteriore'],
 ['Pause rotation','Ferma rotazione'],['Rotate body','Ruota il modello'],
 ['Reset view and layers','Ripristina visuale e livelli'],
 ['SELECTED STRUCTURE','STRUTTURA SELEZIONATA'],['ANATOMICAL INVENTORY','COMPONENTI ANATOMICI'],
 ['SEPARATED STRUCTURES','STRUTTURE SEPARATE'],['ADULT HUMAN · MALE','ADULTO MASCHILE · MODELLO'],
 ['Explode anatomy','Scomponi il corpo'],['Assembled','Ricomposto'],
 ['Every piece','Tutte le parti'],['Reset','Ripristina'],
 ['Drag to pan','Trascina per spostare'],['Drag to orbit','Trascina per ruotare'],
 ['Pinch to zoom','Due dita per ingrandire'],['Tap to inspect','Tocca per esplorare'],
 ['Source & credits','Fonti e crediti'],['Preparing the anatomy','Preparo l’anatomia'],
 ['Loading','Carico'],['Reload viewer','Ricarica modello'],
 ['ANATOMY','ANATOMIA'],['System overview · structure identified from source anatomy','Descrizione generale: struttura ricavata dall’atlante di riferimento'],
 ['Atlas reference','Riferimento atlante'],['Selected pieces','Parti selezionate'],
 ['Included structures','Strutture comprese'],[' more modeled pieces.',' altre parti anatomiche.'],
 ['View anatomical source','Consulta la fonte anatomica'],
 ['Show surrounding anatomy','Mostra strutture vicine'],['Isolate structure','Isola struttura'],
 ['Clear selection','Cancella selezione'],['SOURCE & SCOPE','FONTE E AMBITO'],
 ['A body, revealed.','Il corpo umano in 3D'],
 ['Explore the adult male reference anatomy from BodyParts3D.','Esplora il riferimento anatomico maschile adulto BodyParts3D.'],
 ['2,234 individual meshes and 3,432 named concepts from an adult male reference anatomy.','2.234 mesh individuali e 3.432 concetti dell’atlante maschile adulto di riferimento.'],
 ['This reference does not contain every human structure or variation. Named concepts can contain multiple pieces; each source mesh is rendered once.','Questo riferimento non comprende tutte le possibili strutture o varianti. Un concetto può raggruppare più mesh.'],
 ['Colors and system groupings are designed for exploration. The geometry is simplified for the web, and short explanations provide general educational context. This is an anatomical reference, not a diagnostic or surgical tool.','Colori e sistemi servono allo studio. La geometria è ottimizzata per il web: non è uno strumento diagnostico né chirurgico.'],
 ['Dataset license','Licenza del dataset'],['Original geometry & metadata','Geometrie e metadati originali'],
 ['Read the source publication','Leggi la pubblicazione scientifica'],
 ['2,234','2.234'],['3,432','3.432'],
 ["'piece':'pieces'","'parte':'parti'"]
];
for(const [from,to] of words)page=page.replaceAll(from,to);
page+="\nexport default function Home(){const overlay=new URLSearchParams(window.location.search).get('ora')==='inline';return overlay?<OraOverlay/>:<FullAtlas/>;}\n";
save('app/page.tsx',page);
let html=read('web/index.html');
html=html.replace('lang="en"','lang="it"')
 .replace('content="An interactive atlas of the human body. Explore named anatomical structures, reveal organ systems, and inspect individual parts in 3D."','content="Atlante anatomico BodyParts3D in italiano: esplora organi, muscoli e ossa in 3D."')
 .replace('<title>Human Atlas</title>','<title>ORA · Anatomia 3D</title>');
save('web/index.html',html);
console.log('ORA BodyParts3D: interfaccia italiana e modello inline trasparente installati.');
