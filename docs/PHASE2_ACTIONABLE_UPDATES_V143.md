# ORA v143 — aggiornamenti che servono alla persona

## Difetto riprodotto dalle schermate
Un'attività temporanea seguita in background poteva comparire più volte come Goal, Opportunity e suggerimento. I titoli mostravano l'obiettivo interno «Capire quando...», il dettaglio ripeteva «Mi manca un'informazione che sai solo tu» senza una domanda e la fonte era spesso «originale non disponibile». Un'attività avviata due giorni prima veniva presentata come se il progresso del workflow fosse una nuova informazione utile.

## Contratto di prodotto
L'utente vede una singola notizia **solo** se esiste un fatto o un rischio concreto utile a decidere adesso, oppure una stima di esito da verificare. Una verifica, il suo calendario di monitoraggio, un piano, una domanda generica o una previsione scaduta non sono notizie. La semantica è scelta dal modello in modo trasversale, non dal riconoscimento della parola «panni» o da altre liste di attività.

## Backend
- I Goal `situation_followup` non entrano direttamente in Home come lavori visibili. Restano attivi nel runtime.
- Visibility distingue `action_now`, `outcome_estimate` e `status_only`. Il tipo viene scelto dal modello e registrato; `status_only` e registrazioni storiche prive di classificazione non diventano avvisi sulla vita della persona.
- La proiezione `current_situation_updates` legge soltanto `agent_updates` con risultati recenti, associati a un solo Situation canonico attivo dello stesso proprietario, con evidenze non simulate. Un'evidenza meteo scade rapidamente; una modifica successiva fatta dall'utente invalida il vecchio messaggio. Un Situation produce al massimo un aggiornamento, anche se più agenti la monitorano.
- Le opportunità esplicitamente deperibili non vengono mostrate come aggiornamenti correnti dopo 24 ore senza un nuovo riesame. Le questioni stabili non sono nascoste con questa regola.
- L'azione proprietaria `POST /api/situations/{id}/feedback` consente di dire che un fatto è cambiato (descrizione necessaria), confermare il completamento oppure interrompere il monitoraggio. È versionata e owner-scoped. Una modifica del luogo non viene chiamata «risolta»: aggiorna i fatti correnti e rientra nel normale ciclo autonomo.
- Le richieste all'utente partono dal bisogno specifico già registrato, non da una frase generica sul tipo d'informazione mancante.

## Interfaccia
La Home e la lista leggono la stessa proiezione: una riga sintetica con il consiglio/risultato utile e un'azione chiara. Il dettaglio di una situazione mostra solo che cosa conviene fare, su quale evidenza si basa, quando è iniziata e tre scelte («Ho concluso», «È cambiata», «Non ricordarmelo più»). Non replica stato del workflow, provenienza mancante, attività in corso o richieste senza domanda.

## Evidenze e limiti
I test sintetici verificano due Goal sullo stesso Situation, weather stale, correzione dopo l'osservazione, simulazioni non ammesse, altro account, nessuna istruzione sostitutiva, mutazioni utente versionate e dedup nella proiezione web.
Un dato meteo di previsione non dimostra che un oggetto sia materialmente asciutto: senza misura diretta ORA deve dire «potrebbe essere pronto» e chiedere una conferma, non «è sicuramente pronto». Il tempo indoor dipende da umidità, ventilazione, tessuto e condizioni non necessariamente misurabili; nessuna scadenza viene inventata. Le notifiche effettivamente ricevute e la qualità del giudizio AI live restano collaudi distinti.