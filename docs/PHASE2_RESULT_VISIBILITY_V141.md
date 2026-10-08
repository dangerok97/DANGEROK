# ORA — Fase 2 v141: risultato verificato visibile una sola volta

## Problema

Il collaudo v140 ha mostrato che un obiettivo autonomo può terminare con
un risultato verificabile, anche dopo il riavvio. Un lavoro utile deve poter
essere trovato dalla persona dentro ORA, anche quando non merita una push.

`AgentService._consider_visibility` esiste già e collega l'esito alla
`VisibilityService`, poi ad `AmbientActivity` su Home e, solo quando
la semantica lo richiede, a `NeedService` e alla policy `DeliveryService`.
Non viene creato un secondo orchestratore.

## Difetto trovato e corretto

Due worker concorrenti potevano entrambi leggere che lo stesso risultato
non era stato ancora comunicato. Il secondo insert di `agent_updates`
veniva giustamente rifiutato dal vincolo univoco
`(owner_id, fingerprint)`, ma l'errore era ignorato e **entrambi**
i worker ricevevano comunque il permesso logico di mostrare il risultato.

Ora la lettura preliminare resta un'ottimizzazione e solo l'insert
atomico effettivamente riuscito abilita la visibilità e il successivo
passaggio a Delivery. In caso di duplicato o errore di archivio, il
secondo giudizio torna `silent` e non produce un'attività o una push.
L'isolamento fra utenti resta nel fingerprint univoco owner-scoped.

## Prove CI

`tests/test_phase2_result_visibility_v141.py` verifica, usando
il percorso di completamento v140 su dati sintetici:

- Un solo `AmbientActivity` ambient visibile, con riferimento all'obiettivo
  realmente completato e prove del lavoro.
- Un solo aggiornamento `agent_updates`, un `CommunicationNeed` di
  risultato utile e policy Delivery che sceglie `in_app`.
- Nessun `delivery_plan` di push, nessun `ActionIntent` esterno.
- Ri-aprire il goal concluso non replica l'attività.
- Due worker che superano la lettura preliminare non possono mostrare
  entrambi la stessa informazione.
- Un headline privo di riferimenti a prove non è pubblicabile.

Nel test, il modello di visibilità e la policy di notifica sono
risposte sintetiche controllate; i repository, la conclusione del goal,
la preparazione, `AgentService._consider_visibility`,
`VisibilityService`, `NeedService`, `DeliveryService` e
`AmbientActivity` eseguono il codice applicativo.

## Limiti

Questo gate dimostra la **presenza dei dati destinati alla schermata Home**
nel database e non una sessione grafica aperta su un iPhone.
Il criterio 'in_app' non dimostra la visibilità effettiva sul display:
rendering web/mobile e consegna di notifiche native richiedono prove separate.
Non vengono inviate notifiche vere né collegate fonti personali.
