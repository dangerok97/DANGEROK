# ORA — Fase 2 v140: un obiettivo completato davvero, anche dopo un riavvio

## Domanda da verificare

Il collaudo v137 ha dimostrato che il modello può riconoscere un'iniziativa
utile e crearne il goal. Mancava una prova **integrata** in cui il lavoro
passa da fonte a iniziativa, piano, capacità reale di lettura, evidenza,
preparazione persistita, verifica dell'esito e chiusura, conservando i passaggi
già fatti quando il processo viene interrotto.

## Mondo sintetico (nessun account reale)

Una persona fittizia ha registrato nel proprio archivio ORA una nota:
15 euro al mese per dodici mesi (180 euro) contro un'opzione annuale di
120 euro. Le due opzioni hanno nella nota pari capacità e supporto, ma
l'annuale non rimborsa i mesi inutilizzati. Le informazioni sono attribuite
alla **nota interna**, non verificate presso il fornitore. Non esiste consenso
per cambiare piano o pagare.

L'esito utile è **preparare un confronto informativo** con la differenza di
60 euro, vantaggi, limiti e condizioni ancora da verificare. Non simulare
una modifica al contratto come risultato.

## Due prove complementari

1. **CI scripted, sempre eseguita**: codice reale di Opportunità →
   admission → goal → piano → StepExecutor → memory reader → EvidenceStore →
   preparazione con revisione → verifica → completion gate. Sono controllate
   solo le risposte del modello e il mondo sintetico. Il primo giro può
   eseguire una lettura sola, poi salva un piano incompleto e un checkpoint.
   Il secondo giro usa un nuovo oggetto AgentService con lo stesso database:
   deve **riusare** l'evidenza e concludere senza rileggere, inviare,
   acquistare, chiamare né chiedere informazioni inesistenti.
2. **CI reale Mongo/processo**: database con nome casuale + marcatore di
   proprietà, su Mongo loopback senza autenticazione. Tre processi Python
   separati: il primo salva goal/piano/lettura e termina; il secondo,
   raggiunta artificialmente la scadenza **solo nel DB sintetico**, lascia
   che il runtime Ambient consumi il wake e completi il goal; il terzo
   verifica replay senza lavoro duplicato e isolamento tra utenti.
   Le credenziali di provider e utenti reali non vengono passate ai figli,
   il traffico esterno non Mongo è bloccato da audit hook. La rimozione del
   database richiede il marcatore originario.

In entrambi i casi la fase di visibilità/notifica è volutamente disattivata
per evitare invii: chiusura del lavoro e consegna sul telefono sono due
contratti distinti.

## Prova live col modello

`python -m scripts.phase2_goal_outcome_eval_v140 --mode live`

Usa solo una memoria inventata in Mongo **in memoria**, e solo le due
capabilities non mutanti `information.read` e `document.create`.
Il modello sceglie goal, piano, prossimo passo, contenuto della bozza,
riesame e verifica: un esito fallito resta fallito, senza fallback scripted.
La connessione di rete è consentita solo per chiamare il modello, non
per consultare account personali o effettuare effetti nel mondo.

Questo gate live **non** è una prova di riavvio di processo (quella è in CI
su Mongo reale) e non verifica invii, offerte correnti o consegna di push.

## Criteri di successo verificabili

- Un solo goal aperto e un piano persistito; primo passaggio non conclude
  quando il lavoro utile è ancora incompleto.
- Lettura tramite la capability reale dal record owner-scoped; evidenza con
  provenienza e riferimenti persistiti.
- Ripresa del piano dopo il riavvio, senza ripetere la lettura compiuta.
- Bozza scritta e revisionata su evidenze effettivamente presenti; nessun
  risultato attribuito al fornitore esterno.
- Chiusura `completed` solo dopo giudizio di verifica e gate di evidenza,
  con piano concluso, zero `ActionIntent` esterni, nessun accesso incrociato.
- Replay di un goal già completato non ricrea il lavoro.

## Limiti

Un confronto di note dell'utente non prova che un'offerta sia davvero
acquistabile o economicamente più vantaggiosa oggi. Questa è una prova
orizzontale del funzionamento del sistema di completamento **per un lavoro
informativo entro l'autonomia disponibile**. Restano separati i collaudi
di integrazioni cloud reali, esiti di azioni di terzi, permessi, mobile
nativo, notifiche sul telefono e prestazioni longitudinali multiutente.
Non creare nuove automazioni orarie di sviluppo.
