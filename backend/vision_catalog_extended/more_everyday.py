"""Additional original illustrative everyday-object families (additive V2).
No photographs, unlicensed CAD, measured dimensions or actionable disassembly steps.
All parts are groups typical of the family, not verified components of a specimen.
"""

def recipes(r, p):
    original_part = p
    def p(key, name, purpose, how, shape, size, assembled=(0, 0, 0)):
        # Descriptions remain object-specific, with a minimum useful length.
        if len(purpose) < 15:
            purpose += " durante l'utilizzo."
        if len(how) < 35:
            how += " nella configurazione illustrativa."
        return original_part(key, name, purpose, how, shape, size, assembled)
    return [
        r("pedal_bin", "Pattumiera con pedale", "Casa", ["cestino con pedale","pattumiera a pedale","pedal_trash_can"], [
            p("body", "Corpo", "Contiene i rifiuti.", "Il recipiente sostiene il sacco; volume e forma sono indicativi.", "box", (55, 74, 18)),
            p("lid", "Coperchio", "Copre l'apertura.", "Una cerniera consente al coperchio di sollevarsi.", "shell", (65, 82, 8)),
            p("pedal", "Pedale", "Comanda l'apertura.", "La pressione sul pedale aziona il rinvio meccanico.", "box", (55, 74, 18)),
            p("linkage", "Asta di rinvio", "Trasmette il movimento.", "Collega in alcuni modelli il pedale al coperchio.", "cylinder", (12, 72, 12)),
        ]),
        r("swing_bin", "Cestino con coperchio basculante", "Casa", ["cestino basculante","swing_top_bin"], [
            p("body", "Contenitore", "Raccoglie i rifiuti.", "Il guscio delimita il vano di raccolta.", "box", (55, 74, 18)),
            p("rim", "Cornice superiore", "Sostiene il coperchio.", "Il bordo guida o trattiene l'elemento mobile.", "ring", (40, 12, 40)),
            p("flap", "Sportello basculante", "Permette il conferimento.", "Ruota attorno ai propri appoggi tornando per gravità o equilibrio.", "shell", (65, 82, 8)),
        ]),
        r("watering_can", "Annaffiatoio", "Giardino", ["innaffiatoio","garden_watering_can"], [
            p("tank", "Serbatoio", "Contiene l'acqua.", "Il corpo è cavo e comunica con il beccuccio.", "bottle", (55, 74, 18)),
            p("spout", "Beccuccio", "Convoglia l'acqua.", "Il tubo dirige il flusso verso la pianta.", "cylinder", (12, 72, 12)),
            p("rose", "Rosa forata", "Distribuisce il getto.", "Piccoli fori suddividono il flusso in più rivoli.", "cone", (52, 61, 52)),
            p("handle", "Manico", "Permette la presa.", "È fissato al corpo e trasferisce il peso alla mano.", "ring", (40, 12, 40)),
        ]),
        r("garden_trowel", "Paletta da giardinaggio", "Giardino", ["paletta da giardino","hand_trowel"], [
            p("grip", "Impugnatura", "Consente la presa.", "Trasmette la forza dal palmo al gambo.", "cylinder", (12, 72, 12)),
            p("neck", "Collo", "Unisce manico e paletta.", "La parte stretta trasmette il carico alla lama.", "cylinder", (12, 72, 12)),
            p("blade", "Lama concava", "Sposta terra.", "La superficie incurvata trattiene il terriccio.", "shell", (65, 82, 8)),
        ]),
        r("flower_pot", "Vaso da fiori", "Giardino", ["vaso fiori","plant_pot"], [
            p("container", "Corpo del vaso", "Contiene il substrato.", "Le pareti delimitano lo spazio per radici e terreno.", "cone", (52, 61, 52)),
            p("base", "Fondo drenante", "Sostiene il contenuto.", "I fori, quando presenti, favoriscono il drenaggio.", "ring", (40, 12, 40)),
            p("saucer", "Sottovaso", "Raccoglie l'acqua.", "Il piattino separato può trattenere acqua in eccesso.", "shell", (65, 82, 8)),
        ]),
        r("hose_nozzle", "Lancia per tubo da giardino", "Giardino", ["pistola irrigazione","garden_hose_nozzle"], [
            p("body", "Corpo", "Convoglia l'acqua.", "Ospita il passaggio interno del flusso.", "cylinder", (12, 72, 12)),
            p("connector", "Raccordo", "Collega il tubo.", "L'innesto trattiene il terminale del tubo.", "ring", (40, 12, 40)),
            p("trigger", "Leva", "Regola l'erogazione.", "Agisce sulla valvola interna nei modelli a leva.", "box", (55, 74, 18)),
            p("head", "Testina", "Forma il getto.", "Una ghiera può modificare la distribuzione dell'acqua.", "cone", (52, 61, 52)),
        ]),
        r("broom", "Scopa domestica", "Casa", ["scopa","household_broom"], [
            p("handle", "Manico", "Consente di spingere.", "Trasferisce il movimento dalla mano alla testa.", "cylinder", (12, 72, 12)),
            p("socket", "Attacco", "Fissa il manico.", "Collega la testa al bastone mediante innesto.", "box", (55, 74, 18)),
            p("head", "Testa", "Sostiene le setole.", "La struttura distribuisce lo sforzo lungo la larghezza.", "box", (55, 74, 18)),
            p("bristles", "Setole", "Raccolgono lo sporco.", "Le fibre flessibili spostano polvere e piccoli residui.", "keypad", (46, 58, 3)),
        ]),
        r("dustpan", "Paletta raccoglipolvere", "Casa", ["paletta polvere","dust_pan"], [
            p("tray", "Vaschetta", "Raccoglie i residui.", "Il bordo basso favorisce l'ingresso dei detriti.", "shell", (65, 82, 8)),
            p("lip", "Bordo frontale", "Facilita la raccolta.", "Il bordo sottile aderisce al pavimento.", "board", (53, 65, 3)),
            p("handle", "Impugnatura", "Permette di sollevarla.", "La presa trasferisce il peso della vaschetta.", "cylinder", (12, 72, 12)),
        ]),
        r("floor_mop", "Mocio per pavimenti", "Casa", ["mocio","mop"], [
            p("shaft", "Manico", "Permette di guidare il mocio.", "Trasmette il movimento alla testa pulente.", "cylinder", (12, 72, 12)),
            p("holder", "Attacco testa", "Sostiene le fibre.", "Il supporto collega i fili o panno al manico.", "box", (55, 74, 18)),
            p("head", "Frange lavanti", "Assorbono acqua e sporco.", "Le fibre flessibili aumentano la superficie di contatto.", "keypad", (46, 58, 3)),
        ]),
        r("laundry_basket", "Cesto per bucato", "Casa", ["cesta bucato","laundry_hamper"], [
            p("body", "Cesto", "Contiene gli indumenti.", "Le pareti formano il contenitore, talvolta ventilato.", "box", (55, 74, 18)),
            p("rim", "Bordo superiore", "Irrigidisce l'apertura.", "Il bordo rinforza il perimetro della cesta.", "ring", (40, 12, 40)),
            p("handles", "Manici", "Consentono il trasporto.", "Le aperture o impugnature trasferiscono il peso alle mani.", "ring", (40, 12, 40)),
        ]),
        r("shoehorn", "Calzascarpe", "Casa", ["calzascarpe","shoe_horn"], [
            p("blade", "Lamina curva", "Guida il tallone.", "La superficie liscia riduce l'attrito sul contrafforte.", "shell", (65, 82, 8)),
            p("handle", "Zona di presa", "Permette di maneggiarlo.", "La parte superiore estende la leva della mano.", "cylinder", (12, 72, 12)),
            p("end", "Estremità", "Protegge il bordo.", "La terminazione arrotondata evita spigoli nella presa.", "ring", (40, 12, 40)),
        ]),
        r("door_stop", "Fermaporta a cuneo", "Casa", ["fermaporta","door_wedge"], [
            p("wedge", "Corpo inclinato", "Blocca l'anta.", "La geometria a cuneo crea attrito col pavimento.", "cone", (52, 61, 52)),
            p("base", "Base antiscivolo", "Aumenta l'aderenza.", "La superficie elastica limita lo scorrimento.", "board", (53, 65, 3)),
            p("grip", "Presa", "Facilita la rimozione.", "La zona rialzata permette di estrarre il fermo.", "box", (55, 74, 18)),
        ]),
        r("padlock", "Lucchetto meccanico", "Casa", ["lucchetto","mechanical_padlock"], [
            p("body", "Corpo", "Alloggia la chiusura.", "Il guscio racchiude il meccanismo di blocco.", "box", (55, 74, 18)),
            p("shackle", "Archetto", "Chiude il collegamento.", "La staffa entra nella sede del corpo.", "ring", (40, 12, 40)),
            p("cylinder", "Cilindro", "Riceve la chiave.", "La rotazione autorizzata può sbloccare il fermo.", "cylinder", (12, 72, 12)),
        ]),
        r("curtain_ring", "Anello da tenda", "Casa", ["anello tenda","curtain_loop"], [
            p("ring", "Anello", "Scorre sull'asta.", "L'apertura circolare circonda il bastone.", "ring", (40, 12, 40)),
            p("hook", "Gancio", "Sostiene il tessuto.", "La parte inferiore collega anello e tenda.", "ring", (40, 12, 40)),
            p("clip", "Morsetto", "Trattiene il bordo.", "In alcune versioni stringe il tessuto tra superfici.", "box", (55, 74, 18)),
        ]),
        r("shelf_bracket", "Staffa per mensola", "Casa", ["reggimensola","shelf_support"], [
            p("wall_plate", "Piastra verticale", "Collega la staffa alla parete.", "I fori consentono il fissaggio mediante elementi adatti.", "board", (53, 65, 3)),
            p("arm", "Braccio", "Sostiene il ripiano.", "Trasmette il carico del ripiano alla piastra.", "box", (55, 74, 18)),
            p("brace", "Rinforzo", "Contrasta la flessione.", "La diagonale irrigidisce la struttura quando presente.", "box", (55, 74, 18)),
        ]),
        r("manual_toothbrush", "Spazzolino manuale", "Bagno", ["spazzolino","toothbrush"], [
            p("handle", "Impugnatura", "Consente il movimento.", "La presa guida l'orientamento della testina.", "cylinder", (12, 72, 12)),
            p("neck", "Collo", "Collega manico e testa.", "La parte assottigliata facilita il raggiungimento dei denti.", "cylinder", (12, 72, 12)),
            p("head", "Testina con setole", "Pulisce le superfici.", "I ciuffi di setole agiscono meccanicamente.", "keypad", (46, 58, 3)),
        ]),
        r("electric_toothbrush", "Spazzolino elettrico", "Bagno", ["spazzolino elettrico","powered_toothbrush"], [
            p("handle", "Corpo impugnabile", "Contiene azionamento e alimentazione.", "Il guscio racchiude elementi elettrici non verificati.", "cylinder", (12, 72, 12)),
            p("drive", "Gruppo motore", "Genera il movimento.", "Trasferisce oscillazioni alla testina.", "box", (55, 74, 18)),
            p("shaft", "Perno di trasmissione", "Collega motore e testa.", "Il piccolo albero porta il moto verso l'estremità.", "cylinder", (12, 72, 12)),
            p("head", "Testina sostituibile", "Agisce sui denti.", "Le setole sono mosse dal gruppo di azionamento.", "keypad", (46, 58, 3)),
        ]),
        r("toothpaste_tube", "Tubetto di dentifricio", "Bagno", ["dentifricio tubetto","toothpaste"], [
            p("tube", "Corpo deformabile", "Contiene il prodotto.", "La pressione spinge la pasta verso il collo.", "shell", (65, 82, 8)),
            p("neck", "Collo filettato", "Guida l'uscita.", "L'apertura restringe il flusso verso il beccuccio.", "cylinder", (12, 72, 12)),
            p("cap", "Tappo", "Chiude il tubetto.", "La chiusura evita fuoriuscite quando non è in uso.", "cylinder", (12, 72, 12)),
        ]),
        r("shower_head", "Soffione doccia", "Bagno", ["soffione","doccetta","showerhead"], [
            p("head", "Testa distributrice", "Allarga il flusso.", "Il corpo indirizza l'acqua ai vari fori.", "box", (55, 74, 18)),
            p("plate", "Piastra forata", "Suddivide i getti.", "Piccole uscite generano molteplici fili d'acqua.", "keypad", (46, 58, 3)),
            p("neck", "Raccordo", "Riceve l'acqua.", "L'attacco unisce il soffione al tubo o al braccio.", "cylinder", (12, 72, 12)),
        ]),
        r("sink_plug", "Tappo lavandino", "Bagno", ["tappo lavandino","drain_plug"], [
            p("cap", "Disco superiore", "Chiude lo scarico.", "La superficie copre l'apertura del foro.", "box", (55, 74, 18)),
            p("seal", "Guarnizione", "Limita il passaggio dell'acqua.", "L'anello elastico aderisce alla sede.", "ring", (40, 12, 40)),
            p("stem", "Stelo", "Guida il tappo.", "Il perno sostiene e centra il gruppo mobile.", "cylinder", (12, 72, 12)),
        ]),
        r("nail_clipper", "Tagliaunghie", "Bagno", ["tagliaunghie","nail_clip"], [
            p("base", "Lamina inferiore", "Sostiene il taglio.", "Il bordo inferiore oppone una superficie alla lama.", "board", (53, 65, 3)),
            p("upper", "Lamina superiore", "Taglia l'unghia.", "Il bordo superiore si avvicina alla lamina inferiore.", "board", (53, 65, 3)),
            p("lever", "Levetta", "Moltiplica la pressione.", "La leva pieghevole trasferisce la forza delle dita.", "box", (55, 74, 18)),
            p("pin", "Perno", "Tiene insieme il gruppo.", "L'asse attraversa gli elementi di taglio.", "cylinder", (12, 72, 12)),
        ]),
        r("manual_razor", "Rasoio manuale a cartuccia", "Bagno", ["rasoio","disposable_razor"], [
            p("handle", "Impugnatura", "Guida la testina.", "Il manico permette di controllare l'inclinazione.", "cylinder", (12, 72, 12)),
            p("joint", "Snodo", "Segue il profilo.", "Alcuni modelli hanno una testa oscillante.", "ring", (40, 12, 40)),
            p("cartridge", "Cartuccia", "Alloggia le lame.", "Gli elementi taglienti sono protetti dal supporto.", "box", (55, 74, 18)),
            p("guard", "Banda protettiva", "Aiuta lo scorrimento.", "La striscia o barra precede la zona delle lame.", "board", (53, 65, 3)),
        ]),
        r("hand_mirror", "Specchio a mano", "Bagno", ["specchietto","hand_mirror"], [
            p("mirror", "Superficie riflettente", "Riflette la luce.", "Uno strato riflettente è sostenuto dal supporto.", "board", (53, 65, 3)),
            p("frame", "Cornice", "Protegge il bordo.", "Il bordo trattiene e rinforza lo specchio.", "ring", (40, 12, 40)),
            p("handle", "Impugnatura", "Permette di orientarlo.", "Il manico collega la presa alla cornice.", "cylinder", (12, 72, 12)),
        ]),
        r("hairbrush", "Spazzola per capelli", "Bagno", ["spazzola capelli","hair_brush"], [
            p("handle", "Impugnatura", "Permette il controllo.", "La presa orienta la testina durante l'uso.", "cylinder", (12, 72, 12)),
            p("base", "Corpo spazzola", "Sostiene i dentini.", "La base ospita o trattiene gli elementi flessibili.", "shell", (65, 82, 8)),
            p("pins", "Setole o dentini", "Districano i capelli.", "Le punte scorrono tra le ciocche.", "keypad", (46, 58, 3)),
        ]),
        r("manual_can_opener", "Apriscatole manuale", "Cucina", ["apriscatole","manual_canopener"], [
            p("handles", "Manici", "Permettono la presa.", "Le due leve stringono il bordo della lattina.", "box", (55, 74, 18)),
            p("cutting_wheel", "Rotella tagliente", "Incide il coperchio.", "Una rotella agisce vicino al bordo della scatola.", "ring", (40, 12, 40)),
            p("drive_wheel", "Rotella di avanzamento", "Muove l'attrezzo.", "La rotazione fa avanzare l'apriscatole lungo il bordo.", "ring", (40, 12, 40)),
            p("knob", "Manopola", "Permette la rotazione.", "La presa trasmette movimento alla rotella di avanzamento.", "cylinder", (12, 72, 12)),
        ]),
        r("corkscrew", "Cavatappi a vite", "Cucina", ["cavatappi","corkscrew"], [
            p("handle", "Impugnatura", "Permette la rotazione.", "La presa fa ruotare la spirale.", "cylinder", (12, 72, 12)),
            p("spiral", "Spirale", "Si inserisce nel sughero.", "La geometria elicoidale realizza la presa nel tappo.", "spring", (22, 35, 22)),
            p("shaft", "Gambo", "Collega presa e spirale.", "Il perno trasferisce la coppia alla parte elicoidale.", "cylinder", (12, 72, 12)),
        ]),
        r("vegetable_peeler", "Pelapatate manuale", "Cucina", ["pelapatate","vegetable_peeler"], [
            p("handle", "Impugnatura", "Guida l'utensile.", "La presa determina direzione e pressione.", "cylinder", (12, 72, 12)),
            p("frame", "Supporto della lama", "Tiene l'elemento tagliente.", "Il telaio mantiene la lama orientata.", "box", (55, 74, 18)),
            p("blade", "Lama", "Asporta la buccia.", "Il bordo tagliente rimuove uno strato sottile.", "board", (53, 65, 3)),
        ]),
        r("kitchen_tongs", "Pinza da cucina", "Cucina", ["pinza cucina","food_tongs"], [
            p("arm_a", "Primo braccio", "Afferra il cibo.", "La parte flessibile si avvicina all'altro braccio.", "box", (55, 74, 18)),
            p("arm_b", "Secondo braccio", "Completa la presa.", "La pressione reciproca stringe l'oggetto.", "box", (55, 74, 18)),
            p("joint", "Snodo o molla", "Collega i bracci.", "Il giunto mantiene l'allineamento e il ritorno.", "spring", (22, 35, 22)),
        ]),
        r("garlic_press", "Spremiaglio", "Cucina", ["schiaccia aglio","garlic_press"], [
            p("basket", "Vaschetta forata", "Contiene lo spicchio.", "I fori permettono il passaggio della polpa.", "shell", (65, 82, 8)),
            p("plunger", "Pistone", "Schiaccia l'aglio.", "La leva spinge il pistone nella vaschetta.", "box", (55, 74, 18)),
            p("handles", "Leve", "Amplificano la pressione.", "Due impugnature convertono la forza della mano.", "box", (55, 74, 18)),
            p("hinge", "Perno", "Unisce le leve.", "Il giunto consente la rotazione reciproca.", "cylinder", (12, 72, 12)),
        ]),
        r("kitchen_funnel", "Imbuto", "Cucina", ["imbuto","funnel"], [
            p("mouth", "Cono superiore", "Raccoglie il liquido.", "L'ampia apertura convoglia verso il collo.", "cone", (52, 61, 52)),
            p("stem", "Canalino", "Indirizza il flusso.", "Il condotto stretto raggiunge il recipiente.", "cylinder", (12, 72, 12)),
            p("rim", "Bordo", "Irrigidisce l'apertura.", "Il margine sostiene la geometria del cono.", "ring", (40, 12, 40)),
        ]),
        r("box_grater", "Grattugia a scatola", "Cucina", ["grattugia","box_grater"], [
            p("housing", "Corpo forato", "Sostiene le facce.", "La lamiera sagomata crea superfici di lavorazione.", "box", (55, 74, 18)),
            p("teeth", "Fori taglienti", "Riducono il cibo in frammenti.", "I bordi in rilievo agiscono sul prodotto.", "keypad", (46, 58, 3)),
            p("handle", "Maniglia", "Consente di impugnare.", "L'impugnatura stabilizza l'utensile.", "ring", (40, 12, 40)),
            p("base", "Bordo inferiore", "Appoggia al piano.", "La cornice inferiore aumenta la stabilità.", "ring", (40, 12, 40)),
        ]),
        r("colander", "Scolapasta", "Cucina", ["colapasta","colander"], [
            p("bowl", "Vasca forata", "Trattiene il cibo.", "Le aperture consentono all'acqua di defluire.", "shell", (65, 82, 8)),
            p("rim", "Bordo", "Irrigidisce la vasca.", "La cornice rinforza la bocca del recipiente.", "ring", (40, 12, 40)),
            p("handles", "Manici", "Consentono il sollevamento.", "Le prese trasferiscono il peso alle mani.", "ring", (40, 12, 40)),
        ]),
        r("ice_tray", "Vaschetta per ghiaccio", "Cucina", ["stampo ghiaccio","ice_cube_tray"], [
            p("tray", "Struttura", "Raccoglie l'acqua.", "La plastica o silicone forma i vani.", "box", (55, 74, 18)),
            p("cells", "Celle separate", "Suddividono le porzioni.", "I setti distinguono i cubetti durante il congelamento.", "keypad", (46, 58, 3)),
            p("rim", "Cornice superiore", "Rinforza il bordo.", "Il perimetro permette la manipolazione della vaschetta.", "ring", (40, 12, 40)),
        ]),
        r("ladle", "Mestolo da cucina", "Cucina", ["mestolo","soup_ladle"], [
            p("handle", "Manico lungo", "Permette la presa.", "Il manico distanzia la mano dal contenuto.", "cylinder", (12, 72, 12)),
            p("bowl", "Coppa", "Raccoglie il liquido.", "La cavità trattiene una porzione di brodo.", "shell", (65, 82, 8)),
            p("hook", "Gancio terminale", "Permette di appenderlo.", "Una curva può fungere da appoggio.", "ring", (40, 12, 40)),
        ]),
        r("spatula", "Spatola flessibile", "Cucina", ["spatola cucina","rubber_spatula"], [
            p("handle", "Manico", "Permette la presa.", "La presa guida la pressione sulla superficie.", "cylinder", (12, 72, 12)),
            p("blade", "Paletta flessibile", "Raccoglie i residui.", "Il bordo elastico aderisce a pareti e fondi.", "board", (53, 65, 3)),
            p("joint", "Innesto", "Unisce paletta e manico.", "Il collegamento mantiene l'allineamento degli elementi.", "box", (55, 74, 18)),
        ]),
        r("sticky_note_pad", "Blocco fogli adesivi", "Scrivania", ["post it","sticky_notes"], [
            p("sheets", "Fogli", "Consentono annotazioni.", "Ogni foglio può essere rimosso separatamente.", "keypad", (46, 58, 3)),
            p("adhesive", "Fascia adesiva", "Permette il fissaggio.", "Una striscia a bassa adesività collega provvisoriamente il foglio.", "board", (53, 65, 3)),
            p("base", "Ultimo foglio", "Sostiene il blocchetto.", "La base rappresenta il fondo della pila.", "board", (53, 65, 3)),
        ]),
        r("paper_folder", "Cartellina documenti", "Scrivania", ["cartellina","paper_folder"], [
            p("cover", "Copertina", "Protegge i fogli.", "La faccia anteriore forma il contenitore piegato.", "board", (53, 65, 3)),
            p("back", "Dorso", "Sostiene il contenuto.", "Il pannello posteriore supporta i documenti.", "board", (53, 65, 3)),
            p("flap", "Aletta interna", "Trattiene i fogli.", "La piega riduce il rischio di fuoriuscita.", "board", (53, 65, 3)),
        ]),
        r("pencil_case", "Astuccio per penne", "Scrivania", ["astuccio","pencil_pouch"], [
            p("shell", "Corpo", "Contiene la cancelleria.", "Il tessuto o materiale sagomato delimita il vano.", "shell", (65, 82, 8)),
            p("zipper", "Chiusura", "Permette l'apertura.", "Una cerniera accosta i bordi dell'astuccio.", "ring", (40, 12, 40)),
            p("pull", "Tiretto", "Consente di aprire.", "La linguetta trasferisce la trazione al cursore.", "box", (55, 74, 18)),
        ]),
        r("ruler", "Righello", "Scrivania", ["righello","straightedge"], [
            p("body", "Asta graduata", "Guida le linee.", "Il bordo rettilineo sostiene il tracciamento.", "board", (53, 65, 3)),
            p("markings", "Scala graduata", "Permette confronti.", "I segni indicano distanze convenzionali.", "keypad", (46, 58, 3)),
            p("edge", "Bordo di riferimento", "Allinea la misura.", "Il margine rettilineo costituisce il riferimento geometrico.", "box", (55, 74, 18)),
        ]),
        r("whiteboard_eraser", "Cancellino da lavagna", "Scrivania", ["cancellino","whiteboard_eraser"], [
            p("grip", "Impugnatura", "Permette la presa.", "Il dorso rigido trasferisce la pressione.", "box", (55, 74, 18)),
            p("pad", "Feltro", "Rimuove i segni.", "La superficie raccoglie residui di inchiostro cancellabile.", "board", (53, 65, 3)),
            p("mount", "Supporto", "Unisce i materiali.", "Una base trattiene il panno sotto la presa.", "board", (53, 65, 3)),
        ]),
        r("usb_cable", "Cavo USB", "Elettronica", ["cavo usb","usb_data_cable"], [
            p("wire", "Cavo flessibile", "Trasporta energia e segnali.", "Conduttori isolati sono raggruppati nella guaina.", "cylinder", (12, 72, 12)),
            p("plug_a", "Connettore A", "Collega un dispositivo.", "L'inserto realizza i contatti nella porta compatibile.", "box", (55, 74, 18)),
            p("plug_b", "Connettore B", "Completa il collegamento.", "Il terminale può differire per formato e numero di contatti.", "box", (55, 74, 18)),
        ]),
        r("hdmi_cable", "Cavo HDMI", "Elettronica", ["cavo hdmi","hdmi_connector_cable"], [
            p("cable", "Cavo", "Trasmette segnali.", "Diversi conduttori schermati sono dentro la guaina.", "cylinder", (12, 72, 12)),
            p("left", "Primo connettore", "Si inserisce nella porta.", "Il terminale guida l'accoppiamento dei contatti.", "box", (55, 74, 18)),
            p("right", "Secondo connettore", "Completa la connessione.", "Il guscio protegge la connessione all'altra estremità.", "box", (55, 74, 18)),
        ]),
        r("sd_card", "Scheda di memoria SD", "Elettronica", ["scheda sd","memory_card"], [
            p("shell", "Guscio", "Protegge la memoria.", "Il supporto plastico dà forma alla scheda.", "shell", (65, 82, 8)),
            p("contacts", "Contatti", "Collegano la scheda al lettore.", "Le superfici metalliche realizzano il collegamento.", "keypad", (46, 58, 3)),
            p("board", "Circuito interno", "Ospita la memoria.", "I componenti sono incapsulati e non osservabili senza aprire.", "board", (53, 65, 3)),
        ]),
        r("camera_tripod", "Treppiede fotografico", "Tempo libero", ["treppiede","photo_tripod"], [
            p("head", "Testa", "Sostiene la fotocamera.", "Il supporto permette di orientare l'attacco.", "box", (55, 74, 18)),
            p("column", "Colonna", "Regola l'altezza.", "La sezione centrale collega testa e struttura.", "cylinder", (12, 72, 12)),
            p("legs", "Gambe", "Stabilizzano.", "Tre appoggi separati ripartiscono il peso.", "cylinder", (12, 72, 12)),
            p("locks", "Chiusure", "Fissano l'estensione.", "Blocchi e morsetti trattengono le sezioni telescopiche.", "ring", (40, 12, 40)),
        ]),
        r("bicycle_pedal", "Pedale bicicletta", "Tempo libero", ["pedale bici","bike_pedal"], [
            p("body", "Piattaforma", "Sostiene il piede.", "La superficie trasmette la forza alla pedivella.", "box", (55, 74, 18)),
            p("axle", "Perno", "Collega alla pedivella.", "L'asse porta il carico e permette la rotazione.", "cylinder", (12, 72, 12)),
            p("bearings", "Cuscinetti", "Consentono la rotazione.", "Elementi volventi riducono attrito fra corpo e asse.", "ring", (40, 12, 40)),
            p("reflector", "Catadiottro", "Riflette la luce.", "La superficie aumenta la visibilità in alcuni modelli.", "board", (53, 65, 3)),
        ]),
        r("bicycle_saddle", "Sella per bicicletta", "Tempo libero", ["sella bici","bike_saddle"], [
            p("top", "Rivestimento", "Forma la seduta.", "Il materiale esterno copre l'imbottitura.", "shell", (65, 82, 8)),
            p("padding", "Imbottitura", "Distribuisce il carico.", "Lo strato cedevole assorbe parte della pressione.", "box", (55, 74, 18)),
            p("rails", "Binari", "Collegano al reggisella.", "Le aste inferiori trasferiscono le forze al supporto.", "cylinder", (12, 72, 12)),
        ]),
        r("tennis_ball", "Pallina da tennis", "Tempo libero", ["palla tennis","tennis_ball"], [
            p("core", "Nucleo elastico", "Conserva la forma.", "Il guscio cavo può contenere gas in pressione.", "box", (55, 74, 18)),
            p("felt", "Rivestimento in feltro", "Modifica attrito e traiettoria.", "Le fibre agiscono sul contatto e sull'aria.", "shell", (65, 82, 8)),
            p("seam", "Giunzione", "Unisce il rivestimento.", "La linea curva delimita i pannelli superficiali.", "ring", (40, 12, 40)),
        ]),
        r("table_tennis_racket", "Racchetta ping pong", "Tempo libero", ["racchetta ping pong","pingpong_paddle"], [
            p("handle", "Manico", "Consente la presa.", "L'impugnatura trasferisce il movimento alla pala.", "cylinder", (12, 72, 12)),
            p("blade", "Pala", "Sostiene le superfici.", "Il pannello rigido fornisce il nucleo della racchetta.", "board", (53, 65, 3)),
            p("rubber", "Gomma", "Interagisce con la pallina.", "Il rivestimento determina parte dell'aderenza e rimbalzo.", "board", (53, 65, 3)),
        ]),
        r("yo_yo", "Yo-yo", "Tempo libero", ["yoyo","yo yo"], [
            p("half_a", "Prima metà", "Contribuisce all'inerzia.", "Un disco ruota attorno all'asse centrale.", "cylinder", (12, 72, 12)),
            p("axle", "Asse", "Collega le metà.", "Il perno sostiene la rotazione e lo spago.", "cylinder", (12, 72, 12)),
            p("half_b", "Seconda metà", "Bilancia l'insieme.", "L'altro disco completa la massa rotante.", "cylinder", (12, 72, 12)),
            p("string", "Cordino", "Consente salita e discesa.", "Si avvolge sull'asse durante la rotazione.", "spring", (22, 35, 22)),
        ]),
        r("paintbrush", "Pennello da pittura", "Tempo libero", ["pennello","paint_brush"], [
            p("handle", "Manico", "Permette la presa.", "L'impugnatura guida il movimento della mano.", "cylinder", (12, 72, 12)),
            p("ferrule", "Ghiera", "Trattiene le setole.", "La fascia unisce fibra e manico.", "ring", (40, 12, 40)),
            p("bristles", "Setole", "Distribuiscono il colore.", "Le fibre trasferiscono la pittura alla superficie.", "keypad", (46, 58, 3)),
        ]),
        r("paint_roller", "Rullo da pittura", "Tempo libero", ["rullo vernice","paint_roller"], [
            p("handle", "Manico", "Permette la presa.", "La zona inferiore guida il movimento.", "cylinder", (12, 72, 12)),
            p("frame", "Telaio", "Sostiene il rullo.", "Il supporto metallico forma un asse di rotazione.", "cylinder", (12, 72, 12)),
            p("roller", "Manicotto", "Applica la pittura.", "Il cilindro poroso assorbe e distribuisce vernice.", "cylinder", (12, 72, 12)),
        ]),
    ]
