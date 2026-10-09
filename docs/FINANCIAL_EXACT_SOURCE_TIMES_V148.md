# v148 — Scadenze economiche espresse con fuso orario

Il messaggio iCloud+ mostrato il 9 ottobre 2026 indica un rinnovo da €0,99 al mese a partire da `2026-10-11 03:25:28 America/Los_Angeles`. In Italia, per quella data, significa **11 ottobre 2026 alle 12:25 CEST**. La previsione relativa nel titolo «tra 2 giorni» non può sostituire la data esplicita del corpo.

La v147 precedente ha già la rilettura owner-scoped delle email, la prova degli importi e la protezione dei conti simulati. Questa piccola revisione interviene solo nel suo `source_grounding` esistente. Se il giudizio ha riconosciuto un impegno e ha già espresso una scadenza, una **singola data/ora esplicita con IANA timezone** proveniente dal testo originale prevale sulla stima ricavata dal titolo. Se ci sono più date, la zona non è riconosciuta o l'ora locale è ambigua/inesistente per il cambio DST, il codice non sceglie.

Non vengono inventate scadenze se la fonte o il giudizio non ne confermano una, non si alterano gli importi e il corpo dell'email non viene salvato nel record finanziario. Test: `backend/tests/test_financial_email_grounding_v147.py`.
