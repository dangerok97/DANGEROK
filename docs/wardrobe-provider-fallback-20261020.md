# Guardaroba AI fallback diagnosis — 20 October 2026

Observed in the Railway backend logs at 16:27–16:28 Europe/Rome:
- The explicitly requested visual scan met provider HTTP 402 / provider_quota and
  subsequently provider_timeout, ending in HTTP 503. This is a provider
  billing/quota/runtime issue, not evidence that the user's photo was wrong.
- The stylist request hit Gemini quota, then Gemini's second configured
  account returned model text, but it did not satisfy the strict response
  schema (ValidationError).
- Rules-based fallback correctly used only existing clothing matches,
  but wrongly labeled every invalid model answer 'AI unavailable'.

Patch:
- Normalize harmless JSON formatting drift, never garment IDs or generated prose.
- Discard out-of-inventory numbered candidates; distinguish invalid_response
  from provider outage/quota/timeout in the UI.
- Require at least one genuine style judgment; reject duplicates and unsafe indices.
- Log only fixed validation reason codes, not raw model output or private data.
- Clarify visual-provider quota/timeout messaging.

Not fixed automatically: Google HTTP 402 requires the provider-account owner
to check billing/quota. No code change guarantees a successful paid API call.
Existing wardrobe entries are never migrated or edited by this patch.