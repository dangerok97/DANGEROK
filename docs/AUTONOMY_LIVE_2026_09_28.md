# Autonomia — prove reali 28 settembre 2026

## Rilasci
- 83ec999: calendario Home nel riepilogo autonomo e calendar.local.read. Railway 745110b1 SUCCESS.
- e2fc2b6: riesami temporali senza nuovi dati, cooldown ritentabile. Railway 8955cf61 SUCCESS.
- 4e457f2: calcolo delle sovrapposizioni, controllo delle proposte, fonti calendario nell'ammissione. Railway 039d8d87 SUCCESS.

## Prove
Account sintetici separati. Due eventi Home per il giorno successivo (10–11 e 10:15–11:15), dipendenza dal modulo originale, apertura esplicita dello sportello. App dichiarata in background. Nessuna Home, chat, scansione o avanzamento manuale invocato; soltanto letture degli esiti.

Prima prova: worker spontaneo, cambiamenti consumati, opportunità creata. Test di qualità NON PASS: 15 minuti invece di 45, suggerimento prima dell'apertura non compatibile. Nessun goal; non descritto come lavoro completato.

Seconda prova: revisore non accetta o non restituisce il formato contrattuale; worker conserva le modifiche e programma retry a 300 secondi. Nessun consiglio non verificato pubblicato. Provider di riserva osservati nei log (Groq/Mistral); non prova dell'uso di OpenAI. Affinato schema top-level del revisore e diagnostica per distinguere rifiuto, schema errato, identità modificata e indisponibilità, senza contenuti personali nei log.

Test locali: 18 sul calendario/background, 12 sui riesami, 17 su qualità/fonti/continuità (insiemi parzialmente sovrapposti). Nessuna migrazione, nuova dipendenza runtime, telefonata o invio a terzi.

Obiettivo generale ancora aperto: affidabilità trasversale, risultati utili ripetibili, osservazione continuativa e device reali non attestati da questa prova.

## Recupero e risultato osservato
Rilascio 95e3672, Railway efa30dae SUCCESS. Il wake persistente viene recuperato dopo il riavvio senza nuovi input: controllo verified, opportunità, ammissione del goal, lettura fonti e preparazione effettiva. Alle 17:36 Europe/Rome il goal è in attesa del via libera con bozza completa salvata. Nessun invio eseguito.

Qualità ancora NON pienamente accettata: nella bozza il modello trasforma un conflitto in impossibilità certa e propone consegna postale nella giornata senza prove. Rafforzate le istruzioni sia di generazione sia di revisione; questa modifica non costituisce prova di accuratezza del modello. La bozza già esistente non viene riscritta retroattivamente.

Corretto anche il tipo delle fonti: una notifica di cambiamento non deve sovrascrivere calendar_event con change. Regressione dedicata.

Prova effettiva OpenAI su account sintetico: provider configurato ma failure_kind=quota, runtime_state=cooldown. La risposta viene dai fallback; non è prova di uso OpenAI e non è stato cambiato il provider primario.

## Preparazione deterministica e ricerca Amazon — verifica in corso
La lettura autenticata del caso sintetico ha confermato che `/opportunities/{id}/work` e `/agent` espongono la bozza salvata, ma la vecchia bozza inventa un corriere garantito nello stesso giorno. Per una coppia di impegni Home ancora attivi e sovrapposti, la nuova preparazione rilegge le due fonti del proprietario, calcola l'intersezione e produce una richiesta di spostamento senza attribuire disponibilità, tempi di percorrenza o invii già eseguiti. Se i due impegni cambiano o non sono più sovrapposti, non prepara il vecchio conflitto. Non modifica le bozze già persistite.

La capacità conversazionale `prepare_amazon_search` genera una ricerca su Amazon.it per una categoria specifica con query minima e senza dati personali. È un passaggio all'utente: nessun catalogo, prezzo, disponibilità, carrello, ordine o collegamento dell'account Amazon è verificato da questa capacità. Un catalogo ufficiale richiede accesso e approvazione per Amazon Creators API; Amazon Pay serve a pagare presso un proprio commerciante, non a ordinare prodotti retail da Amazon per conto del cliente. Prove cloud del nuovo rilascio ancora da eseguire.

Sul rilascio `113fb2f` la richiesta esplicita di una lampada Amazon ora ha restituito un link apribile e un resoconto veritiero in circa sette secondi, anche durante indisponibilità dei modelli. Nel secondo account sintetico separato gli impegni Home (10:00–11:00 e 10:15–11:15) hanno generato autonomamente l'opportunità con 45 minuti corretti, ma l'ammissione si è fermata su una richiesta di indirizzi: work `needs_user`, nessuna bozza. Non è un risultato accettato. Una correzione successiva ammette e prepara subito questo preciso tipo di conflitto rilegendo le fonti; smoke cloud ancora aperto.

Terzo account sintetico dopo il rilascio `1e71f5c`: il worker ha creato goal e bozza pronta, con 45 minuti calcolati, il 29/09/2026 e una richiesta di spostamento che chiede disponibilità al referente. Nessun destinatario scelto né messaggio inviato. L'ispezione completa ha mostrato due opportunità e due goal per gli stessi due eventi; una scheda indicava erroneamente lunedì invece di martedì e suggeriva servizi non verificati. La successiva normalizzazione dei fatti Home e dell'identità dell'opportunità evita questa ripetizione nei nuovi casi; da provare sul servizio pubblicato. Le vecchie schede sintetiche non sono riscritte retroattivamente.
