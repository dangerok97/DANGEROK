# ORA v147 — i soldi spiegati partendo dalla fonte, non dal titolo

## Segnalazione del 9 ottobre 2026

L'utente mostra:
- Focus: «Admin: Conosco un pagamento entro fine mese», pulsante «Organizza».
- Conti e denaro: un conto «Mock ASPSP» con saldo €3.250 non marcato come simulato; «Carta di credito — importo non noto», «Qualcosa di economico — importo non noto».
- Fonte ING dell'8 ottobre: il 10 ottobre è previsto l'addebito mensile delle spese Mastercard Gold. **Non è indicato l'importo**. Il messaggio rinvia a «Prossimi addebiti»/estratto conto per conoscerlo.
- Fonte iCloud dell'8 ottobre: piano 50 GB, rinnovo €0,99 mensili dall'11 ottobre 2026 (orario del messaggio in America/Los_Angeles). L'importo **è indicato**.

## Root cause e correzioni

1. `connected.service._pass_on` inoltrava al ragionamento economico il solo `signal.for_ai()`, anche quando il testo privato era stato letto transientemente per decidere la rilevanza. Ora un messaggio giudicato economicamente pertinente può essere riletto tramite il privacy gate già esistente, una volta, per i dettagli necessari. L'estratto non viene salvato in fatti, provenance, change log, notifiche o log.
2. Il modello riceve l'estratto originale e istruzioni esplicite per distinguere addebito di carta **senza importo** da abbonamento con prezzo **esplicitamente indicato**. `financial/source_grounding.py` respinge cifre inventate che non compaiono con un simbolo o indicatore di valuta nella fonte. 50 GB, date e numeri carta non sono importi.
3. `FinancialStore.remember` permette alla rilettura *della stessa email appartenente allo stesso utente* di sostituire una vecchia descrizione più generica, mantenendone lo storico e impedendo la duplicazione di un debito. Mai fondere email diverse solo perché riguardano lo stesso tipo di spesa.
4. Per le interpretazioni vecchie, il tasto «Rileggi le email economiche» in Conti e denaro effettua al massimo cinque letture su esatte email originali con accesso owner-scoped. Lascia audit senza body e ignora messaggi già corretti; errori di collegamento non diventano importi immaginari.
5. Il vecchio Action Engine confondeva la categoria di flusso `admin` con la prova di una `bill`, generando un falso Focus «Organizza» persino da hint non legati a task, reminder o documento. Ora salta i contenitori privi di un'azione ancorata e non trasforma `admin` in `bill`. Le sessioni attive restano riprendibili.
6. `BankReadService` conserva se il provider è simulato. La pagina mostra «CONTO DI PROVA / Saldo simulato (non reale)», inclusi i record legacy chiaramente indicati come Mock/Sandbox/Demo. Il modello finanziario non lo considera saldo disponibile reale.

## Perimetro e limiti

- Il pulsante di rilettura serve agli **errori storici già persistiti**; le nuove email passano direttamente per la lettura corretta se l'accesso è disponibile e la sorgente è ritenuta economicamente pertinente.
- Gmail deve essere ancora collegato e accessibile, altrimenti ORA dichiara il limite e non modifica il fatto.
- Nessuna simulazione è usata per decidere se il mutuo, l'affitto o altri impegni siano sostenibili.
- Un messaggio bancario non rappresenta di per sé un addebito realmente eseguito o un importo di estratto conto confermato. ORA deve verificare nel servizio bancario disponibile e autorizzato.
- Test automatici provano la sicurezza del flusso e gli esempi sintetici: verifica manuale sull'account reale ancora necessaria.

## Gate

`backend/tests/test_financial_email_grounding_v147.py`, `frontend/src/components/home/v3/home3.test.ts`, CI completa e regressioni bancarie/Connected Life.
