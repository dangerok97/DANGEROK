# ORA staging — 28 settembre 2026

- Due impegni Home sovrapposti: la preparazione rilegge gli eventi attivi e calcola i minuti di sovrapposizione, poi produce una richiesta di spostamento senza disponibilità o invii inventati.
- La conversazione può preparare una ricerca Amazon.it per un oggetto utile o richiesto. La ricerca non consulta il catalogo Amazon e non ordina: scelta, prezzo e checkout restano sul sito Amazon.
- Verifica locale: 21 test mirati superati; verifica cloud sul nuovo SHA ancora necessaria.
- Il collegamento a un catalogo ufficiale richiederebbe accesso idoneo ad Amazon Creators API e valutazione dei termini per il caso d'uso ORA.

Aggiornamento: il primo test cloud Amazon ha evidenziato una risposta senza collegamento durante indisponibilità AI. La richiesta esplicita usa ora un passaggio diretto e persistito alla ricerca; 43 test mirati PASS in locale. Verifica del nuovo rilascio ancora aperta. La connessione di un account Amazon e l'ordine retail automatico non sono funzionalità di questo rilascio.

Verifica successiva: rilascio Amazon `113fb2f` SUCCESS e prova autenticata con link effettivo e limiti corretti. La seconda prova del calendario ha rilevato il conflitto ma chiesto indirizzi invece di preparare la bozza. La nuova correzione per due eventi Home attivi prepara immediatamente la bozza dalle fonti e nasconde quella superata dopo un cambiamento; 59 test locali mirati PASS. Resta la prova cloud di quest'ultima correzione.

Terza prova cloud sul rilascio `1e71f5c`: bozza autonoma pronta, con tempi esatti e nessun invio. Due schede duplicate e una data settimanale errata hanno richiesto un'ulteriore normalizzazione dei riferimenti Home prima della verifica finale.
