# ORA staging — 28 settembre 2026

- Due impegni Home sovrapposti: la preparazione rilegge gli eventi attivi e calcola i minuti di sovrapposizione, poi produce una richiesta di spostamento senza disponibilità o invii inventati.
- La conversazione può preparare una ricerca Amazon.it per un oggetto utile o richiesto. La ricerca non consulta il catalogo Amazon e non ordina: scelta, prezzo e checkout restano sul sito Amazon.
- Verifica locale: 21 test mirati superati; verifica cloud sul nuovo SHA ancora necessaria.
- Il collegamento a un catalogo ufficiale richiederebbe accesso idoneo ad Amazon Creators API e valutazione dei termini per il caso d'uso ORA.

Aggiornamento: il primo test cloud Amazon ha evidenziato una risposta senza collegamento durante indisponibilità AI. La richiesta esplicita usa ora un passaggio diretto e persistito alla ricerca; 43 test mirati PASS in locale. Verifica del nuovo rilascio ancora aperta. La connessione di un account Amazon e l'ordine retail automatico non sono funzionalità di questo rilascio.
