# ORA v157 — Nessuna situazione lasciata con un primo controllo fittizio

## Osservazione sul sito reale (11 ottobre 2026)

Su una sessione autenticata ORA, la Home / Memoria temporanea mostrava una situazione
«Panni stesi ad asciugare all'aperto» ancora attiva, con esito atteso generico
«oggi», ma «Nessun controllo programmato». Il dettaglio /situazione non mostrava
le stesse situazioni temporanee. Questa osservazione **non** prova nulla circa
l'asciugatura, il meteo o la possibilità di ricevere push sul telefono.

## Primo difetto architetturale

Una Situation con `attention_intent` entra correttamente nel Life Graph,
nell'OpportunityDiscovery e nel sistema di verifica in background. Tuttavia
un'Opportunity scan può scegliere legittimamente **silence** e non produrre
un goal, mentre il recupero precedente di `repair_missing_dedicated_wakes`
riparava **soltanto** sveglie per cui esisteva già un `next_run_at`.
Non era possibile recuperare il PRIMO controllo mai deciso.

## Intervento

- `situations/first_checkpoint.py` ammette in modo bounded (massimo 2 per
  passaggio) soltanto Situations *attive, owner-scoped, con intento di attenzione
  esplicito*, senza controllo schedulato.
- Usa il gestore LLM già esistente, con un unico contratto JSON generale:
  `schedule`, `needs_input` o `no_benefit`. Il modello sceglie ragione,
  momento di riesame entro 72h, scopo, esito atteso, condizione di avviso.
  Non ci sono timer per parole come panni, consegne, farmaci e così via.
- L'ora scelta è un **checkpoint di lettura**, mai previsione fisica di
  asciugatura. Senza fonte disponibile il modello può registrare un blocco.
  Nessun accesso al meteo/posizione viene simulato o presunto.
- La richiesta passa da `arrange_followup`, lo stesso confine
  Situation → Agent goal → Ambient wake già operativo: ricontrolla la revisione
  prima e dopo la deliberazione e solo un read-back confermato autorizza lo
  stato `scheduled`. Nessun push o scrittura verso terzi.
- L'ammissione è persistente per owner+situation+revision, con claim atomico,
  scadenza delle lease, massimo 3 tentativi e retry differito. Un blocker
  osservato non causa lavoro automatico infinito. Una nuova revisione della
  Situation riapre un nuovo giudizio e invalida il precedente.
- Il normale fallback Ambient tratta una Situation senza primo check come
  un debito d'attenzione e la esamina nelle wake già esistenti; non viene
  aggiunto un nuovo scheduler. Il ciclo resta limitato dagli stessi budget.
- `read_followup` include causa `needs_input`, `no_benefit`, retry o
  paused, e non dice mai «controllo programmato» finché manca la sveglia.
- `/situazione` mostra le stesse Situations della mappa VITA/temporanea,
  ultima verifica, diagnosi e prossimo controllo confermato. L'assenza di
  dati non diventa un appuntamento inventato.

## Accettazione separata

**CI sintetica**: model decision → goal → wake pending → readback,
concorrenza/replay senza duplicati, owner isolation, no_benefit/needs_input,
model failure, revisione cambiata. La pipeline esistente mantiene i test
sulla verifica successiva, esiti e cancellazioni.

**Reality gate**: su ORA pubblicata rileggere la Situation attiva già
presente senza modificarla e verificare una delle sole due conclusioni
corrette: nuova sveglia eseguibile con timestamp verificato OPPURE blocker
registrato e motivato. Non dichiarare «panni asciutti» senza osservazione,
né push ricevuta senza dispositivo nativo.

**Ancora aperto**: qualità della stima dell'esito utile con dati meteo reali,
ricezione push su iPhone/app chiusa, verifica end-to-end di un'azione dal
primo evento al suo completamento fisico. Il modello può scegliere
`needs_input` quando manca luogo/fonte, correttamente.
