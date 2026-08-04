# ORA — Roadmap di sviluppo

Basata sull’audit funzionale del 2026-08-04. Ordine: fondamenta → organizzazione → documenti → AI → integrazioni → produzione.

## FASE A — Fondamenta

| Attività | Priorità | Dipendenze | Complessità | Criterio di completamento |
|----------|----------|------------|-------------|---------------------------|
| A1 Allineare Profilo/Aggiungi con moduli reali (niente “In arrivo” su Documenti attivo) | critica | — | S | UI coerente; smoke UI manuale |
| A2 Harden auth: messaggi errore, rate-limit login, documentare JWT expiry | alta | Auth email OK | M | Test 401/409; doc sicurezza aggiornata |
| A3 Session UX: splash loading + redirect affidabile post-login web | alta | AuthContext | S | Login → Home senza flicker; refresh mantiene sessione |
| A4 Error banner + empty/offline già presenti: checklist su ogni tab | alta | Home pattern | S | Ogni tab ha empty/error/loading verificati |
| A5 Rimuovere/nascondere client API legacy `/tasks` dal FE se non usato | media | — | S | Nessun import morto; lint OK |

## FASE B — Organizzazione personale

| Attività | Priorità | Dipendenze | Complessità | Criterio di completamento |
|----------|----------|------------|-------------|---------------------------|
| B1 Completare E2E azioni Decision in UI (complete/postpone/block) | alta | A3 | M | Azioni cambiano status in Mongo + Home aggiornata |
| B2 Modello “promemoria” leggero su postpone/deadline (senza push) | media | B1 | M | Lista scadenze o badge Home verificabile |
| B3 Agenda giornaliera da Daily (solo lettura) | media | Daily OK | M | Schermata/sheet “giornata” navigabile |
| B4 Notifiche locali (expo-notifications) opzionali | media | B2 | L | Reminder locale su decision con deadline |
| B5 Google Calendar OAuth locale end-to-end | alta | GOOGLE_OAUTH_* | L | Sync eventi → daily/decisions aggiornati |

## FASE C — Progetti e documenti

| Attività | Priorità | Dipendenze | Complessità | Criterio di completamento |
|----------|----------|------------|-------------|---------------------------|
| C1 Test upload documento web + download | critica | Documents API | M | File in lista + dettaglio apribile |
| C2 Collegare Aggiungi→Documento al flusso upload reale | alta | C1 | S | Nessun “In arrivo” fuorviante |
| C3 Insights + DocumentActionsBar verificati su 1 PDF/immagine | alta | C1 | M | Azioni copia/link senza crash |
| C4 Scope “Progetti”: decidere se life_nodes type=project o rimandare | media | Product | S | Dec di decisione + issue backlog |
| C5 Ricerca documenti (già q=) esposta meglio in UI | media | C1 | S | Query restituisce match | 

## FASE D — Assistente AI

| Attività | Priorità | Dipendenze | Complessità | Criterio di completamento |
|----------|----------|------------|-------------|---------------------------|
| D1 Configurare `LLM_PROVIDER=openai` in locale (doc + .env.example) | alta | OPENAI_API_KEY utente | S | /resolve e /memory/ask 200 con chiave |
| D2 UX quando LLM assente: CTA “configura AI” non solo 502/503 grezzo in UI | alta | adapter LLM | S | Messaggio IT in Home/Memoria |
| D3 Memoria ask con citazione sources in UI | media | D1 | M | Sources visibili sotto risposta |
| D4 Guardrail: niente auto-azioni irreversibili da LLM | alta | D1 | M | Test: resolve non completa da sola |
| D5 Chat libera | bassa | Product | L | Solo se vision lo richiede (oggi no) |

## FASE E — Integrazioni

| Attività | Priorità | Dipendenze | Complessità | Criterio di completamento |
|----------|----------|------------|-------------|---------------------------|
| E1 Google Login first-party (sostituire Emergent) | media | Google Cloud | L | Login Google senza Emergent |
| E2 Apple Calendar su device build | media | EAS/iOS | L | Sync EventKit verificato |
| E3 Apple Sign-In | bassa | Apple Developer | L | Pulsante non placeholder |
| E4 Gmail / email | media | OAuth mail | L | Solo dopo privacy review |
| E5 Push remoti | media | provider push | L | Opt-in + test device |

## FASE F — Produzione

| Attività | Priorità | Dipendenze | Complessità | Criterio di completamento |
|----------|----------|------------|-------------|---------------------------|
| F1 Suite smoke CI (health, auth, decisions) | alta | — | M | CI green su PR |
| F2 Security review: vault, CORS, secret scan | critica | — | M | Checklist firmata in docs |
| F3 Privacy policy + data deletion flow | alta | connectors revoke | M | Endpoint/UX cancellazione |
| F4 Build mobile (EAS) staging | alta | Expo | L | Build installabile |
| F5 Deploy API + backup Mongo | critica | hosting | L | Restore testato |
| F6 Analytics privacy-friendly | bassa | — | M | Eventi aggregati senza PII |

## Sequenza consigliata (prossime 4 settimane)

1. **A1** coerenza UI  
2. **C1** upload documenti verificato  
3. **B1** azioni decision E2E  
4. **D2** UX senza LLM + **D1** quando c’è chiave  
5. **B5** Google Calendar quando ci sono OAuth secrets  
6. **F1/F2** in parallelo alla crescita feature
