# v145 — Non chiedere di risolvere un viaggio già terminato

**Segnalazione reale:** 9 ottobre 2026, dettaglio Aggiornamenti: viaggio a Vibo Marina del 20 settembre 2026, due orari discordanti, richiesta ancora attiva; un vecchio testo dice erroneamente «42 giorni».

## Causa verificata nel codice

La lettura delle discrepanze calendario in `opportunities/snapshot.py` metteva in fondo gli appuntamenti passati, ma **continuava a inviarli all'AI**. La successiva superficie di Home si affidava alla classificazione `time_sensitivity="perishable"` e a `valid_until`, entrambi opzionali e storicamente variabili. I goal avviati potevano quindi restare in attesa di una risposta anche dopo la data effettiva del viaggio.

## Correzione generale

1. Prima del ragionamento, una discrepanza su un appuntamento viene accettata solo se il calendario originale **proprietario** è datato, verificabile e non è terminato. Se la fonte è scollegata, non si trasforma in una nuova richiesta.
2. Le opportunità storiche sono rilette contro l'appuntamento **reale**, indipendentemente dalla categoria di urgenza scritta dall'AI. La singola scheda viene esclusa da Home e dai dettagli quando la fonte è scaduta o il vecchio conflitto non è più verificabile.
3. Anche i goal agent collegati e le richieste di chiarimento vengono sottoposti allo stesso controllo. Non possono produrre notifiche, risposte o autorizzazioni eseguibili dopo la scadenza. Il worker che riprende un goal a fonte scaduta lo archivia in modo tracciabile senza eseguire operazioni esterne e cancella i Need pendenti.
4. Un link salvato a un avviso ormai chiuso non mostra nuovamente il lavoro: il dettaglio presenta una spiegazione di chiusura.
5. Nessuna memoria permanente viene cancellata. Una controversia successiva al viaggio (rimborso, spese o altri esiti) resta separata e non viene confusa con la scelta dell'orario **prima della partenza**.

## Gate di regressione

`backend/tests/test_vibo_stale_disagreement_v145.py`: stesso giorno ed evento dello screenshot; opportunità anche quando il modello la classifica erroneamente `changing`; fonti future, mancanti e altrui; dettaglio, Home, deep link, azioni e notifiche; recupero del goal senza effetti esterni. Il gate entra in CI.

## Cosa resta da osservare sul vero account

Prove automatiche e deploy non equivalgono a consultare l'account reale in iPhone. Dopo il rilascio v145 va verificato se la scheda Vibo Marina scompare effettivamente dalla lista, dal conteggio e dai vecchi link. Se non accade, serve una diagnosi owner-scoped del record residuo: non si devono inventare la provenienza o il contenuto del database.
