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
