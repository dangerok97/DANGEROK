/** Authored educational relationships for reviewed seed families only.
 * No model output is allowed to invent a tour or executable animation.
 * Sources support the general principle, not the internals of the user's unit.
 */
import type { Manifest } from './scene';
import { EXTRA_TOURS, EXTRA_TOUR_SHAPES } from './walkthroughLibrary';
export type TourSource = { title:string; url:string };
export type TourStep = {
  title:string; text:string; parts:readonly string[];
  links:readonly (readonly [string,string])[];
  effect:'energy'|'press'|'signal'|'spring'|'seal'|'sense'|'light'|'flow'|'rotation'|'material'|'sound'|'heat';
  sourceIndexes?:readonly number[];
};
export type Walkthrough = { key:string; title:string; sources:readonly TourSource[]; steps:readonly TourStep[]; note?:string };
const tours:Record<string,Walkthrough>={
  ...EXTRA_TOURS,
  remote_control:{key:'remote_control',title:'Da un tasto al segnale',sources:[
    {title:'Adafruit — segnali di un telecomando IR',url:'https://learn.adafruit.com/ir-sensor/using-an-ir-sensor'},
    {title:'Adafruit — comando di un emettitore IR',url:'https://learn.adafruit.com/internet-of-things-infrared-remote/wiring'},
  ],steps:[
    {title:'L’energia arriva dalle pile',text:'Nella configurazione illustrata, le pile alimentano la scheda. Le linee mostrano il collegamento funzionale, non il cablaggio reale.',parts:['battery_a','battery_b','pcb'],links:[['battery_a','pcb'],['battery_b','pcb']],effect:'energy'},
    {title:'Il tasto diventa un comando',text:'La pressione sul pulsante viene rilevata dai contatti della scheda. L’elettronica determina quale comando trasmettere.',parts:['keypad','pcb'],links:[['keypad','pcb']],effect:'press'},
    {title:'Il LED invia il messaggio',text:'La scheda pilota l’emettitore con impulsi infrarossi. Il ricevitore del dispositivo interpreta il codice: non è un fascio visibile come quello disegnato qui.',parts:['pcb','emitter'],links:[['pcb','emitter']],effect:'signal'},
  ]},
  click_pen:{key:'click_pen',title:'Il piccolo meccanismo dello scatto',sources:[
    {title:'Faber-Castell — esempio di meccanismo a pulsante, GB1246702A',url:'https://patents.google.com/patent/GB1246702A/en'},
  ],steps:[
    {title:'Il pulsante spinge la ricarica',text:'Premendo il pulsante, il meccanismo fa avanzare la ricarica. Qui pulsante e fermi sono rappresentati come un unico gruppo semplificato.',parts:['click','refill'],links:[['click','refill']],effect:'press'},
    {title:'Molla e fermo lavorano insieme',text:'La molla si comprime, mentre il fermo mantiene la punta nella posizione di scrittura. Lo schema non riproduce le camme di un modello specifico.',parts:['spring','refill','click'],links:[['click','refill'],['spring','refill']],effect:'spring'},
    {title:'Un altro scatto libera il ritorno',text:'Quando il meccanismo rilascia il fermo, la molla riporta la ricarica verso l’interno. Forma e disposizione del sistema possono cambiare fra penne.',parts:['spring','refill','tip'],links:[['spring','refill'],['refill','tip']],effect:'spring'},
  ]},
  water_bottle:{key:'water_bottle',title:'Contenere, chiudere, proteggere',sources:[
    {title:'BERICAP — chiusura a vite e anello di prima apertura',url:'https://bericap.com/product/ds28-7065-eco-uni-1331/'},
  ],steps:[
    {title:'Il corpo contiene il liquido',text:'Il corpo forma il recipiente e il collo guida l’uscita del liquido. Materiale, capacità e proporzioni non sono misurati da questa animazione.',parts:['body'],links:[],effect:'seal'},
    {title:'Il tappo chiude il collo',text:'Nella famiglia a vite illustrata, il tappo si accoppia al collo e le superfici di tenuta contribuiscono alla chiusura. Esistono sistemi diversi.',parts:['cap','body'],links:[['cap','body']],effect:'seal'},
    {title:'L’anello segnala la prima apertura',text:'In molte chiusure, piccoli collegamenti dell’anello si interrompono alla prima apertura. La presenza dell’anello non certifica da sola la sicurezza del contenuto.',parts:['ring','cap'],links:[['ring','cap']],effect:'seal'},
  ]},
  computer_mouse:{key:'computer_mouse',title:'Dal gesto al computer',sources:[
    {title:'Logitech — sensore ottico e rilevamento del movimento',url:'https://www.logitech.com/blog/2020/09/15/logitech-g-introduces-hero-25k-sensor-the-industrys-highest-performing-dpi-offering/'},
    {title:'Logitech — pulsanti e sensore di un mouse',url:'https://www.logitechg.com/en-in/shop/p/g402-hyperion-fury-fps-gaming-mouse.910-004070'},
  ],steps:[
    {title:'Il gruppo ottico rileva lo spostamento',text:'Il sensore osserva la superficie e ricava il movimento. L’elettronica usa questa informazione per comunicare lo spostamento al computer.',parts:['sensor','board'],links:[['sensor','board']],effect:'sense'},
    {title:'Il clic diventa un ingresso',text:'Nella variante con pulsanti meccanici, la parte superiore aziona gli interruttori letti dalla scheda. Il tipo di comando varia fra modelli.',parts:['top','board'],links:[['top','board']],effect:'press'},
    {title:'La rotella aggiunge lo scorrimento',text:'La rotazione viene rilevata e convertita in un comando. Il percorso mostra una relazione funzionale, non il circuito o il collegamento radio del tuo mouse.',parts:['wheel','board'],links:[['wheel','board']],effect:'sense'},
  ]},
  flashlight:{key:'flashlight',title:'Dall’energia alla luce',sources:[
    {title:'Energizer — alimentazione e gruppo luminoso LED',url:'https://energizer.com/eu/south-africa/product/energizer-led-lantern/'},
    {title:'Energizer — torcia LED e fascio luminoso',url:'https://energizer.com/product/lighting/flashlights-lighting/vision-hd-6aa-performance-metal-light/'},
  ],steps:[
    {title:'La batteria fornisce energia',text:'L’alimentazione raggiunge il gruppo luminoso attraverso il circuito e il comando di accensione. Questi ultimi sono semplificati, non ricostruiti nel dettaglio.',parts:['battery','led'],links:[['battery','led']],effect:'energy'},
    {title:'Il LED produce luce',text:'Il gruppo LED converte parte dell’energia elettrica in luce. L’animazione non misura potenza, temperatura o stato della batteria.',parts:['led','reflector'],links:[['led','reflector']],effect:'light'},
    {title:'L’ottica orienta il fascio',text:'Nella variante illustrata, il riflettore aiuta a dirigere la luce e la protezione frontale ripara l’ottica. Altre torce usano sistemi differenti.',parts:['reflector','lens'],links:[['reflector','lens']],effect:'light'},
  ]},
};

