# ORA v146 — Una previsione non è un'attività già eseguita

## Caso osservato — 9 ottobre 2026
Dettaglio Aggiornamenti su mobile: «È previsto per oggi l'arrivo del pacco Amazon». La card mostrava «Prossimo passo — Non è disponibile un'azione eseguibile» e, dopo una verifica generica, un messaggio sul monitoraggio non confermato.

## Problema
`elencoAggiornamenti()` trattava **ogni** Opportunity come un lavoro da avviare, assegnava sempre `lavoro:'verify'` e «Verifica con ORA», anche quando la fonte non offriva né una domanda puntuale né un intervento possibile. `UpdateNextStep` compilava così una falsa sezione «Prossimo passo». La successiva risposta del modello poteva non avere alcuna utilità e dare l'idea di un controllo programmato che non risultava registrato.

## Correzione, senza hard-code di "pacco" o "Amazon"
1. Il backend trasmette `informational_only` da struttura del record (nessuna azione e nessuna domanda), non tramite parole chiave della descrizione.
2. La schermata informativa dice esplicitamente cosa è noto e cosa no. Non presenta un'attività vuota, non conferma l'esito previsto e non afferma che sia in corso un monitoraggio.
3. Un eventuale risultato di una verifica precedente viene mostrato come risposta storica, non come controllo attivo.
4. L'azione opzionale **Approfondisci con ORA** apre una conversazione contestuale con l'ID originale dell'opportunità. La bozza generica è modificabile e viene inviata soltanto quando l'utente decide; i dettagli personali non sono inseriti nell'URL.
5. Il percorso che apre una scheda opportunità come dettaglio rimane il default: solo il passaggio esplicito `entry='opportunity'` apre la conversazione con la relativa fonte.
6. Una segnalazione con offerta esplicita o domanda concreta mantiene «Verifica con ORA» e il normale percorso di lavoro.

## Confini di realtà
ORA possiede un capability di consultazione di messaggi collegati e situazioni relative a spedizioni, ma **non** un collegamento diretto al tracking in tempo reale del corriere/Amazon. Questa correzione non inventa stati «consegnato», modifiche, monitoraggi o notifiche. L'autonomia di monitoraggio richiede evidenza fresca e un job realmente schedulato nell'agent/ambient esistente.

## Prove
- `backend/tests/test_informational_updates_v146.py`.
- `frontend/src/components/home/v3/home3.test.ts` (verifica che non si crei una falsa azione e che la conversazione mantenga il handle originale).
- CI completa, regressioni native/situazioni e verifica mobile.
