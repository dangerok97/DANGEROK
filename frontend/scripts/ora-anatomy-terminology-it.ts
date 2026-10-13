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
/** Added clinically grounded anatomy descriptors and common Latin forms. */
const supplementary:Record<string,Gloss>={
 bronchial:{it:"bronchiale"},
 tributary:{it:"affluente"},
 capitis:{it:"della testa"},
 cervicis:{it:"del collo"},
 thoracis:{it:"del torace"},
 femoris:{it:"del femore"},
 radialis:{it:"radiale"},
 ulnaris:{it:"ulnare"},
 biliary:{it:"biliare"},
 limb:{it:"arto"},
 system:{it:"sistema"},
 lingular:{it:"lingulare"},
 compartment:{it:"compartimento"},
 region:{it:"regione"},
 symphysis:{it:"sinfisi"},
 pectoralis:{it:"pettorale"},
 pectoral:{it:"pettorale"},
 acromial:{it:"acromiale"},
 humeral:{it:"omerale"},
 thoraco:{it:"toraco"},
 neuraxis:{it:"nevrasse"},
 longissimus:{it:"lunghissimo"},
 iliocostalis:{it:"ileocostale"},
 semispinalis:{it:"semispinale"},
 caudate:{it:"caudato"},
 deltoid:{it:"deltoide"},
 colic:{it:"colico"},
 bronchopulmonary:{it:"broncopolmonare"},
 teres:{it:"rotondo"},
 colliculus:{it:"collicolo"},
 tarsal:{it:"tarsale"},
 choroidal:{it:"coroideo"},
 hemisphere:{it:"emisfero"},
 tract:{it:"tratto"},
 thyrohyoid:{it:"tiroioideo"},
 hepatovenous:{it:"epatovenoso"},
 nose:{it:"naso"},
 eyelid:{it:"palpebra"},
 plate:{it:"lamina"},
 index:{it:"indice"},
 investing:{it:"rivestimento"},
 obturator:{it:"otturatore"},
 serratus:{it:"dentato"},
 forearm:{it:"avambraccio"},
 trapezius:{it:"trapezio"},
 median:{it:"mediano"},
 constrictor:{it:"costrittore"},
 pancreaticoduodenal:{it:"pancreatoduodenale"},
 free:{it:"libero"},
 skeleton:{it:"scheletro"},
 opponens:{it:"opponente"},
 fibularis:{it:"peroneo"},
 gluteus:{it:"gluteo"},
 vastus:{it:"vasto"},
 scalenus:{it:"scaleno"},
 cusp:{it:"cuspide"},
 suprarenal:{it:"surrenale"},
 anatomical:{it:"anatomico"},
 subsegmental:{it:"sottosegmentario"},
 girdle:{it:"cingolo"},
 rotator:{it:"rotatore"},
 perforating:{it:"perforante"},
 arteria:{it:"arteria"},
 cricothyroid:{it:"cricotiroideo"},
 chest:{it:"torace"},
 leg:{it:"gamba"},
 spinal:{it:"spinale"},
 intermediate:{it:"intermedio"},
 pontine:{it:"pontino"},
 matter:{it:"sostanza"},
 pancreatic:{it:"pancreatico"},
 carpal:{it:"carpale"},
 big:{it:"grande"},
 thumb:{it:"pollice"},
 abdominal:{it:"addominale"},
 indicis:{it:"dell'indice"},
 frontobasal:{it:"frontobasale"},
 ileocolic:{it:"ileocolico"},
 popliteal:{it:"popliteo"},
 axillary:{it:"ascellare"},
 leaflet:{it:"lembo"},
 lobar:{it:"lobare"},
 side:{it:"lato"},
 mediastinum:{it:"mediastino"},
 oculomotor:{it:"oculomotore"},
 ophthalmic:{it:"oftalmico"},
 gemellus:{it:"gemello"},
 splenius:{it:"splenio"},
 pericallosal:{it:"pericalloso"},
 capsule:{it:"capsula"},
 brachium:{it:"braccio"},
 stria:{it:"stria"},
 thalamus:{it:"talamo"},
 saphenous:{it:"safeno"},
 subscapular:{it:"sottoscapolare"},
 diagonal:{it:"diagonale"},
 conus:{it:"cono"},
 gluteal:{it:"gluteo"},
 component:{it:"componente"},
 thigh:{it:"coscia"},
 systemic:{it:"sistemico"},
 content:{it:"contenuto"},
 check:{it:"fissazione"},
 tendinous:{it:"tendineo"},
 lens:{it:"cristallino"},
 minimus:{it:"minimo"},
 medius:{it:"medio"},
 quadratus:{it:"quadrato"},
 tensor:{it:"tensore"},
 fasciae:{it:"della fascia"},
 latae:{it:"lata"},
 tibialis:{it:"tibiale"},
 lateralis:{it:"laterale"},
 clavicular:{it:"clavicolare"},
 levatores:{it:"elevatori"},
 costarum:{it:"delle coste"},
 interossei:{it:"interossei"},
 rhomboid:{it:"romboide"},
 colli:{it:"del collo"},
 obliquus:{it:"obliquo"},
 stylohyoid:{it:"stiloioideo"},
 angular:{it:"angolare"},
 posteromedial:{it:"posteromediale"},
 geniculate:{it:"genicolato"},
 subcostal:{it:"sottocostale"},
 musculophrenic:{it:"muscolofrenico"},
 iris:{it:"iride"},
 sclera:{it:"sclera"},
 infratrochlear:{it:"infratrocleare"},
 nasolacrimal:{it:"nasolacrimale"},
 canaliculus:{it:"canalicolo"},
 corona:{it:"corona"},
 ciliaris:{it:"ciliare"},
 integumentary:{it:"cutaneo"},
 intercostalis:{it:"intercostale"},
 atria:{it:"atri"},
 circular:{it:"circolare"},
 suprascapular:{it:"sovrascapolare"},
 sternocleidomastoid:{it:"sternocleidomastoideo"},
 skull:{it:"cranio"},
 joint:{it:"articolazione"},
 joints:{it:"articolazioni"},
 cord:{it:"cordone"},
 vocal:{it:"vocale"},
 efferent:{it:"efferente"},
 afferent:{it:"afferente"},
 epidermis:{it:"epidermide"},
 nasopharynx:{it:"rinofaringe"},
 scapula:{it:"scapola"},
 humerus:{it:"omero"},
 palpebrae:{it:"delle palpebre"},
 superioris:{it:"superiore"},
 uterine:{it:"uterino"},
 capsular:{it:"capsulare"},
 lymph:{it:"linfa"},
 preganglionic:{it:"pregangliare"},
 postganglionic:{it:"postgangliare"},
 hypoglossal:{it:"ipoglosso"},
 metacarpus:{it:"metacarpo"},
 tarsus:{it:"tarso"},
 collar:{it:"collare"},
 parotid:{it:"parotideo"},
 submandibular:{it:"sottomandibolare"},
 precuneal:{it:"precuneale"},
 fiber:{it:"fibra"},
 fibers:{it:"fibre"},
 nucleus:{it:"nucleo"},
 floor:{it:"pavimento"},
 roof:{it:"tetto"},
 cingulum:{it:"cingolo"},
 axial:{it:"assiale"},
 forehead:{it:"fronte"},
 quadriceps:{it:"quadricipite"},
 tympanic:{it:"timpanico"},
 epiglottic:{it:"epiglottico"},
};
Object.assign(word,supplementary);
/** Additional medical names from the source terminology coverage audit. */
const medicalExtensions:Record<string,Gloss>={
 penis:{it:"pene"},
 lumbrical:{it:"lombricale"},
 scapular:{it:"scapolare"},
 pharyngeal:{it:"faringeo"},
 thoracodorsal:{it:"toracodorsale"},
 veli:{it:"del velo"},
 palatini:{it:"palatino"},
 crico:{it:"crico"},
 eleventh:{it:"undicesimo"},
 intestine:{it:"intestino"},
 testicular:{it:"testicolare"},
 myocardium:{it:"miocardio"},
 wrist:{it:"polso"},
 anterolateral:{it:"anterolaterale"},
 paracentral:{it:"paracentrale"},
 forebrain:{it:"prosencefalo"},
 white:{it:"bianco"},
 midbrain:{it:"mesencefalo"},
 splenic:{it:"splenico"},
 thyro:{it:"tiro"},
 abdomen:{it:"addome"},
 calcaneal:{it:"calcaneale"},
 lumborum:{it:"dei lombi"},
 spinalis:{it:"spinale"},
 intertransversarius:{it:"intertrasversario"},
 digastric:{it:"digastrico"},
 sphenoid:{it:"sfenoidale"},
 commissure:{it:"commessura"},
 fornix:{it:"fornice"},
 costocervical:{it:"costocervicale"},
 thyrocervical:{it:"tirocervicale"},
 tricuspid:{it:"tricuspide"},
 aortic:{it:"aortico"},
 sesamoid:{it:"sesamoide"},
 pudendal:{it:"pudendo"},
 superficialis:{it:"superficiale"},
 insular:{it:"insulare"},
 splenial:{it:"spleniale"},
 prefrontal:{it:"prefrontale"},
 corpus:{it:"corpo"},
 terminalis:{it:"terminale"},
 telencephalon:{it:"telencefalo"},
 princeps:{it:"principale"},
 mitral:{it:"mitrale"},
 taenia:{it:"tenia"},
 raphe:{it:"rafe"},
 hip:{it:"anca"},
 twelfth:{it:"dodicesimo"},
 vena:{it:"vena"},
 sector:{it:"settore"},
 intrapulmonary:{it:"intrapolmonare"},
 intrinsic:{it:"intrinseco"},
 musculature:{it:"muscolatura"},
 cortex:{it:"corteccia"},
 sac:{it:"sacco"},
 coccygeus:{it:"coccigeo"},
 iliococcygeus:{it:"ileococcigeo"},
 pubococcygeus:{it:"pubococcigeo"},
 puborectalis:{it:"puborettale"},
 ani:{it:"dell’ano"},
 retinaculum:{it:"retinacolo"},
 intertransversarii:{it:"intertrasversari"},
 interspinales:{it:"interspinali"},
 interspinalis:{it:"interspinale"},
 hypothalamic:{it:"ipotalamico"},
 postcommunicating:{it:"postcomunicante"},
 celiac:{it:"celiaco"},
 accessory:{it:"accessorio"},
 ileal:{it:"ileale"},
 basilic:{it:"basilico"},
 main:{it:"principale"},
 urinary:{it:"urinario"},
 thymus:{it:"timo"},
 ureteric:{it:"ureterale"},
 jugular:{it:"giugulare"},
 anastomosis:{it:"anastomosi"},
 thorax:{it:"torace"},
 tissue:{it:"tessuto"},
 pelvis:{it:"bacino"},
 cluster:{it:"gruppo"},
 mouth:{it:"bocca"},
 bony:{it:"osseo"},
 knee:{it:"ginocchio"},
 lake:{it:"lago"},
 suspensory:{it:"sospensore"},
 supratrochlear:{it:"sovratrocleare"},
 trochlea:{it:"troclea"},
 trochlear:{it:"trocleare"},
 vitreous:{it:"vitreo"},
 magnus:{it:"grande"},
 tertius:{it:"terzo"},
 accessorius:{it:"accessorio"},
 maximus:{it:"massimo"},
 gracilis:{it:"gracile"},
 iliacus:{it:"iliaco"},
 iliotibial:{it:"ileotibiale"},
 externus:{it:"esterno"},
 internus:{it:"interno"},
 pectineus:{it:"pettineo"},
 piriformis:{it:"piriforme"},
 plantaris:{it:"plantare"},
 popliteus:{it:"popliteo"},
 psoas:{it:"psoas"},
 sartorius:{it:"sartorio"},
 semimembranosus:{it:"semimembranoso"},
 semitendinosus:{it:"semitendinoso"},
 soleus:{it:"soleo"},
 intermedius:{it:"intermedio"},
 medialis:{it:"mediale"},
 anal:{it:"anale"},
 subclavius:{it:"succlavio"},
 transversus:{it:"trasverso"},
 breves:{it:"brevi"},
 longi:{it:"lunghi"},
 sternocostal:{it:"sternocostale"},
 anconeus:{it:"anconeo"},
 brachialis:{it:"brachiale"},
 brachioradialis:{it:"brachioradiale"},
 coracobrachialis:{it:"coracobrachiale"},
 profundus:{it:"profondo"},
 cranium:{it:"cranio"},
 zygomaticus:{it:"zigomatico"},
 malleolus:{it:"malleolo"},
 calcaneus:{it:"calcagno"},
 metatarsus:{it:"metatarso"},
 subcutaneous:{it:"sottocutaneo"},
 periosteum:{it:"periostio"},
 sinus:{it:"seno"},
 inferioris:{it:"inferiore"},
 caroticus:{it:"carotideo"},
 auricular:{it:"auricolare"},
 pterygoid:{it:"pterigoideo"},
 facialis:{it:"facciale"},
 lacrimalis:{it:"lacrimale"},
 cephalic:{it:"cefalico"},
 externalis:{it:"esterno"},
 internum:{it:"interno"},
 dorsum:{it:"dorso"},
 articular:{it:"articolare"},
 occipitalis:{it:"occipitale"},
 interosseus:{it:"interosseo"},
 scleral:{it:"sclerale"},
 sphenoidal:{it:"sfenoidale"},
 mucosa:{it:"mucosa"},
 posterolateral:{it:"posterolaterale"},
 olivary:{it:"olivare"},
 thalamic:{it:"talamico"},
 pons:{it:"ponte"},
 ventricularis:{it:"ventricolare"},
 cuneus:{it:"cuneo"},
 periventricular:{it:"periventricolare"},
 sternal:{it:"sternale"},
 frontalis:{it:"frontale"},
 cavernous:{it:"cavernoso"},
 abducens:{it:"abducente"},
 lacuna:{it:"lacuna"},
 alveolus:{it:"alveolo"},
};
Object.assign(word,medicalExtensions);
for(const key of ['matter','sclera','iris','musculature'])if(word[key])word[key].g='f';
const direct:Record<string,string>={
 'heart':'Cuore','brain':'Encefalo','cerebellum':'Cervelletto','liver':'Fegato',
 'external ear':'Orecchio esterno','internal ear':'Orecchio interno','middle ear':'Orecchio medio',
 'white matter':'Sostanza bianca','gray matter':'Sostanza grigia',
 'lacrimal sac':'Sacco lacrimale','lacrimal lake':'Lago lacrimale',
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
const normal=(name:string)=>name.toLowerCase().replace(/[\u2010-\u2015-]/g,' ').replace(/\bsupra orbital\b/g,'supraorbital').replace(/\s+/g,' ').trim();
const headNames=['ear','matter','hemisphere','sac','lake','lens','sclera','iris','musculature','wrist','thigh','hip','leg','pelvis','intestine','penis','trachea','forebrain','midbrain','phalanx','cartilage','ligament','artery','vein','nerve','muscle','tendon','tooth','bone','gyrus','sulcus','ganglion','plexus','bronchus','vertebra','rib','trunk','branch','head','wall','cavity','duct','lobe','fossa','chamber','gland','ventricle','atrium','part','body','root','process','foramen','arch','canal','disk','ring','segment','division','subdivision','valve','tree','set'];
const sortedHeads=[...headNames].sort((a,b)=>b.length-a.length);
/** Generic anatomical explanations are more honest than inventing physiology. */
export function systemExplanation(system:string,label:string):string{
 // Short, conservative explanations of the structures users actually tap.
 if(/orecchio esterno|padiglione auricolare/i.test(label))return 'L’orecchio esterno comprende il padiglione auricolare e il condotto uditivo esterno: raccoglie e convoglia le onde sonore verso il timpano.';
 if(/sostanza bianca/i.test(label))return 'La sostanza bianca è costituita prevalentemente da fasci di fibre nervose, molte delle quali mielinizzate, che collegano differenti aree del sistema nervoso.';
 if(/osso frontale/i.test(label))return 'L’osso frontale forma la fronte, una parte della volta cranica e del tetto delle cavità orbitarie; contribuisce a proteggere l’encefalo.';
 if(/osso parietale/i.test(label))return 'Le ossa parietali formano gran parte della volta e delle pareti laterali del cranio e si articolano con le ossa vicine attraverso le suture.';
 if(/osso occipitale/i.test(label))return 'L’osso occipitale costituisce la regione posteriore e inferiore del cranio. Attorno al foro occipitale passa il collegamento tra encefalo e midollo spinale.';
 if(/osso sfenoidale/i.test(label))return 'L’osso sfenoide si trova alla base del cranio, prende parte alle pareti delle orbite e si articola con numerose altre ossa craniche.';
 if(/mandibola/i.test(label))return 'La mandibola è l’osso mobile della parte inferiore del volto: sostiene i denti inferiori e consente i movimenti della masticazione.';
 if(/cristallino/i.test(label))return 'Il cristallino è una lente trasparente all’interno dell’occhio; cambiando curvatura contribuisce a mettere a fuoco la luce sulla retina.';
 if(/cornea/i.test(label))return 'La cornea è la superficie trasparente anteriore dell’occhio: protegge i tessuti interni e contribuisce in modo importante alla rifrazione della luce.';
 if(/retina/i.test(label))return 'La retina contiene cellule sensibili alla luce che trasformano gli stimoli luminosi in segnali destinati al sistema nervoso.';
 if(/giro .*cerebral|giro .*frontale|giro .*temporale|giro .*cingolato|giro .*parietale/i.test(label))return 'Un giro cerebrale è una piega della corteccia che aumenta la superficie disponibile. I diversi giri occupano posizioni anatomiche specifiche e partecipano a funzioni differenti.';
 if(/falange/i.test(label))return 'Le falangi sono le ossa delle dita: sono collegate da articolazioni che consentono flessione, estensione e altre componenti del movimento.';
 if(/gengiva/i.test(label))return 'La gengiva è il tessuto mucoso che circonda i denti e ricopre parte dei processi alveolari delle ossa mascellari.';
 if(/legamento/i.test(label))return 'Un legamento è una struttura fibrosa che collega segmenti scheletrici e contribuisce alla stabilità di un’articolazione.';
 if(/tendine/i.test(label))return 'Il tendine è una struttura di tessuto connettivo che trasmette la forza generata dal muscolo verso le strutture alle quali si inserisce.';
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
 if(/^osso\b|^organo\b|^occhio\b|^arco\b|^emisfero\b|^orecchio\b/.test(text.toLowerCase()))return 'dell’'+text.charAt(0).toLowerCase()+text.slice(1);
 if(/^(?:vena|rete|ghiandola|cartilagine|parete|cavità|falange|trachea|mandibola|mano)\b/.test(text.toLowerCase()))return 'della '+text.charAt(0).toLowerCase()+text.slice(1);
 if(/^(?:cuore|bulbo|nervo|bronco|giro|cranio|polmone|ventricolo|capo|pene|ginocchio|polso|sacco|miocardio|fegato|rene)\b/.test(text.toLowerCase()))return 'del '+text.charAt(0).toLowerCase()+text.slice(1);
 return 'di '+text.charAt(0).toLowerCase()+text.slice(1);
};
function manualDental(s:string):string|null{
 const match=s.match(/^(left|right) (lower|upper) (?:(first|second|third|fourth|central|lateral) )?secondary (molar|premolar|incisor|canine)(?: tooth)?$/);
 if(!match)return null;
 const [,side,height,ord,type]=match;
 const names:{[k:string]:string}={molar:'molare',premolar:'premolare',incisor:'incisivo',canine:'canino'};
 const nums:{[k:string]:string}={first:'primo',second:'secondo',third:'terzo',fourth:'quarto'};
 const position=ord==='central'?'centrale':ord==='lateral'?'laterale':null;
 return capitalize([ord&&nums[ord],names[type],position,'permanente',height==='lower'?'inferiore':'superiore',side==='left'?'sinistro':'destro'].filter(Boolean).join(' '));
}
function translateCore(s:string,depth:number):{name:string;translated:boolean}{
 if(depth>4)return {name:capitalize(s),translated:false};
 s=normal(s);
 if(!s)return {name:'',translated:false};
 if(direct[s])return {name:direct[s],translated:true};
 const tooth=manualDental(s);
 if(tooth)return {name:tooth,translated:true};
 // Source BodyParts3D groups hand muscles using "Set of ... of right hand".
 // These are collections, not a single muscle; do not emit hybrid English or
 // mechanically gender-convert the Italian noun "mano" to the invalid "mana".
 const handMuscleSet=s.match(/^set of (lumbricals|dorsal interossei|palmar interossei) of (right|left) hand$/);
 if(handMuscleSet){
  const names:Record<string,string>={
   lumbricals:'Muscoli lombricali', 'dorsal interossei':'Muscoli interossei dorsali',
   'palmar interossei':'Muscoli interossei palmari'
  };
  return {name:names[handMuscleSet[1]]+' della mano '+(handMuscleSet[2]==='left'?'sinistra':'destra'),translated:true};
 }
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
  // Nouns have lexical gender and must not be inflected like adjectives:
  // "mano" is feminine, but must never become "mana".
  return v.g||token===head?v.it:agree(v.it,gender);
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
