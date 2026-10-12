/** ORA Italian educational labels for the pinned BodyParts3D 4.0 reference.
 * Source FMA identifiers are never changed. Names not safely mapped remain
 * available in their source language with an explicit "nome originale" note.
 * This is not an automatic clinical terminology certification.
 */
import type {Atlas} from './anatomy';

export const SISTEMI_IT:Record<string,{name:string;description:string}>={
 skeletal:{name:'Scheletro',description:'Le ossa sostengono il corpo, proteggono gli organi e offrono punti di inserzione ai muscoli.'},
 muscular:{name:'Muscoli',description:'I muscoli producono movimento, stabilizzano le articolazioni e contribuiscono alla produzione di calore.'},
 cardiac:{name:'Cuore',description:'Il cuore pompa il sangue nella circolazione polmonare e sistemica mediante quattro cavità e valvole.'},
 sensory:{name:'Organi di senso',description:'Occhi e orecchie rilevano stimoli e inviano segnali al sistema nervoso.'},
 arterial:{name:'Arterie',description:'Le arterie portano il sangue dal cuore ai tessuti, incluse le arterie polmonari verso i polmoni.'},
 venous:{name:'Vene',description:'Le vene riportano il sangue verso il cuore; le vene polmonari trasportano sangue ossigenato.'},
 nervous:{name:'Sistema nervoso',description:'Encefalo, midollo spinale e nervi elaborano e trasmettono segnali sensitivi, motori e autonomi.'},
 respiratory:{name:'Apparato respiratorio',description:'Le vie aeree e i polmoni permettono gli scambi di ossigeno e anidride carbonica.'},
 digestive:{name:'Apparato digerente',description:'Il tubo digerente e gli organi associati trasformano e assorbono i nutrienti.'},
 urinary:{name:'Apparato urinario',description:'I reni filtrano il sangue; ureteri e vescica raccolgono e trasportano l’urina.'},
 lymphatic:{name:'Sistema linfatico',description:'I vasi linfatici drenano i fluidi e gli organi linfoidi collaborano alle difese immunitarie.'},
 endocrine:{name:'Sistema endocrino',description:'Le ghiandole endocrine rilasciano ormoni che regolano numerose funzioni.'},
 reproductive:{name:'Apparato riproduttivo',description:'Questo modello maschile adulto mostra strutture riproduttive tipiche, non quelle della persona ripresa.'},
 integumentary:{name:'Superficie corporea',description:'La cute protegge i tessuti e contribuisce a sensibilità e termoregolazione.'},
 connective:{name:'Tessuti connettivi',description:'Cartilagini, legamenti e altri tessuti connettono e sostengono le strutture.'},
};
export const SPIEGAZIONI_IT:Record<string,string>={
 'heart':'Il cuore è una pompa muscolare con quattro cavità; il lato destro invia il sangue ai polmoni e quello sinistro al resto del corpo.',
 'cuore':'Il cuore è una pompa muscolare con quattro cavità; il lato destro invia il sangue ai polmoni e quello sinistro al resto del corpo.',
 'brain':'L’encefalo coordina funzioni sensoriali e motorie, memoria, linguaggio e regolazione di numerosi processi.',
 'encefalo':'L’encefalo coordina funzioni sensoriali e motorie, memoria, linguaggio e regolazione di numerosi processi.',
 'liver':'Il fegato metabolizza nutrienti, produce bile e sintetizza proteine plasmatiche.',
 'fegato':'Il fegato metabolizza nutrienti, produce bile e sintetizza proteine plasmatiche.',
 'stomach':'Lo stomaco immagazzina e mescola gli alimenti con acido ed enzimi prima del duodeno.',
 'stomaco':'Lo stomaco immagazzina e mescola gli alimenti con acido ed enzimi prima del duodeno.',
 'pancreas':'Il pancreas produce enzimi digestivi e ormoni come insulina e glucagone.',
 'spleen':'La milza filtra il sangue e partecipa alle risposte immunitarie.',
 'milza':'La milza filtra il sangue e partecipa alle risposte immunitarie.',
 'urinary bladder':'La vescica urinaria raccoglie l’urina proveniente dai reni.',
 'vescica urinaria':'La vescica urinaria raccoglie l’urina proveniente dai reni.',
 'trachea':'La trachea collega laringe e bronchi, mantenendo aperto il condotto respiratorio grazie agli anelli cartilaginei.',
 'diaphragm':'Il diaframma è un muscolo respiratorio che separa torace e addome.',
 'diaframma':'Il diaframma è un muscolo respiratorio che separa torace e addome.',
};

