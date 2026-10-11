# Ripresa della verifica roadmap finale — 11 ottobre 2026

## Punto recuperato

La versione remota `staging/cloud` era `295c46448e57d5b5c138b6d39451738230c222ce`.
Backend e web Railway risultavano SUCCESS su distribuzioni del 10 ottobre.
Le PR #199 e #200 erano aperte, entrambe sulla stessa base; è stata ripresa
#200 con correzioni aggiuntive e port selettivo delle parti utili di #199.

## Difetti riprodotti e correzioni

1. L'intenzione di seguire una Situation poteva non produrre un lavoro o
   una wake. La prima valutazione è ora persistita e recuperabile, distinta
   da un vero checkpoint e vincolata alla revisione della fonte.
2. Un `_wait` privo di scelta temporale poteva promuovere un retry di sei
   ore a controllo reale. La promozione richiede scelta esplicita e una
   lettura con provenienza valida per lo stesso owner/goal.
3. Un aggiornamento della Situation poteva confermare l'arresto anche
   quando la cancellazione del lavoro era fallita. Il turno verifica ora
   job e wake; il runner ricontrolla anche revoche/revisioni della fonte.
4. La vista mensile leggeva `life_nodes` mentre Home leggeva gli eventi
   normalizzati in ingestion: ora condividono selezione e fonte canonica.
   La UI non tratta stati degradati/incompleti come collegamenti riusciti.
5. La rilettura della stessa email poteva scartare correzioni a nome,
   controparte, natura e precisione della data come già conosciute.
   I riferimenti legacy sono normalizzati, l'identità conservata è quella
   realmente persistita e gli avvisi informativi usano fonte/data originali.
6. Un completamento di un vecchio ciclo poteva cancellare un'intenzione
   aggiornata durante la chiusura. La chiusura verifica la revisione e usa
   un identificatore diverso per ogni ciclo, anche quando il goal è riusato.
7. L'azione calendario poteva scegliere il primo account collegato e
   archiviare specchi con lo stesso ID esterno appartenenti ad altri
   account/calendari. Il target e il consenso vengono ora verificati sulla
   precisa istanza dell'evento; i riferimenti ambigui sono respinti e gli
   aggiornamenti locali restano circoscritti allo stesso target.
8. Il primo giro CI ha rilevato una doppia cancellazione nella rotta degli
   avvisi. La mutazione della Situation è ora l'unico percorso di arresto;
   la rotta rilegge intenzione, goal e wake persistiti prima di confermarlo.
   Una cancellazione dichiarata ma non salvata, una wake rimasta attiva o
   un nuovo ciclo concorrente producono un conflitto invece di un falso
   successo. Interrompere il monitoraggio non dichiara risolta la Situation.

## Validazione

Tutti i nuovi dati sono sintetici e isolati in memoria. Le fonti dei test
non sono letture di Gmail, Calendar, banche o meteo reali. Le prove verificano
i percorsi applicativi, ownership, persistenza, stato e recovery; non
certificano giudizio di un modello live o recapito sul telefono.

- Regressione conclusiva monitoraggio: 156 test PASS, inclusi casi di
  ammissione concorrente, revoca, riattivazione, source revision, persistenza
  e sparizione/spostamento della wake durante la conferma.
- Finanza e calendario: 65 test PASS nel giro integrato, inclusi i casi
  inizialmente falliti.
- TypeScript: PASS; esportazione web finale: PASS.
- Frontend: 17 test PASS (account, Google login, presenza); lint dei file
  modificati senza errori, con tre warning (refresh intenzionale dell'agenda
  e due warning preesistenti).
- Totale delle regressioni backend sopra elencate: 221 test PASS.
- Scansione dello storico Git disponibile: PASS, zero pattern ad alta
  confidenza di segreti e zero percorsi sensibili rilevati.

Durante il rilascio sono stati verificati anche 262 test con mock dei gruppi
calendario/departure e destinazione delle azioni: tutti PASS. I due moduli
che richiedono un Mongo reale restano affidati al servizio dedicato in CI.
Il gruppo sintetico di autonomia, aggiornamento delle fonti e recovery ha
superato 230 test su 50 moduli; i due moduli Ambient che richiedono Mongo
reale e il comando di continuità con Mongo restano verifiche della CI.
Lo step completo sugli aggiornamenti, dopo la correzione degli avvisi,
ha superato 74 test, inclusi cinque nuovi casi di persistenza e concorrenza.
Il primo giro CI ha superato i controlli finanziari, Situation, TypeScript,
telefonia, audit e UI mobile Chromium/WebKit; il job Backend si è fermato
sulla regressione degli avvisi descritta al punto 8. Quei risultati non
vengono presentati come CI finale verde: il nuovo head richiede un giro
completo successivo alla correzione. Gli esiti conclusivi sono nella PR.

## Autorizzazione e tracciamento del rilascio

