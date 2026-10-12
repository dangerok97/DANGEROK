"""Original parametric family schematics, not copied CAD or verified interiors.
Sources support general component principles only; geometry and explanatory copy
are original. Some groups are bonded in real objects. All dimensions are graphic
units, never measurements or repair instructions for the photographed specimen.
"""
from __future__ import annotations
import math
import re
import unicodedata
from vision_catalog_extended import extended_recipes
from vision_catalog_extended.more_everyday import recipes as newest_everyday_recipes

PACK_VERSION = "common-126-v1"
LIMIT = ("Schema di famiglia: forme, proporzioni e disposizione indicative. Mostra gruppi "
         "principali, anche saldati o incollati nell'oggetto reale; non certifica il modello "
         "fotografato e non è una guida allo smontaggio.")
BATTERY = " Non aprire o modificare batterie e circuiti alimentati."
SOURCES = {
    "phone": ("Apple: gruppi principali di uno smartphone", "https://support.apple.com/en-us/100308"),
    "tablet": ("Apple: parti principali di un tablet", "https://support.apple.com/en-us/122080"),
    "laptop": ("Apple: gruppi principali di un portatile", "https://support.apple.com/es-es/100603"),
    "earbuds": ("iFixit: osservazione diretta di auricolari e custodia", "https://www.ifixit.com/Teardown/AirPods+Teardown/75578"),
    "usb": ("Kingston: unità USB con cappuccio", "https://www.kingston.com/it/usb-flash-drives/datatraveler-exodia-g2-usb-3-2-usb-flash-drive"),
    "mechanical_pencil": ("Pentel: portamine e guida della mina", "https://pentel.eu/pens/mechanical-pencil/"),
    "marker": ("edding: corpo, cappuccio e punta", "https://www.edding.com/products/edding-28-whiteboard-marker/"),
    "pump": ("Aptar: pompa, attuatore e ghiera", "https://beauty.latamcatalog.aptar.com/en/product/hi-flow/"),
    "insulated": ("Thermos: doppia parete e isolamento", "https://thermos.com/products/40oz-icon-dual-temp-beverage-bottle"),
}


def p(key, name, purpose, how, shape, size, assembled=(0, 0, 0)):
    return dict(key=key, name=name, function=purpose, how_it_works=how, shape=shape,
                size=list(size), assembled=list(assembled), evidence="typical")


def recipe(key, title, category, aliases, parts, *, note="", sources=()):
    columns = min(3, len(parts)); rows = math.ceil(len(parts) / columns)
    dx = max(45, max(item["size"][0] for item in parts) + 22)
    dy = max(50, max(item["size"][1] for item in parts) + 24)
    for i, item in enumerate(parts):
        row, col = divmod(i, columns)
        in_row = min(columns, len(parts) - row * columns)
        item["exploded"] = [round((col - (in_row - 1) / 2) * dx, 3),
                            round(((rows - 1) / 2 - row) * dy, 3), 0]
    return dict(key=key, title=title, category=category, aliases=list(aliases),
                sources=[dict(title=SOURCES[s][0], url=SOURCES[s][1]) for s in sources],
                manifest=dict(schema_version=1, canonical_key=key, title=title,
                              evidence_level="illustrative", match_scope="family", units="illustrative",
                              parts=parts, limitations=LIMIT + note))


BASE_META = {
    "remote_control": ("Telecomando a infrarossi", "Elettronica", ("telecomando", "tv_remote", "infrared_remote", "remote")),
    "click_pen": ("Penna a scatto", "Scrivania", ("penna_a_scatto", "retractable_pen", "click_ballpoint_pen")),
    "water_bottle": ("Bottiglia con tappo", "Casa", ("bottiglia", "plastic_water_bottle", "plastic_bottle")),
    "computer_mouse": ("Mouse ottico", "Elettronica", ("mouse", "optical_mouse", "pc_mouse")),
    "flashlight": ("Torcia portatile", "Piccoli utensili", ("torcia", "torch", "handheld_flashlight")),
}


