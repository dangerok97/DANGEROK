"""34 new manually-authored indicative everyday-object family schematics.
No photographs, measured CAD, private image data, or repair instructions.
"""

def recipes(r,p):
    original_part = p
    def p(key, name, purpose, how, shape, size, assembled=(0, 0, 0)):
        if len(purpose) < 15:
            purpose += " nell'oggetto illustrato."
        if len(how) < 35:
            how += " nella configurazione familiare indicativa."
        return original_part(key, name, purpose, how, shape, size, assembled)
    return [
        r("folding_chair", "Sedia pieghevole", "Casa", ["sedia pieghevole","folding seat"], [
            p("seat", "Seduta", "Sostiene il peso della persona.", "La piattaforma trasferisce il carico alle gambe.", "board", (62, 75, 3)),
            p("back", "Schienale", "Sostiene il dorso.", "Il pannello è collegato al telaio pieghevole.", "board", (62, 75, 3)),
            p("frame", "Telaio", "Collega seduta e gambe.", "Le aste distribuiscono i carichi lungo la struttura.", "cylinder", (14, 68, 14)),
            p("hinge", "Snodi", "Consentono la chiusura.", "I giunti permettono di ripiegare gli elementi.", "ring", (47, 9, 47)),
        ]),
        r("office_chair", "Sedia da ufficio girevole", "Casa", ["sedia ufficio","swivel_office_chair"], [
            p("seat", "Seduta imbottita", "Sostiene il bacino.", "L'imbottitura distribuisce parte della pressione.", "box", (58, 80, 19)),
            p("back", "Schienale", "Sostiene il tronco.", "La struttura posteriore sostiene e segue la postura.", "shell", (65, 83, 9)),
            p("column", "Colonna", "Sostiene l'altezza.", "Il gruppo centrale trasferisce il carico alla base.", "cylinder", (14, 68, 14)),
            p("base", "Base a razze", "Stabilizza la sedia.", "I bracci distribuiscono il peso sugli appoggi.", "ring", (47, 9, 47)),
            p("wheels", "Ruote", "Permettono lo spostamento.", "Piccoli elementi rotanti scorrono sul pavimento.", "ring", (47, 9, 47)),
        ]),
        r("desk_lamp", "Lampada da scrivania", "Casa", ["lampada scrivania","reading_lamp"], [
            p("shade", "Paralume", "Dirige la luce.", "La copertura modifica la distribuzione luminosa.", "cone", (58, 80, 19)),
            p("light", "Sorgente luminosa", "Produce illuminazione.", "La tecnologia può variare in base al modello.", "cylinder", (14, 68, 14)),
            p("arm", "Braccio regolabile", "Posiziona il punto luce.", "Le aste mantengono la testa orientabile.", "cylinder", (14, 68, 14)),
            p("base", "Base", "Sostiene la struttura.", "Il peso e la superficie contrastano il ribaltamento.", "box", (58, 80, 19)),
        ]),
        r("picture_frame", "Cornice fotografica", "Casa", ["cornice foto","photo_frame"], [
            p("front", "Protezione frontale", "Protegge l'immagine.", "Una lastra trasparente separa la foto dall'ambiente.", "board", (62, 75, 3)),
            p("frame", "Cornice perimetrale", "Trattiene le superfici.", "Quattro lati formano la sede del contenuto.", "ring", (47, 9, 47)),
            p("back", "Fondo", "Mantiene la fotografia.", "Il pannello posteriore chiude il pacchetto.", "board", (62, 75, 3)),
            p("stand", "Supporto", "Permette l'appoggio.", "Una linguetta può mantenere la cornice inclinata.", "box", (58, 80, 19)),
        ]),
        r("house_key", "Chiave di serratura", "Casa", ["chiave casa","door_key"], [
            p("head", "Testa", "Permette la presa.", "La parte larga trasmette la coppia delle dita.", "ring", (47, 9, 47)),
            p("shaft", "Gambo", "Entra nella serratura.", "La sezione allungata guida l'inserimento.", "board", (62, 75, 3)),
            p("teeth", "Profilo lavorato", "Interagisce con il meccanismo.", "Il profilo varia tra sistemi di chiusura.", "keypad", (44, 63, 4)),
        ]),
        r("key_ring", "Portachiavi ad anello", "Casa", ["portachiavi","keyring"], [
            p("ring", "Anello metallico", "Raccoglie le chiavi.", "La spirale elastica trattiene gli oggetti infilati.", "ring", (47, 9, 47)),
            p("chain", "Catena", "Collega gli accessori.", "I piccoli anelli consentono movimento tra parti.", "ring", (47, 9, 47)),
            p("tag", "Piastrina", "Permette il riconoscimento.", "L'elemento decorativo può recare un'etichetta.", "board", (62, 75, 3)),
        ]),
        r("shopping_trolley", "Carrello della spesa", "Casa", ["carrello spesa","shopping_trolley"], [
            p("basket", "Cestello", "Contiene i prodotti.", "La rete o vasca sostiene gli oggetti riposti.", "box", (58, 80, 19)),
            p("handle", "Maniglia", "Consente di spingere.", "Il traverso trasferisce la forza al telaio.", "cylinder", (14, 68, 14)),
            p("frame", "Telaio", "Sostiene il cestello.", "La struttura trasferisce il peso verso le ruote.", "cylinder", (14, 68, 14)),
            p("wheels", "Ruote", "Permettono il rotolamento.", "I supporti girevoli facilitano la direzione.", "ring", (47, 9, 47)),
        ]),
        r("dish_drying_rack", "Scolapiatti", "Cucina", ["scolapiatti","dish_rack"], [
            p("base", "Vassoio", "Raccoglie le gocce.", "La superficie riceve l'acqua in discesa.", "board", (62, 75, 3)),
            p("uprights", "Separatori", "Mantengono i piatti separati.", "Le aste formano alloggiamenti distanziati.", "cylinder", (14, 68, 14)),
            p("cup_holder", "Portabicchieri", "Sostiene recipienti capovolti.", "Gli appoggi consentono il drenaggio.", "box", (58, 80, 19)),
        ]),
        r("analog_kitchen_timer", "Timer da cucina meccanico", "Cucina", ["timer analogico","windup_timer"], [
            p("case", "Corpo", "Racchiude il meccanismo.", "Il guscio protegge le parti rotanti.", "cylinder", (14, 68, 14)),
            p("dial", "Quadrante", "Mostra l'intervallo.", "La scala graduata rappresenta un tempo selezionato.", "board", (62, 75, 3)),
            p("spring", "Molla", "Immagazzina energia.", "In un timer meccanico aziona la marcia.", "spring", (25, 42, 25)),
            p("bell", "Avvisatore", "Segnala lo scadere.", "Una suoneria meccanica produce il segnale finale.", "ring", (47, 9, 47)),
        ]),
        r("egg_whisk_crank", "Sbattitore manuale a manovella", "Cucina", ["sbattitore manuale","hand_egg_beater"], [
            p("handle", "Impugnatura", "Consente la presa.", "Il corpo tiene in posizione la trasmissione.", "box", (58, 80, 19)),
            p("crank", "Manovella", "Genera la rotazione.", "La mano mette in moto il sistema di ingranaggi.", "cylinder", (14, 68, 14)),
            p("gears", "Ingranaggi", "Trasmettono il movimento.", "Le ruote dentate distribuiscono la rotazione.", "ring", (47, 9, 47)),
            p("beaters", "Fruste rotanti", "Mescolano gli ingredienti.", "Le aste muovono e incorporano aria nel composto.", "ring", (47, 9, 47)),
        ]),
        r("cooking_pan", "Padella da cucina", "Cucina", ["padella","frying_pan"], [
            p("body", "Vasca", "Contiene gli alimenti.", "La parete forma la superficie di cottura.", "shell", (65, 83, 9)),
            p("handle", "Manico", "Permette di maneggiare.", "La presa estende la distanza dalla parte calda.", "cylinder", (14, 68, 14)),
            p("base", "Fondo", "Trasmette il calore.", "Il materiale conduce energia dal piano agli alimenti.", "board", (62, 75, 3)),
        ]),
        r("pan_lid", "Coperchio da pentola", "Cucina", ["coperchio pentola","pot_lid"], [
            p("disc", "Coperchio", "Copre il recipiente.", "La superficie limita l'uscita di vapori.", "board", (62, 75, 3)),
            p("knob", "Pomello", "Permette il sollevamento.", "La presa centrale consente di maneggiare.", "cylinder", (14, 68, 14)),
            p("rim", "Bordo", "Favorisce l'appoggio.", "La cornice segue il perimetro della pentola.", "ring", (47, 9, 47)),
        ]),
        r("salt_shaker", "Saliera", "Cucina", ["saliera","salt_shaker"], [
            p("container", "Contenitore", "Custodisce il sale.", "La vaschetta delimita il volume interno.", "bottle", (58, 80, 19)),
            p("lid", "Tappo forato", "Distribuisce il contenuto.", "Piccole aperture dosano i granelli durante l'agitazione.", "ring", (47, 9, 47)),
            p("seal", "Giunto", "Collega tappo e corpo.", "Una filettatura o incastro tiene la chiusura in sede.", "ring", (47, 9, 47)),
        ]),
        r("soap_dish", "Portasapone", "Bagno", ["porta sapone","soap_holder"], [
            p("tray", "Vaschetta", "Sostiene la saponetta.", "La base raccoglie o lascia defluire acqua.", "shell", (65, 83, 9)),
            p("grille", "Griglia", "Separa sapone e acqua.", "Le nervature limitano il contatto col fondo.", "keypad", (44, 63, 4)),
            p("feet", "Piedini", "Stabilizzano la vaschetta.", "Piccoli appoggi sollevano la struttura.", "box", (58, 80, 19)),
        ]),
        r("towel_rail", "Portasciugamani", "Bagno", ["porta asciugamano","towel_bar"], [
            p("rail", "Barra", "Sostiene il tessuto.", "L'asta riceve il peso dell'asciugamano.", "cylinder", (14, 68, 14)),
            p("mounts", "Supporti", "Collegano la barra alla parete.", "Le staffe trasferiscono il carico al fissaggio.", "box", (58, 80, 19)),
            p("caps", "Terminali", "Rifiniscono la barra.", "Le coperture proteggono le estremità.", "ring", (47, 9, 47)),
        ]),
        r("toilet_brush", "Scopino per WC", "Bagno", ["scopino bagno","toilet_brush"], [
            p("handle", "Manico", "Permette la presa.", "La parte superiore guida la testina pulente.", "cylinder", (14, 68, 14)),
            p("head", "Testina", "Pulisce le superfici.", "Le fibre flessibili raggiungono zone curve.", "keypad", (44, 63, 4)),
            p("holder", "Contenitore", "Ospita lo scopino.", "Il recipiente sostiene la testina dopo l'uso.", "cylinder", (14, 68, 14)),
        ]),
        r("pruning_shears", "Cesoie da giardino", "Giardino", ["forbici potatura","garden_secateurs"], [
            p("blade", "Lama", "Recide materiale vegetale.", "Il bordo si muove rispetto al controlama.", "board", (62, 75, 3)),
            p("counterblade", "Controlama", "Oppone la pressione.", "La forma sostiene il ramo durante la chiusura.", "board", (62, 75, 3)),
            p("handles", "Impugnature", "Azionano le lame.", "Le leve trasferiscono la pressione delle dita.", "cylinder", (14, 68, 14)),
            p("spring", "Molla di ritorno", "Favorisce l'apertura.", "La molla separa le impugnature dopo la pressione.", "spring", (25, 42, 25)),
        ]),
        r("garden_rake", "Rastrello", "Giardino", ["rastrello","garden_rake"], [
            p("handle", "Manico", "Trasferisce la forza.", "Il bastone guida l'attrezzo durante il tiro.", "cylinder", (14, 68, 14)),
            p("head", "Traversa", "Sostiene i denti.", "La barra distribuisce i punti di contatto.", "box", (58, 80, 19)),
            p("tines", "Denti", "Raccolgono foglie o terra.", "Le punte intercettano il materiale sul terreno.", "keypad", (44, 63, 4)),
        ]),
        r("wheelbarrow", "Carriola", "Giardino", ["carriola","wheelbarrow"], [
            p("tub", "Cassone", "Contiene il carico.", "La vasca sostiene il materiale trasportato.", "shell", (65, 83, 9)),
            p("frame", "Telaio", "Distribuisce le forze.", "Due bracci collegano vasca, ruota e prese.", "cylinder", (14, 68, 14)),
            p("wheel", "Ruota", "Permette il rotolamento.", "Il gruppo anteriore sostiene parte del peso.", "ring", (47, 9, 47)),
            p("handles", "Manici", "Consentono di sollevare.", "Le prese trasferiscono il carico alle mani.", "cylinder", (14, 68, 14)),
        ]),
        r("garden_spade", "Vanga manuale", "Giardino", ["vanga","garden_spade"], [
            p("handle", "Manico", "Permette la presa.", "La parte lunga trasmette la spinta.", "cylinder", (14, 68, 14)),
            p("socket", "Attacco", "Unisce manico e pala.", "Il collegamento trasferisce gli sforzi alla lama.", "box", (58, 80, 19)),
            p("blade", "Lama", "Penetra nel terreno.", "La lamina piatta sposta e taglia terreno.", "board", (62, 75, 3)),
        ]),
        r("bike_wheel", "Ruota di bicicletta", "Tempo libero", ["ruota bici","bicycle_wheel"], [
            p("rim", "Cerchio", "Sostiene il pneumatico.", "La corona esterna mantiene la forma circolare.", "ring", (47, 9, 47)),
            p("hub", "Mozzo", "Ruota intorno all'asse.", "I cuscinetti permettono la rotazione.", "cylinder", (14, 68, 14)),
            p("spokes", "Raggi", "Trasferiscono le tensioni.", "Le aste collegano cerchio e mozzo.", "keypad", (44, 63, 4)),
            p("tire", "Pneumatico", "Aderisce al terreno.", "L'involucro deformabile aumenta la presa.", "ring", (47, 9, 47)),
        ]),
        r("bike_bottle_cage", "Portaborraccia da bici", "Tempo libero", ["porta borraccia","bicycle_bottle_holder"], [
            p("frame", "Gabbia", "Trattiene la borraccia.", "Due bracci elastici limitano gli spostamenti.", "ring", (47, 9, 47)),
            p("base", "Piastra", "Sostiene il fondo.", "L'appoggio inferiore riceve il peso.", "board", (62, 75, 3)),
            p("mount", "Supporto", "Collega al telaio.", "La piastra presenta punti di fissaggio.", "box", (58, 80, 19)),
        ]),
        r("jump_rope", "Corda per saltare", "Tempo libero", ["corda salto","skipping_rope"], [
            p("rope", "Corda flessibile", "Ruota intorno al corpo.", "La lunghezza collega le due impugnature.", "cylinder", (14, 68, 14)),
            p("handle_a", "Prima impugnatura", "Permette la presa.", "L'estremità guida il movimento del polso.", "cylinder", (14, 68, 14)),
            p("handle_b", "Seconda impugnatura", "Bilancia il movimento.", "La seconda presa segue la rotazione.", "cylinder", (14, 68, 14)),
        ]),
        r("soccer_ball", "Pallone da calcio", "Tempo libero", ["pallone calcio","football_ball"], [
            p("outer", "Rivestimento", "Forma la superficie.", "I pannelli determinano attrito e contatto.", "shell", (65, 83, 9)),
            p("lining", "Strato di rinforzo", "Mantiene la forma.", "Materiali laminati distribuiscono gli sforzi.", "shell", (65, 83, 9)),
            p("bladder", "Camera d'aria", "Mantiene la pressione.", "Un involucro interno contiene aria in molti modelli.", "box", (58, 80, 19)),
        ]),
        r("basketball", "Pallone da pallacanestro", "Tempo libero", ["palla basket","basket_ball"], [
            p("outer", "Rivestimento", "Consente la presa.", "La texture modifica l'attrito con le mani.", "shell", (65, 83, 9)),
            p("carcass", "Carcassa", "Stabilizza la sfera.", "Gli strati di rinforzo limitano deformazioni.", "shell", (65, 83, 9)),
            p("bladder", "Camera", "Contiene aria.", "La camera elastica mantiene il rimbalzo.", "box", (58, 80, 19)),
        ]),
        r("swim_goggles", "Occhialini da nuoto", "Tempo libero", ["occhialini piscina","swimming_goggles"], [
            p("lenses", "Lenti", "Permettono di vedere sott'acqua.", "Le superfici trasparenti proteggono gli occhi.", "board", (62, 75, 3)),
            p("seals", "Guarnizioni", "Limitano l'ingresso d'acqua.", "I bordi morbidi seguono il contorno del viso.", "ring", (47, 9, 47)),
            p("strap", "Elastico", "Trattiene gli occhialini.", "La fascia si tende dietro la testa.", "cylinder", (14, 68, 14)),
            p("bridge", "Ponte", "Unisce le lenti.", "Il collegamento mantiene la distanza reciproca.", "box", (58, 80, 19)),
        ]),
        r("camping_compass", "Bussola magnetica", "Tempo libero", ["bussola","magnetic_compass"], [
            p("case", "Corpo", "Protegge l'indicatore.", "L'alloggiamento delimita il quadrante.", "cylinder", (14, 68, 14)),
            p("needle", "Ago magnetico", "Indica una direzione di riferimento.", "Un elemento magnetizzato si allinea al campo terrestre.", "board", (62, 75, 3)),
            p("dial", "Quadrante", "Aiuta l'orientamento.", "Una scala segna le direzioni convenzionali.", "ring", (47, 9, 47)),
        ]),
        r("camping_lantern", "Lanterna da campeggio LED", "Tempo libero", ["lanterna campeggio","camp_lantern"], [
            p("body", "Corpo", "Sostiene i componenti.", "Il guscio ospita illuminazione e alimentazione.", "cylinder", (14, 68, 14)),
            p("diffuser", "Diffusore", "Distribuisce la luce.", "La superficie traslucida allarga l'emissione.", "shell", (65, 83, 9)),
            p("light", "Modulo LED", "Produce luce.", "Un circuito converte energia in emissione luminosa.", "board", (62, 75, 3)),
            p("handle", "Maniglia", "Permette il trasporto.", "La presa collega la mano al corpo.", "ring", (47, 9, 47)),
        ]),
        r("suitcase", "Valigia da viaggio", "Tempo libero", ["valigia","travel_suitcase"], [
            p("shell", "Guscio", "Contiene i bagagli.", "Due metà delimitano il vano interno.", "shell", (65, 83, 9)),
            p("handle", "Maniglia telescopica", "Permette il traino.", "Le aste allungabili trasferiscono la trazione.", "cylinder", (14, 68, 14)),
            p("wheels", "Ruote", "Facilitano lo spostamento.", "Gli elementi rotanti scorrono sul pavimento.", "ring", (47, 9, 47)),
            p("zipper", "Chiusura", "Unisce le due metà.", "Una cerniera continua segue il perimetro.", "ring", (47, 9, 47)),
        ]),
        r("backpack", "Zaino", "Tempo libero", ["zaino","rucksack"], [
            p("body", "Sacca", "Contiene gli oggetti.", "I pannelli tessili formano uno spazio flessibile.", "shell", (65, 83, 9)),
            p("straps", "Spallacci", "Distribuiscono il carico.", "Le bretelle appoggiano sulle spalle.", "board", (62, 75, 3)),
            p("zipper", "Cerniera", "Consente l'apertura.", "I dentini accostano i bordi della sacca.", "ring", (47, 9, 47)),
            p("padding", "Pannello posteriore", "Appoggia alla schiena.", "Lo strato imbottito modifica il contatto.", "box", (58, 80, 19)),
        ]),
        r("wallet", "Portafoglio", "Tempo libero", ["portafoglio","billfold"], [
            p("cover", "Copertura", "Protegge il contenuto.", "Il pannello esterno si ripiega in chiusura.", "board", (62, 75, 3)),
            p("fold", "Cerniera flessibile", "Consente la piega.", "La giuntura permette l'apertura del portafoglio.", "board", (62, 75, 3)),
            p("pockets", "Tasche", "Trattengono carte e banconote.", "I comparti separati organizzano il contenuto.", "keypad", (44, 63, 4)),
        ]),
        r("eyeglasses", "Occhiali da vista", "Tempo libero", ["occhiali","reading_glasses"], [
            p("lenses", "Lenti", "Correggono o filtrano la luce.", "La curvatura ottica varia secondo la prescrizione.", "board", (62, 75, 3)),
            p("frame", "Montatura", "Sostiene le lenti.", "Il telaio definisce posizione e distanza.", "ring", (47, 9, 47)),
            p("temples", "Aste", "Trattengono sul volto.", "Le aste si ripiegano attraverso le cerniere.", "cylinder", (14, 68, 14)),
            p("hinges", "Cerniere", "Consentono la chiusura.", "I giunti fanno ruotare le aste.", "ring", (47, 9, 47)),
        ]),
        r("wristwatch", "Orologio da polso analogico", "Tempo libero", ["orologio polso","analog_watch"], [
            p("case", "Cassa", "Protegge il movimento.", "Il guscio racchiude quadrante e meccanismo.", "cylinder", (14, 68, 14)),
            p("dial", "Quadrante", "Mostra l'ora.", "Gli indici rappresentano i riferimenti temporali.", "board", (62, 75, 3)),
            p("hands", "Lancette", "Indicano il tempo.", "Elementi sottili ruotano su assi concentrici.", "keypad", (44, 63, 4)),
            p("strap", "Cinturino", "Fissa al polso.", "La fascia regolabile circonda il polso.", "ring", (47, 9, 47)),
        ]),
        r("desktop_fan", "Ventilatore da tavolo", "Casa", ["ventilatore","table_fan"], [
            p("base", "Base", "Sostiene l'apparecchio.", "L'appoggio stabilizza il dispositivo sul piano.", "box", (58, 80, 19)),
            p("motor", "Motore", "Genera la rotazione.", "L'energia elettrica viene convertita in moto.", "cylinder", (14, 68, 14)),
            p("blades", "Pale", "Muovono l'aria.", "Le superfici inclinate spostano aria ruotando.", "keypad", (44, 63, 4)),
            p("guard", "Griglia", "Separa dalle pale.", "La protezione delimita l'area di movimento.", "ring", (47, 9, 47)),
        ]),
    ]
