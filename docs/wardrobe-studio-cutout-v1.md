# ORA Studio Cutout — opt-in pilot architecture

## Why a separate service?
ORA's primary API remains lightweight. ONNX Runtime and the segmentation
checkpoint live only in an isolated private Railway service. The pilot uses
pinned 4.57MB U²-NetP weights from the U²-Net Apache-2.0 project, SHA-256
verified in the worker image at build time. No BRIA/commercially restricted
checkpoint is downloaded at runtime.

## Privacy, user control, fallback
1. A logged-in ORA user explicitly clicks "Crea foto vetrina fronte/retro".
2. The backend decrypts only that user's normalized source photograph and
   passes one JPEG to ORA_CUTOUT_URL on the Railway private network.
3. The isolated worker returns one 576x576 transparent PNG studio composition.
   It keeps **no** copy, has no public domain, no photo request logging, and no
   runtime external network calls.
4. The backend validates transparency, dimensions and reasonable foreground
   coverage, then returns an **ephemeral user-visible preview**. No DB mutation.
5. VITA shows the cutout on BOTH light and dark backgrounds to reveal damaged
   edges, offers "Scarta" or "Accetta". Acceptance includes the exact normalized
   source hash and optimistic garment revision. After approval, the cutout PNG
   is stored encrypted with a distinct AEAD scope and does NOT replace front/back
   source images or visual metadata.
6. The user can show originals at any time or revoke a cutout without deleting
   the underlying garment or front/back photos.

## Deployment gate
- Add a dedicated Railway service pointing to repo /backend,
  Dockerfile /backend/Dockerfile.cutout-worker; one worker, no public domain.
- Deploy with a random >=32-char ORA_CUTOUT_TOKEN.
- Configure backend *only after worker validated*: 
  ORA_WARDROBE_CUTOUT_URL=http://<service>.railway.internal:8080,
  ORA_WARDROBE_CUTOUT_TOKEN=<same secret>.
- No cutout UI buttons are shown until both vars validate as internal-only.
- Railway new-build pause or worker deployment failure leaves the cutout
  disabled; the existing wardrobe, styling AI and manual front/back photos
  continue operating normally.
- Credentials and photos MUST NEVER be committed to Git.
- Run test masks, auth/owner isolation tests and representative user-approved
  clothing/photo QA (white on light, black on dark, sleeves, collars, fringes,
  shoe laces and cluttered backgrounds) before enabling on the live ORA API.
- Do not claim studio/ecommerce quality from CI; automated tests exercise a
  synthetic ONNX output, not real model quality.
- Model can eventually be replaced with a higher-quality commercially
  licensed checkpoint, without touching the central catalog/API.

## Correctness
The backend endpoints are authenticated and revision fenced:
- GET /api/wardrobe/showcase/availability
- POST /api/wardrobe/items/{id}/showcase/preview?revision=N&view=front|back
- PUT /api/wardrobe/items/{id}/showcase with {revision,view,source_sha256,png_b64}
- DELETE /api/wardrobe/items/{id}/showcase with {revision,view}

An item has at most two accepted *derived* images (front/back) and still just
one garment ID. Source JPEGs and derived studio PNGs are encrypted in MongoDB
using different associated data. The acceptance/revoke handlers never alter
the inventory category, style preference reactions or original user photos.
Photo replacement invalidates its corresponding studio cutout.
