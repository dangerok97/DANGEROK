# ORA v148 — Identità delle fonti economiche e conti di prova

## Casi osservati il 9 ottobre 2026
- Carta Mastercard Gold ING: email ricevuta l'8 ottobre, addebito previsto il 10 ottobre; **l'importo non è indicato**. ORA non deve associarvi importi di altri movimenti bancari.
- iCloud+ 50 GB: email dell'8 ottobre, rinnovo per €0,99 al mese a partire dall'11 ottobre, ore 03:25:28 `America/Los_Angeles` (12:25 in Italia).
- Il conto `Mock ASPSP` con saldo €3.250 e movimenti ricorrenti di prova non rappresenta risorse economiche reali.
- L'utente non capiva l'origine di righe come `Carta di credito` e `Qualcosa di economico`.

## Perché una v148 dopo la v147
La v147 ha già corretto il Focus `Admin: Conosco un pagamento`, ha introdotto una rilettura delle email finanziarie collegate e ha separato il saldo Mock da quello reale. Questa versione **non duplica quei cambiamenti**. Chiude i seguenti punti di leggibilità e provenienza:

1. `email_labels_for_facts`: da un riferimento alla fonte `mail:<id>` o dall'identificativo esatto della provenienza, rilegge **soltanto l'oggetto** della stessa email normalizzata e soltanto per lo stesso proprietario. Non legge né salva il corpo.
2. La sezione `Cosa ho capito` può mostrare `Da dove viene: Email «Promemoria dalla tua carta di credito»`, oppure il titolo dell'email iCloud+, accanto al fatto registrato, anche se il nome storico rimane generico. Non trasforma automaticamente l'oggetto in una spesa confermata.
3. `financial_observations` conserva `provider_reality` accanto alla fonte. Per le righe vecchie si controlla il conto originale; se il provider è Mock/Sandbox, **le ripetizioni e i movimenti recenti sono etichettati SIMULATO**, separati dai movimenti di conti veri anche quando hanno identica descrizione.
4. Un timestamp esplicito completo e con zona IANA, unico nella fonte transitoria, può precisare `due_at` solo **dopo** che il giudizio finanziario ha riconosciuto una vera obbligazione con data. Non riempie `due_at` dal nulla, non conserva il body e non usa il valore come importo.

## Confini importanti
- Non viene inventato il saldo della carta ING; la cifra è ignota fino a lettura di fonte autorizzata che la dichiari.
- Non si fondono €760 o €14,99 del provider Mock con ING, Apple o addebiti reali per somiglianza.
- Per la rilettura retrospettiva delle email storiche l'utente può usare l'azione già esistente `Rileggi le email economiche`, che limita gli accessi e non memorizza i body.
- I test sintetici e la CI non dimostrano, da soli, il rendering su un account reale autenticato.

## Test
`backend/tests/test_finance_provenance_v148.py` più il gate Home 3.0 e l'intera CI.
