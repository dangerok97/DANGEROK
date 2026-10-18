# ORA Guardaroba — pilot V1 (isolated, not released)

## Scope
- `/api/wardrobe/items` authenticated inventory CRUD, revision conflicts, owner isolation.
- Optional foreground JPEG/PNG/WebP photo (max 5 MB). Server strips EXIF, bounds pixels,
  creates a 480px JPEG and encrypts it using a *domain-separated* AES-GCM key derived
  from `TOKEN_VAULT_KEY`. Media is never public; responses use `private, no-store`.
- Catalog in VITA → Guardaroba, no new main tab, max 75 garments for this pilot.
- Occasion selector (run, casual evening, chic evening, club, wedding). One-piece dresses
  and jumpsuits can form a complete outfit with shoes (without fake trousers/tops); no hallucinated
  items and no automatic use of clothes marked as unavailable / laundry.
- Static, auditable preliminary pairing rules. The `engine=rules-v1` label is intentional.
  Outfit advice is **not** yet advanced AI fashion judgment and does not imply dress-code fit.
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
- Personal preference learning, fashion-trend curation, fit/size assessment.
- Conversational wardrobe tools shared by ORA app and WhatsApp; calendar/real meteo.
- Multi-garment photographic import, bulk duplicate identification, two-piece suits as a linked set.
- Professional fashion-stylist quality assessment and real-account end-to-end pilot.

## Release gate
This commit only creates a PR against `staging/cloud`: DO NOT merge or deploy by default.
First require isolated backend HTTP and privacy tests, frontend typecheck, native/web
photo-picking + AI-draft QA, and real-user evaluation on representative clothes.
Provider credentials are not required by unit/browser QA, which use synthetic responses;
**no live model accuracy has been demonstrated by those tests**.
The already open autonomy PR #350 remains untouched.
