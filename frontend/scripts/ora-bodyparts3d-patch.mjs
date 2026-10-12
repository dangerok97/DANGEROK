/** Deterministic adaptation of pinned BodyParts3D. No changes to geometry or ids. */
import {readFileSync,writeFileSync,copyFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
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
 ['ora-bodyparts3d-locale-it.ts','app/ora-locale-it.ts']
])copyFileSync(join(source,from),join(root,to));

let anatomy=read('app/anatomy.ts');
anatomy=once(anatomy,'export interface Part {id:string;name:string;conceptId:string;',
 'export interface Part {id:string;name:string;originalName?:string;conceptId:string;');
anatomy=once(anatomy,'export interface Concept {id:string;name:string;elements:string[]}',
 'export interface Concept {id:string;name:string;originalName?:string;elements:string[]}');
anatomy="import {SISTEMI_IT,SPIEGAZIONI_IT} from './ora-locale-it';\n"+anatomy;
anatomy+="\nfor(const system of SYSTEMS){const it=SISTEMI_IT[system.id];if(!it)throw Error('Lingua italiana mancante');system.name=it.name;system.description=it.description;}\nObject.assign(EXPLANATIONS,SPIEGAZIONI_IT);\n";
save('app/anatomy.ts',anatomy);

let scene=read('app/scene.tsx');
scene=once(scene,'export default function AnatomyScene({atlas,state,onSelect,onProgress,onError}:Props){',
 "export default function AnatomyScene({atlas,state,onSelect,onProgress,onError}:Props){\n const oraInline=new URLSearchParams(window.location.search).get('ora')==='inline';");
scene=once(scene,"new T.WebGLRenderer({antialias:true,alpha:false,powerPreference:'high-performance'})",
 "new T.WebGLRenderer({antialias:true,alpha:oraInline,powerPreference:'high-performance'})");
scene=once(scene,"renderer.setClearColor('#f2f3f3');",
 "renderer.setClearColor(oraInline?'#000000':'#f2f3f3',oraInline?0:1);");
scene=once(scene,'ground.visible=platform.visible=ring.visible=innerRing.visible=amount<.5&&!s.isolate;',
 'ground.visible=platform.visible=ring.visible=innerRing.visible=amount<.5&&!s.isolate&&!oraInline;');
scene=scene.replace('Interactive human anatomy. Drag to orbit, pinch or scroll to zoom, and tap a structure to inspect it.',
 'Anatomia 3D: trascina per ruotare, pizzica per ingrandire e tocca una parte per selezionarla.');
scene=scene.replace('The 3D session was paused by your device. Reload to continue.',
 'La sessione 3D è stata interrotta dal dispositivo. Riaprila per continuare.');
scene=scene.replace('This browser could not start the 3D viewer. Please try a browser with WebGL enabled.',
 'Questo browser non riesce ad avviare la visualizzazione 3D. Usa un browser con WebGL.');
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
