# ORA — un solo ramo sperimentale, un solo rilascio finale

Data della ricognizione: 16 ottobre 2026.
Ramo: `experiment/ora-autonomy-reconciliation-20261016`.

## Scelta tecnica
Tutte le nuove modifiche funzionali riguardanti l'autonomia vengono integrate
e collaudate in questo ramo; non vengono pubblicate una per una in produzione.
Ogni modifica ha una PR mirata verso QUESTO ramo e non verso `staging/cloud`.
I rami storici #279, #220 e #212 non vanno fusi per intero: sono divergenti,
alcuni hanno prove negative, e alcuni moduli mancano gia' perche' sostituiti.

## Recuperi gia' integrati nel ramo sperimentale
- #345: CAL164, correzione del **giorno della settimana** della sola risposta
  fondata su prova del calendario, senza modificare un evento/orario.
  5 workflow verdi al commit testato.
- #348: recupero limitato della CREATE di Situation incompleta dopo due
  dichiarazioni invalide del modello; nessun checkpoint inventato.
  Test privacy su dati semantici, non su identificativi casuali.
  5 workflow verdi al commit testato.

Questi due recuperi NON risolvono gli attuali blocchi end-to-end.

## Requisiti per la decisione di rilascio — nessuna percentuale fittizia

1. **Fonte → obiettivo → risultato autonomo**: una comunicazione esterna
   reale, nuova e pertinente viene interpretata da ORA, porta ad un effetto
   autorizzato e verificato, e aggiorna Home/VITA. Esiste un pilot abilitato,
   ma non c'e' una prova completa di successo su un caso esterno.
2. **Situation temporanea**: la dichiarazione naturale attiva un obiettivo;
   viene confermata una wake persistente; un controllo recupera evidenze
   aggiornate; un risultato utile (agire ora / non ancora / stima con limiti)
   viene comunicato; la situazione termina senza inventare la misura fisica.
   Il test 'panni all'aperto' ha prodotto 'Programmazione da recuperare'.
3. **Esattezza degli effetti**: calendario locale e autorizzazioni mantengono
   titolo, data, fuso e orario dell'utente, con readback indipendente, zero
   duplicati e revoca effettiva. Test reale: richiesto 20/10 18:00-18:10
   Europe/Rome ma mostrato 12:00-12:10. Bloccante.
4. **Recupero e ripianificazione**: interruzione dei processi, indisponibilita'
   del modello, aggiornamento/revoca delle fonti e retry non perdono obiettivi,
   non producono azioni doppie e non consumano lavoro valido. Molti test
   sintetici esistono; non tutti sono convalidati in un ciclo live completo.
5. **Notifica verificata sul dispositivo**: risultato utile → sistema Delivery
   originale → provider → ricevuta/dispositivo, incluse le preferenze e
   WhatsApp dove supportato. Accettazione provider non equivale a ricezione.
6. **Parita' dei canali e UX**: le competenze del Core operano dall'app e
   dai canali collegati, senza piu' permessi/tasti del necessario. Capacita'
   attualmente parziali; vanno testate come scenari completi.

## Piano del rilascio unico
- Portare le sei condizioni al livello di accettazione misurabile in una
  preview Railway **isolata**, con test sintetici, modello reale e collaudo
  mirato su un account di prova consenziente.
- Congelare un **commit candidato** e riconciliarlo con eventuali modifiche
  indispensabili di sicurezza di `staging/cloud` prima del rilascio.
- Rieseguire le regressioni e la prova di accettazione sul tree **esatto**
  che sara' pubblicato; non considerare un merge un deploy.
- Pubblicare una sola release (promozione in `staging/cloud` e deployment
  Railway backend/web sul commit verificato), con rollback pronto.
- Mai collegare la produzione a un branch sperimentale che continua a
  ricevere commit. Non sovrascrivere grants, token o database degli utenti.

Questo e' un protocollo di promozione del prodotto, non una previsione di
data o una garanzia di autonomia universale in ogni situazione.
