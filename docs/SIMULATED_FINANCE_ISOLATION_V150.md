# ORA v150 — I soldi di prova non sono soldi dell'utente

9 ottobre 2026. Continuazione dei casi finanziari ING/iCloud e Mock ASPSP dopo v147–v149.

## Problema residuale

v148b etichettava le righe e i saldi simulati in **Conti e denaro**, ma alcuni percorsi avevano ancora accesso a osservazioni bancarie fittizie senza separarle dai dati reali:

- `financial.observed.this_month` sommava indistintamente movimenti bancari reali e di prova;
- `financial.horizon.what_is_coming` poteva includere fatti economici precedentemente derivati da `FakeBankProvider`, anche quando conservati come memorie governate;
- `financial.movements.look_at_a_movement` poteva proporre un movimento di test come un fatto della persona tramite governance;
- `financial.batching.read_what_is_new` poteva pagare interpretazioni AI su un estratto conto fittizio;
- `what_was_seen` poteva fondere in una singola presunta ricorrenza righe con descrizione simile provenienti da conto reale e conto simulato.

Un saldo `Mock ASPSP` non è una disponibilità reale. Un addebito `-€760` di prova non è un pagamento autentico.

## Correzioni

1. Un controllo unico, `financial.reality`, usa `provenance.provider_reality` e, per dati storici, metadati del conto **scoperti solo per owner_id**. Non deduce che una riga sia fittizia dal suo importo o dal suo nome commerciale.
2. I nuovi movimenti dichiarati simulati restano come osservazioni di prova, ma non creano un fatto economico, una proposta di memoria, un obiettivo o una previsione reale. La coda di interpretazione li registra come `simulated` senza chiamare il modello.
3. La somma del mese esclude le righe fittizie e comunica il conteggio escluso. Se esistono soltanto dati simulati, non produce un falso totale di spese/entrate reali.
4. Le ricorrenze raggruppano separatamente movimenti veri e simulati, ed etichettano i secondi con `simulato=true`.
5. Le memorie finanziarie storiche con riferimenti bancari dimostrabilmente **solo** simulati non contribuiscono più all'orizzonte reale. Il loro archivio non viene cancellato, e in `Conti e denaro` restano riconoscibili con stato `SIMULATO`.
6. Riferimenti mancanti o una fonte mista simulata/reale sono trattati in modo conservativo: non dichiarati fittizi in assenza di prove sufficienti.

## Gate

`backend/tests/test_simulated_finance_isolation_v150.py` prova la mancata promozione di importi di test a memoria, il budget zero di chiamate AI per una banca fittizia, le somme del mese solo reali, ricorrenze reali/fittizie con identica descrizione, l'isolamento tra account e la neutralizzazione di memorie storiche fittizie.

Nessuna scrittura di pulizia distruttiva sul database. I saldi simulati restano nel percorso demo, non entrano negli strumenti di finanziamento reale. L'uso con account autenticato e consentito richiede verifica end-to-end dopo il deployment.