def common_recipes():
    return [
        recipe("smartphone", "Smartphone", "Elettronica", ("mobile_phone", "cell_phone", "cellphone", "smart_phone", "telefonino", "telefono_cellulare"), [
            p("display", "Display tattile", "Visualizza immagini e raccoglie i tocchi.", "Vetro, pannello e sensori sono raggruppati; spesso sono incollati fra loro.", "box", (66, 140, 2), (0, 0, 7)),
            p("frame", "Telaio", "Sostiene i gruppi interni.", "Fissaggi e sedi dipendono dal modello: qui la struttura è semplificata.", "shell", (72, 150, 6)),
            p("mainboard", "Scheda principale", "Elabora dati e coordina le funzioni.", "Circuiti di calcolo e comunicazione sono riuniti sulla scheda; il tracciato è illustrativo.", "board", (30, 67, 2), (-16, 31, 2)),
            p("battery", "Batteria", "Fornisce energia al telefono.", "Il pacco batteria è rappresentativo, senza dedurne capacità o numero di celle.", "box", (40, 78, 4), (10, -16, 1)),
            p("camera", "Gruppo fotocamera", "Acquisisce le immagini.", "Obiettivo e sensore sono un insieme; numero e disposizione non sono verificati sul tuo telefono.", "box", (19, 24, 6), (-18, 52, 4)),
            p("speaker", "Altoparlante", "Riproduce i suoni.", "Un trasduttore muove una membrana. Altri microfoni e sensori sono omessi.", "box", (27, 12, 5), (0, -61, 1)),
            p("back", "Copertura posteriore", "Chiude l'involucro.", "Può essere incollata al telaio. Il materiale non è dedotto dalla foto.", "shell", (72, 150, 2), (0, 0, -6)),
        ], note=BATTERY, sources=("phone",)),
        recipe("tablet", "Tablet", "Elettronica", ("tablet_computer", "tablet_device"), [
            p("screen", "Display tattile", "Mostra i contenuti e rileva i tocchi.", "Vetro, pannello e sensori sono rappresentati insieme.", "box", (105, 158, 2), (0, 0, 6)),
            p("case", "Scocca", "Sostiene la struttura.", "Il guscio sottile ospita le parti principali.", "shell", (113, 168, 5)),
            p("battery", "Pacco batteria", "Alimenta il tablet.", "Può comprendere più celle; quantità e capacità non sono qui verificate.", "box", (78, 119, 3), (-7, -7, 1)),
            p("board", "Scheda elettronica", "Gestisce calcolo e comunicazioni.", "Molti componenti sono integrati o saldati sulla scheda.", "board", (21, 110, 2), (39, 8, 1)),
            p("camera", "Fotocamera", "Acquisisce immagini.", "Ottica e sensore formano il gruppo, ma il tablet può avere più fotocamere.", "box", (13, 15, 5), (39, 69, 3)),
            p("audio", "Gruppo altoparlanti", "Emette il suono.", "I trasduttori sono raggruppati senza indicarne il numero esatto.", "box", (71, 10, 4), (0, -72, 1)),
        ], note=BATTERY, sources=("tablet",)),
        recipe("laptop", "Computer portatile", "Elettronica", ("notebook_computer", "laptop_computer", "portatile"), [
            p("display", "Gruppo schermo", "Visualizza le informazioni.", "Pannello e coperchio sono riuniti; cerniere e cavi sono semplificati.", "box", (214, 136, 5), (0, 0, 20)),
            p("keyboard", "Tastiera", "Raccoglie le pressioni dei tasti.", "La griglia è simbolica: meccanismo e layout variano.", "keypad", (194, 66, 3), (0, 29, 8)),
            p("trackpad", "Superficie di puntamento", "Rileva i movimenti delle dita.", "Sensori sotto la superficie interpretano posizione e gesti.", "box", (70, 38, 2), (0, -41, 8)),
            p("mainboard", "Scheda principale", "Collega le funzioni del computer.", "Processore e memorie possono essere saldati. Le parti minori sono raggruppate.", "board", (188, 47, 3), (0, 42, 2)),
            p("battery", "Pacco batteria", "Fornisce energia senza cavo.", "Numero e disposizione delle celle variano; non aprire il pacco.", "box", (170, 49, 5), (0, -32, 1)),
            p("base", "Base e pannello inferiore", "Contengono e proteggono le parti.", "Il sistema termico non è riprodotto: alcuni modelli hanno ventole, altri no.", "shell", (224, 147, 10)),
        ], note=BATTERY, sources=("laptop",)),
        recipe("computer_keyboard", "Tastiera a membrana", "Elettronica", ("keyboard", "pc_keyboard", "membrane_keyboard", "tastiera"), [
            p("keys", "Tasti", "Trasmettono i comandi delle dita.", "Sono raffigurati simbolicamente, senza un layout linguistico specifico.", "keypad", (210, 72, 4), (0, 0, 8)),
            p("membrane", "Strati della membrana", "Rilevano i contatti dei tasti.", "La pressione avvicina superfici conduttive. Non rappresenta una tastiera meccanica.", "box", (209, 71, 1), (0, 0, 4)),
            p("controller", "Scheda di controllo", "Traduce i contatti in comandi.", "Il circuito legge la matrice dei tasti e comunica con il dispositivo collegato.", "board", (53, 18, 2), (74, 27, 1)),
            p("top", "Cornice", "Guida e protegge i tasti.", "Le aperture sono semplificate, non riproducono ogni foro reale.", "shell", (224, 86, 4), (0, 0, 5)),
            p("base", "Guscio inferiore", "Sostiene gli strati.", "Connessione e supporti dipendono dalla variante.", "shell", (224, 86, 7), (0, 0, -3)),
        ]),
        recipe("game_controller", "Controller di gioco", "Elettronica", ("gamepad", "joypad", "gaming_controller", "video_game_controller"), [
            p("front", "Guscio frontale", "Sostiene comandi e impugnatura.", "Forma semplificata, senza identificare una console.", "shell", (137, 82, 12), (0, 0, 10)),
            p("buttons", "Pulsanti", "Trasmettono le pressioni ai contatti.", "Il gruppo riunisce pulsanti e relative superfici di contatto.", "keypad", (48, 49, 3), (35, 12, 6)),
            p("left_stick", "Levetta sinistra", "Impartisce comandi direzionali.", "Un gruppo di rilevamento legge l'inclinazione; il tipo di sensore non è determinato.", "cylinder", (18, 17, 18), (-31, -9, 12)),
            p("right_stick", "Levetta destra", "Fornisce un secondo comando direzionale.", "La posizione viene letta dalla scheda; non è una diagnosi di usura.", "cylinder", (18, 17, 18), (20, -19, 12)),
            p("board", "Scheda di controllo", "Raccoglie i comandi.", "Collegamento, alimentazione e vibrazione dipendono dal modello e sono omessi.", "board", (105, 56, 3)),
            p("rear", "Guscio posteriore", "Chiude l'involucro.", "Fissaggi e geometria delle impugnature variano.", "shell", (137, 82, 12), (0, 0, -12)),
        ]),
        recipe("usb_flash_drive", "Chiavetta USB", "Elettronica", ("usb_stick", "usb_drive", "thumb_drive", "pen_drive", "chiavetta_usb"), [
            p("housing", "Involucro", "Protegge l'elettronica.", "È rappresentata una variante con cappuccio.", "shell", (22, 55, 7)),
            p("board", "Scheda", "Collega i gruppi elettronici.", "Piste e componenti sono stilizzati, non un circuito esatto.", "board", (17, 39, 2), (0, -1, 1)),
            p("memory", "Memoria flash", "Conserva i dati anche senza alimentazione.", "È un gruppo funzionale: memoria e controllo possono essere integrati nello stesso componente.", "box", (12, 18, 1.5), (0, -8, 3)),
            p("connector", "Connettore USB", "Collega l'unità a un dispositivo compatibile.", "La forma rappresenta un connettore generico; non certifica standard o velocità.", "box", (13, 15, 4), (0, 29, 0)),
            p("cap", "Cappuccio", "Protegge il connettore quando non è in uso.", "Altre chiavette usano una slitta e non hanno questo pezzo.", "shell", (23, 20, 8), (0, 33, 0)),
        ], sources=("usb",)),
        recipe("wireless_earbud", "Auricolare wireless", "Elettronica", ("wireless_earbuds", "bluetooth_earbud", "bluetooth_earbuds", "auricolare_wireless"), [
            p("housing", "Involucro", "Contiene e sostiene le parti.", "Forma schematica: non replica un auricolare di marca.", "shell", (25, 35, 13)),
            p("driver", "Trasduttore audio", "Converte il segnale elettrico in suono.", "Una membrana vibrante genera variazioni della pressione dell'aria.", "cylinder", (12, 5, 12), (0, 6, 3)),
            p("battery", "Batteria", "Alimenta l'auricolare.", "Spesso è incollata o collegata con saldature. Non aprirla o forarla.", "cylinder", (10, 11, 10), (0, -8, 0)),
            p("board", "Circuito radio e controllo", "Riceve ed elabora i dati audio.", "I circuiti possono essere flessibili e disposti intorno agli altri elementi.", "board", (16, 23, 1), (0, 0, -4)),
            p("microphone", "Microfono", "Rileva i suoni esterni o la voce.", "Numero e posizione cambiano; non si deduce la presenza di cancellazione del rumore.", "box", (4, 4, 3), (8, -12, 0)),
        ], note=BATTERY, sources=("earbuds",)),
        recipe("earbud_charging_case", "Custodia di ricarica auricolari", "Elettronica", ("earbuds_case", "earbud_case", "wireless_earbuds_charging_case", "custodia_auricolari"), [
            p("lid", "Coperchio", "Protegge gli alloggiamenti.", "Può usare una cerniera e magneti; sono qui raggruppati.", "shell", (65, 25, 24), (0, 26, 0)),
            p("holder", "Alloggiamenti e contatti", "Posizionano gli auricolari per la carica.", "I contatti permettono il collegamento elettrico quando gli auricolari sono inseriti.", "shell", (56, 39, 13), (0, 2, 6)),
            p("battery", "Batteria della custodia", "Immagazzina energia per ricaricare gli auricolari.", "Capacità e numero di celle non sono ricavati dalla foto.", "box", (35, 25, 5), (0, -1, -3)),
            p("board", "Circuito di ricarica", "Gestisce l'energia e i collegamenti.", "La tecnologia della porta e l'eventuale ricarica wireless dipendono dal modello.", "board", (45, 16, 2), (0, -14, 0)),
            p("case", "Guscio inferiore", "Contiene il gruppo di alimentazione.", "Può essere sigillato o incollato; la vista non implica che sia apribile a mano.", "shell", (65, 48, 24), (0, -4, -3)),
        ], note=BATTERY, sources=("earbuds",)),
        recipe("wooden_pencil", "Matita in legno", "Scrivania", ("pencil", "graphite_pencil", "matita", "matita_in_legno"), [
            p("wood", "Involucro in legno", "Sostiene e protegge la mina.", "Le porzioni di legno sono incollate: la separazione nello schema è concettuale.", "cylinder", (8, 142, 8)),
            p("core", "Mina", "Lascia il tratto sulla carta.", "È l'elemento scrivente interno; durezza e composizione non sono identificate qui.", "cylinder", (2.4, 154, 2.4), (0, -3, 0)),
            p("point", "Zona temperata", "Espone e sostiene la parte finale della mina.", "È una regione dello stesso legno, non un puntale smontabile.", "cone", (8, 16, 8), (0, -79, 0)),
        ]),
        recipe("mechanical_pencil", "Portamine", "Scrivania", ("propelling_pencil", "automatic_pencil", "portamine"), [
            p("body", "Corpo", "Permette la presa e contiene il meccanismo.", "Il corpo guida i gruppi interni lungo l'asse di scrittura.", "cylinder", (10, 113, 10)),
            p("lead", "Mina", "Traccia il segno sulla carta.", "Avanza poco alla volta. Il diametro è qui solo illustrativo.", "cylinder", (1.4, 95, 1.4), (0, -22, 0)),
            p("clutch", "Gruppo di avanzamento", "Trattiene e fa avanzare la mina.", "Pinza e richiamo sono raggruppati; il meccanismo varia tra portamine.", "cylinder", (6, 23, 6), (0, -38, 0)),
            p("guide", "Puntale e guida", "Sostengono la mina vicino alla carta.", "Alcune guide sono fisse, altre scorrono; questa vista non identifica la variante.", "cone", (9, 19, 9), (0, -65, 0)),
            p("button", "Pulsante", "Aziona l'avanzamento.", "È raffigurata una variante con comando superiore.", "cylinder", (8, 13, 8), (0, 61, 0)),
        ], sources=("mechanical_pencil",)),
        recipe("capped_pen", "Penna con cappuccio", "Scrivania", ("capped_ballpoint_pen", "penna_con_cappuccio", "ballpoint_pen_with_cap"), [
            p("barrel", "Corpo", "Contiene il gruppo scrivente.", "Il corpo è rappresentato cavo, senza un particolare marchio.", "cylinder", (10, 115, 10)),
            p("refill", "Tubo dell'inchiostro", "Conserva l'inchiostro.", "La riserva e la punta possono formare una ricarica unica.", "cylinder", (3.5, 121, 3.5), (0, -4, 0)),
            p("tip", "Punta a sfera", "Porta l'inchiostro sulla carta.", "La piccola sfera è racchiusa nel gruppo finale. La sua dimensione non è misurata.", "cone", (4, 10, 4), (0, -67, 0)),
            p("cap", "Cappuccio", "Copre e protegge la punta.", "Lo schema lo mostra sopra la punta; incastri e fori variano.", "cylinder", (13, 40, 13), (0, -50, 0)),
        ]),
        recipe("marker", "Pennarello", "Scrivania", ("felt_tip_pen", "whiteboard_marker", "pennarello", "felt_marker"), [
            p("barrel", "Corpo", "Contiene la riserva di inchiostro.", "Il contenitore protegge il materiale interno.", "cylinder", (17, 105, 17)),
            p("reservoir", "Riserva di inchiostro", "Alimenta la punta.", "Nei pennarelli a fibra una riserva porosa trattiene il liquido. Altre varianti hanno sistemi differenti.", "cylinder", (11, 80, 11), (0, 0, 0)),
            p("nib", "Punta porosa", "Deposita l'inchiostro.", "Il materiale poroso porta il liquido alla superficie di scrittura.", "cylinder", (6, 21, 6), (0, -60, 0)),
            p("cap", "Cappuccio", "Protegge la punta.", "La chiusura aiuta a limitare l'essiccazione; non tutti i pennarelli hanno la stessa tenuta.", "cylinder", (20, 36, 20), (0, -52, 0)),
            p("plug", "Chiusura posteriore", "Chiude il contenitore della riserva.", "Può essere integrata o fissata stabilmente, non necessariamente rimovibile.", "cylinder", (17, 6, 17), (0, 55, 0)),
        ], sources=("marker",)),
        recipe("glue_stick", "Colla stick", "Scrivania", ("colla_stick", "gluestick", "solid_glue_stick"), [
            p("tube", "Contenitore", "Protegge e guida lo stick.", "È un tubo che accompagna il movimento del supporto interno.", "cylinder", (24, 78, 24)),
            p("glue", "Stick adesivo", "Deposita l'adesivo sulla superficie.", "Il cilindro è materiale consumabile; la formula non viene identificata.", "cylinder", (19, 62, 19), (0, 6, 0)),
            p("lift", "Supporto e vite", "Sollevano lo stick.", "La rotazione della base fa avanzare un supporto lungo una guida; i gruppi sono semplificati.", "cylinder", (6, 55, 6), (0, -7, 0)),
            p("base", "Base rotante", "Permette di regolare l'uscita.", "Trasmette la rotazione al meccanismo interno.", "cylinder", (25, 10, 25), (0, -44, 0)),
            p("cap", "Cappuccio", "Protegge la superficie adesiva.", "Chiude la parte superiore e aiuta a limitare l'essiccazione.", "cylinder", (26, 24, 26), (0, 46, 0)),
        ]),
        recipe("stapler", "Pinzatrice da scrivania", "Scrivania", ("office_stapler", "desktop_stapler", "pinzatrice", "cucitrice"), [
            p("lever", "Leva superiore", "Trasmette la pressione della mano.", "La leva agisce sul gruppo che spinge il punto metallico.", "box", (24, 113, 13), (0, 0, 16)),
            p("magazine", "Caricatore", "Contiene e guida i punti.", "Una guida allinea i punti verso la zona di uscita.", "shell", (18, 105, 8), (0, 0, 5)),
            p("pusher", "Spingipunti", "Mantiene la fila verso l'uscita.", "Un elemento elastico spinge il cursore. È rappresentato come gruppo, non come schema di montaggio.", "box", (12, 27, 4), (0, 27, 6)),
            p("driver", "Lamina di spinta", "Spinge il punto attraverso i fogli.", "Scende quando si preme la leva; la corsa non è simulata fisicamente.", "box", (13, 3, 15), (0, -45, 7)),
            p("base", "Base con incudine", "Sostiene la carta e ripiega il punto.", "La parte metallica inferiore guida il ripiegamento delle estremità.", "box", (31, 123, 7), (0, 0, -11)),
        ]),
        recipe("adhesive_tape_roll", "Rotolo di nastro adesivo", "Scrivania", ("tape_roll", "sticky_tape_roll", "nastro_adesivo", "adhesive_tape"), [
            p("core", "Anima del rotolo", "Sostiene il nastro avvolto.", "È il supporto centrale; materiale e dimensioni non sono verificati.", "ring", (35, 20, 35)),
            p("backing", "Supporto del nastro", "Dà continuità al materiale adesivo.", "La pellicola o carta porta lo strato adesivo; qui è mostrata arrotolata.", "ring", (67, 20, 67)),
            p("adhesive", "Strato adesivo", "Permette l'adesione.", "È uno strato sottile sul supporto, non un pezzo indipendente da estrarre.", "ring", (65, 19, 65)),
        ]),
        recipe("clothespin", "Molletta per bucato", "Casa", ("clothes_peg", "clothes_pin", "laundry_clip", "molletta"), [
            p("jaw_left", "Prima leva", "Stringe il tessuto insieme all'altra leva.", "La pressione delle dita apre l'estremità opposta. La forma è semplificata.", "box", (11, 73, 7), (-5, 0, 0)),
            p("jaw_right", "Seconda leva", "Completa la presa.", "Le due leve lavorano intorno alla zona della molla.", "box", (11, 73, 7), (5, 0, 0)),
            p("spring", "Molla di torsione", "Mantiene chiusa la presa.", "La spirale e le estremità elastiche sono rese schematicamente: non è una molla di ricambio dimensionata.", "spring", (15, 9, 15), (0, 3, 0)),
        ]),
        recipe("soap_dispenser", "Dispenser di sapone", "Casa", ("liquid_soap_dispenser", "pump_bottle", "soap_pump", "dispenser_sapone"), [
            p("bottle", "Flacone", "Contiene il liquido.", "Lo schema non identifica il contenuto o la sua compatibilità con la pompa.", "bottle", (57, 120, 57)),
            p("tube", "Pescante", "Porta il liquido alla pompa.", "Il tubo raggiunge il contenuto del flacone.", "cylinder", (4, 111, 4), (0, 5, 0)),
            p("pump", "Pompa e valvole", "Dosano il liquido.", "Un pistone modifica il volume della camera; le valvole regolano la direzione del flusso.", "cylinder", (17, 37, 17), (0, 53, 0)),
            p("spring", "Elemento di richiamo", "Riporta l'attuatore alla posizione iniziale.", "Una molla tipica ripristina la corsa; posizione e materiale variano.", "spring", (10, 17, 10), (0, 54, 0)),
            p("head", "Testa e beccuccio", "Riceve la pressione ed eroga il liquido.", "Il canale convoglia il prodotto verso l'uscita.", "box", (43, 11, 18), (12, 82, 0)),
            p("collar", "Ghiera", "Collega la pompa al flacone.", "La chiusura tipica si avvita sul collo.", "ring", (29, 12, 29), (0, 66, 0)),
        ], sources=("pump",)),
        recipe("trigger_spray_bottle", "Flacone con spruzzatore", "Casa", ("trigger_sprayer", "trigger_spray", "spray_bottle", "spruzzatore_manual"), [
            p("bottle", "Flacone", "Contiene il liquido.", "È una variante manuale, non una bomboletta pressurizzata. Non identifica il contenuto.", "bottle", (65, 144, 48)),
            p("tube", "Tubo pescante", "Collega il contenuto alla pompa.", "La sua estremità raggiunge la parte bassa del contenitore.", "cylinder", (4, 137, 4), (0, 5, 0)),
            p("head", "Testa con pompa", "Convoglia e spinge il liquido.", "Camera e valvole sono raggruppate; funzionamento e materiali dipendono dalla variante.", "box", (63, 25, 23), (12, 85, 0)),
            p("trigger", "Grilletto", "Aziona la pompa manualmente.", "La leva trasmette la pressione della mano al pistone.", "box", (8, 35, 17), (34, 60, 0)),
            p("nozzle", "Ugello", "Modifica l'uscita del liquido.", "La geometria dell'uscita determina un getto o uno spruzzo; nessuna pressione è dedotta.", "box", (11, 14, 18), (46, 85, 0)),
            p("collar", "Ghiera", "Unisce testa e contenitore.", "La chiusura è illustrata come un gruppo, non una tenuta certificata.", "ring", (29, 13, 29), (0, 76, 0)),
        ]),
        recipe("insulated_bottle", "Borraccia termica", "Casa", ("vacuum_bottle", "vacuum_flask", "insulated_water_bottle", "borraccia_termica"), [
            p("outside", "Parete esterna", "Protegge il contenitore interno.", "In questa famiglia forma una doppia parete. Non tutte le borracce sono isolate.", "bottle", (58, 162, 58)),
            p("inside", "Contenitore interno", "È a contatto con la bevanda.", "Lo spazio tra le pareti riduce gli scambi termici. Non è un pezzo normalmente estraibile.", "bottle", (50, 151, 50), (0, 4, 0)),
            p("cap", "Tappo isolante", "Chiude l'apertura.", "La struttura del tappo contribuisce a limitare scambi e fuoriuscite; prestazioni non misurate.", "cylinder", (30, 24, 30), (0, 91, 0)),
            p("seal", "Guarnizione", "Aiuta la tenuta della chiusura.", "È una parte tipica, ma forma e presenza vanno verificate sul prodotto.", "ring", (25, 3, 25), (0, 82, 0)),
        ], sources=("insulated",)),
        recipe("screwdriver", "Cacciavite manuale", "Piccoli utensili", ("manual_screwdriver", "cacciavite", "flat_screwdriver"), [
            p("handle", "Impugnatura", "Permette di esercitare la rotazione.", "La presa trasmette la coppia al gambo. Lo schema non certifica isolamento elettrico.", "cylinder", (26, 71, 26), (0, 38, 0)),
            p("shaft", "Gambo", "Trasmette la rotazione alla punta.", "È normalmente solidale con l'impugnatura e può includere la punta nello stesso pezzo.", "cylinder", (6, 100, 6), (0, -29, 0)),
            p("tip", "Punta a taglio", "Si accoppia alla testa della vite.", "È raffigurata una variante a taglio: l'estremità è una regione del gambo, non sempre un inserto separato.", "box", (8, 11, 2), (0, -82, 0)),
        ], note=" Non usare questo schema per lavori su parti sotto tensione."),
    ]


