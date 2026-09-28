# VITA → compiti ORA: verifica del 28 settembre 2026

## Metodo e significato del risultato

Sono state confrontate le dieci aree di `life_profile/areas.py`, le 38 domande
guidate di `life_profile/guided.py`, la scrittura nel profilo, le due letture
personali (`life_memory/assemble.py` e `conversation_engine/ai_core/context_sources.py`),
il catalogo delle capacità di `conversation_engine/ai_core/tools/registry.py`,
e le carte dei benefici. I test usano profili sintetici e un database finto;
non attestano chiamate o pagamenti effettivi verso provider reali.

**Leggibile** significa che ORA può reperire la risposta pertinente al compito.
**Eseguibile** significa che esiste una capacità che produce un effetto e che
le condizioni necessarie, inclusa l'autorizzazione dell'utente, sono presenti.
Una stella, una carta beneficio o un piano non sono di per sé un'azione completata.

| Area VITA | Dato utilizzabile e compito raggiungibile | Limite verificato |
| --- | --- | --- |
| Casa | Situazione abitativa, città, convivenza e utenze contestualizzano ricerca, piani e promemoria in calendario; documenti caricati possono fornire date. | La guida non chiede la scadenza di affitto, bolletta o rata; nessun pagamento o rinnovo della polizza casa è esposto come capacità di conversazione. La cifra della rata mutuo non viene immessa nel contesto generico. |
| Lavoro | Stato, tipo, contratto, orario, modalità e ruolo sono recuperabili per pianificare gli impegni. | Nessuna scadenza lavorativa o disponibilità oraria strutturata è prodotta dalla sola guida; nessun invio a datore/portali come capacità generica. |
| Studio | Stato, percorso e fase possono fondare un piano; esiste anche un flusso separato per il piano di studio e il calendario. | Per ricordare un esame servono materia e data, che la guida VITA non raccoglie. |
| Mobilità | Mezzi e relazione con l'auto contestualizzano navigazione; la guida può salvare la scadenza dell'assicurazione auto e il libretto. | Tempo di viaggio live richiede posizione e servizio di routing disponibile; revisione e bollo non si ricavano dalla sola scelta dei mezzi. Nessun pagamento bollo. |
| Famiglia | Composizione e numero figli sono disponibili come contesto per piani e calendario; la telefonata può essere preparata con risoluzione del destinatario. | La guida non identifica singoli familiari, numeri o ricorrenze. Chiamare richiede destinatario risolto, provider pronto e autorizzazione. |
| Patrimonio | Beni, immobili e finanziamenti forniscono contesto per ragionare e pianificare. | Nessun beneficio dedicato nel catalogo e nessuna operazione bancaria, catastale o patrimoniale eseguibile. |
| Finanze | Fasce di reddito, risparmi e spese ricorrenti supportano risposte contestuali; esiste capacità finanziaria di sola lettura. | La guida non identifica importi, conti o scadenze di una singola uscita. Nessuna disposizione di pagamento o accesso automatico al conto. |
| Assicurazioni | Tipi di copertura e polizze caricate supportano ricerca e potenziali promemoria quando la data è nota. | La guida chiede i tipi, non la data di rinnovo: l'avviso non è fondato sulla sola compilazione. Nessuna stipula o rinnovo presso l'assicuratore. |
| Servizi | Tipologie di fornitori e contratto telefonico caricato possono contestualizzare una ricerca o una telefonata. | Mancano normalmente fornitore preciso, prezzo, scadenza e numero: nessuna disdetta automatica né monitoraggio completo degli abbonamenti dalla sola guida. |
| Salute | Obiettivi generali sono leggibili per organizzare un piano o un evento del calendario. | La guida non raccoglie visita, medico o data; nessuna prenotazione sanitaria. I dati clinici sensibili non sono propagati nel contesto generico. |

## Riscontri tecnici e correzioni

1. Le risposte guidate vengono salvate nel `LifeProfile`. Prima di questa
   verifica, i valori a scelta multipla non diventavano frasi di memoria e
   alcuni codici di scelta restavano opachi. Ora le etichette provengono dal
   catalogo guidato, senza inventare significati per valori sconosciuti.
2. La lettura del profilo in conversazione tagliava ai primi 24 fatti secondo
   l'ordine di inserimento. Con 40 annotazioni Casa, aree compilate più tardi
   potevano scomparire. Ora sceglie prima 30 candidati pertinenti alla domanda;
   il ranking finale mantiene il budget di evidenza.
3. `get_profile_snapshot` prima leggeva Stage A, che non include il profilo.
   Ora legge i fatti del profilo e i pochi fatti account ammessi. Le categorie
   includono le risposte iniziali su casa, lavoro e studio.
4. I benefici mostrati in Home sono marcati `knowledge_only` e navigano alla
   configurazione: non certificano che un'azione sia stata compiuta.
5. Il tool telefonico **prepara** la chiamata. La disponibilità del provider,
   la risoluzione del destinatario e il mandato sono verificati prima della
   telefonata; il test di questa verifica non ha chiamato terzi. Il calendario
   può creare, aggiornare e cancellare eventi con i normali controlli e con
   sincronizzazione esterna solo se il connettore è configurato e confermato.

## Verifica riproducibile

`backend/tests/test_vita_ora_actionability.py` esercita ogni domanda a scelta
guidata, la persistenza simulata in memoria per tutte e dieci le aree, il
recupero dal profilo fitto, il riepilogo esplicito e la protezione degli
identificatori. I test esistenti di contesto, profilo e memoria sono eseguiti
insieme. Questa evidenza prova la disponibilità dei dati per compiti pertinenti,
non un successo end-to-end di dieci diverse azioni nel mondo reale.

## Lacune di prodotto da affrontare

Per promesse verificabili occorre raccogliere, quando l'utente richiede il
compito, gli identificatori e le date mancanti; legare le carte beneficio
all'evidenza necessaria e a un'azione reale; implementare e verificare ogni
integrazione esterna separatamente. In particolare Patrimonio non ha alcun
beneficio specifico e il monitoraggio di assicurazioni/servizi/salute non deve
partire dal solo tipo o obiettivo. Conservare autorizzazione, verifica del
destinatario e lettura dell'esito come requisiti di esecuzione.
