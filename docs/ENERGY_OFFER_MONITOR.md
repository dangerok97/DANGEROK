# Ricerca continua delle offerte online

## Personalizzazione dopo il caricamento

La ricerca rilegge i fatti confermati del profilo al momento di ogni controllo.
Oltre al comune dichiarato, per RC auto può usare la marca e il modello
confermati (per esempio dopo la verifica del libretto). Targa, telaio, indirizzo
e documenti integrali non entrano nelle query. Una modifica confermata al
comune o al modello anticipa il prossimo controllo dei monitor pertinenti;
non richiede che l'utente ricarichi il contratto. Il pannello mostra i
passaggi ancora necessari per verificare copertura, requisiti e preventivo
personale per ciascuna categoria. Il modello auto da solo non determina il
premio e la stima di vendita luce/gas non prova che la tariffa sia acquistabile
nel comune dichiarato.

## Esperienza

Una bolletta luce o gas, una polizza auto, casa o generica oppure un contratto telefonico riconosciuto
crea un controllo persistente. ORA cerca offerte online subito dopo
l'elaborazione del documento e poi ogni sette giorni, anche se l'app non è
aperta. La pagina Documenti mostra ultimo controllo, prossimo controllo,
alternative con link alla pagina del venditore e un comando per sospendere la
ricerca. Un nuovo risparmio stimato positivo sulla componente di vendita
innesca la revisione delle opportunità: ORA valuta se comunicarlo. Le pagine
senza confronto personale restano visibili come piste per un preventivo e non
innescano da sole un avviso di risparmio.
Durante il primo percorso, dopo il caricamento di bolletta, polizza o contratto
telefonico compare anche lo stato del confronto: si aggiorna mentre ORA legge
il documento e ricerca le offerte, senza interrompere le domande successive.
Il percorso propone il caricamento del contratto telefonico a chi indica il
telefono tra i servizi ricorrenti.

## Fonti e limiti

Ogni passaggio avvia `ResearchService` con `allow_reuse=False`. Il servizio
usa i provider web già configurati, pianifica ricerche mirate, valuta evidenze
e produce citazioni. Nessun export XML o catalogo di offerte viene scaricato,
indicizzato o mantenuto. Per luce e gas sono valutate le pagine di offerte
specifiche osservate dalla ricerca, anche se non incluse nella sua sintesi;
per gli altri contratti restano richieste pagine citate dalla sintesi. URL e
identificatori di fonte vengono controllati. La data di osservazione è
visibile. Dopo dieci giorni il risultato non entra in nuove valutazioni e
scompare dalla pagina.

Il testo del documento, nome, indirizzo, POD/PDR, targa e numero di polizza non
entrano nelle query web. Per l'energia si usa eventualmente il solo consumo
annuo e l'unità. Prezzo unitario e quota commerciale del contratto attuale
vengono estratti localmente soltanto da voci esplicitamente etichettate. Un
confronto numerico richiede le stesse due componenti nello snippet oppure nella
pagina ufficiale della singola offerta e una tariffa fissa. La pagina viene
letta in tempo reale con limiti di dimensione e tempo, senza conservarne una
copia; risposte con rinvio, indirizzi non pubblici e prezzi multipli sono
scartati. Tariffe variabili, valori
multipli, OCR non confermato o consumi annui stimati restano senza cifra.
La stima riguarda la sola componente di vendita: non include rete, imposte,
oneri, sconti, requisiti o il totale della bolletta. ORA consiglia di
verificare il preventivo completo prima del cambio. Se la tariffa pubblica è
incompleta ma la bolletta contiene entrambe le componenti, ORA indica la
soglia annua che un nuovo preventivo deve battere. Se una polizza riporta un
premio annuo esplicito, usa quel premio come soglia a parità di coperture;
non deduce un risparmio dal prezzo pubblicitario. Per la RC auto la schermata
offre anche il collegamento al preventivatore pubblico IVASS: il questionario
personale viene compilato dall'utente e ORA non trasmette dati della polizza.
Se un contratto telefonico riporta un canone mensile esplicito e non proviene
da OCR non confermato, ORA lo usa come soglia; chiede di verificare traffico,
roaming, copertura, attivazione, requisiti e promozioni. Non dichiara un
risparmio numerico dal solo canone pubblicato. Una ricerca fallita non vale come «nessuna
offerta» e viene ripetuta dopo dodici ore. Anche una ricerca senza pagine
specifiche verificabili viene ripetuta dopo dodici ore, mantenendo il
consiglio sulla soglia personale se il documento la permette.
Tra le offerte con entrambe le componenti confrontabili, ORA ordina per
risparmio stimato e propone quella con il valore maggiore. La ricerca chiede
esplicitamente prezzi e quote fisse alle fonti ufficiali; non definisce
«migliore sul mercato» una proposta se non ha dati per confrontarla.
Se la prima ricerca non trova prezzi confrontabili, ORA prova una seconda
ricerca mirata alle singole pagine con prezzo unitario e quota commerciale.
Se anche questa è inconcludente, due query di prezzo precise interrogano
direttamente il provider web già configurato; le fonti osservate vengono
registrate con data e URL e le singole pagine sono valutate con le stesse
regole prudenziali. Le query non contengono dati della bolletta né un elenco
predefinito di venditori. Se la prima ricerca su assicurazioni o telefonia non
trova pagine di offerte specifiche, ORA interroga anche il provider web con
una ricerca pubblica mirata senza dati personali. Lo stesso recupero avviene
quando la sintesi della ricerca è insufficiente, purché il provider web
restituisca fonti pubbliche; in caso contrario il controllo viene ritentato.
Le pagine generali che raccolgono più tariffe non vengono presentate come
un'offerta individuale. Per la telefonia vengono esclusi anche homepage e
liste di piani e pagine intitolate soltanto «Offerte», anche quando il
selettore AI le avrebbe proposte: una pagina
deve identificare un piano specifico prima di apparire come alternativa.