def normalize_key(value):
    if not isinstance(value, str):
        return ""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", value.strip()).strip("_")


def all_recipes():
    """Original twenty recipes plus the additive fifty-family pack."""
    return common_recipes() + extended_recipes(recipe, p) + newest_everyday_recipes(recipe, p)


def metadata():
    rows = {key: dict(key=key, title=title, category=category, aliases=list(aliases), sources=[])
            for key, (title, category, aliases) in BASE_META.items()}
    for entry in all_recipes():
        rows[entry["key"]] = {k: v for k, v in entry.items() if k != "manifest"}
    return rows


METADATA = metadata()
ALIASES = {}
for _key, _row in METADATA.items():
    for _alias in [_key, _row["title"], *_row["aliases"]]:
        _normalized = normalize_key(_alias)
        if _normalized in ALIASES and ALIASES[_normalized] != _key:
            raise RuntimeError("Conflicting Vision family alias")
        ALIASES[_normalized] = _key


def canonical_key(value):
    normalized = normalize_key(value)
    return ALIASES.get(normalized, normalized)


def recognition_hint():
    return "; ".join(f"{key}: {row['title']}" for key, row in METADATA.items())


def model_metadata(key):
    item = METADATA.get(key)
    if not item:
        return dict(category="Altri oggetti", aliases=[], sources=[])
    return dict(category=item["category"], aliases=list(item["aliases"]), sources=list(item["sources"]))
