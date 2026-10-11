# ORA v157 — presa in carico eseguibile delle Situazioni temporanee

## Difetto osservato su account autenticato (11 ottobre 2026)
La scheda Home `PANNI STESI` esiste con inserimento 11 ottobre alle 10:15 e scopo futuro, ma segnala `Nessun controllo programmato`. Il dato rimane in memoria temporanea senza una sveglia collegata. Non è prova delle condizioni fisiche dei panni o di errori meteo.

## Causa software
Una Situation salvata con `attention_intent` era affidata alla discovery generica: poteva decidere il silenzio senza creare un Agent goal. Il recupero v149 rimetteva la sveglia solo a un goal che possedeva già un `next_run_at`; nessun recupero poteva generare da zero il lavoro mancante.

## Correzione v157
- `SituationService` ammette subito nel medesimo motore Agent/Ambient l'intenzione di attenzione **già decisa dal modello**. Goal e primo wake owner-scoped con id stabile, senza nuovo timer specifico per panni e senza un nuovo orchestratore.
- La prima sveglia significa **riesaminare e pianificare** (`situation_initial_review`), non controllare meteo o avvisare. Il dettaglio ha `status=review_pending`, `assessment_at/label` ma **non** `next_check_at` finché l'AI non fissa un checkpoint.
- Quando AI Core `schedule_situation_check` o Agent `_wait` scelgono un checkpoint, il goal viene promosso a `situation_followup` e il calendario delle sveglie viene aggiornato senza confondere la vecchia ora di revisione con la nuova ora di controllo.
- Il recupero Ambient esistente tenta anche l'ammissione delle situazioni vecchie attive e attente senza goal, limitandosi a un batch owner-scoped; una nuova scansione non crea duplicati.
- Un wake perso dopo ammissione può essere recuperato dal meccanismo v149. Annullamenti, risoluzioni e ritiro dell'intenzione cancellano goal e wake pertinenti, senza toccare le situazioni degli altri utenti.
- Se il motore Ambient è spento, nessun goal di monitoraggio viene creato e nessuna futura verifica viene promessa.
- Se il modello non ha ancora stabilito un checkpoint, la UI descrive il **riesame** anziché inventare una notifica, una fonte meteo o l'esito fisico.

## Sicurezza
Nessun tempo di asciugatura o orario di notifica inventato. Nessun nuovo provider, permesso, invio, chiamata, pagamento o promemoria di calendario reale. Il risultato finale resta condizionato alle prove effettive del modello e alle fonti accessibili. Il browser non può provare il push nativo iOS.

## Test
`backend/tests/test_situation_initial_admission_v157.py`: ammissione idempotente, separazione del riesame dal controllo, promozione a checkpoint, re-check con modello, blocco e recupero della sveglia, isolamento utenti, recupero su Situation già esistente, annullamento e ritiro esplicito dell'attenzione. Eseguito in CI v157 e in `situation-followup-regressions.yml` con le regressioni precedenti.

## Accettazione reale
Dopo il rilascio, su account autenticato: la situazione originale non deve essere duplicata o cancellata; l'eventuale `review_pending` deve essere verificabile tramite backend e non spacciato per controllo; solo un `scheduled` con orario, goal e wake validi dimostra un checkpoint. Al prossimo wake il modello deve leggere davvero il contesto e le fonti consentite. Nessun risultato fisico può essere dedotto dalla sola esecuzione tecnica.
