# ORA Guardaroba — pilot V1 (isolated, not released)

## Scope
- `/api/wardrobe/items` authenticated inventory CRUD, revision conflicts, owner isolation.
- Optional foreground JPEG/PNG/WebP photo (max 5 MB). Server strips EXIF, bounds pixels,
  creates a 480px JPEG and encrypts it using a *domain-separated* AES-GCM key derived
  from `TOKEN_VAULT_KEY`. Media is never public; responses use `private, no-store`.
- Catalog in VITA → Guardaroba, no new main tab, max 75 garments for this pilot.
- Occasion selector (run, casual evening, chic evening, club, wedding); no hallucinated
  items and no automatic use of clothes marked as unavailable / laundry.
- Static, auditable preliminary pairing rules. The `engine=rules-v1` label is intentional.
  Outfit advice is **not** yet advanced AI fashion judgment and does not imply dress-code fit.

## Reuse and credits
Concepts for body-role completeness, formality and temperature bucketing adapted from
[Wardrowbe](https://github.com/Anyesh/wardrowbe) by Anish S. under MIT.
See `backend/wardrobe/THIRD_PARTY_LICENSE.txt`. Do not import its Next.js frontend or
PostgreSQL schema into ORA's Expo/FastAPI/MongoDB application.

## Not yet included
- AI photographic classification, automatic color/material tagging, background removal.
- Personal preference learning, fashion-trend curation, fit/size assessment.
- Conversational wardrobe tools shared by ORA app and WhatsApp; calendar/real meteo.
- Multi-garment photographic import, bulk duplicate identification.
- Professional fashion-stylist quality assessment and real-account end-to-end pilot.

## Release gate
This commit only creates a PR against `staging/cloud`: DO NOT merge or deploy by default.
First require isolated backend HTTP and privacy tests, frontend typecheck, native/web
photo-picking QA, and real-user evaluation on representative clothes.
The already open autonomy PR #350 remains untouched.
