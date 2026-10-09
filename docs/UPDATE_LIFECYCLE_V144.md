# V144 — aggiornamenti utili, situazioni seguite e viaggi già trascorsi

Richiesta 9 ottobre 2026 dopo tre video e un compleanno scaduto.

## Perché questa revisione

1. Un generico obiettivo interno («Capire quando la situazione raggiunge l'esito utile...») non è una spiegazione per la persona. La pagina deve mostrare quale situazione viene seguita, il suo stato dichiarato, perché ORA la controlla, quale condizione può richiedere attenzione, quando è prevista la prossima verifica e l'eventuale ultimo riscontro realmente eseguito.
2. L'avviso temporaneo legato a un appuntamento passato è inutilizzabile: gli aggiornamenti legacy nati senza `valid_until` sono verificati contro **le date del calendario originario**. La verifica è limitata a opportunità classificate perishable e appoggiata su riferimenti proprietari esistenti. Una disputa su orari tra email e calendario usa `connected_situation_links.target_ref`. Un rimborso dopo un viaggio, una fonte illeggibile o un evento senza data non sono cancellati per supposizione.
3. Le richieste vaghe dell'agente non devono costringere la persona a indovinare la domanda: nell'aggiornamento compare solo la richiesta specifica di un Need persistito. In mancanza di tale informazione, l'azione non è proposta come se fosse pronta.

## Interazione

- **Non ancora · Ricalcola** e **È cambiata · Spiega a ORA** aprono l'originale conversazione (quando nota) con una bozza pertinente che l'utente deve ancora inviare. È il motore cognitivo esistente a leggere nuovi fatti, rivedere situazione e scegliere se/come pianificare un altro controllo; l'apertura da sola non simula una stima di asciugatura né promette una nuova sveglia.
- **Situazione conclusa** aggiorna lo stato canonico con revisione attesa, poi interrompe goal, needs e wake.
- **Ok grazie · Basta avvisi** cancella i futuri avvisi del goal e ritira l'intenzione di monitoraggio senza sostenere che i panni siano asciutti o la situazione risolta.
- La conferma di una notifica ricevuta non equivale a una conferma dello stato fisico.
- La disponibilità dell'alert/monitor dipende dagli effettivi dati salvati, dalle fonti meteo aggiornate e dall'abilitazione del runtime e delle notifiche.

## Verifiche sintetiche

Tests: `backend/tests/test_useful_updates_v144.py`, `frontend/src/components/home/v3/home3.test.ts`, CI con controlli backend, TypeScript, sicurezza e regressioni di prodotto.

## Restano da validare su dispositivo reale

Notifica anticipata per pioggia, affidabilità del meteo disponibile, stima di asciugatura, turni «li ho messi dentro», «quando smette la pioggia li rimetto fuori», ri-schedulazione autonoma e resa della schermata autenticata. Nella V144 esiste il percorso per riferire il cambio alla stessa sessione e utilizzare il planner già presente: la prova end-to-end con questi turni specifici non va dichiarata finché non eseguita.
