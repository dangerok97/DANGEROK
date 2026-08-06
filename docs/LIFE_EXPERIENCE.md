# Life Experience — esperienza AI-first di ORA

Ultimo aggiornamento: 2026-08-06  
Branch: `feature/life-experience-ai-documents` (da `feature/life-experience-ai`)

## Cos’è

Life Experience è la **prima conversazione naturale** con ORA dopo la registrazione.
Non è un wizard, non è un questionario, non è una sezione «completa il profilo».

ORA (AI Life Strategist) dirige la conversazione: decide *cosa* chiedere, *quando* e *perché*, in base al beneficio concreto per l’utente.

## Principi

1. Conversazione naturale — una domanda per turno
2. L’AI è il regista; il backend è sicurezza, persistenza e gate delle azioni irreversibili
3. Preferenza per documenti quando sostituiscono molte domande (rogito, libretto, piano di studi)
4. Domini in qualsiasi ordine (Casa, Auto, Studio, Lavoro, Salute, Finanze, Famiglia, Animali, Viaggi, Assicurazioni, Abbonamenti, …)
5. Dopo il primo avvio: **mai** mostrare Life Setup su Home — solo benefici in italiano
6. Proactive spiega sempre il beneficio — mai «Completa il profilo»
7. Privacy minima: mai password/OTP/PIN; niente dati non essenziali
8. Fallback deterministico in italiano se Gemini assente

## Flusso utente (primo avvio)

1. Registrazione / login → gate verso conversazione (`/life-setup`, UX Life Experience)
2. Saluto filosofia ORA (italiano)
3. Loop: contesto → piano → **una** domanda → risposta / documento / skip
4. Re-plan a ogni nuovo contesto
5. Uscita / complete → Home con card beneficio («Adesso posso seguire il tuo mutuo.»)
6. Proactive con copy beneficio

## Catene di beneficio

| Catena | Percorso |
|--------|----------|
| Casa | casa → mutuo → scadenze → calendar → goal → proactive |
| Auto | auto → libretto → assicurazione → revisione → bollo → reminder |
| Università | università → piano studi → esami → docs → study plan |

## Documenti reali + AI Document Understanding

Da `feature/life-experience-ai-documents`: quando ORA raccomanda un documento (rogito, libretto, bolletta, mutuo, piano di studi…), la conversazione apre il **vero file picker Expo**, avvia l'upload attraverso Documents V2 (unica pipeline), e dopo l'estrazione esegue un livello aggiuntivo di comprensione AI (Gemini via Provider Manager, fallback deterministico onesto se assente) che mappa i dati nel Life Profile con provenienza completa. Dettagli: `LIFE_EXPERIENCE_REAL_DOCUMENTS.md`, `AI_DOCUMENT_UNDERSTANDING.md`, `LIFE_DOCUMENT_MAPPING.md`, `CROSS_DOCUMENT_REASONING.md`, verifica onesta per tipo in `LIFE_EXPERIENCE_DOCUMENT_VERIFICATION.md`.

## Stack tecnico

- `backend/ai_life_strategist/` — reasoning loop, Gemini (Provider Manager), fallback
- `backend/life_setup/` — sessione, Life Profile, sync Graph/Goal, documenti reali (`document_mapping.py`, `cross_document.py`)
- `backend/documents/intelligence/life_reasoning.py` — AI Document Understanding (Gemini, structured Pydantic, fallback)
- Home adapter + Proactive generator — benefit cards italiane
- FE `frontend/app/life-setup/` — conversazione (route legacy, esperienza Life Experience) + file picker reale + pannello risultato documento

## Fuori scope (stub)

Email, Open Banking, WhatsApp, Weather — **non** integrati.