/** Sources belong to a step, not to an unrelated panel or a physical-unit claim. */
export function sourcesForStep(tour:Walkthrough,index:number):readonly TourSource[]{
  if(!Number.isInteger(index)||index<0||index>=tour.steps.length)return [];
  const ids=tour.steps[index].sourceIndexes??tour.sources.map((_,i)=>i);
  if(ids.length===0||ids.some(i=>!Number.isInteger(i)||i<0||i>=tour.sources.length))return [];
  return [...new Set(ids)].map(i=>tour.sources[i]);
}

/** Only the authored seed family and part contract can unlock a walkthrough.
 * This is structural compatibility, not proof of the user's hidden hardware.
 */
export function walkthroughFor(manifest:Manifest,sourceType?:string):Walkthrough|null{
  if(sourceType!=='seed'||manifest.schema_version!==1||manifest.evidence_level!=='illustrative'
    ||manifest.match_scope!=='family'||manifest.units!=='illustrative')return null;
  if(!Object.prototype.hasOwnProperty.call(tours,manifest.canonical_key))return null;
  const tour=tours[manifest.canonical_key];
  const keys=new Set(manifest.parts.map(p=>p.key));
  if(keys.size!==manifest.parts.length)return null;
  const expected=EXTRA_TOUR_SHAPES[manifest.canonical_key];
  if(expected&&(manifest.parts.length!==Object.keys(expected).length
    ||manifest.parts.some(p=>expected[p.key]!==p.shape||p.evidence!=='typical')))return null;
  if(!tour.sources.length||tour.sources.some(s=>!s.title.trim()||!/^https:\/\/[^\s/]+\//.test(s.url)))return null;
  return tour.steps.every((step,index)=>{
    const highlighted=new Set(step.parts);
    return step.parts.length>0&&highlighted.size===step.parts.length
      &&step.parts.every(k=>keys.has(k))
      &&step.links.every(([from,to])=>from!==to&&highlighted.has(from)&&highlighted.has(to))
      &&sourcesForStep(tour,index).length>0;
  })?tour:null;
}

/** Bounded single run; pause/resume is stable and the last step never loops. */
export class TourClock{
  index=0;elapsed=0;playing=false;done=false;
  readonly duration=6000;
  constructor(readonly count:number){}
  start(auto=true){this.index=0;this.elapsed=0;this.done=false;this.playing=auto;}
  tick(ms:number){
    if(!this.playing||this.count<1||!Number.isFinite(ms)||ms<=0)return;
    this.elapsed+=Math.min(ms,100);
    if(this.elapsed>=this.duration){
      if(this.index+1<this.count){this.index++;this.elapsed=0;}
      else{this.elapsed=this.duration;this.playing=false;this.done=true;}
    }
  }
  seek(index:number){this.index=Math.max(0,Math.min(this.count-1,Math.trunc(index)||0));this.elapsed=0;this.playing=false;this.done=false;}
  toggle(){if(this.done){this.index=0;this.elapsed=0;this.done=false;}this.playing=!this.playing;}
  stop(){this.playing=false;}
  get phase(){return Math.max(0,Math.min(1,this.elapsed/this.duration));}
}
