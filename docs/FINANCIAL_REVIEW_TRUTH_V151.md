# ORA v151 — Riletture email con esiti verificabili e scadenze giornaliere

Contesto: aggiornamenti di ORA, Focus economico ING/iCloud e dati bancari simulati. Le correzioni principali sono già state distribuite nella serie v147–v150 (PR #185, #187, #189, #191). Questa revisione corregge due regressioni residue.

## 1. Un secondo clic non è un errore di Gmail

Prima, `review_email_financial_sources` ignorava le email già rilette (correttamente) ma poi dichiarava «Non ho potuto rileggere le email» quando il conteggio era zero: l'utente poteva interpretarlo come un collegamento Gmail guasto. Peggio, conteggiava anche `nothing` e `already_known` come fonti «corrette» e diceva che i dati erano aggiornati.

Ora distingue:
- `checked`: fonti per cui si è tentata una rilettura
- `read_successfully`: email originali effettivamente lette (non implica correzione)
- `updated`: nuovi fatti/modifiche rilevate
- `unchanged`: fatto riletto ma già corretto
- `unconfirmed`: il giudizio non ha confermato il precedente significato economico, senza cancellazioni arbitrarie
- `already_reviewed`: fonti già verificate, non rilette inutilmente
- `not_available`: impossibilità di rileggere o concludere l'interpretazione

Se tutte le fonti erano già verificate, lo dice esplicitamente. Se non ci sono fatti economici già riconosciuti da rileggere, non spaccia l'assenza di candidati per una casella Gmail vuota.

## 2. Riferimenti Gmail legacy normalizzati

Un vecchio fatto può contenere un riferimento `mail:<id>` nel campo provenance invece del solo `<id>`. La nuova verifica usa l'ID Gmail normalizzato, sempre con controllo del proprietario, mantenendo l'ID canonico nelle fonti del fatto.

## 3. Scadenze senza ora valide per l'intera giornata

Per un fatto finanziario con `due_at: 2026-10-10` il sistema precedente creava implicitamente la mezzanotte UTC. Alle 11:00 dello stesso 10 ottobre la voce non era più «in arrivo». ORA ora tratta le scadenze **solo-data** come valide per tutta la data indicata. Un timestamp con ora e offset espliciti resta invece una scadenza puntuale e non viene prorogato. Non viene dichiarato avvenuto l'addebito: si mantiene soltanto visibile l'impegno fino alla fine del giorno.

## Confini

Nessun importo inventato, nessun trasferimento, lettura bancaria o invio email avviato, nessuna mutazione di memorie permanenti esistenti. Questi test usano dati sintetici; il comportamento nell'account reale va verificato con una sessione autenticata.