/** Terms with a well-established Italian anatomical equivalent. */
const exact:Record<string,string>={
 'heart':'Cuore','brain':'Encefalo','cerebrum':'Cervello','cerebellum':'Cervelletto',
 'spinal cord':'Midollo spinale','liver':'Fegato','stomach':'Stomaco','pancreas':'Pancreas',
 'spleen':'Milza','esophagus':'Esofago','oesophagus':'Esofago','trachea':'Trachea',
 'diaphragm':'Diaframma','urinary bladder':'Vescica urinaria','bladder':'Vescica',
 'aorta':'Aorta','kidney':'Rene','left kidney':'Rene sinistro','right kidney':'Rene destro',
 'lung':'Polmone','left lung':'Polmone sinistro','right lung':'Polmone destro',
 'small intestine':'Intestino tenue','large intestine':'Intestino crasso',
 'colon':'Colon','rectum':'Retto','appendix':'Appendice','gallbladder':'Colecisti',
 'left atrium':'Atrio sinistro','right atrium':'Atrio destro',
 'left ventricle':'Ventricolo sinistro','right ventricle':'Ventricolo destro',
 'atrium':'Atrio','ventricle':'Ventricolo','coronary artery':'Arteria coronaria',
 'femur':'Femore','humerus':'Omero','radius':'Radio','ulna':'Ulna','tibia':'Tibia',
 'fibula':'Fibula','pelvis':'Bacino','sternum':'Sterno','clavicle':'Clavicola',
 'scapula':'Scapola','mandible':'Mandibola','skull':'Cranio',
 'vertebral column':'Colonna vertebrale','vertebra':'Vertebra',
 'rib':'Costa','ribs':'Coste','patella':'Rotula','hand':'Mano','foot':'Piede',
 'head':'Testa','neck':'Collo','face':'Volto','arm':'Braccio','leg':'Gamba',
 'left eye':'Occhio sinistro','right eye':'Occhio destro','eye':'Occhio',
 'ear':'Orecchio','left ear':'Orecchio sinistro','right ear':'Orecchio destro',
 'tongue':'Lingua','larynx':'Laringe','pharynx':'Faringe','thyroid gland':'Tiroide',
 'prostate':'Prostata','testis':'Testicolo','penis':'Pene','urethra':'Uretra',
 'inferior vena cava':'Vena cava inferiore','superior vena cava':'Vena cava superiore',
 'pulmonary artery':'Arteria polmonare','pulmonary vein':'Vena polmonare',
 'bronchus':'Bronco','bronchi':'Bronchi','skin':'Pelle','muscle':'Muscolo',
 'nerve':'Nervo','artery':'Arteria','vein':'Vena','bone':'Osso',
};
const terms:[RegExp,string][]=[
 [/\bwall of (the )?right atrium\b/gi,'parete dell’atrio destro'],
 [/\bwall of (the )?left atrium\b/gi,'parete dell’atrio sinistro'],
 [/\bwall of (the )?right ventricle\b/gi,'parete del ventricolo destro'],
 [/\bwall of (the )?left ventricle\b/gi,'parete del ventricolo sinistro'],
 [/\bcavity of (the )?right ventricle\b/gi,'cavità del ventricolo destro'],
 [/\bcavity of (the )?left ventricle\b/gi,'cavità del ventricolo sinistro'],
 [/\bcavity of (the )?right atrium\b/gi,'cavità dell’atrio destro'],
 [/\bcavity of (the )?left atrium\b/gi,'cavità dell’atrio sinistro'],
 [/\bleft ventricle\b/gi,'ventricolo sinistro'],[/\bright ventricle\b/gi,'ventricolo destro'],
 [/\bleft atrium\b/gi,'atrio sinistro'],[/\bright atrium\b/gi,'atrio destro'],
 [/\bcoronary arter(?:y|ies)\b/gi,'arterie coronarie'],
 [/\bspinal cord\b/gi,'midollo spinale'],[/\bcranial nerve\b/gi,'nervo cranico'],
 [/\bthoracic vertebra\b/gi,'vertebra toracica'],[/\bcervical vertebra\b/gi,'vertebra cervicale'],
 [/\blumbar vertebra\b/gi,'vertebra lombare'],
 [/\b(superior|upper)\b/gi,'superiore'],[/\b(inferior|lower)\b/gi,'inferiore'],
 [/\banterior\b/gi,'anteriore'],[/\bposterior\b/gi,'posteriore'],
 [/\bmedial\b/gi,'mediale'],[/\blateral\b/gi,'laterale'],
 [/\bleft\b/gi,'sinistro'],[/\bright\b/gi,'destro'],
 [/\bventricle\b/gi,'ventricolo'],[/\batrium\b/gi,'atrio'],[/\bvalves?\b/gi,'valvola'],
 [/\barter(?:y|ies)\b/gi,'arteria'],[/\bveins?\b/gi,'vena'],[/\bnerves?\b/gi,'nervo'],
 [/\bmuscles?\b/gi,'muscolo'],[/\btendons?\b/gi,'tendine'],[/\bligaments?\b/gi,'legamento'],
 [/\bvertebrae?\b/gi,'vertebra'],[/\bbones?\b/gi,'osso'],
 [/\bbrain\b/gi,'encefalo'],[/\bheart\b/gi,'cuore'],
 [/\blungs?\b/gi,'polmone'],[/\bkidneys?\b/gi,'rene'],[/\bliver\b/gi,'fegato'],
 [/\bstomach\b/gi,'stomaco'],[/\bpancreas\b/gi,'pancreas'],[/\bspleen\b/gi,'milza'],
 [/\bbladder\b/gi,'vescica'],[/\btrachea\b/gi,'trachea'],
 [/\bskin\b/gi,'cute'],[/\bcavity\b/gi,'cavità'],[/\bwall\b/gi,'parete'],
 [/\bhead\b/gi,'testa'],[/\bneck\b/gi,'collo'],[/\bhand\b/gi,'mano'],
 [/\bfoot\b/gi,'piede'],[/\bjoint\b/gi,'articolazione'],
 [/\bof the\b/gi,'del'],[/\bof\b/gi,'di'],
];
const capitalize=(s:string)=>s? s.charAt(0).toLocaleUpperCase('it')+s.slice(1):s;
export function italianName(name:string):string {
 const source=name.trim();if(!source)return source;
 const key=source.toLowerCase();
 if(exact[key])return exact[key];
 let output=source;
 for(const [pattern,value] of terms)output=output.replace(pattern,value);
 // If the source contains unfamiliar terms, preserve them for scientific traceability.
 return capitalize(output);
}
export function italianAtlas(atlas:Atlas):Atlas{
 return {...atlas,
  parts:atlas.parts.map(p=>({...p,originalName:p.name,name:italianName(p.name)})),
  concepts:atlas.concepts.map(c=>({...c,originalName:c.name,name:italianName(c.name)})),
 };
}
