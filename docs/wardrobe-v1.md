# ORA Guardaroba — pilot V1 · incremental live quality improvements

## Scope
- `/api/wardrobe/items` authenticated inventory CRUD, revision conflicts, owner isolation.
- Optional foreground JPEG/PNG/WebP photo (max 5 MB). Server strips EXIF, bounds pixels,
  creates a 480px JPEG and encrypts it using a *domain-separated* AES-GCM key derived
  from `TOKEN_VAULT_KEY`. Media is never public; responses use `private, no-store`.
- Catalog in VITA → Guardaroba, no new main tab, max 75 garments for this pilot.
- Occasion selector (run, casual evening, chic evening, club, wedding). One-piece dresses
  and jumpsuits can form a complete outfit with shoes (without fake trousers/tops); no hallucinated
  items and no automatic use of clothes marked as unavailable / laundry.
- Style suggestions now use a **two-stage AI stylist** when requested: ORA builds
  a bounded list of *owned, available* complete outfits, then the existing LLM
  manager ranks numbered options for event/formality/color.
  **Grounded explanation contract (Oct 20, 2026):** the model is allowed to
  return ONLY enumerated assessments and an enumerated shirt-wearing adjustment.
  The server writes all displayed Italian explanations and allows an adjustment
  only if that real garment supports it. This prevents model prose from
  recommending an unrecorded belt, jacket or accessory.
  Guardrails flag black shoes against brown trousers as a *possible* contrast,
  and formal shoes against an explicit 'non troppo formale' preference.
  A single eligible combination is labelled as the only current possibility,
  never described as the objectively best outfit.
  Model output cannot invent garment IDs: server validates option numbers and
  resolves the exact original item IDs. No photographs, user IDs or login data
  are sent to the stylist. In failure/timeout, explicit `rules-v1` fallback
  is returned with `ai_status=unavailable` (not a falsely successful AI look).
- `use_ai=false` preserves the legacy deterministic /outfits API contract;
  the new VITA look button explicitly uses AI and supports a short style note.
- Shared read-only `suggest_wardrobe_outfit` AI Core capability gives the
  existing app and WhatsApp channels access to the same owner-scoped inventory.
  It sends text garment summaries only (never photos) and does not send WhatsApp
  notifications or alter the user's wardrobe.
- Optional `POST /api/wardrobe/analyze` with existing ORA Vision (Gemini, fallback OpenAI
  if configured). Authenticated, image max 5 MB; strips metadata and downscales before
  sending JPEG to the configured AI provider(s). The user **explicitly** presses
  "Riconosci con AI" after selecting a photo. No provider call on photo selection.
- AI output is schema-validated (single garment, category, color, optional formality,
  confidence high/medium only). A tentative suggestion fills **editable** fields:
  it is never saved automatically. Uncertain, unsupported or malformed results never
  prefill an item; provider errors preserve the manual path.
- Cost control: an atomic **per-account quota** of 12 analyses per hour reuses the
  existing TTL-indexed rate-limit collection. Images and model raw output are not
  persisted to MongoDB by the analysis endpoint.

## Reuse and credits
Concepts for body-role completeness, formality and temperature bucketing adapted from
[Wardrowbe](https://github.com/Anyesh/wardrowbe) by Anish S. under MIT.
See `backend/wardrobe/THIRD_PARTY_LICENSE.txt`. Do not import its Next.js frontend or
PostgreSQL schema into ORA's Expo/FastAPI/MongoDB application.

## Not yet included
- Automatic bulk classification, reliable material/tag extraction and background removal (only an explicit, user-reviewed single-photo AI *draft* is implemented).
- Persistent outfit acceptance/feedback learning, live fashion-trend curation, fit/size assessment.
- Verified end-to-end WhatsApp provider delivery and real-account conversations; calendar/real meteo.
- Multi-garment photographic import, bulk duplicate identification, two-piece suits as a linked set.
- Independent professional stylist-quality assessment, actual garment photos and real-account end-to-end pilot.

## Release gate
This commit only creates a PR against `staging/cloud`: DO NOT merge or deploy by default.
First require isolated backend HTTP and privacy tests, frontend typecheck, native/web
photo-picking, AI draft + owner-scoped stylist QA, and real-user evaluation on representative clothes.
Provider credentials are not required by unit/browser QA, which use synthetic responses;
**no live model accuracy has been demonstrated by those tests**.
The already open autonomy PR #350 remains untouched.

## Feedback-driven quality gate
The screenshot of blue shirt + brown trousers + black lace-ups, requested as
'elegante ma senza essere troppo formale', exposed ungrounded belt advice and
excessively flattering prose. The new deterministic quality guardrails require:
- Honest contrast/formality cautions, rather than unqualified praise.
- No invented belt, accessory, clothing purchase or unknown material.
- Larger user-owned garment thumbnails and visible reservations in VITA.
- Alternate shoes may compete even when shirt and trousers remain unchanged.
- Synthetic regressions cannot establish aesthetic correctness on real clothes.


## Visual knowledge, strictly opt-in (v2)
A user-selected photograph remains encrypted in the wardrobe collection.
Pressing **Analizza stile con AI** on an individual saved garment decrypts its
existing EXIF-free JPEG in memory and explicitly submits it to the configured
ORA Vision model. No background bulk scan or new external API key.
The model returns only enumerated visual descriptors (pattern, visible structure,
surface *appearance*, warm/cool tone and confidence); these are proposed values,
not product properties or actual fabric composition. **Nothing is persisted
until the owner reviews and confirms** the proposal in VITA. Any field can be
corrected through chips. A saved profile is cleared when its photograph,
category or registered color changes, and a user can remove it explicitly.
Photo hash and optimistic revision prevent confirmation against a changed
photograph; only the owner can scan, approve or clear it. A low-confidence
scan is never saved. The confirmed metadata, not the JPEG, may accompany
outfit descriptors sent to the AI stylist. A visible N/M coverage label
indicates how many worn items have reviewed visual metadata. ORA still cannot
judge actual fit on a human from a garment catalog.

## Taste learning, explicit and owner-isolated
"Mi piace / Non mi piace" persists one reaction per exact outfit+occasion
in a dedicated owner-scoped collection (max 250 unique reactions/account).
It does not silently learn from clicks or other app activity. Later calls
prioritize liked real combinations, down-rank shared items disliked in other
combinations, and *exclude* exact previously disliked outfits. If all complete
outfits were declined, ORA says there is no currently acceptable combination,
rather than inventing alternatives. Saving or changing an opinion is reversible.
Deleting a garment also deletes any of its associated feedback. The AI sees
only bounded clothing descriptors and an anonymous like flag per candidate;
it never receives account IDs, encrypted photos, feedback database keys,
or private personal context. This is lightweight preference ranking, not
model fine-tuning or professional fashion expertise.

## Release limits
- Visual analysis requires an explicit click per saved garment and an explicit
  second confirmation for details, so existing users' photographs are not
  automatically exported for analysis.
- No automatic outfit photography/rendering or virtual try-on. A source photo
  that shows multiple garments may produce an uncertain response; a human must
  review it.
- Synthetic backend/Playwright tests prove correctness of ownership, data,
  preference filters and interactions, not visual recognition accuracy on
  real clothing photos. Live provider behavior must still be field-tested.
