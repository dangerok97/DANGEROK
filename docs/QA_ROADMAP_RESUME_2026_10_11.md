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

## Collaudo personale ancora richiesto

La sessione browser corrente mostra la pagina di login. Dopo autenticazione,
verificare la situazione temporanea e il suo stato persistito, gli eventi
Home/mese e la provenienza leggibile delle card. L'assenza di accesso non
viene compensata creando token, leggendo credenziali o modificando dati a
mano. Nessuna chiamata, email o transazione viene inviata per questo test.

## Limiti residui osservati nel codice

La lettura transitoria di alcune email rimane limitata a un frammento:
informazioni fuori da quel testo possono ancora richiedere una lettura più
completa della fonte. I duplicati storici ambigui non vengono fusi in modo
automatico. Il calendario seleziona gli eventi per data di inizio e mantiene
il comportamento preesistente sugli eventi che attraversano più mesi.
