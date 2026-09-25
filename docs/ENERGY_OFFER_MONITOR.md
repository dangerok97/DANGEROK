# Monitor continuo delle offerte luce e gas

## Esperienza

Quando ORA legge una bolletta luce o gas, registra una sorveglianza dell'utenza. Cerca subito nel Portale Offerte pubblico e ripete il controllo ogni sette giorni, finché la sorveglianza resta attiva. La data del prossimo controllo è in MongoDB e sopravvive ai riavvii. La persona vede lo stato nella pagina Documenti e può sospendere o riattivare i controlli. Un'offerta nuova o una differenza materiale aggiornata avvia il normale giudizio delle opportunità; la stessa fotografia del mercato non crea un secondo avviso. Nessun cambio di fornitore è avviato automaticamente.

## Fonte e confronto

- Fonte: [Open Data del Portale Offerte](https://www.ilportaleofferte.it/portaleOfferte/it/open-data.page), export XML giornaliero collegato dalla pagina ufficiale. Nessuna bolletta o dato personale viene inviato al portale.
- Ogni alternativa porta codice, nome, dominio del venditore, pagina dell'offerta, data di validità e data di osservazione.
- Per la luce, una possibile differenza annua viene esposta soltanto se la bolletta contiene consumo annuo effettivo e codice dell'offerta attuale, quest'ultima è ancora presente nell'export, e le due offerte hanno componenti di vendita a prezzo fisso, semplici e confrontabili. Si considerano costo unitario, quota fissa e, quando la potenza è nota, quota potenza. La differenza non include imposte, trasporto, oneri, conguagli o condizioni contrattuali ulteriori: è una pista da verificare, non una promessa sul totale della bolletta.
- Se manca il consumo annuo, viene stimato dal periodo fatturato solo per orientare la ricerca. Non produce una cifra di risparmio. Se mancano i termini dell'offerta attuale, l'offerta esterna è mostrata come alternativa, senza dichiararla migliore.
- Il gas viene sorvegliato e può mostrare offerte pubblicate con nome e fonte. La stima economica del gas resta disabilitata finché il tracciato e gli ambiti territoriali non sono coperti da un calcolo verificato.
- Offerte indicizzate, con sconti, vincoli, fasce, scaglioni o geografia ristretta non alimentano il confronto numerico. Un fallimento della fonte non viene tradotto in «nessuna offerta»: è registrato e ritentato dopo 12 ore.

## Operatività

`energy_offer_monitors` contiene un record per utente, commodity e identificatore hash dell'utenza; non memorizza il POD/PDR in chiaro. `energy_offer_catalog` riusa gli export pubblici per 20 ore. Il runtime ambientale lavora un'utenza dovuta al minuto, con lease di 15 minuti. Indici unici e indice su scadenza sono creati all'avvio. L'API autenticata `GET/PATCH /api/energy-offers/monitoring` offre lettura e controllo. Documento cancellato o archiviato, oppure preferenza disattivata, ferma il monitor; una fonte vecchia più di 10 giorni non entra nelle nuove valutazioni.

## Verifica e limiti

Test locali: parsing della bolletta, URL ufficiale consentito, offerte scadute/variabili/condizionate escluse, differenza calcolata da componenti omogenee, assenza di affermazione quando manca la tariffa attuale, offerte gas senza cifra. Il test di persistenza usa il Mongo isolato della CI. Il download live dell'export non è verificabile dal sandbox locale: prima di attivare in produzione occorre verificare raggiungibilità, dimensione e forma dell'XML reale e osservare almeno un ciclo completo su staging con una bolletta fittizia.
