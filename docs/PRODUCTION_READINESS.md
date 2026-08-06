# ORA — Production Readiness

**Verdict tip `09404f1` (2026-08-06): NON PRONTO PER PRODUZIONE.**  
Uso quotidiano **locale/dev** su Expo **web** + backend Mongo: sì per percorsi core (auth email, Home, Study/Travel, Documents V2, CE/Life Experience).  
Ship pubblico / store / multi-tenant: **no**.

Stati usati nel resto dell’audit: `NON ESISTE` | `ARCHITETTURA` | `PROTOTIPO` | `PARZIALE` | `FUNZIONANTE` | `VERIFICATO` | `PRODUZIONE`.  
**PRODUZIONE** non assegnata a nessun modulo (manca evidence ops reale).

---

## 1. Can we ship?

| Domanda | Risposta |
|---------|----------|
| Ship store iOS/Android oggi? | **No** — mobile **never** verified |
| Soft-launch web PWA interna? | **No** senza hardening sicurezza, CORS, secrets, observability |
| Demo locale / investor walkthrough web? | **Sì** sui percorsi VERIFICATO |
| Daily personal use (dev machine)? | **Parziale sì** — eccellente su studio/viaggio/documenti; delude su email/finanze/voce/push |

---

## 2. Blocker (ship-stoppers)

1. **Mobile nativo mai verificato** — Expo RN esiste; smoke iOS/Android = never.
2. **CORS `allow_origins=["*"]` + credentials** — non accettabile in produzione.
3. **Logout non invalida JWT** — sessione survivor fino a scadenza (~30d).
4. **Secret / ops mancanti tipici** — `JWT_SECRET` rotazione, vault, rate limit, audit prod, backup Mongo, monitoring/alerting: non evidenti come stack prod.
5. **Social login reale** — Google Login spesso bloccato da client ID; Apple Login placeholder keys.
6. **Push notifications** — `NON ESISTE` (policy Proactive non è delivery).
7. **Integrazioni life-data** — Email / WhatsApp / Open Banking / Weather = stub (`ARCHITETTURA`); profilo UI «In arrivo».
8. **Voice STT** — `PROTOTIPO` (hint digita); non assistente vocale.
9. **Emergent legacy** — bridge/auth path ancora documentato; non portable come dipendenza prod.
10. **Google Calendar** — create/update real OK in past smoke; checklist delete/reconnect incompleta; dipende da OAuth per-utente.
11. **LLM dependency** — resolve/ask/memory/strategist Gemini: degrada onestamente ma UX “AI” incompleta senza chiavi.
12. **Nessun evidence deploy production** (DNS, HTTPS hardened, CI gate continuo, incident runbook).

---

## 3. Gaps per area

| Area | Gap |
|------|-----|
| Auth | Apple real; Google web client; JWT revoke; SecureStore device |
| Home / Proactive | Stub channels empty; no push; Goal tab assente by design |
| Life Experience | Upload binario Documents V2 da conversazione incompleto; consent UI calendario strategist |
| Documents | Mobile picker/OCR device; storage locale-only |
| Calendar | Apple device; Google delete/reconnect completeness |
| Comms | Email/WhatsApp zero |
| Money | Finance/Open Banking zero |
| Voice | STT/TTS assenti |
| Ops | Observability, backups, rate limits, CSP, secret management |
| Legal/privacy | Consents UI minima vs claims “Life OS” su dati sensibili |

---

## 4. Cosa è abbastanza solido per demo (non prod)

- Email register/login + Home V2 goal-aware  
- Intent → Action → Study / Travel (web)  
- Documents V2 flashcards / Interrogami / search (web)  
- Conversation Engine + Semantic gap questions  
- Life Experience / Strategist (fallback IT; Gemini se chiave)  
- Google Calendar write sync (quando OAuth configurato)  
- Proactive ORA TI CONSIGLIA su generatori reali (study skip, travel prep, calendar overlap, docs)

---

## 5. Criteri minimi per avvicinarsi a PRODUZIONE

- [ ] Smoke nativo iOS + Android sui top 5 flussi  
- [ ] CORS allowlist, HTTPS only, secret rotation, JWT revoke/blacklist o short TTL+refresh  
- [ ] Rate limiting + authz audit su write routes  
- [ ] Backup/restore Mongo collaudato  
- [ ] Monitoring (error rate, LLM latency, OAuth failures)  
- [ ] Push locale almeno (`expo-notifications`) o rimozione claim  
- [ ] Social login real E2E o rimozione CTA  
- [ ] Dichiarazione onesta: stub channels non in marketing come “connessi”  
- [ ] CI verde pytest + Playwright gate su branch principale  

Finché questi non sono evidenza, lo stato massimo onesto resta **VERIFICATO** (locale), mai **PRODUZIONE**.
