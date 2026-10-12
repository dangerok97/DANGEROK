# Vision — 25 percorsi didattici / 75 passaggi

Data: 12 ottobre 2026. Implementazione candidata, verifiche di rilascio nella PR.

Il catalogo rimane di 25 famiglie: questa versione non aggiunge altri 20 modelli,
ma completa i percorsi dei 20 introdotti nel pacchetto common-25-v1.
Ogni famiglia ha tre passaggi originali, riferiti a gruppi davvero presenti nel
manifest. I collegamenti sono simbolici; non vengono spostati ingranaggi reali,
misurate correnti/forze o ricostruiti gli interni del singolo esemplare.

Esempi: pulsante/matrice/controllo della tastiera; grilletto/pompa/ugello dello
spruzzatore; richiamo e riempimento del dispenser; leve/molla a torsione della
molletta; pareti e chiusura della borraccia isolante. La punta della matita e
lo strato adesivo del nastro sono regioni o strati, non ricambi staccabili.

Le fonti consultate sono collegate al singolo passaggio e supportano principi
costruttivi generali o esempi esplicitamente nominati. Testi e link sono nel
modulo walkthroughLibrary.ts; nessun disegno CAD o testo lungo e copiato.
Marchi nelle fonti NON identificano la marca dell'oggetto fotografato.

I riferimenti principali sono documentazione Apple e Analog Devices per i
gruppi elettronici/tocco; Adafruit per matrici e joystick; Kingston per Flash;
Bluetooth SIG, Sony e osservazione iFixit per l'audio; Pilot, Faber-Castell,
Pentel, edding e Pritt per gli strumenti di scrittura; 3M per il nastro; brevetti
originali di meccanismi per molletta, pinzatrice e pompe; Aptar per spruzzatori;
Thermos per doppia parete; Wera per trasmissione meccanica della coppia.

Le fonti esterne vengono aperte soltanto su scelta dell'utente. L'avvio di un
percorso non invia foto, non fa chiamate AI e non registra nuovi dati. Seed
incompatibili e modelli generati non ereditano automaticamente un percorso.
Il controllo del contratto e una difesa strutturale, non una verifica semantica
universale della geometria.

Test previsti: tutti i 75 passaggi disegnabili senza mutare i manifest, fonti
HTTPS e indici coerenti, duplicati/chiavi/forme incompatibili rifiutati; 20 nuove
famiglie esplorate in Chromium desktop/mobile e WebKit; ripristino del focus,
pausa e termine senza loop; fonti contestuali e controlli su schermi compatti.
Restano attivi i gate di flash/zoom/crop, X senza riapertura, schema fisso e
nessuna scansione durante l'esplorazione. I video nei test sono sintetici.

Nessuna nuova dipendenza, migrazione o modifica ai dati del catalogo. La prova
su fotocamera e flash fisici iPhone resta separata, non implicita nei test UI.
