# ORA v130 — Recupero persistente dei promemoria

Data: 8 ottobre 2026. Base: v129, `f3724d1`. Obiettivo: non perdere un promemoria annuale già autorizzato se il processo si interrompe fra la scrittura della memoria corretta/dimenticata e il riallineamento della ricorrenza.

## Contratto implementato

- La governance della memoria cambia lo stato del vecchio ricordo e, **nello stesso aggiornamento Mongo del medesimo documento**, registra `recurring_reconcile.status=pending`, con il prossimo momento di controllo. Se il processo si arresta dopo questo aggiornamento, il lavoro da svolgere resta nel database.
- La via immediata riallinea la ricorrenza e imposta `completed` soltanto dopo il completamento degli aggiornamenti. Un fallimento non deve essere considerato esito positivo.
- `RecurringMemoRecovery` legge un piccolo gruppo di marcatori pendenti, li reclama con un lease e un token, risolve soltanto ricordi dello stesso proprietario, percorre al massimo 12 sostituzioni e trasferisce/disabilita **soltanto ricorrenze esistenti e autorizzate**. Una destinazione non ancora salvata produce un rinvio, non una cancellazione.
- Errori di database e processi terminati lasciano la riconciliazione riutilizzabile; il recupero limita il lotto e applica backoff di 60–3.600 secondi per evitare attese infinite su un'unica pratica.
- Il backend esegue una passata limitata all'avvio. La corsia già esistente `recurring-memos` include la verifica periodica del recupero, senza aumentare il numero massimo di corsie del runtime e senza introdurre un nuovo scheduler. Non è un'automazione di sviluppo.
- Il momento di scadenza controlla lo stato effettivo del ricordo. Una memoria `superseded` non genera una notifica falsa e non viene definitivamente disabilitata prima di aver risolto l'eventuale ricordo successore.

## Prove

`test_recurring_memo_recovery_v130.py` copre: interruzione immediatamente dopo la persistenza della correzione, ripresa, assenza di duplicati, backoff in errore, lease di worker scaduto, dimenticanza, isolamento per owner, protezione contro avvisi sulla vecchia data, assenza di ricorrenze create senza richiesta.

`PHASE2_REAL_MONGO=1 python -m pytest -q tests/test_recurring_memo_restart_v130.py -x` richiede un Mongo di test senza autenticazione su loopback. Due interpreti Python distinti, con un'interruzione forzata del primo, verificano che soltanto Mongo conservi gli stati necessari al recupero. Il terzo passaggio assicura l'idempotenza. Il database usa un nome UUID e viene eliminato soltanto se il suo marker di proprietà coincide. Non vengono utilizzati account, LLM o provider reali.

## Confini non coperti

- **Non è una transazione multi-documento** tra vecchio ricordo, nuovo ricordo e memo; il recupero è eventuale dopo che il nuovo ricordo esiste. Se il processo muore prima che venga salvato il ricordo sostitutivo, il codice non fabbrica un ricordo e resta in attesa del completamento della scrittura originaria.
- Il trasferimento della ricorrenza non dimostra che una notifica sia arrivata al telefono. La consegna richiede il percorso Opportunity → Delivery → dispositivo, da collaudare separatamente.
- Il loop periodico dipende dall'abilitazione del runtime ambientale; la passata di startup resta limitata per non bloccare il server. Una indisponibilità prolungata di Mongo ritarda le riconciliazioni.
- È preservato il consenso precedente: nessun comando di correzione della memoria crea un promemoria se prima non ne esisteva uno.

Questo rilascio non modifica la UI, non aggiunge una seconda schedulazione e non afferma completata l'autonomia generale.
