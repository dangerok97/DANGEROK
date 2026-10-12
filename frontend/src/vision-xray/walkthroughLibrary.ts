/** Twenty authored educational paths for the common-25 seed pack.
 * Sources describe general principles or a named example, NOT the photographed
 * unit. Links are illustrative, not repair procedures or physical simulation.
 */
import type { Walkthrough, TourStep, TourSource } from './walkthrough';
import type { Part } from './scene';
const source=(title:string,url:string):TourSource=>({title,url});
const step=(title:string,text:string,parts:string[],links:[string,string][],effect:TourStep['effect'],sourceIndexes:number[]=[0]):TourStep=>({title,text,parts,links,effect,sourceIndexes});
const electronicNote='Relazioni funzionali indicative, non cablaggi misurati. Non aprire batterie o circuiti alimentati.';
const mechanicalNote='Relazioni meccaniche illustrative, non una simulazione delle forze o una guida allo smontaggio.';
const materialNote='Strati e regioni sono separati solo per spiegare: non sono necessariamente pezzi staccabili.';
const fluidNote='Percorso del liquido illustrativo; valvole e camera di pompaggio sono raggruppate, non misurate.';
const touch=source('Analog Devices — rilevamento e comunicazione della posizione del tocco','https://www.analog.com/en/products/max11855.html');
const matrix=source('Adafruit — lettura dei contatti in una matrice di pulsanti','https://learn.adafruit.com/matrix-keypad/pinouts');
const earbuds=source('iFixit — osservazione diretta di un esempio di auricolare e custodia','https://www.ifixit.com/Teardown/AirPods+Teardown/75578');
const ballpoint=source('Pilot — principio della scrittura a sfera','https://www.pilotpen.eu/our-products/liquid-ink-pens/');
export const EXTRA_TOURS:Record<string,Walkthrough>={
 smartphone:{key:'smartphone',title:'Dal tocco alle immagini',note:electronicNote,sources:[
  source('Apple — gruppi di display, batteria e fotocamera: esempio iPhone 14','https://support.apple.com/en-us/100308'),touch,
 ],steps:[
  step('La batteria alimenta l’elettronica','La batteria fornisce energia ai circuiti che coordinano il telefono. Il collegamento alla scheda è simbolico: non indica cavi, capacità o stato di carica reali.',['battery','mainboard'],[['battery','mainboard']],'energy',[0]),
  step('Il tocco diventa un ingresso','I sensori del display rilevano la posizione del dito e la comunicano all’elettronica. Il gruppo display riunisce qui pannello e rilevamento tattile; il chip effettivo non è identificato.',['display','mainboard'],[['display','mainboard']],'sense',[1]),
  step('La fotocamera alimenta l’anteprima','Il gruppo fotocamera acquisisce l’immagine, che viene elaborata e presentata sul display. Numero di obiettivi e percorso interno dipendono dal telefono: questa è una relazione tra gruppi.',['camera','mainboard','display'],[['camera','mainboard'],['mainboard','display']],'signal',[0]),
 ]},
 tablet:{key:'tablet',title:'Un grande schermo che risponde',note:electronicNote,sources:[
  source('Apple — gruppi principali di un tablet: esempio iPad A16','https://support.apple.com/en-us/122080'),touch,
 ],steps:[
  step('L’energia raggiunge la scheda','Il pacco batteria alimenta il tablet quando non è collegato al caricatore. Le celle sono raggruppate: qui non se ne determinano numero, capacità o autonomia.',['battery','board'],[['battery','board']],'energy',[0]),
  step('Il dito comunica una posizione','Il sistema tattile rileva dove appoggi il dito e fornisce un ingresso all’elettronica. Il collegamento rappresenta informazioni, non una pressione meccanica sulla scheda.',['screen','board'],[['screen','board']],'sense',[1]),
  step('La risposta arriva sullo schermo','I circuiti elaborano i comandi e aggiornano i contenuti visualizzati. Fotocamera e audio sono altri gruppi del tablet, ma non devono partecipare a ogni tocco.',['board','screen'],[['board','screen']],'signal',[0,1]),
 ]},
 laptop:{key:'laptop',title:'Dalle dita al risultato sullo schermo',note:electronicNote,sources:[
  source('Apple — tastiera, trackpad, scheda e schermo: esempio MacBook Air','https://support.apple.com/es-es/100603'),matrix,touch,
 ],steps:[
  step('Tasti e gesti diventano ingressi','Tastiera e superficie di puntamento rilevano comandi diversi: pressioni e posizioni delle dita. Le linee li collegano al gruppo di elaborazione senza riprodurre i circuiti del portatile.',['keyboard','trackpad','mainboard'],[['keyboard','mainboard'],['trackpad','mainboard']],'sense',[0,1,2]),
  step('La scheda coordina le operazioni','La scheda principale elabora gli ingressi e comunica con il gruppo schermo. Processore, memorie e collegamenti minori sono riuniti: non è una mappa dei singoli chip.',['mainboard','display'],[['mainboard','display']],'signal',[0]),
  step('La batteria permette l’uso senza cavo','La batteria alimenta i gruppi del computer attraverso i circuiti di gestione. La rappresentazione non misura consumo o autonomia e non suggerisce di aprire il pacco.',['battery','mainboard'],[['battery','mainboard']],'energy',[0]),
 ]},
 computer_keyboard:{key:'computer_keyboard',title:'Come una pressione diventa un tasto',note:'Schema di tastiera a membrana: non descrive gli interruttori di una tastiera meccanica.',sources:[matrix,
  source('Adafruit — esempio di tastiera a membrana','https://www.adafruit.com/product/419'),
 ],steps:[
  step('Il tasto avvicina i contatti','Nella famiglia a membrana, la pressione del tasto avvicina gli strati conduttivi nella zona interessata. Lo schema non riproduce ogni contatto o il layout di una lingua.',['keys','membrane'],[['keys','membrane']],'press',[1]),
  step('Il controllo legge la matrice','La scheda esamina righe e colonne dei contatti per distinguere il tasto premuto. La griglia permette di leggere più pulsanti senza assegnare a ciascuno una coppia di fili separata.',['membrane','controller'],[['membrane','controller']],'sense',[0]),
  step('Il rilascio termina la pressione','Quando il tasto torna a riposo, il contatto cambia stato. Il controllo rileva il rilascio e aggiorna il comando; modalità e collegamento al computer dipendono dalla tastiera.',['keys','membrane','controller'],[['keys','membrane'],['membrane','controller']],'signal',[0,1]),
 ]},
 game_controller:{key:'game_controller',title:'Pressioni e direzioni per il gioco',note:electronicNote,sources:[matrix,
  source('Adafruit — esempio di joystick con due assi e ritorno centrale','https://www.adafruit.com/product/5628'),
 ],steps:[
  step('I pulsanti producono comandi distinti','Premendo un pulsante si modifica lo stato del relativo contatto. La scheda legge l’ingresso: il numero dei pulsanti e il circuito effettivo dipendono dal controller.',['buttons','board'],[['buttons','board']],'press',[0]),
  step('Le levette aggiungono la direzione','I gruppi delle levette rilevano l’inclinazione lungo due assi. Lo schema non stabilisce se il tuo controller usi potenziometri o un altro tipo di sensore.',['left_stick','right_stick','board'],[['left_stick','board'],['right_stick','board']],'sense',[1]),
  step('Il ritorno al centro cambia la lettura','Nella variante con richiamo elastico, lasciando la levetta questa torna verso il centro e il sensore comunica la nuova posizione. Non è una misura di precisione o usura.',['left_stick','board'],[['left_stick','board']],'spring',[1]),
 ]},
 usb_flash_drive:{key:'usb_flash_drive',title:'Dalla porta USB ai dati conservati',note:'La memoria è rappresentata separata dalla scheda per chiarezza; nella chiavetta reale può essere saldata o integrata.',sources:[
  source('Kingston — guida alle memorie Flash e ai drive USB','https://media.kingston.com/pdfs/MKF-283.3-Flash-Memory-Guide_IT.pdf'),
 ],steps:[
  step('Il connettore collega la chiavetta','Il connettore consente lo scambio di dati con il dispositivo ospite e l’alimentazione dell’elettronica. La geometria non determina la versione USB o la velocità.',['connector','board'],[['connector','board']],'signal'),
  step('Il controllo gestisce la memoria','L’elettronica sulla scheda organizza letture e scritture nelle celle Flash. Il controllo e la memoria sono gruppi concettuali: possono essere integrati in modi differenti.',['board','memory'],[['board','memory']],'signal'),
  step('I dati restano senza alimentazione','La memoria Flash è non volatile: conserva i dati anche quando viene scollegata. Non significa conservazione eterna o assenza di guasti; qui non viene verificato alcun file.',['memory'],[],'material'),
 ]},
 wireless_earbud:{key:'wireless_earbud',title:'Dal segnale wireless al suono',note:electronicNote,sources:[
  source('Bluetooth SIG — trasmissione audio wireless','https://www.bluetooth.com/learn-about-bluetooth/solutions/audio-streaming/'),earbuds,
  source('Sony — trasduttore dinamico e membrana: esempio di auricolare','https://pro.sony/en_FI/products/headphones/mdr-7550'),
 ],steps:[
  step('La scheda riceve l’audio','Il collegamento wireless porta i dati audio all’elettronica dell’auricolare. Il percorso non stabilisce quale versione Bluetooth, codec o chip sia presente nel tuo esemplare.',['board'],[],'signal',[0]),
  step('Il trasduttore muove la membrana','La scheda fornisce il segnale al trasduttore. Nella variante dinamica, la membrana produce variazioni di pressione nell’aria che percepiamo come suono. Il movimento qui è simbolico.',['board','driver'],[['board','driver']],'sound',[1,2]),
  step('La piccola batteria mantiene l’ascolto','La batteria alimenta l’elettronica durante l’uso. Il gruppo microfono può raccogliere l’audio, ma funzioni e numero di microfoni variano: non viene simulata la cancellazione del rumore.',['battery','board','microphone'],[['battery','board'],['microphone','board']],'energy',[1]),
 ]},
 earbud_charging_case:{key:'earbud_charging_case',title:'Una riserva di energia per gli auricolari',note:electronicNote,sources:[
  source('Apple — ricaricare gli auricolari nella custodia','https://support.apple.com/en-us/119912'),earbuds,
 ],steps:[
  step('La custodia conserva energia','La batteria della custodia offre una riserva per ricaricare gli auricolari. Porta e possibili sistemi wireless sono omessi; non tutti i modelli hanno le stesse modalità di ricarica.',['battery','board'],[['battery','board']],'energy',[0,1]),
  step('Le sedi allineano i contatti','Il supporto interno mantiene gli auricolari in posizione rispetto ai contatti di ricarica. Qui sedi e contatti sono riuniti in un solo gruppo: non è la forma esatta del tuo prodotto.',['holder','board'],[['board','holder']],'energy',[1]),
  step('L’elettronica gestisce la ricarica','La scheda trasferisce energia ai contatti delle sedi quando gli auricolari sono inseriti. La luce animata non indica corrente, percentuale o stato di carica misurati.',['battery','board','holder'],[['battery','board'],['board','holder']],'energy',[0,1]),
 ]},
 wooden_pencil:{key:'wooden_pencil',title:'Perché la matita lascia una traccia',note:materialNote,sources:[
  source('Faber-Castell — mina di grafite e argilla','https://www.faber-castell.com/products/6CtGraphitePencilTin/900010'),
  source('Faber-Castell — involucro di legno e fissaggio della mina','https://www.faber-castell.pl/products/Grip2001graphitepencilBred/517021'),
 ],steps:[
  step('Il legno sostiene la mina','Il rivestimento permette di impugnare la matita e sostiene la mina lungo il corpo. Nel prodotto reale i materiali sono uniti: il modello li separa per mostrarli.',['wood','core'],[['wood','core']],'material',[1]),
  step('La punta porta la mina sulla carta','La zona appuntita rende accessibile l’estremità scrivente. La punta evidenziata è una regione della matita, non un componente che si stacca dall’involucro e dalla mina.',['core','point'],[['core','point']],'material',[0,1]),
  step('Il materiale forma il segno','Durante la scrittura una piccola quantità di materiale della mina si deposita sulla carta. La composizione a base di grafite e argilla contribuisce alle diverse durezze.',['core','point'],[['core','point']],'material',[0]),
 ]},
 mechanical_pencil:{key:'mechanical_pencil',title:'La mina avanza senza temperare',note:mechanicalNote,sources:[
  source('Pentel — pulsante, pinza e guida della mina','https://www.pentel.co.uk/wp-content/uploads/2020/12/Pentel_Automatic_Pencils_Maintenance_Guide.pdf'),
 ],steps:[
  step('Il pulsante aziona la pinza','Nel portamine a pulsante illustrato, il comando muove il meccanismo che trattiene e rilascia la mina. Il gruppo include elementi piccoli non disegnati individualmente.',['button','clutch'],[['button','clutch']],'press'),
  step('La mina avanza e viene trattenuta','L’azione del meccanismo consente alla mina di avanzare; la pinza la trattiene nella posizione di scrittura. La corsa e i fermi non sono ricostruiti per un modello specifico.',['clutch','lead'],[['clutch','lead']],'press'),
  step('La guida sostiene l’estremità','Il puntale guida il tratto di mina vicino alla carta. Non è una punta con inchiostro: il materiale scrivente è la mina, che resta fragile quando sporge troppo.',['guide','lead'],[['guide','lead']],'material'),
 ]},
 capped_pen:{key:'capped_pen',title:'Il percorso dell’inchiostro fino alla sfera',note:materialNote,sources:[ballpoint,
  source('Pilot — penne a sfera e ricariche','https://www.pilotpen.eu/our-products/ballpoint-pens/'),
 ],steps:[
  step('Il corpo sostiene la ricarica','Il corpo rende comoda la presa e mantiene la ricarica in posizione. Il serbatoio contiene l’inchiostro; nello schema non ne viene identificata la formulazione.',['barrel','refill'],[['barrel','refill']],'material',[1]),
  step('La sfera distribuisce l’inchiostro','Quando scrivi, la piccola sfera della punta ruota contro la carta e trasferisce inchiostro dal sistema di alimentazione. Qui sfera e sede sono rappresentate nel gruppo puntale.',['refill','tip'],[['refill','tip']],'flow',[0]),
  step('Il cappuccio protegge la punta','Quando la penna non viene usata, il cappuccio copre il puntale. La tenuta e la protezione dall’essiccamento dipendono dalla costruzione: non si presume una chiusura ermetica universale.',['cap','tip'],[['cap','tip']],'seal',[0,1]),
 ]},
 marker:{key:'marker',title:'Dal serbatoio alla punta porosa',note:materialNote,sources:[
  source('edding — alimentazione capillare della punta: esempio MTK 25','https://www.edding.com/products/edding-mtk-25-refill-service-permanent-marker/'),
  source('edding — corpo, punta e cappuccio: esempio di pennarello','https://www.edding.com/products/edding-28-whiteboard-marker/'),
 ],steps:[
  step('Il serbatoio trattiene l’inchiostro','Nel pennarello capillare illustrato, il materiale interno conserva l’inchiostro e lo mette in contatto con la punta. Non descrive tutti i pennarelli a valvola o a vernice.',['barrel','reservoir'],[['barrel','reservoir']],'material',[0]),
  step('La punta riceve l’inchiostro','La capillarità favorisce il movimento dell’inchiostro verso la punta porosa mentre il segno consuma quello disponibile. Non serve una pompa elettrica e non viene misurata la portata.',['reservoir','nib'],[['reservoir','nib']],'flow',[0]),
  step('Il cappuccio copre la zona scrivente','Dopo l’uso, il cappuccio protegge la punta e limita l’esposizione all’aria. Alcuni prodotti tollerano intervalli senza cappuccio, ma non è una proprietà garantita per ogni pennarello.',['cap','nib'],[['cap','nib']],'seal',[1]),
 ]},
 glue_stick:{key:'glue_stick',title:'Ruotare, applicare, richiudere',note:'La risalita è un principio meccanico; la separazione della colla dal supporto è soltanto esplicativa.',sources:[
  source('Pritt — origine del meccanismo a rotazione','https://www.prittworld.ca/en/about-us.html'),
  source('Pritt — applicazione e chiusura dello stick','https://www.prittarabia.com/products/central-pdp.html/pritt-original-glue-sticks/SAP_0201BAP20126.html'),
 ],steps:[
  step('La base aziona il supporto','Ruotando la base si comanda il supporto che porta lo stick verso l’apertura. Lo schema riunisce il meccanismo di avanzamento, senza ricostruire la filettatura del prodotto.',['base','lift','glue'],[['base','lift'],['lift','glue']],'rotation',[0]),
  step('La superficie cede uno strato di colla','Il materiale adesivo viene steso sulla superficie da unire. Il corpo sostiene il blocco mentre lo usi: non ci sono alimentazione o riscaldamento elettrico nel modello illustrato.',['tube','glue'],[['tube','glue']],'material',[1]),
  step('Il cappuccio protegge lo stick','Richiudere il cappuccio limita l’essiccamento del materiale durante la conservazione. Lo schema non deduce ingredienti, tempi di presa o compatibilità con qualsiasi materiale.',['cap','tube','glue'],[['cap','tube']],'seal',[1]),
 ]},
 stapler:{key:'stapler',title:'Dalla leva al punto ripiegato',note:mechanicalNote,sources:[
  source('Leitz — caricatore, spingipunti, lama e incudine, US8297485B2','https://patents.google.com/patent/US8297485B2/en'),
 ],steps:[
  step('Lo spingipunti prepara il successivo','Nel caricatore, lo spingipunti mantiene la fila contro l’arresto anteriore. I punti metallici non sono un gruppo separato di questo modello: il percorso evidenzia gli organi che li guidano.',['pusher','magazine'],[['pusher','magazine']],'spring'),
  step('La leva comanda la lama','Premendo la leva, la lama spinge il punto anteriore fuori dalla fessura del caricatore e attraverso i fogli. Il collegamento mostra l’azione, non la forza applicata.',['lever','driver','magazine'],[['lever','driver'],['driver','magazine']],'press'),
  step('La base ripiega le estremità','L’incudine sulla base guida il ripiegamento delle estremità del punto. Qui è compresa nella base: posizione e modalità di chiusura dipendono dalla pinzatrice.',['driver','base'],[['driver','base']],'press'),
 ]},
 adhesive_tape_roll:{key:'adhesive_tape_roll',title:'Un supporto e uno strato adesivo',note:materialNote,sources:[
  source('3M — struttura di un nastro con adesivo sensibile alla pressione','https://www.3m.co.za/3M/en_ZA/p/d/b40067704/'),
 ],steps:[
  step('L’anima sostiene il rotolo','Il supporto flessibile è avvolto attorno all’anima. L’anima organizza il rotolo, mentre il materiale del nastro può essere film, carta o un altro supporto.',['core','backing'],[['core','backing']],'material'),
  step('L’adesivo riveste il supporto','Lo strato adesivo è legato al supporto e forma la superficie che aderisce. Nel modello i due strati sono allontanati per spiegarli, non perché si stacchino durante l’uso normale.',['backing','adhesive'],[['backing','adhesive']],'material'),
  step('La pressione migliora il contatto','Nel nastro sensibile alla pressione, premere favorisce il contatto tra adesivo e superficie. Non serve attivarlo come una colla a caldo; tipo e forza di adesione restano specifici del prodotto.',['adhesive','backing'],[['backing','adhesive']],'press'),
 ]},
 clothespin:{key:'clothespin',title:'Due leve e una molla',note:mechanicalNote,sources:[
  source('Esempio di molletta a due leve e molla, US2748437A','https://patents.google.com/patent/US2748437A/en'),
 ],steps:[
  step('Premere i manici apre le ganasce','Le due metà lavorano come leve. Avvicinando le estremità che impugni, le estremità opposte si allontanano per lasciare passare il tessuto. Il fulcro è semplificato.',['jaw_left','jaw_right'],[['jaw_left','jaw_right']],'press'),
  step('La molla si carica elasticamente','Nella molletta illustrata, l’apertura deforma elasticamente la molla a torsione. Non è una batteria né una semplice molla assiale: la geometria mostrata resta schematica.',['jaw_left','jaw_right','spring'],[['jaw_left','spring'],['jaw_right','spring']],'spring'),
  step('Il rilascio richiude la presa','Lasciando i manici, la molla tende a riportare le due ganasce una verso l’altra. La forza effettiva dipende dalla molletta e dal tessuto e non viene misurata qui.',['spring','jaw_left','jaw_right'],[['spring','jaw_left'],['spring','jaw_right']],'spring'),
 ]},
 soap_dispenser:{key:'soap_dispenser',title:'Una pressione, poi il riempimento',note:fluidNote,sources:[
  source('Pompa per fluidi con camera e richiamo elastico, EP3352634B1','https://patents.google.com/patent/EP3352634B1/en'),
  source('Esempio di pompa dosatrice con valvole, EP1433535A2','https://patents.google.com/patent/EP1433535A2/en'),
 ],steps:[
  step('La pressione aziona la camera','Quando la camera contiene prodotto, premere la testa riduce il volume disponibile nella pompa. Le valvole indirizzano il liquido: qui sono comprese nel gruppo pompa.',['head','pump'],[['head','pump']],'press',[0,1]),
  step('Il prodotto esce dalla testa','Il liquido spinto dalla pompa raggiunge il canale di uscita della testa. La linea indica il percorso funzionale, non un tubo o una quantità di sapone misurati.',['pump','head'],[['pump','head']],'flow',[0,1]),
  step('Il ritorno richiama altro liquido','Al rilascio, il richiamo elastico riporta il meccanismo e la camera si riempie attraverso il pescante. L’adescamento iniziale può richiedere più azioni; la molla può essere disposta diversamente.',['spring','pump','bottle','tube'],[['spring','pump'],['bottle','tube'],['tube','pump']],'flow',[0,1]),
 ]},
 trigger_spray_bottle:{key:'trigger_spray_bottle',title:'Il grilletto trasforma il liquido in spruzzo',note:fluidNote,sources:[
  source('Aptar — esempio di pompa manuale a grilletto','https://www.aptar.com/en-us/products/tsp-full-plastic-trigger-spray-pump'),
  source('Pompa a grilletto con pescante e ugello, US5624060A','https://patents.google.com/patent/US5624060A/en'),
 ],steps:[
  step('Il grilletto aziona la pompa','Il movimento del grilletto aziona il meccanismo nella testa, che spinge il liquido presente nella camera. Non è una bomboletta aerosol e non si presume che tutto il flacone sia pressurizzato.',['trigger','head'],[['trigger','head']],'press',[0,1]),
  step('L’ugello forma l’uscita','Il liquido dalla testa attraversa l’ugello, che influenza la forma dell’erogazione. Spruzzo, getto e possibilità di regolazione dipendono dalla costruzione: non ogni flacone offre gli stessi modi.',['head','nozzle'],[['head','nozzle']],'flow',[0,1]),
  step('Il ritorno riempie la camera','Al ritorno del meccanismo, la pompa richiama prodotto dal flacone attraverso il tubo pescante. Le valvole del gruppo testa gestiscono la direzione del flusso durante il ciclo.',['bottle','tube','head'],[['bottle','tube'],['tube','head']],'flow',[1]),
 ]},
 insulated_bottle:{key:'insulated_bottle',title:'Rallentare lo scambio di calore',note:'Le linee descrivono relazioni termiche, non temperature o prestazioni misurate. Il vuoto è uno spazio, non un pezzo aggiuntivo.',sources:[
  source('Thermos — doppia parete e isolamento sotto vuoto','https://thermos.com/blogs/news/how-vacuum-insulation-works-the-science-behind-thermos%C2%AE-products'),
 ],steps:[
  step('La parete interna contiene la bevanda','Il recipiente interno contiene il liquido; la parete esterna forma l’involucro. Sono mostrati separati per chiarezza, non come pezzi da staccare per usare la borraccia.',['inside','outside'],[['inside','outside']],'material'),
  step('Lo spazio tra le pareti isola','Nella famiglia sotto vuoto, l’aria ridotta tra le pareti limita conduzione e convezione attraverso quello spazio. Non elimina tutti gli scambi: restano irraggiamento e collegamenti strutturali.',['inside','outside'],[],'heat'),
  step('Anche la chiusura conta','Tappo e tenuta chiudono l’apertura, uno dei percorsi di scambio con l’esterno. La borraccia rallenta il cambiamento di temperatura: non produce caldo o freddo e non conserva la temperatura per sempre.',['cap','seal','inside'],[['cap','seal'],['seal','inside']],'seal'),
 ]},
 screwdriver:{key:'screwdriver',title:'Dalla mano alla vite',note:'Percorso della coppia, non elettrico. La punta può essere la parte terminale dello stesso stelo, non un inserto separabile.',sources:[
  source('Wera — impugnatura, stelo e trasmissione della coppia: esempio costruttivo','https://www.wera.de/en/tools/917-sph-screwdriver-for-phillips-screws'),
 ],steps:[
  step('L’impugnatura raccoglie la rotazione','La mano applica una rotazione all’impugnatura. La sua forma aiuta a trasmettere la coppia; il modello non simula lo sforzo o certifica l’isolamento elettrico.',['handle','shaft'],[['handle','shaft']],'rotation'),
  step('Lo stelo trasmette la coppia','Lo stelo collega l’impugnatura alla zona di contatto con la vite. Il trasferimento è meccanico, senza un motore o un circuito nascosto.',['shaft','tip'],[['shaft','tip']],'rotation'),
  step('Il profilo della punta fa presa','La punta trasferisce la rotazione alla vite attraverso un profilo compatibile. Nello schema la zona terminale è evidenziata separatamente, ma può essere ricavata nello stesso pezzo di metallo dello stelo.',['tip','shaft'],[['shaft','tip']],'rotation'),
 ]},
};
/** Reviewed part contract for common-25-v1; changed geometry groups need review. */
export const EXTRA_TOUR_SHAPES:Record<string,Readonly<Record<string,Part['shape']>>>={
 smartphone:{display:'box',frame:'shell',mainboard:'board',battery:'box',camera:'box',speaker:'box',back:'shell'},
 tablet:{screen:'box',case:'shell',battery:'box',board:'board',camera:'box',audio:'box'},
 laptop:{display:'box',keyboard:'keypad',trackpad:'box',mainboard:'board',battery:'box',base:'shell'},
 computer_keyboard:{keys:'keypad',membrane:'box',controller:'board',top:'shell',base:'shell'},
 game_controller:{front:'shell',buttons:'keypad',left_stick:'cylinder',right_stick:'cylinder',board:'board',rear:'shell'},
 usb_flash_drive:{housing:'shell',board:'board',memory:'box',connector:'box',cap:'shell'},
 wireless_earbud:{housing:'shell',driver:'cylinder',battery:'cylinder',board:'board',microphone:'box'},
 earbud_charging_case:{lid:'shell',holder:'shell',battery:'box',board:'board',case:'shell'},
 wooden_pencil:{wood:'cylinder',core:'cylinder',point:'cone'},
 mechanical_pencil:{body:'cylinder',lead:'cylinder',clutch:'cylinder',guide:'cone',button:'cylinder'},
 capped_pen:{barrel:'cylinder',refill:'cylinder',tip:'cone',cap:'cylinder'},
 marker:{barrel:'cylinder',reservoir:'cylinder',nib:'cylinder',cap:'cylinder',plug:'cylinder'},
 glue_stick:{tube:'cylinder',glue:'cylinder',lift:'cylinder',base:'cylinder',cap:'cylinder'},
 stapler:{lever:'box',magazine:'shell',pusher:'box',driver:'box',base:'box'},
 adhesive_tape_roll:{core:'ring',backing:'ring',adhesive:'ring'},
 clothespin:{jaw_left:'box',jaw_right:'box',spring:'spring'},
 soap_dispenser:{bottle:'bottle',tube:'cylinder',pump:'cylinder',spring:'spring',head:'box',collar:'ring'},
 trigger_spray_bottle:{bottle:'bottle',tube:'cylinder',head:'box',trigger:'box',nozzle:'box',collar:'ring'},
 insulated_bottle:{outside:'bottle',inside:'bottle',cap:'cylinder',seal:'ring'},
 screwdriver:{handle:'cylinder',shaft:'cylinder',tip:'box'},
};
