"""Original educational kitchen recipes. Not measured CAD or repair instructions."""
SOURCES = {
    "moka": ("Bialetti — esempio di struttura della moka", "https://bialetti-cookware.zendesk.com/hc/en-us/articles/5416235346322-How-to-use-the-Moka-Express"),
    "press": ("Bodum — recipiente, stantuffo e filtro di una French press", "https://www.bodum.com/nl/nl/1932-17-chambord"),
    "grinder": ("HARIO — gruppi di un macinacaffè manuale", "https://www.hario-europe.com/products/coffee-grinder-smart-g"),
    "pepper": ("Peugeot — principio delle macine per pepe", "https://fr.peugeot-saveurs.com/en_fr/inspiration/why-is-a-pepper-grinder-so-important/"),
    "tea": ("OXO — cestello, supporti e coperchio di un infusore", "https://www.oxo.com/oxo-tea-infuser-basket.html"),
    "citrus": ("OXO — spremiagrumi manuale con filtro e recipiente", "https://www.oxo.com/small-citrus-juicer.html"),
    "spinner": ("OXO — cestello, pompa e freno di una centrifuga", "https://www.oxo.com/salad-spinner.html"),
    "rolling": ("OXO — esempio di mattarello con impugnature", "https://www.oxo.com/shop/kitchenware/tools-gadgets/baking-pastry-tools/non-stick-rolling-pin.html"),
    "whisk": ("OXO — fili e impugnatura di una frusta", "https://www.oxo.com/11-whisk-394.html"),
}
HOT = " Non aprire o smontare recipienti caldi o in pressione; non modificare le valvole."


