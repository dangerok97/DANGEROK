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
annuo e l'unità. Una pagina di offerta può dimostrare che esiste
un'alternativa, ma non che sia la più conveniente per questa persona. Il
sistema non afferma risparmi o superiorità senza prezzo completo, requisiti,
coperture e condizioni del contratto attuale confrontabili. Il pannello
esplicita questa incertezza. Una ricerca fallita non vale come «nessuna
offerta» e viene ripetuta dopo dodici ore.

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

## Verifica prima dell'attivazione

I test coprono profili senza identificatori sensibili, polizze, selezione di
sole fonti citate, periodicità persistente, deduplica e ritentativi. Restano
da provare con un provider configurato nell'ambiente di esercizio una ricerca
vera, un documento sintetico end to end e la resa della schermata. I
risultati di ricerca dipendono dalla disponibilità dei provider e dalle
pagine pubblicate dai venditori. Per presentare offerte come «più
convenienti» serve ancora un confronto verificabile di prezzo e condizioni.
