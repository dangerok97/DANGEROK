"""Distinct everyday mechanisms. Geometry is educational, not a physical model."""

def recipes(r, p):
    return [
        r("pencil_sharpener", "Temperamatite manuale", "Scrivania", ("temperamatite", "manual_pencil_sharpener", "pencil_sharpener_block"), [
            p("body", "Corpo di guida", "Mantiene la matita inclinata rispetto alla lama.", "Il foro conico è riassunto nel corpo; forma e angolo esatti non sono ricostruiti.", "box", (35,46,25), (0,0,0)),
            p("blade", "Lama", "Rimuove sottili trucioli durante la rotazione.", "Il filo lavora lungo il fianco della matita; non è una guida alla sostituzione o all'affilatura.", "box", (11,35,1), (0,0,14)),
            p("screw", "Vite di fissaggio", "Trattiene la lama sul corpo.", "Il fissaggio è rappresentativo, senza misure o specifiche del ricambio.", "cylinder", (4,7,4), (0,1,16)),
        ], note=" Non toccare il filo della lama."),
        r("correction_tape", "Correttore a nastro", "Scrivania", ("correttore_nastro", "whiteout_tape", "tape_corrector"), [
            p("housing", "Involucro", "Protegge e allinea le bobine.", "Le due metà e i supporti sono raggruppati.", "shell", (75,48,17), (0,0,0)),
            p("supply", "Bobina del nastro nuovo", "Contiene il supporto con lo strato coprente.", "Il nastro viene guidato verso la punta; non è una gomma abrasiva.", "ring", (28,9,28), (-16,0,2)),
            p("takeup", "Bobina di recupero", "Raccoglie il supporto dopo il trasferimento.", "Un meccanismo mantiene il nastro in tensione; disposizione e ingranaggi variano.", "ring", (19,9,19), (17,0,2)),
            p("tip", "Punta applicatrice", "Preme il nastro sulla carta.", "Lo strato coprente resta sulla superficie mentre il supporto prosegue alla bobina di recupero.", "box", (12,21,5), (33,-20,2)),
        ], refs=(("Tombow — nastro, applicatore e recupero", "https://www.tombowusa.com/products/mono-correction-tape-hybrid-style-10-pack"),)),
        r("binder_clip", "Fermacarte a pinza", "Scrivania", ("binder_clip_paper", "fermacarte_pinza", "foldback_clip"), [
            p("spring_body", "Corpo elastico", "Serra il mazzetto di fogli.", "La lamina piegata si deforma elasticamente; il volume è schematico, non una sezione esatta.", "shell", (42,26,20), (0,0,0)),
            p("lever_a", "Prima leva", "Aiuta ad aprire una ganascia.", "Il filo ripiegato fa da leva sul corpo; non è il pezzo che genera la forza elastica principale.", "ring", (29,37,3), (0,28,10)),
            p("lever_b", "Seconda leva", "Permette l'apertura insieme alla prima.", "Le due leve possono essere ripiegate lungo i fogli.", "ring", (29,37,3), (0,28,-10)),
        ]),
        r("ring_binder", "Raccoglitore ad anelli", "Scrivania", ("raccoglitore_anelli", "ring_folder", "ringbinder"), [
            p("cover", "Copertina", "Protegge i fogli.", "Le due facce e il dorso sono raggruppati come struttura di supporto.", "shell", (155,203,20), (0,0,-5)),
            p("spine", "Base del meccanismo", "Fissa gli anelli alla copertina.", "Il supporto mantiene allineate le metà degli anelli.", "box", (19,169,8), (-57,0,0)),
            p("rings", "Gruppo anelli", "Trattiene i fogli perforati.", "Sono schematizzati come un gruppo; numero, forma e distanza variano fra raccoglitori.", "ring", (33,112,7), (-57,0,10)),
            p("release", "Comando di apertura", "Apre o richiude il meccanismo nella variante illustrata.", "Leve e piastre elastiche sono semplificate; non tutti i raccoglitori usano lo stesso comando.", "box", (13,18,4), (-57,-82,4)),
        ]),
        r("desktop_tape_dispenser", "Dispenser da tavolo per nastro", "Scrivania", ("dispenser_nastro", "desktop_tape_holder", "scotch_dispenser"), [
            p("base", "Base", "Mantiene stabile il dispenser.", "Il peso e il fondo antiscivolo possono essere integrati; non sono misurati dalla scena.", "shell", (117,50,33), (0,0,0)),
            p("hub", "Supporto della bobina", "Consente la rotazione del rotolo.", "Il perno o inserto si accoppia al nucleo del nastro.", "cylinder", (15,29,15), (-26,12,0)),
            p("roll", "Rotolo di nastro", "Fornisce il materiale adesivo.", "È un gruppo consumabile distinto dal dispenser e si srotola durante il tiro.", "ring", (43,21,43), (-26,18,0)),
            p("cutter", "Bordo di taglio", "Separa la porzione prelevata.", "La dentatura è simbolica. Non toccare il bordo tagliente.", "box", (8,8,29), (52,12,0)),
        ]),
        r("staple_remover", "Levapunti a pinza", "Scrivania", ("levapunti", "staple_extractor", "claw_staple_remover"), [
            p("upper_jaw", "Ganascia superiore", "Fa presa sulla graffetta.", "Le punte sono raggruppate in una sagoma semplice, non affilate nel modello.", "box", (19,52,5), (0,0,8)),
            p("lower_jaw", "Ganascia inferiore", "Lavora insieme alla ganascia opposta.", "Il movimento coordinato solleva e piega il punto; non è una guida per rimuovere punti medici.", "box", (19,52,5), (0,0,-8)),
            p("pivot", "Perno", "Permette la rotazione relativa.", "Tiene unite le ganasce nella zona posteriore.", "cylinder", (7,16,7), (0,21,0)),
            p("spring", "Molla di ritorno", "Riapre la pinza quando viene rilasciata.", "È una rappresentazione del gruppo elastico; la forma della molla può differire.", "spring", (8,12,8), (0,12,0)),
        ]),
        r("hole_punch", "Perforatore da scrivania", "Scrivania", ("perforatrice_carta", "perforatore_fogli", "paper_hole_punch"), [
            p("lever", "Leva", "Trasmette la pressione della mano ai punzoni.", "Il fulcro consente una corsa dei punzoni più breve rispetto alla presa.", "box", (91,53,7), (0,4,23)),
            p("punches", "Gruppo punzoni", "Taglia i fori nella carta.", "I due punzoni tipici sono raggruppati; la disposizione non certifica un formato di rilegatura.", "cylinder", (9,31,9), (0,5,4)),
            p("base", "Base e matrice", "Supportano i fogli durante il taglio.", "Le aperture accolgono i punzoni e fanno cadere i dischetti di carta.", "box", (94,59,9), (0,0,-12)),
            p("guide", "Guida fogli", "Aiuta a posizionare il foglio.", "La battuta è regolabile nella variante illustrata; non è una misura ottenuta dalla foto.", "box", (136,8,5), (0,25,-4)),
            p("tray", "Vaschetta degli scarti", "Raccoglie i dischetti di carta.", "Si trova sotto la matrice; molla e fissaggi sono omessi.", "shell", (91,56,9), (0,0,-23)),
        ]),
        r("measuring_tape", "Metro a nastro retrattile", "Piccoli utensili", ("metro_nastro", "tape_measure", "retractable_measure"), [
            p("housing", "Custodia", "Protegge il nastro avvolto.", "Le due metà e gli appoggi sono un gruppo.", "shell", (60,61,23), (0,0,0)),
            p("tape", "Nastro graduato", "Porta le divisioni di misura.", "È rappresentato avvolto. Il modello non legge distanze o certifica la scala.", "ring", (43,15,43), (0,0,1)),
            p("recoil", "Molla di richiamo", "Riavvolge il nastro.", "È una molla piatta a spirale rappresentata con un anello simbolico, non una molla elicoidale.", "ring", (22,3,22), (0,0,3)),
            p("lock", "Freno", "Trattiene il nastro estratto.", "Il pattino agisce sul nastro nella variante illustrata.", "box", (16,12,8), (20,14,7)),
            p("hook", "Gancio terminale", "Offre un riferimento sul bordo dell'oggetto.", "Il gioco del gancio può essere previsto dal costruttore; lo schema non ne valuta l'usura.", "box", (19,9,3), (32,-15,1)),
        ], note=" Non aprire la custodia: il richiamo può essere sotto tensione."),
        r("door_hinge", "Cerniera a libro", "Casa", ("cerniera_porta", "butt_hinge", "cerniera_a_libro"), [
            p("leaf_a", "Prima ala", "Si fissa a una delle due strutture.", "La piastra e i suoi occhielli sono raggruppati; i fori sono schematici.", "box", (30,80,3), (-18,0,0)),
            p("leaf_b", "Seconda ala", "Si fissa alla parte mobile.", "I suoi occhielli si alternano a quelli dell'altra ala.", "box", (30,80,3), (18,0,0)),
            p("pin", "Perno", "Definisce l'asse di rotazione.", "Attraversa gli occhielli; non tutte le cerniere hanno un perno estraibile.", "cylinder", (7,85,7), (0,0,0)),
            p("bush", "Appoggi e boccole", "Guidano la rotazione e gli appoggi.", "Sono un gruppo tipico; cuscinetti o boccole separate non sono presenti in ogni modello.", "ring", (10,7,10), (0,-33,0)),
        ]),
        r("lever_door_handle", "Maniglia a leva", "Casa", ("maniglia_leva", "door_lever_handle", "maniglia_porta"), [
            p("lever", "Leva di presa", "Trasmette la rotazione della mano.", "Il profilo è stilizzato; non identifica un sistema di serratura.", "box", (79,12,17), (30,0,14)),
            p("rose", "Rosetta", "Copre il fissaggio alla porta.", "Può essere circolare o parte di una placca.", "cylinder", (38,8,38), (0,0,5)),
            p("spindle", "Quadro di collegamento", "Trasmette la rotazione al meccanismo interno.", "È il collegamento meccanico; lo scrocco e la serratura non vengono ricostruiti.", "box", (7,7,62), (0,0,-18)),
            p("return", "Gruppo di ritorno", "Aiuta a riportare la leva in posizione.", "La molla può essere nella maniglia oppure nel meccanismo della porta: qui è una parte tipica non verificata.", "ring", (23,5,23), (0,0,0)),
        ]),
        r("swivel_castor", "Ruota girevole per mobili", "Casa", ("ruota_mobile", "furniture_caster", "swivel_caster", "rotella_girevole"), [
            p("plate", "Piastra di fissaggio", "Collega la ruota al mobile.", "La piastra è un esempio; altre varianti hanno un perno.", "box", (50,5,43), (0,45,0)),
            p("swivel", "Snodo girevole", "Permette alla forcella di orientarsi.", "Il sistema di appoggio ruota attorno all'asse verticale.", "ring", (25,10,25), (0,32,0)),
            p("fork", "Forcella", "Sostiene l'asse della ruota.", "Le due guance sono raggruppate in un supporto schematico.", "shell", (38,41,35), (0,6,0)),
            p("wheel", "Ruota", "Rotola sul pavimento.", "Mozzo e battistrada sono riuniti; portata e materiale non sono dedotti.", "cylinder", (34,18,34), (0,-13,0)),
            p("axle", "Asse", "Collega la ruota alla forcella.", "Orientamento e fissaggio del gruppo sono semplificati.", "cylinder", (5,29,5), (0,-13,0)),
        ]),
        r("coat_hanger", "Grucce con gancio metallico", "Casa", ("gruccia", "wooden_coat_hanger", "appendiabiti_gruccia"), [
            p("shoulders", "Supporto delle spalle", "Sostiene il capo.", "Le due spalle sono rappresentate come un gruppo; il profilo triangolare è semplificato.", "box", (156,17,11), (0,10,0)),
            p("hook", "Gancio", "Appende la gruccia all'asta.", "La curvatura aperta del filo è schematizzata; non è un anello chiuso nel prodotto reale.", "ring", (24,36,4), (0,44,0)),
            p("bar", "Barra inferiore", "Può sostenere pantaloni o altri capi.", "Il collegamento alle spalle dipende dalla costruzione. Non tutte le grucce hanno la barra.", "cylinder", (9,138,9), (0,-15,0)),
        ]),
        r("suction_hook", "Gancio a ventosa", "Casa", ("gancio_ventosa", "suction_cup_hook", "vacuum_hook"), [
            p("cup", "Ventosa", "Aderisce a una superficie adatta.", "La deformazione e la differenza di pressione contribuiscono alla presa; il bordo deve mantenere il contatto.", "cone", (43,10,43), (0,0,0)),
            p("hub", "Supporto centrale", "Collega la ventosa al gancio.", "Nella variante semplice trasmette il carico al corpo elastico.", "cylinder", (13,11,13), (0,10,0)),
            p("hook", "Gancio", "Sostiene l'oggetto appeso.", "La sagoma è un inviluppo del gancio. La scena non valuta la portata o l'aderenza reale.", "ring", (20,29,4), (0,24,0)),
        ]),
        r("window_squeegee", "Tergivetro manuale", "Casa", ("tergivetro", "glass_squeegee", "shower_squeegee"), [
            p("handle", "Manico", "Permette di guidare il tergivetro.", "Trasmette la pressione al supporto della lama flessibile.", "cylinder", (15,88,15), (0,-38,0)),
            p("channel", "Supporto trasversale", "Mantiene rettilineo il bordo di lavoro.", "La scanalatura trattiene l'inserto; il sistema esatto di fissaggio varia.", "box", (137,12,9), (0,12,0)),
            p("blade", "Labbro flessibile", "Spinge l'acqua sulla superficie.", "Il bordo elastico si adatta al vetro. Non è una lama da taglio.", "box", (139,13,2), (0,21,0)),
        ]),
        r("lint_roller", "Rullo levapelucchi adesivo", "Casa", ("rullo_levapelucchi", "adhesive_lint_roller", "rullo_abiti"), [
            p("handle", "Impugnatura", "Permette di far scorrere il rullo.", "Il manico tiene la mano separata dalla superficie adesiva.", "cylinder", (18,65,18), (0,-54,0)),
            p("axle", "Perno", "Supporta il rotolo.", "La ricarica ruota attorno al supporto nella variante illustrata.", "cylinder", (11,76,11), (0,12,0)),
            p("core", "Nucleo della ricarica", "Mantiene la forma del rotolo.", "Può essere di cartone o plastica; il materiale non è identificato dalla ricetta.", "ring", (22,69,22), (0,12,0)),
            p("sheets", "Fogli adesivi", "Trattengono peli e pelucchi.", "Sono strati avvolti, non ruote meccaniche. Il numero di fogli non è determinato.", "ring", (38,71,38), (0,12,0)),
        ]),
        r("trigger_clamp", "Morsetto a una mano", "Piccoli utensili", ("morsetto_rapido", "one_handed_clamp", "trigger_bar_clamp"), [
            p("rail", "Barra guida", "Collega e allinea le ganasce.", "La barra resiste al carico nella variante illustrata; la portata non è calcolata.", "box", (11,176,5), (0,0,0)),
            p("fixed", "Ganascia fissa", "Fornisce un appoggio al pezzo.", "Si trova a un'estremità della barra.", "box", (43,17,14), (16,73,0)),
            p("sliding", "Ganascia mobile", "Si avvicina al pezzo lungo la guida.", "La presa e il corpo del meccanismo sono raggruppati.", "shell", (47,43,18), (16,-27,0)),
            p("trigger", "Leva di avanzamento", "Fa avanzare il serraggio.", "Un sistema di presa sulla barra converte le pressioni successive in avanzamento.", "box", (13,40,9), (38,-50,0)),
            p("release", "Comando di rilascio", "Libera il movimento della ganascia.", "Non sostituisce una valutazione di sicurezza del serraggio o del carico.", "box", (12,11,9), (23,-11,0)),
        ], refs=(("BESSEY — guida, ganasce, leva e rilascio", "https://bessey.de/en-gb/bessey-tool/news/press-releases/one-handed-clamp-ez-series"),)),
        r("zipper", "Chiusura lampo", "Casa", ("cerniera_lampo", "chiusura_zip", "zip_fastener"), [
            p("tape_left", "Nastro sinistro", "Collega la chiusura al tessuto.", "Il bordo porta una fila di elementi; cuciture e tessitura sono semplificate.", "box", (19,140,1), (-14,0,0)),
            p("tape_right", "Nastro destro", "Sostiene l'altra fila di elementi.", "Le due metà vengono unite o separate dal cursore.", "box", (19,140,1), (14,0,0)),
            p("elements", "Elementi di accoppiamento", "Si incastrano per chiudere la zip.", "Denti o spirale sono un gruppo simbolico, non una dentatura compatibile con ricambi reali.", "keypad", (13,134,2), (0,0,1)),
            p("slider", "Cursore e tirante", "Guidano l'unione o la separazione.", "Il passaggio interno porta le due file ad accoppiarsi; il tirante serve alla presa.", "shell", (15,22,5), (0,24,3)),
            p("stops", "Fermi terminali", "Limitano la corsa del cursore.", "Forma e configurazione cambiano fra zip separabili e non separabili.", "box", (13,5,3), (0,-67,1)),
        ], refs=(("YKK — struttura e funzionamento della chiusura lampo", "https://www.ykk.com/english/ykk/tech/01.html"),)),
    ]