## Operatività

`energy_offer_monitors` conserva un record per persona e contratto con
categoria, riferimento al documento, data di prossima verifica, lease, ID
della ricerca e un massimo di tre alternative. Il nome della collezione e
l'endpoint `GET/PATCH /api/energy-offers/monitoring` restano per
compatibilità; il contenuto ora comprende anche assicurazioni. Il runtime
`ambient` consuma un controllo dovuto circa ogni minuto. Un documento
cancellato o archiviato o una preferenza disattivata ferma la sorveglianza.
La ricerca riparte con una nuova lettura del web dopo ogni scadenza, anche
dopo un riavvio.

Questa bozza non cambia fornitore, non acquista una polizza e non contatta
venditori. Eventuali azioni future devono passare per l'autorità ordinaria
dell'agente ORA.

## Verifica

La ricerca reale e il monitor su ORA Staging sono stati provati con bolletta e
polizza sintetiche. Il 26/09 una bolletta sintetica da 2.700 kWh/anno con
prezzo 0,22 €/kWh e quota commerciale 12 €/mese ha prodotto una proposta
Iren Web Self Luce Prezzo Fisso con stima di 203,70 €/anno in meno sulla sola
componente di vendita. La pagina ufficiale è stata letta durante il controllo.
Il prossimo controllo è stato programmato sette giorni dopo; il documento di
prova è stato rimosso e il monitor sospeso. La resa visiva nell'app installata
non è ancora stata verificata manualmente.
Il test integrato usa una bolletta sintetica e due offerte con condizioni
esplicite: verifica la migliore proposta, un nuovo controllo dopo sette giorni
con prezzi cambiati e il cambio di consiglio dopo il riavvio del servizio.
Il tempo settimanale viene simulato, senza attendere sette giorni reali.
I risultati dipendono dalla disponibilità dei provider e dalle pagine dei
venditori; un preventivo personale resta necessario per decidere un cambio.
# Personalizzazione e soglia degli avvisi

La ricerca usa il comune soltanto quando è stato dichiarato o confermato
dall'utente nel profilo: indirizzo, coordinate, targa, POD/PDR e testo integrale
del documento non vengono inviati come query. Il comune è un vincolo da
verificare nella fonte: il solo fatto di cercarlo non dimostra che l'offerta
sia sottoscrivibile lì.

Il monitor registra anche alternative non confrontabili per permettere
all'utente di aprire la fonte e richiedere un preventivo. Una nuova revisione
proattiva delle opportunità viene avviata soltanto se compare un'offerta con
stima positiva della componente di vendita su consumi e condizioni esplicite;
un cambio di titolo, una tariffa più cara o una pagina generica non costituiscono
una notizia di risparmio. Per RC auto occorrono un preventivo personale e la
verifica di veicolo, conducente e garanzie; per telefonia occorrono copertura,
limiti del piano e requisiti di accesso. Non esiste al momento un catalogo
completo e verificato di tutte le offerte del mercato né un preventivatore
personale integrato per assicurazioni: ORA non può garantire la migliore
offerta assoluta.