def recipes(r, p):
    return [
        r("moka_pot", "Caffettiera moka", "Cucina", ("moka", "caffettiera_moka", "stovetop_coffee_maker"), [
            p("boiler", "Caldaia", "Contiene l'acqua prima dell'erogazione.", "È il recipiente inferiore. Riscaldandosi, l'aria e il vapore contribuiscono a spingere l'acqua verso il filtro.", "cylinder", (56, 58, 56), (0,-47,0)),
            p("funnel", "Imbuto portacaffè", "Contiene il caffè macinato.", "Il condotto inferiore pesca l'acqua e il cestello la distribuisce nel caffè; le forature sono schematiche.", "cone", (43, 45, 43), (0,-13,0)),
            p("filter", "Piastrina filtrante", "Trattiene parte dei residui solidi.", "La piastra forata è alla base del raccoglitore. Non è un filtro per rendere potabile l'acqua.", "cylinder", (45,2,45), (0,11,0)),
            p("gasket", "Guarnizione", "Contribuisce alla tenuta fra le due metà.", "Si appoggia alle superfici di accoppiamento; dimensioni e materiale dipendono dalla caffettiera.", "ring", (49,3,49), (0,13,0)),
            p("collector", "Raccoglitore e camino", "Raccoglie il caffè che risale.", "Il condotto centrale e il recipiente superiore sono un gruppo semplificato, non separati in ogni particolare.", "cylinder", (61,67,61), (0,48,0)),
            p("lid_handle", "Coperchio e presa", "Chiudono superiormente e consentono la presa.", "Manico, pomolo e coperchio sono raggruppati; non ne viene verificata la temperatura.", "box", (75,8,60), (12,85,0)),
            p("valve", "Valvola di sicurezza", "È un elemento di sicurezza della caldaia.", "Non è un comando da regolare durante l'uso. L'immagine non ne verifica il funzionamento o la pulizia.", "cylinder", (8,9,8), (29,-36,0)),
        ], note=HOT, refs=(SOURCES["moka"],)),
        r("french_press", "Caffettiera a stantuffo", "Cucina", ("french_press_coffee_maker", "caffettiera_a_stantuffo", "coffee_plunger"), [
            p("beaker", "Recipiente", "Contiene acqua e caffè durante l'infusione.", "Il corpo è illustrato come una parete cilindrica; il materiale e la capacità non sono misurati.", "ring", (66,110,66), (0,0,0)),
            p("base_frame", "Base e supporto", "Sostengono il recipiente.", "Il telaio e la presa esterna sono riuniti; alcune caffettiere non hanno un telaio separato.", "shell", (78,115,70), (0,0,-5)),
            p("rod", "Asta dello stantuffo", "Trasmette la pressione al filtro.", "Scorre nel coperchio e guida il gruppo filtrante verso il fondo.", "cylinder", (5,128,5), (0,20,0)),
            p("filter", "Gruppo filtrante", "Separa gran parte dei fondi dalla bevanda.", "Rete, supporti e bordo elastico sono raggruppati. Il disegno non specifica la finezza della rete.", "cylinder", (61,5,61), (0,-35,0)),
            p("lid", "Coperchio e pomolo", "Guidano l'asta e permettono di premere.", "Il coperchio non trasforma il recipiente in una camera a pressione.", "cylinder", (69,12,69), (0,60,0)),
        ], note=" Attenzione a liquidi e superfici caldi.", refs=(SOURCES["press"],)),
        r("manual_coffee_grinder", "Macinacaffè manuale", "Cucina", ("hand_coffee_grinder", "macinacaffe_manuale", "manual_burr_grinder"), [
            p("hopper", "Tramoggia", "Contiene i chicchi da macinare.", "La gravità li porta verso il gruppo di macinazione.", "ring", (47,62,47), (0,28,0)),
            p("handle", "Manovella", "Trasmette il movimento della mano.", "La leva fa ruotare l'albero; la presa è semplificata.", "box", (83,7,13), (25,65,0)),
            p("shaft", "Albero", "Collega manovella e macina interna.", "Ruota in supporti che aiutano a tenere allineato il meccanismo.", "cylinder", (5,93,5), (0,17,0)),
            p("burrs", "Coppia di macine", "Frantuma e riduce i chicchi.", "La variante illustrata usa una macina interna e una esterna, raggruppate; non lame rotanti.", "cone", (34,29,34), (0,-7,0)),
            p("adjuster", "Regolazione della macinatura", "Varia la distanza utile fra le macine.", "Il registro modifica la granulometria; il numero delle posizioni non è dedotto dalla foto.", "ring", (24,6,24), (0,-25,0)),
            p("catcher", "Raccoglitore", "Riceve il caffè macinato.", "È sotto le macine e non contiene un motore elettrico.", "cylinder", (47,43,47), (0,-50,0)),
        ], refs=(SOURCES["grinder"],)),
        r("pepper_mill", "Macinapepe manuale", "Cucina", ("macinapepe", "manual_pepper_grinder", "pepper_grinder"), [
            p("body", "Corpo e serbatoio", "Contengono i grani di pepe.", "La cavità alimenta il meccanismo posto alla base.", "bottle", (44,113,44), (0,0,0)),
            p("head", "Testa di presa", "Permette di ruotare il comando.", "Nella variante rappresentata la testa trasmette il movimento all'albero centrale.", "cylinder", (43,24,43), (0,70,0)),
            p("shaft", "Albero di trasmissione", "Trasferisce la rotazione alle macine.", "Il collegamento interno mantiene il comando e il meccanismo solidali.", "cylinder", (4,103,4), (0,0,0)),
            p("burrs", "Meccanismo di macinazione", "Spezza e macina i grani.", "Le superfici dentate guidano e riducono il pepe; un macinasale può avere un meccanismo differente.", "cone", (28,19,28), (0,-43,0)),
            p("setting", "Registro", "Regola la macinatura nella variante illustrata.", "La regolazione agisce sull'accoppiamento delle macine; non determina dosi o valori nutrizionali.", "ring", (21,7,21), (0,88,0)),
        ], refs=(SOURCES["pepper"],)),
        r("tea_infuser", "Infusore da tè a cestello", "Cucina", ("tea_basket", "basket_tea_infuser", "infusore_te", "filtro_te"), [
            p("basket", "Cestello filtrante", "Contiene le foglie durante l'infusione.", "Le aperture lasciano circolare l'acqua; la rete è rappresentata in modo schematico.", "ring", (50,66,50), (0,0,0)),
            p("rim", "Bordo di appoggio", "Sostiene il cestello sulla tazza.", "Le prese laterali si appoggiano al bordo; la compatibilità con una tazza non è verificata.", "box", (89,6,20), (0,35,0)),
            p("lid", "Coperchio", "Copre l'infusore.", "In alcune varianti può essere usato anche come base raccogligocce.", "cylinder", (62,5,62), (0,44,0)),
        ], refs=(SOURCES["tea"],)),
        r("citrus_juicer", "Spremiagrumi manuale", "Cucina", ("manual_citrus_juicer", "spremiagrumi_manuale", "citrus_reamer"), [
            p("reamer", "Cono spremitore", "Preme la polpa durante la rotazione del frutto.", "Le nervature reali aiutano a estrarre il succo; qui il gruppo è stilizzato.", "cone", (42,36,42), (0,49,0)),
            p("strainer", "Filtro", "Trattiene semi e parte della polpa.", "Le aperture fanno scendere il succo nel recipiente sottostante.", "ring", (75,7,75), (0,31,0)),
            p("cup", "Recipiente", "Raccoglie il succo.", "Il beccuccio e le eventuali tacche sono raggruppati; nessuna misura di volume è ricavata dal disegno.", "cylinder", (73,58,73), (0,-4,0)),
        ], refs=(SOURCES["citrus"],)),
        r("oil_dispenser", "Oliera con beccuccio", "Cucina", ("oliera", "oil_pourer", "oil_bottle_dispenser"), [
            p("bottle", "Contenitore", "Conserva l'olio.", "Il corpo e il collo sono un unico gruppo; il materiale non è identificato da questa ricetta.", "bottle", (50,122,50), (0,0,0)),
            p("seal", "Inserto di tenuta", "Accoppia il beccuccio al collo.", "L'inserto limita le perdite fra le due parti; non ne certifica l'ermeticità.", "ring", (24,14,24), (0,64,0)),
            p("spout", "Beccuccio", "Guida l'uscita dell'olio.", "Il passaggio è schematico; alcuni versatori hanno un condotto separato per l'aria.", "cylinder", (10,32,10), (0,84,0)),
            p("cap", "Coperchietto", "Copre l'uscita quando non è in uso.", "Chiusure e sistemi antigoccia variano fra oliere.", "cylinder", (15,7,15), (0,104,0)),
        ]),
        r("glass_jar", "Barattolo con coperchio a vite", "Cucina", ("barattolo_vetro", "screw_lid_jar", "glass_storage_jar"), [
            p("body", "Barattolo", "Contiene il prodotto.", "Corpo e fondo sono un gruppo continuo; il disegno non verifica resistenza termica o integrità.", "cylinder", (73,94,73), (0,0,0)),
            p("lid", "Coperchio filettato", "Chiude l'apertura.", "Il bordo si accoppia al collo; la filettatura esatta non è riprodotta.", "cylinder", (78,12,78), (0,55,0)),
            p("liner", "Zona di tenuta", "Contribuisce alla chiusura fra coperchio e vetro.", "Può essere integrata nel coperchio e non essere rimovibile. Non è una verifica della sicurezza di una conserva.", "ring", (66,2,66), (0,49,0)),
        ]),
        r("food_storage_box", "Contenitore alimentare a scatto", "Cucina", ("food_container", "contenitore_alimentare", "clip_food_box"), [
            p("box", "Vaschetta", "Contiene gli alimenti.", "Fondo e pareti sono un unico gruppo; le misure sono illustrative.", "shell", (112,72,51), (0,0,0)),
            p("lid", "Coperchio", "Copre l'apertura della vaschetta.", "Si appoggia al bordo e distribuisce la pressione delle chiusure.", "box", (117,77,4), (0,0,28)),
            p("gasket", "Guarnizione perimetrale", "Contribuisce alla tenuta.", "La sagoma semplificata indica il bordo di contatto. Non tutte le scatole hanno una guarnizione separata.", "shell", (106,66,2), (0,0,25)),
            p("clips", "Chiusure a scatto", "Trattengono il coperchio.", "Sono riunite in un gruppo simbolico; numero e posizione dipendono dal contenitore.", "box", (123,13,7), (0,0,30)),
        ]),
        r("kitchen_scale", "Bilancia digitale da cucina", "Cucina", ("digital_kitchen_scale", "bilancia_cucina", "food_scale"), [
            p("platform", "Piano di appoggio", "Sostiene ciò che viene pesato.", "Trasmette il carico al sistema di misura.", "box", (104,94,4), (0,12,14)),
            p("sensor", "Gruppo di misura", "Rileva la forza applicata.", "Nella variante illustrata la deformazione di un elemento sensibile viene convertita in un segnale elettrico.", "box", (44,31,6), (0,12,7)),
            p("board", "Scheda di lettura", "Elabora il segnale del sensore.", "Tara e visualizzazione sono gestite dall'elettronica; nessuna precisione è dedotta dal modello.", "board", (58,30,2), (0,-34,4)),
            p("display", "Display e comandi", "Mostrano il risultato e permettono la tara.", "La finestra e i tasti sono un gruppo funzionale.", "box", (65,22,3), (0,-38,13)),
            p("case", "Base e vano alimentazione", "Contengono le parti e l'alimentazione.", "La disposizione delle pile varia. Lo schema non misura il peso di oggetti nella foto.", "shell", (113,135,13), (0,0,-2)),
        ]),
        r("digital_kitchen_timer", "Timer digitale da cucina", "Cucina", ("digital_timer", "timer_digitale", "kitchen_countdown_timer"), [
            p("display", "Display", "Mostra il tempo impostato o residuo.", "Il conteggio è prodotto dal circuito, non da una ruota meccanica.", "box", (55,30,2), (0,13,8)),
            p("buttons", "Pulsanti", "Consentono di impostare e avviare il conteggio.", "Le pressioni sono lette dalla scheda.", "keypad", (54,19,3), (0,-22,7)),
            p("board", "Circuito temporizzatore", "Tiene il conteggio e comanda l'avviso.", "L'orologio elettronico e il controllo sono raggruppati senza specificare i componenti interni.", "board", (60,52,2), (0,0,2)),
            p("buzzer", "Segnalatore acustico", "Emette l'avviso alla fine del conteggio.", "È rappresentato un trasduttore compatto; suono e volume non sono simulati.", "cylinder", (19,5,19), (16,-18,-1)),
            p("housing", "Involucro e vano pila", "Proteggono l'elettronica.", "Pila, supporto o magnete posteriore dipendono dalla variante e sono raggruppati.", "shell", (73,68,15), (0,0,-3)),
        ]),
        r("salad_spinner", "Centrifuga per insalata", "Cucina", ("centrifuga_insalata", "lettuce_spinner", "salad_dryer"), [
            p("bowl", "Ciotola", "Raccoglie l'acqua che esce dal cestello.", "La ciotola resta ferma all’esterno del cestello che ruota e raccoglie le gocce espulse.", "ring", (105,69,105), (0,-7,0)),
            p("basket", "Cestello forato", "Sostiene e fa ruotare le foglie.", "Le aperture permettono all'acqua di separarsi dalle foglie; le forature sono schematiche.", "ring", (87,57,87), (0,0,0)),
            p("lid", "Coperchio e trasmissione", "Guidano il cestello e trasmettono il movimento.", "Gli ingranaggi sono raggruppati; sono possibili comandi a pompa, corda o manovella.", "cylinder", (110,12,110), (0,37,0)),
            p("pump", "Comando a pressione", "Aziona la rotazione nella variante illustrata.", "La corsa verticale viene trasmessa al meccanismo nel coperchio.", "cylinder", (32,21,32), (0,54,0)),
            p("brake", "Freno", "Consente di rallentare il cestello.", "È un gruppo funzionale, non una ricostruzione del brevetto o delle superfici reali.", "box", (20,7,20), (33,46,0)),
        ], refs=(SOURCES["spinner"],)),
        r("rolling_pin", "Mattarello con manici", "Cucina", ("mattarello", "handled_rolling_pin", "pastry_roller"), [
            p("roller", "Rullo", "Stende l'impasto.", "La superficie cilindrica distribuisce la pressione; il rullo è mostrato verticalmente per esplorarlo.", "cylinder", (37,125,37), (0,0,0)),
            p("axle", "Perno interno", "Sostiene il rullo nella variante rotante.", "Il rullo può girare attorno al perno. I mattarelli monoblocco non hanno questo sistema.", "cylinder", (5,175,5), (0,0,0)),
            p("handle_left", "Prima impugnatura", "Permette di guidare il rullo.", "La presa è solidale al supporto; forma e rivestimento sono indicativi.", "cylinder", (20,39,20), (0,-86,0)),
            p("handle_right", "Seconda impugnatura", "Consente la guida con l'altra mano.", "Si trova all'estremità opposta dello stesso asse.", "cylinder", (20,39,20), (0,86,0)),
        ], refs=(SOURCES["rolling"],)),
        r("balloon_whisk", "Frusta da cucina", "Cucina", ("frusta_cucina", "wire_whisk", "balloon_whisk_tool"), [
            p("handle", "Impugnatura", "Permette di muovere la frusta.", "La presa trasferisce il movimento ai fili curvi.", "cylinder", (19,71,19), (0,-53,0)),
            p("collar", "Collare di fissaggio", "Trattiene le estremità dei fili.", "Può essere integrato o incollato al manico, non necessariamente smontabile.", "ring", (21,12,21), (0,-11,0)),
            p("wires", "Gruppo di fili curvi", "Mescola e incorpora aria negli ingredienti.", "È disegnato come un inviluppo aperto: numero e curvatura dei fili reali non sono riprodotti.", "ring", (47,87,30), (0,37,0)),
        ], refs=(SOURCES["whisk"],)),
    ]
