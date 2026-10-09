# ORA V143 — Aggiornamenti con contesto, nascita e scadenza

9 ottobre 2026. Riferimento: video dell'utente (pagamento, panni, viaggio) e screenshot compleanno 8 ottobre visualizzato il 9.

## Contratto visibile

- Memoria durevole != notifica giornaliera. Chiudere una scheda scaduta non cancella il compleanno o altre informazioni memorizzate.
- Il dettaglio indica la data di creazione *dell'avviso*, non la data del fatto, e indica valid_until quando la fonte lo conosce.
- Le opportunità scadute non entrano in Home neppure quando non è ancora passata una nuova scansione autonoma; il filtro si applica a ogni lettura, oltre al job di scadenza già esistente.
- Il medesimo filtro governa il conteggio e l'elenco in Home e nelle pagine Aggiornamenti. I goal agent scaduti non si presentano come richieste ancora aperte.
- Una riga economica informativa non è automaticamente una missione: titolo specifico del movimento, importo e fonte ricostruibile nel testo; non si promuove a focus generico Organizza.
- Se la scadenza non è nota, l'interfaccia dichiara «Scadenza non indicata», senza inventare data o ora.

## Regressioni introdotte

- Compleanno 8 ottobre: valido l'8, escluso dalla Home il 9, memoria annuale non mutata dal filtro.
- Viaggio scaduto: una valid_until nel passato rende l'opportunità invisibile.
- Date-only: restano visibili nel giorno indicato e non inventano un orario.
- Data creazione opportunità e obiettivi propagate fino alla UI.
- Pagamento economico sintetico: nome, importo e provenienza visibili; il riepilogo non diventa una task generica.

## Limiti deliberatamente non dichiarati completati

1. Le opportunità storiche senza valid_until, come una discrepanza ricavata da una conversazione, richiedono un controllo della data dell'evento originario o una nuova scadenza fondata. Non si eliminano opportunità senza scadenza in blocco.
2. L'intelligenza sui panni richiede un ciclo di vita dedicato (stesi → asciugatura → ritirati, oppure rientrati per pioggia → nuovo avviso quando il meteo consente di ristenderli) e dati meteo/posizione attendibili; non è implementato qui.
3. Le domande dell'agente che riportano «Mi manca un'informazione che sai solo tu» senza domanda puntuale richiedono revisione del contratto di chiarimento e delle azioni.
4. Un avviso attivo non può dichiararsi risolto semplicemente perché l'utente ha aperto o letto il dettaglio.

Non confondere test sintetici/CI con prova reale autenticata e push su smartphone.
