# Ricerca continua delle offerte online

## Esperienza

Una bolletta luce o gas, una polizza auto, casa o generica oppure un contratto telefonico riconosciuto
crea un controllo persistente. ORA cerca offerte online subito dopo
l'elaborazione del documento e poi ogni sette giorni, anche se l'app non è
aperta. La pagina Documenti mostra ultimo controllo, prossimo controllo,
alternative con link alla pagina del venditore e un comando per sospendere la
ricerca. Un risultato nuovo entra nel normale flusso delle opportunità: ORA
decide se vale la pena proporlo, senza creare un avviso a ogni controllo.

## Fonti e limiti

Ogni passaggio avvia `ResearchService` con `allow_reuse=False`. Il servizio
usa i provider web già configurati, pianifica ricerche mirate, valuta evidenze
e produce citazioni. Nessun export XML o catalogo di offerte viene scaricato,
indicizzato o mantenuto. Solo le pagine di venditori o assicuratori che la
ricerca ha effettivamente citato possono diventare alternative; URL e
identificatori di fonte vengono controllati. La data di osservazione è
visibile. Dopo dieci giorni il risultato non entra in nuove valutazioni e
scompare dalla pagina.

Il testo del documento, nome, indirizzo, POD/PDR, targa e numero di polizza non
entrano nelle query web. Per l'energia si usa eventualmente il solo consumo
annuo e l'unità. Prezzo unitario e quota commerciale del contratto attuale
vengono estratti localmente soltanto da voci esplicitamente etichettate. Un
confronto numerico richiede le stesse due componenti nello snippet della
pagina ufficiale citata e una tariffa fissa; tariffe variabili, valori
multipli, OCR non confermato o consumi annui stimati restano senza cifra.
La stima riguarda la sola componente di vendita: non include rete, imposte,
oneri, sconti, requisiti o il totale della bolletta. ORA consiglia di
verificare il preventivo completo prima del cambio. Se la tariffa pubblica è
incompleta ma la bolletta contiene entrambe le componenti, ORA indica la
soglia annua che un nuovo preventivo deve battere. Se una polizza riporta un
premio annuo esplicito, usa quel premio come soglia a parità di coperture;
non deduce un risparmio dal prezzo pubblicitario. Una ricerca fallita non vale come «nessuna
offerta» e viene ripetuta dopo dodici ore. Anche una ricerca senza pagine
specifiche verificabili viene ripetuta dopo dodici ore, mantenendo il
consiglio sulla soglia personale se il documento la permette.

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
polizza sintetiche. I test coprono anche estrazione prudente delle componenti,
stima positiva, rifiuto di prezzi variabili o incompleti, deduplica e
ritentativi. Il consiglio quantificato richiede ancora una prova end to end
con fonte web che pubblichi entrambi i valori nello snippet e la verifica UI.
I risultati dipendono dalla disponibilità dei provider e dalle pagine dei
venditori; un preventivo personale resta necessario per decidere un cambio.