Il primo tentativo di push era stato respinto dal controllo automatico,
che richiedeva una conferma nel testo utente corrente. L'utente ha poi
autorizzato esplicitamente il push nel repository `dangerok97/DANGEROK`,
l'aggiornamento e il merge della PR #200 dopo CI verde e il rilascio dei
servizi Railway `ora-backend` e `ora-web`.

Prima del push è stata verificata l'integrazione senza conflitti con
`staging/cloud` aggiornato a `af888559364d43836e5831867289e2cd70db6cc0`,
che comprende il lavoro Vision indipendente. Quel lavoro viene preservato.

La [PR #200](https://github.com/dangerok97/DANGEROK/pull/200) registra gli
SHA e gli esiti effettivi di CI, merge e distribuzione; i PASS della sezione
precedente documentano la validazione locale. Il rilascio richiede controlli
verdi sull'ultimo commit e conferma SUCCESS del nuovo codice per entrambi
i servizi. La proposta alternativa #199 viene chiusa dopo il merge.
Il collaudo autenticato resta distinto da queste verifiche tecniche.

## Rilascio #200 verificato

Il commit finale della PR è `6d18380090b68a64353fd509ac1846e10bb5cb8c`:
tutti i nove job della PR e le due workflow di push sono passati.
Squash merge in `8e9b878a5c1665c41e5e2046ab17e87dc0ad5134`.
Anche i run dopo il merge [CI 38162123121](https://github.com/dangerok97/DANGEROK/actions/runs/38162123121)
e [Situation 38162123023](https://github.com/dangerok97/DANGEROK/actions/runs/38162123023)
sono SUCCESS. La proposta #199 è stata chiusa dopo l'integrazione.

Entrambi i servizi Railway hanno raggiunto SUCCESS sullo stesso SHA:
backend `af83d72a-43b1-4369-a401-a04601c22d19`,
web `a323dc45-b95a-4571-8d7a-dc22c1a375b9`.
Health backend e web HTTP 200, database raggiungibile e catalogo Vision
HTTP 401 senza autenticazione. Il successivo deploy Vision `bb1a6a2`
conserva il rilascio come antenato e non modifica i file della PR #200.

## Collaudo autenticato e correzioni successive

L'accesso Google è riuscito; profilo e dati dell'account erano visibili.
La verifica è rimasta in lettura, con una domanda diagnostica a ORA che
ha richiesto di leggere lo stato esistente senza riattivare il monitoraggio.
Nessun token creato, credenziale letta, chiamata, email, pagamento o evento
esterno prodotto dal collaudo.

- La card finanziaria osservata dichiara origine da conferma dell'utente,
  importo non noto e periodicità senza inventare il giorno. Creazione e
  termine di visibilità sono leggibili: il termine a 24 ore riguarda la
  permanenza dell'avviso, non una scadenza di pagamento. Nessun lavoro era
  avviato da quella segnalazione. Non è una prova di rilettura email live.
- Il calendario Home contava un'attività che apriva una guida operativa,
  mentre Agenda mostrava zero eventi. `ContextRail` usava anche `due_at` e
  `goal_target_date`: il nuovo selettore ammette soltanto fonti calendario
  con identità e inizio validi, lasciando le attività nelle altre sezioni.
- La Situation temporanea è conservata, ma prima della patch aggiuntiva
  non mostra un goal, un checkpoint o un'ultima verifica. La risposta di
  ORA conferma la diagnosi senza attribuire la causa al meteo o ai permessi.
- Riprodotto il ritardo di un intento persistito: una revisione per altro
  motivo tre ore prima bloccava `situation_unattended` nel cooldown di 12
  ore. Ora usa l'intervallo urgente esistente di 30 minuti, entro la sweep
  già prevista. Una Situation con il solo esito atteso rimane una nota;
  campi d'intento composti solo da spazi non entrano nemmeno nel batch.
- Distinta la diagnosi di nota senza intento salvato, con readback
  `attention_saved` sconosciuto se la lettura dell'owner non è disponibile.
  Il cockpit descrive ora anche il riesame senza chiamarlo controllo.
- Riprodotta e corretta la perdita del flag `knowledge_only` nel passaggio
  da nodo a HomeItem. Il gate esclude il nodo informativo prima del ranking,
  mentre un evento manuale valido continua a essere ammesso.

Verifica della patch `ora/v158-live-qa-consistency`: 106 test backend
integrati PASS, quattro regressioni frontend PASS, TypeScript PASS,
compileall e diff check PASS. ESLint senza errori, tre warning preesistenti
nel cockpit. Build web completa PASS (1.745 moduli); scenario mobile
Chromium PASS per la sequenza non programmato → riesame → controllo.
WebKit locale non eseguibile per librerie OS assenti: deve superare il gate
CI mobile. La fixture ha impedito richieste esterne durante il test locale.
Gli esiti conclusivi della CI e della ripetizione sul sito sono registrati
nella PR della patch, senza contenuti personali dell'account.

Resta da dimostrare sul caso reale il ciclo completo di controllo con fonti,
checkpoint persistito, esito e consegna al dispositivo. I test sintetici,
il worker acceso e il login riuscito non sono prove equivalenti.

## Limiti residui osservati nel codice

La lettura transitoria di alcune email rimane limitata a un frammento:
informazioni fuori da quel testo possono ancora richiedere una lettura più
completa della fonte. I duplicati storici ambigui non vengono fusi in modo
automatico. Il calendario seleziona gli eventi per data di inizio e mantiene
il comportamento preesistente sugli eventi che attraversano più mesi.

## Rilascio #203 e collaudo successivo

La [PR #203](https://github.com/dangerok97/DANGEROK/pull/203) è stata
integrata in `42fba0e93ba2e6c8be263b2bc072bbe1c7956b15`, con tree identico
al locale verificato `41a45b65952c27cf8e54fd02d67a4556bbb1412b` e base
`bb1a6a2`. Tutti i gate della PR sono verdi: CI, Situation e otto prove
mobile distribuite fra Chromium e WebKit. Anche la CI dopo il merge
[38166067866](https://github.com/dangerok97/DANGEROK/actions/runs/38166067866)
e la suite Situation
[38166067849](https://github.com/dangerok97/DANGEROK/actions/runs/38166067849)
sono SUCCESS sullo stesso SHA.

Backend Railway `2fdda864-6146-49b3-a893-ce30fee16210` SUCCESS alle
19:01:37 UTC; web `0add894b-d7cf-4dbe-a367-759a979467ed` SUCCESS alle
19:02:12 UTC dell'11 ottobre. Entrambi distribuiscono `42fba0e9`, con
una replica sana, nessun lavoro pendente e health HTTP 200. Le sorgenti
dei due servizi erano prive di branch e sono state ricollegate a
`staging/cloud` per distribuire il commit integrato.

Il confronto autenticato sul giorno precedentemente incoerente mostra
zero eventi sia nel calendario Home sia in Agenda. L'attività operativa
resta presente nella sua sezione. Non sono stati creati, spostati o
eliminati appuntamenti per ottenere questo risultato.

La Situation esistente è stata recuperata dal worker senza ricrearla o
reinviare la richiesta di attenzione: la schermata mostra un'ultima verifica
alle 21:03 e un prossimo controllo alle 22:03 nel fuso visualizzato dalla UI.
Il risultato cita una località la cui associazione alla Situation fisica
non è stata dimostrata. La diagnosi testuale del modello non costituisce
una prova autonoma della provenienza geografica. Il collaudo dimostra ora
ammissione, esecuzione e checkpoint persistito, ma non ancora la correttezza
del giudizio locale o la consegna di una notifica sul dispositivo.

## Rilettura email e ultimo approfondimento

La vista dettagliata delle connessioni mostra Gmail connesso e Google
Calendar con autorizzazione scaduta. Il login Google e la disponibilità di
Gmail non sono stati usati come prova di accesso agli eventi Calendar.

Una sola pressione di «Rileggi le email economiche» ha elaborato fonti già
collegate, senza cercare una nuova raccolta di messaggi. Esito UI: cinque
email verificate, una informazione aggiornata, due già corrette, due senza
un fatto economico confermato. Non è stato letto o salvato il corpo email
tramite il browser del collaudo, né è stata data una risposta di conferma
alle proposte finanziarie. Il saldo e i movimenti bancari visibili restano
esplicitamente dati simulati.

La rilettura ha prodotto una domanda «importo non noto» rispetto a «importo
non noto». Riproduzione sintetica: il confronto mancava prima della
presentazione, e anche una differenza reale di data veniva mostrata come
domanda sul solo importo. La patch successiva seleziona proposte attive
con differenze concrete, condivide la domanda fra le superfici e conserva
i campi confermati non specificati dalla nuova proposta quando l'utente
risponde esplicitamente sì. Le letture restano prive di mutazioni.

L'analisi del controllo ha inoltre rilevato la perdita del contesto della
Situation nel passaggio alla ricerca e dell'ambito geografico nelle fasi
di valutazione e sintesi. Un risultato parziale con un riferimento di ricerca
poteva superare la promozione della prima verifica. La patch preserva il
contesto dell'owner e richiede un esito completato e sufficientemente
supportato. Questo controllo meccanico non dimostra da solo che una fonte
riguardi il luogo fisico corretto: tale limite rimane esplicito.

Validazione locale dell'ultima patch: 148 test backend integrati PASS
(Situation, diagnosi, finanza, ricerca e calendario), 55 regressioni
finanziarie mirate PASS con sovrapposizione, TypeScript PASS, build web
completa PASS (1.745 moduli), lint frontend senza errori. I 47 warning di
stile del client API sono preesistenti. La correzione tipografica di un
apostrofo JSX nel file Vita elimina l'unico errore lint incontrato.
Scansione Git disponibile e diff check PASS. Le prove sono sintetiche e
non sostituiscono i gate con Mongo reale, il collaudo della versione
distribuita o la verifica della località della Situation.
