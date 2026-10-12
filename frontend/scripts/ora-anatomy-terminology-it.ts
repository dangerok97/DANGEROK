/** Deterministic, reviewable terminology for BodyParts3D FMA labels.
 * Preserve the original English source, FMA identifiers and exact geometry.
 * No invented medical claims; use transparent source labels for unfamiliar terms.
 */
type Gender='m'|'f';
type Gloss={it:string;g?:Gender};
const word:Record<string,Gloss>={
 artery:{it:'arteria',g:'f'},arteries:{it:'arterie',g:'f'},vein:{it:'vena',g:'f'},
 veins:{it:'vene',g:'f'},nerve:{it:'nervo'},nerves:{it:'nervi'},bone:{it:'osso'},
 bones:{it:'ossa'},muscle:{it:'muscolo'},muscles:{it:'muscoli'},tendon:{it:'tendine'},
 ligament:{it:'legamento'},cartilage:{it:'cartilagine',g:'f'},ganglion:{it:'ganglio'},
 plexus:{it:'plesso'},branch:{it:'ramo'},branches:{it:'rami'},trunk:{it:'tronco'},
 wall:{it:'parete',g:'f'},cavity:{it:'cavità',g:'f'},chamber:{it:'camera',g:'f'},
 head:{it:'capo'},body:{it:'corpo'},part:{it:'parte',g:'f'},segment:{it:'segmento'},
 subdivision:{it:'suddivisione',g:'f'},division:{it:'divisione',g:'f'},
 root:{it:'radice',g:'f'},arch:{it:'arco'},ring:{it:'anello'},
 foramen:{it:'foro'},process:{it:'processo'},duct:{it:'dotto'},
 valve:{it:'valvola',g:'f'},organ:{it:'organo'},gland:{it:'ghiandola',g:'f'},
 lobe:{it:'lobo'},lobule:{it:'lobulo'},gyrus:{it:'giro'},
 sulcus:{it:'solco'},fissure:{it:'scissura',g:'f'},pole:{it:'polo'},
 fossa:{it:'fossa',g:'f'},canal:{it:'canale'},space:{it:'spazio'},zone:{it:'zona',g:'f'},
 layer:{it:'strato'},set:{it:'insieme'},tree:{it:'rete',g:'f'},
 phalanx:{it:'falange',g:'f'},phalanges:{it:'falangi',g:'f'},
 vertebra:{it:'vertebra',g:'f'},vertebrae:{it:'vertebre',g:'f'},
 disk:{it:'disco'},disc:{it:'disco'},rib:{it:'costa',g:'f'},
 tooth:{it:'dente'},teeth:{it:'denti'},jaw:{it:'mascella',g:'f'},
 eye:{it:'occhio'},eyeball:{it:'bulbo oculare'},ear:{it:'orecchio'},
 foot:{it:'piede'},hand:{it:'mano',g:'f'},finger:{it:'dito'},
 toe:{it:'dito del piede'},fingers:{it:'dita'},toes:{it:'dita del piede'},
 brain:{it:'encefalo'},cerebrum:{it:'cervello'},cerebellum:{it:'cervelletto'},
 heart:{it:'cuore'},lung:{it:'polmone'},lungs:{it:'polmoni'},
 liver:{it:'fegato'},spleen:{it:'milza',g:'f'},pancreas:{it:'pancreas'},
 kidney:{it:'rene'},kidneys:{it:'reni'},stomach:{it:'stomaco'},bladder:{it:'vescica',g:'f'},
 colon:{it:'colon'},ileum:{it:'ileo'},jejunum:{it:'digiuno'},
 duodenum:{it:'duodeno'},rectum:{it:'retto'},anus:{it:'ano'},
 aorta:{it:'aorta',g:'f'},bronchus:{it:'bronco'},bronchi:{it:'bronchi'},
 trachea:{it:'trachea',g:'f'},larynx:{it:'laringe',g:'f'},pharynx:{it:'faringe',g:'f'},
 ureter:{it:'uretere'},urethra:{it:'uretra',g:'f'},uterus:{it:'utero'},
 ovary:{it:'ovaio'},testis:{it:'testicolo'},prostate:{it:'prostata',g:'f'},
 cornea:{it:'cornea',g:'f'},choroid:{it:'coroide',g:'f'},retina:{it:'retina',g:'f'},
 gingiva:{it:'gengiva',g:'f'},skin:{it:'cute',g:'f'},hair:{it:'pelo'},
 fascia:{it:'fascia',g:'f'},membrane:{it:'membrana',g:'f'},
 anterior:{it:'anteriore'},posterior:{it:'posteriore'},superior:{it:'superiore'},
 inferior:{it:'inferiore'},upper:{it:'superiore'},lower:{it:'inferiore'},
 lateral:{it:'laterale'},medial:{it:'mediale'},middle:{it:'medio'},
 central:{it:'centrale'},internal:{it:'interno'},external:{it:'esterno'},
 proximal:{it:'prossimale'},distal:{it:'distale'},dorsal:{it:'dorsale'},
 ventral:{it:'ventrale'},palmar:{it:'palmare'},plantar:{it:'plantare'},
 deep:{it:'profondo'},superficial:{it:'superficiale'},
 first:{it:'primo'},second:{it:'secondo'},third:{it:'terzo'},fourth:{it:'quarto'},
 fifth:{it:'quinto'},sixth:{it:'sesto'},seventh:{it:'settimo'},eighth:{it:'ottavo'},
 ninth:{it:'nono'},tenth:{it:'decimo'},
 common:{it:'comune'},proper:{it:'proprio'},major:{it:'maggiore'},minor:{it:'minore'},
 great:{it:'grande'},small:{it:'piccolo'},little:{it:'piccolo'},
 long:{it:'lungo'},short:{it:'breve'},longus:{it:'lungo'},brevis:{it:'breve'},
 flexor:{it:'flessore'},extensor:{it:'estensore'},adductor:{it:'adduttore'},
 abductor:{it:'abduttore'},pronator:{it:'pronatore'},supinator:{it:'supinatore'},
 levator:{it:'elevatore'},depressor:{it:'depressore'},
 transverse:{it:'trasverso'},oblique:{it:'obliquo'},rectus:{it:'retto'},
 radial:{it:'radiale'},ulnar:{it:'ulnare'},brachial:{it:'brachiale'},
 brachii:{it:'del braccio'},femoral:{it:'femorale'},tibial:{it:'tibiale'},
 fibular:{it:'fibulare'},peroneal:{it:'peroneale'},pelvic:{it:'pelvico'},
 iliac:{it:'iliaco'},costal:{it:'costale'},intercostal:{it:'intercostale'},
 cervical:{it:'cervicale'},thoracic:{it:'toracico'},lumbar:{it:'lombare'},
 sacral:{it:'sacrale'},cranial:{it:'cranico'},occipital:{it:'occipitale'},
 frontal:{it:'frontale'},temporal:{it:'temporale'},parietal:{it:'parietale'},
 orbital:{it:'orbitario'},supraorbital:{it:'sovraorbitario'},
 suborbital:{it:'sottoorbitario'},infraorbital:{it:'infraorbitario'},
 ethmoidal:{it:'etmoidale'},nasal:{it:'nasale'},lacrimal:{it:'lacrimale'},
 zygomatic:{it:'zigomatico'},mandibular:{it:'mandibolare'},maxillary:{it:'mascellare'},
 supra:{it:'sovra'},infra:{it:'sotto'},inter:{it:'inter'},
 palatine:{it:'palatino'},dental:{it:'dentale'},alveolar:{it:'alveolare'},
 ciliary:{it:'ciliare'},nasociliary:{it:'nasociliare'},
 hyoid:{it:'ioide'},thyroid:{it:'tiroideo'},arytenoid:{it:'aritenoide'},
 cricoid:{it:'cricoide'},cuneiform:{it:'cuneiforme'},
 corniculate:{it:'corniculato'},septal:{it:'settale'},septum:{it:'setto'},
 olfactory:{it:'olfattivo'},optic:{it:'ottico'},auditory:{it:'uditivo'},
 facial:{it:'facciale'},trigeminal:{it:'trigemino'},vagus:{it:'vago'},
 pulmonary:{it:'polmonare'},cardiac:{it:'cardiaco'},coronary:{it:'coronarico'},
 cerebral:{it:'cerebrale'},cerebellar:{it:'cerebellare'},
 hepatic:{it:'epatico'},renal:{it:'renale'},mesenteric:{it:'mesenterico'},
 portal:{it:'portale'},gastric:{it:'gastrico'},intestinal:{it:'intestinale'},
 venous:{it:'venoso'},arterial:{it:'arterioso'},vascular:{it:'vascolare'},
 lymphatic:{it:'linfatico'},segmental:{it:'segmentario'},
 ventricular:{it:'ventricolare'},interventricular:{it:'interventricolare'},
 interventriculum:{it:'interventricolare'},
 ventricle:{it:'ventricolo'},atrium:{it:'atrio'},atrial:{it:'atriale'},
 ascending:{it:'ascendente'},descending:{it:'discendente'},recurrent:{it:'ricorrente'},
 circumflex:{it:'circonflesso'},collateral:{it:'collaterale'},
 communicating:{it:'comunicante'},connecting:{it:'connettivo'},
 primary:{it:'primario'},secondary:{it:'secondario'},tertiary:{it:'terziario'},
 terminal:{it:'terminale'},marginal:{it:'marginale'},
 apical:{it:'apicale'},basal:{it:'basale'},digital:{it:'digitale'},
 metacarpal:{it:'metacarpale'},
 metatarsal:{it:'metatarsale'},interosseous:{it:'interosseo'},
 epigastric:{it:'epigastrico'},vertebral:{it:'vertebrale'},
 phrenic:{it:'frenico'},genicular:{it:'genicolato'},
 subclavian:{it:'succlavio'},carotid:{it:'carotide'},
 brachiocephalic:{it:'brachiocefalico'},callosomarginal:{it:'callosomarginale'},
 postcentral:{it:'postcentrale'},precentral:{it:'precentrale'},
 fusiform:{it:'fusiforme'},supramarginal:{it:'sovramarginale'},
 parahippocampal:{it:'paraippocampale'},cingulate:{it:'cingolato'},
 occipitotemporal:{it:'occipitotemporale'},temporoccipital:{it:'temporooccipitale'},
 biceps:{it:'bicipite'},triceps:{it:'tricipite'},gastrocnemius:{it:'gastrocnemio'},
 carpi:{it:'del carpo'},digitorum:{it:'delle dita'},digiti:{it:'del dito'},
 pollicis:{it:'del pollice'},hallucis:{it:'dell’alluce'},minimi:{it:'minimo'},
 pollex:{it:'pollice'},hallux:{it:'alluce'},
 intervertebral:{it:'intervertebrale'},epidural:{it:'epidurale'},
 papillary:{it:'papillare'},molar:{it:'molare'},
 premolar:{it:'premolare'},incisor:{it:'incisivo'},canine:{it:'canino'},
 visceral:{it:'viscerale'},
};
const direct:Record<string,string>={
 'heart':'Cuore','brain':'Encefalo','cerebellum':'Cervelletto','liver':'Fegato',
 'mandible':'Mandibola','skull':'Cranio','frontal bone':'Osso frontale',
 'hyoid bone':'Osso ioide','thyroid cartilage':'Cartilagine tiroidea',
 'gingiva of upper jaw':'Gengiva della mascella superiore',
 'gingiva of lower jaw':'Gengiva della mandibola',
 'optic nerve':'Nervo ottico','facial nerve':'Nervo facciale',
 'spinal cord':'Midollo spinale','sciatic nerve':'Nervo sciatico',
 'temporal bone':'Osso temporale','occipital bone':'Osso occipitale',
 'frontal lobe':'Lobo frontale','temporal lobe':'Lobo temporale',
 'renal artery':'Arteria renale','renal vein':'Vena renale',
 'left kidney':'Rene sinistro','right kidney':'Rene destro',
 'right coronary artery':'Arteria coronaria destra','left coronary artery':'Arteria coronaria sinistra',
 'inferior vena cava':'Vena cava inferiore','superior vena cava':'Vena cava superiore',
 'urinary bladder':'Vescica urinaria','vertebral column':'Colonna vertebrale',
 'small intestine':'Intestino tenue','large intestine':'Intestino crasso',
 'ascending aorta':'Aorta ascendente','descending aorta':'Aorta discendente',
 'intervertebral disk':'Disco intervertebrale',
 'orbital gyrus':'Giro orbitario',
 'right hip bone':'Osso dell’anca destro','left hip bone':'Osso dell’anca sinistro',
};
const originals=new Set(['of','the','to','and','with','from','for']);
const capitalize=(s:string)=>s?s.charAt(0).toLocaleUpperCase('it')+s.slice(1):s;
const feminine=new Set(['arteria','vena','gingiva','cavità','camera','parete','gengiva','ossa','costa','cartilagine','retina','coroide','fossa','milza','valvola','mano','falange','cute','suddivisione','radice','ghiandola','trachea','lingua','mascella','mandibola','rete']);
function agree(s:string,gender:Gender):string{
 if(gender==='f' && s.endsWith('ico'))return s.slice(0,-1)+'a';
 if(gender==='f' && /o$/.test(s)){
  if(s.endsWith('o'))return s.slice(0,-1)+'a';
 }
 return s;
}
const normal=(name:string)=>name.toLowerCase().replace(/[\u2010-\u2015-]/g,' ').replace(/\s+/g,' ').trim();
const headNames=['phalanx','cartilage','ligament','artery','vein','nerve','muscle','tendon','tooth','bone','gyrus','sulcus','ganglion','plexus','bronchus','vertebra','rib','trunk','branch','head','wall','cavity','duct','lobe','fossa','chamber','gland','ventricle','atrium','part','body','root','process','foramen','arch','canal','disk','ring','segment','division','subdivision','valve','tree','set'];
const sortedHeads=[...headNames].sort((a,b)=>b.length-a.length);
/** Generic anatomical explanations are more honest than inventing physiology. */
export function systemExplanation(system:string,label:string):string{
 if(/(?:osso|costa|falange|vertebra|mandibola|cranio|scheletro)/i.test(label))return 'Struttura del sistema scheletrico. La sua posizione e i rapporti con gli elementi vicini sono illustrati dal modello 3D di riferimento.';
 if(/(?:arteria|vena|vascolar|arterioso|venoso)/i.test(label))return 'Struttura del sistema circolatorio. I vasi arteriosi trasportano il sangue dal cuore, quelli venosi lo riportano verso il cuore. Il modello ne mostra la disposizione generale.';
 if(/(?:nervo|ganglio|plesso)/i.test(label))return 'Elemento del sistema nervoso. È rappresentato nella sua posizione anatomica generale; non corrisponde a una valutazione clinica della persona inquadrata.';
 if(/(?:muscolo|tendine|flessore|estensore)/i.test(label))return 'Struttura collegata al movimento e alla stabilizzazione. Muscoli e tendini contribuiscono a trasmettere le forze ai segmenti corporei.';
 const descriptions:Record<string,string>={
 skeletal:'Componente ossea o articolare del modello anatomico: fornisce sostegno e contribuisce alla protezione degli organi.',
 muscular:'Componente muscolare del modello anatomico, coinvolta nel movimento e nella stabilità delle articolazioni.',
 nervous:'Componente del sistema nervoso, che trasmette o integra segnali anatomici.',
 arterial:'Componente della rete arteriosa, che trasporta il sangue dal cuore ai tessuti.',
 venous:'Componente della rete venosa, che riporta il sangue verso il cuore.',
 respiratory:'Componente dell’apparato respiratorio, responsabile del passaggio e dello scambio dei gas.',
 sensory:'Componente coinvolta nella ricezione o trasmissione degli stimoli sensoriali.',
 digestive:'Componente dell’apparato digerente, coinvolta nell’elaborazione e nell’assorbimento dei nutrienti.'
 };
 return descriptions[system]||'Struttura anatomica rappresentata nel modello BodyParts3D. Per un dettaglio scientifico, consulta la denominazione originale associata all’identificatore FMA.';
}
const connector=(text:string):string=>{
 if(/^arteria\b|^aorta\b/.test(text.toLowerCase()))return 'dell’'+text.charAt(0).toLowerCase()+text.slice(1);
 if(/^osso\b|^organo\b|^occhio\b|^arco\b/.test(text.toLowerCase()))return 'dell’'+text.charAt(0).toLowerCase()+text.slice(1);
 if(/^(?:vena|rete|ghiandola|cartilagine|parete|cavità|falange|trachea|mandibola)\b/.test(text.toLowerCase()))return 'della '+text.charAt(0).toLowerCase()+text.slice(1);
 if(/^(?:cuore|bulbo|nervo|bronco|giro|cranio|polmone|ventricolo|capo)\b/.test(text.toLowerCase()))return 'del '+text.charAt(0).toLowerCase()+text.slice(1);
 return 'di '+text.charAt(0).toLowerCase()+text.slice(1);
};
function manualDental(s:string):string|null{
 const match=s.match(/^(left|right) (lower|upper) (?:(first|second|third|fourth) )?secondary (molar|premolar|incisor|canine)(?: tooth)?$/);
 if(!match)return null;
 const [,side,height,ord,type]=match;
 const names:{[k:string]:string}={molar:'molare',premolar:'premolare',incisor:'incisivo',canine:'canino'};
 const nums:{[k:string]:string}={first:'primo',second:'secondo',third:'terzo',fourth:'quarto'};
 return capitalize([ord&&nums[ord],names[type],'permanente',height==='lower'?'inferiore':'superiore',side==='left'?'sinistro':'destro'].filter(Boolean).join(' '));
}
function translateCore(s:string,depth:number):{name:string;translated:boolean}{
 if(depth>4)return {name:capitalize(s),translated:false};
 s=normal(s);
 if(!s)return {name:'',translated:false};
 if(direct[s])return {name:direct[s],translated:true};
 const tooth=manualDental(s);
 if(tooth)return {name:tooth,translated:true};
 const ofIndex=s.indexOf(' of ');
 if(ofIndex>0){
  const left=translateCore(s.slice(0,ofIndex),depth+1);
  const right=translateCore(s.slice(ofIndex+4),depth+1);
  const g=connector(right.name);
  return {name:left.name+' '+g,translated:left.translated&&right.translated};
 }
 const sideMatch=s.match(/^(left|right) (.*)$/);
 let side='';
 if(sideMatch){side=sideMatch[1];s=sideMatch[2];}
 // Check exact after stripping laterality.
 if(direct[s]){
  const base=direct[s],female=feminine.has(base.toLowerCase().split(' ')[0]);
  return {name:base+(side?' '+(side==='left'?(female?'sinistra':'sinistro'):(female?'destra':'destro')):''),translated:true};
 }
 const names=s.split(' ');
 // Move main nominal head (often the last noun in English) to the front.
 const headIndex=names.findIndex((v,i)=>sortedHeads.includes(v)&&i===names.length-1);
 const head=headIndex>=0?names[headIndex]:null;
 const gender:Gender=head?(word[head]?.g||'m'):word[names[0]]?.g||'m';
 // Italian anatomical nomenclature puts the structure descriptor before
 // orientation: "arteria temporale anteriore", never "arteria anteriore temporale".
 const orientation=new Set(['anterior','posterior','superior','inferior','middle','lateral','medial',
  'central','internal','external','upper','lower','proximal','distal','common','superficial','deep']);
 const descriptors=head?names.slice(0,headIndex):[];
 const ordered=[...descriptors.filter(t=>!orientation.has(t)),...descriptors.filter(t=>orientation.has(t))];
 const body=head?[head,...ordered]:names;
 let translated=true;
 const translatedWords=body.map(token=>{
  if(originals.has(token)){translated=false;return token;}
  const v=word[token];
  if(!v){translated=false;return token;}
  return agree(v.it,gender);
 });
 const name=capitalize(translatedWords.join(' ')+(side?' '+(side==='left'?(gender==='f'?'sinistra':'sinistro'):(gender==='f'?'destra':'destro')):''));
 return {name,translated};
}
/** Never display a half-Italian, semantically invalid blend as a verified name. */
export function anatomyNameIt(name:string):{name:string;reviewed:boolean}{
 const source=name.trim();
 if(!source)return {name:source,reviewed:false};
 const value=translateCore(source,0);
 return {name:value.translated?value.name:source,reviewed:value.translated};
}
