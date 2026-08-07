# Digital Twin Model

Il **Digital Twin** in ORA è il Life Object arricchito dal Knowledge Model: rappresentazione viva e storica della realtà dell’utente (casa, auto, lavoro, …).

## Principi

1. **Storico immutabile dei Fact** — mai hard-delete; supersede / archive.
2. **Ipotesi ≠ Fatti** — ORA può pensare; solo conferma (utente o prova migliore) crea Fact.
3. **Gemini consulente** — propone sezioni separate; backend decide.
4. **Goal solo collegati** — nessun motore Goal duplicato.
5. **Memoria narrativa** — eventi raccontabili (acquisto → mutuo → cambio fornitore → solare → vendita).
6. **Timeline semantica** — percorsi di vita, non solo sort per data documento.

## Ciclo di vita di un Fact

```
[nuova info verificata]
        │
        ▼
   Fact current ─────────────┐
        │                    │
        │ valore cambia      │ archive esplicito
        ▼                    ▼
   Fact superseded      Fact archived
   (active=false)       (active=false)
        │
        └── resta interrogabile per sempre
```

## Domande abilitate dalla storia

- Quanti fornitori energia in N anni?
- Quando è stato chiuso / surrogato il mutuo?
- Qual era l’indirizzo precedente (se superseduto)?

## Relazione con satelliti

Documents, Conversation, Calendar, Goal, Proactive, Home restano satelliti.  
Il Digital Twin **possiede** la verità strutturata; i satelliti leggono/scrivono tramite il motore esistente + Knowledge Model.

## Limiti attuali

- Nessuna UI Home / Life Objects
- Write API minime (confirm/reject/outcome) per test
- Email / banking / WhatsApp = origin predisposti, non wired
