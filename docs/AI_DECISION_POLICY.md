# AI Decision Policy — Life Experience

## L’AI può

- Scegliere la prossima domanda (una sola)
- Preferire un documento al posto di molte domande
- Spiegare il beneficio in italiano semplice
- Soft-resume dopo interruzione (un solo suggerimento)
- Attivare card Home / Proactive basate su benefici concreti

## L’AI non può

- Decidere azioni irreversibili (cancellazioni, pagamenti, invii) senza gate esplicito
- Chiedere password, PIN, OTP, IBAN, CVV
- Inventare integrazioni Email / Banking / WhatsApp / Weather
- Mostrare wizard / «completa il profilo»
- Ripetere domande già poste, rifiutate o rimandate
- Esporre catene di pensiero interne all’utente

## Backend come gate

Il backend:

1. Valida e sanitizza (policy privacy)
2. Persiste Life Profile / sessione
3. Sincronizza Life Graph / Goal (best-effort)
4. Blocca campi non sicuri nei piani Gemini (`filter_unsafe_plan_fields`)

## Fallback

Se Gemini è assente o invalido: `question_planner.plan_next` — stesso contratto Pydantic, copy italiano, benefit-driven.
