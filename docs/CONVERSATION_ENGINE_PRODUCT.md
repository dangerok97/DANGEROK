# Conversation Engine — Product

**Not a chatbot.** ORA Conversation Engine is a stateful collaboration orchestrator: one question → answer → system action → result → next question. It produces real changes (goals, projects, calendar, study/travel plans) via existing engines.

## What users experience

1. On Home, **PARLA CON ORA** (mic stub + text + send).
2. User says e.g. “Fra due settimane parto.” or “Voglio preparare l'esame.”
3. ORA opens a **guided one-question screen** (Action Engine chips) — never a chat bubble thread.
4. Each answer can create/update Goal, Project, calendar events, Brain links.
5. If interrupted: Home / Proactive show **“Stavamo organizzando…” → Continua / Riprendi** — never “Apri chat”.

## Origins

| Origin | Status |
|--------|--------|
| home, voice, text, documents, notifications, proactive | Active entry paths |
| email, whatsapp, open_banking | Stub only — structure accepted, no simulated data |

Voice uses the same engine; STT is stubbed (type text, mic marks `origin=voice`).

## Memory

Answered slots are remembered for the session (`known_slots`). ORA does not re-ask what Intent/AE already know.

## Resume

Paused / waiting sessions keep a `resume_token`. Summary phrasing: “Stavamo organizzando la tua vacanza.” / “Stavamo preparando il tuo esame.” CTA: **Continua** or **Riprendi**.

## Flag

`CONVERSATION_ENGINE_ENABLED` (default ON). When OFF, `/api/conversation/*` returns disabled; Home PARLA should fail soft.

## Limits (honest)

- Not ChatGPT / messenger / infinite free chat.
- LLM/Gemini only when Intent/Goal/Action are insufficient (via those engines).
- Email / WhatsApp / Open Banking: stubs only.
- Mic: no real STT yet.
- Domain logic stays in Intent / Goal / Action / Projects / Brain / Proactive — CE only orchestrates.
