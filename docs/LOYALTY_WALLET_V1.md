# ORA — Portafoglio tessere v1

## Product

VITA → Portafoglio tessere → Aggiungi tessera. The secondary `/portafoglio` route stays inside the existing tabs shell: the desktop rail and mobile navigation remain available. The existing VITA header is extended by a named wrapper export; other VITA sections are unchanged.

The user can enter a static loyalty-card code or explicitly select/capture a JPEG, PNG or WebP image. The code is decoded deterministically, not by an LLM. Multiple detected codes require a choice. The user supplies a name and confirms that the card is static and is not a payment card. Search, favorites, editing, deletion with confirmation and a white full-screen checkout view are included. The exact number remains selectable/readable. The user is asked to raise screen brightness; the application does not claim to control brightness. A browser wake lock is requested only while the checkout view is open, when supported.

Supported symbologies: Code 128, Code 39, EAN-13, EAN-8, UPC-A, ITF, QR. Inputs preserve leading zeroes and exact text. Check digits are validated, never repaired automatically; unsupported text/formats are rejected. The encoder must read back the generated PNG with exactly the same format and payload before accepting a save.

**Software read-back is not proof of merchant acceptance.** Every card carries `acceptance=not_verified_at_checkout`; the UI makes the distinction explicit. A merchant test with the real user-owned card is still required.

## Architecture and privacy

- UI: `frontend/src/wallet/`, route `frontend/app/(tabs)/portafoglio.tsx`.
- Domain: `backend/loyalty_wallet.py`.
- API: `backend/routers/loyalty_wallet.py`, mounted under `/api/wallet` using the existing `get_current_user` dependency.
- API operations: GET/PUT `/cards`, DELETE `/cards/{id}?revision=...`, POST `/decode` (raw bounded image upload).
- Images are processed transiently on the ORA backend. Original uploaded images are not stored on the server and are not sent to an AI or external decoding service. Native file selection can use the operating system's temporary picker cache.
- Generated barcode images, code, name and other card metadata are encrypted together with AES-256-GCM. Nonces are random; authenticated additional data binds the owner and card ID.
- A separate wallet key is derived with HKDF from the existing `TOKEN_VAULT_KEY`, falling back to `OAUTH_TOKEN_ENCRYPTION_KEY`. No key is hardcoded and the API fails closed with a readable 503 when secure configuration is absent. This is server-side encryption, not end-to-end encryption or a hardware-backed KMS guarantee.
- Keep the master secret stable. Rotating/removing it without decrypt/re-encrypt migration makes stored cards unreadable; do not rotate keys as part of this release.
- Collection `loyalty_wallets`: one aggregate per owner, `_id` and `user_id` set from authenticated identity. Only owner, aggregate revision and encrypted card entries are stored in clear. MongoDB's existing `_id` uniqueness provides the required primary index; no destructive migration is needed.
- Compare-and-swap writes prevent lost updates. Each card has an expected revision. Identical first-save retries do not duplicate a card. Deletions remove the encrypted payload from the active aggregate and are idempotent; existing backup-retention policy still applies.
- Limit: 100 cards; input photo ≤8 MB and ≤16 megapixels. No URL fetching, public media endpoint, card code in navigation URLs, or application payload logging.
- The frontend binds requests and responses to the captured login token. Changing accounts unmounts the wallet state. No unencrypted persistent local wallet cache is introduced. Successful responses use `Cache-Control: private, no-store`.

## Dependencies and configuration

One new backend dependency: `zxing-cpp==3.1.1`, pinned in both backend requirements files. The Railway Dockerfile already installs `requirements-cloud.txt`. No new frontend package, paid provider or external account is required. Existing vault master configuration is required for storage; it has not been changed by this feature.

## Verification

Local command:

```sh
python -m pytest -q tests/test_loyalty_wallet.py -ra
```

The initial isolated run passed 28 tests; seven real-codec cases were skipped because the local execution environment did not contain `zxingcpp`. This is not a full acceptance result. Dedicated `Loyalty wallet tests` CI first requires the real codec import, then runs the complete suite. Existing application CI checks compilation/build and unrelated regressions.

Covered cases include exact code preservation, invalid checksums/formats, explicit static-card confirmation, rejection of extra payment fields, ciphertext privacy/tamper protection/owner binding, account isolation, idempotence, stale revisions, concurrent writes, deletion and capacity. The real-codec cases render and decode all seven formats with synthetic values, including leading zeros and a Unicode QR payload.

Release gates: the real-codec suite, application CI, authenticated browser flow, responsive mobile view, account switch and checkout presentation must be checked before treating this as a verified release. Actual merchant acceptance can only be established by a store test. Never insert test cards into an existing real user's account.

## Explicitly not implemented

Payments, NFC, dynamic/rotating codes, issuer account login, automatic points balance, coupon activation, geofenced suggestions, Apple Wallet/Google Wallet export, direct chat/WhatsApp card handoff, and persistent offline reopening. A card already loaded in memory can be displayed while that page stays open, but the app must not advertise complete offline availability. A secure device cache and offline app shell are a separate follow-up.

The first release is a bounded loyalty-card wallet, not a universal replacement for official merchant apps.


## V1.1 — faster at checkout, without exposing card data (14 October 2026)

This release addresses the costliest usability gap: opening a tile used to lead to an intermediate detail panel and require another tap before the barcode appeared. The large tile now opens the cashier screen in **one tap**. Editing/deleting stays behind the separate **Gestisci** control. After closing a tile's cashier screen the user returns to the list. The existing detail panel still supports editing, deleting and cashier preview.

- Favorites remain at the top and can be toggled with one touch directly from a tile, without opening the editor; other cards sort by most recently opened on *that device*, then by name.
- The last four cards can be opened directly from **Usate di recente** when at least two have been used; **Cancella recenti** clears the local order. Recent ordering stores at most eight opaque card IDs, SHA-256 owner-scoped, in device storage; it **never stores a barcode, image, card name or card number**. This is not an offline wallet or cross-device usage tracking.
- Cashier view supports **Ruota codice di 90°** for linear barcodes, useful on narrow phones, plus next/previous card switching without going back to the list. QR codes are not rotated.
- Explicit **Copia numero** uses the operating system clipboard on user request; be mindful that an operating-system clipboard can remain available to other apps.
- Saving now rejects accidental duplicates with the same normalized merchant name, format and code. An identical code used by a *different* merchant is allowed: the same phone number can legally be a loyalty number for different chains. All checks happen inside the owner-scoped encrypted aggregate, with existing compare-and-swap retries.

The cashier screen still requires that the card has already been fetched at least once in the current app session. **Reopening the app while offline is NOT supported**: encrypted durable offline storage and offline authentication require a separate audited implementation. This patch intentionally avoids persisting plaintext codes/images in AsyncStorage or browser localStorage, which would create an avoidable security regression. This is a transparent technical limitation, not a promised offline feature.

Verification gates: backend duplicate/concurrency tests, TypeScript, production web export, complete existing checkout E2E on Chromium and WebKit, and additional synthetic checks for one-tap cashier, QR rotation exclusion, device-local recent ordering, card switching while temporarily offline, preserved desktop rail, and clipboard action presence. No real user cards are used in automated tests; in-store scanner acceptance remains unverified until a real checkout.


## V1.2 — Discoverability fix: visible wallet inside VITA

The first release did not give the wallet an explicit place in VITA's normal section flow; it injected a card immediately after `VitaHeader` by silently re-exporting a wrapped header in `src/components/vita/index.ts`. A user browsing later sections (profile progress → Places → bank → life areas) would not find it. The wallet's own `/portafoglio` page and backend worked, but this was a **real discoverability defect**, not a missing tutorial.

The header override has been removed and the original `VitaHeader` contract restored. VITA now renders a clearly titled **TESSERE FEDELTÀ** section with a **Portafoglio tessere** entry immediately after **LUOGHI**, before **LA TUA VITA**. The section is visible on desktop and phone, and is rendered even when no cards exist or the Life Map is empty/unavailable. It opens the existing wallet route, requiring regular user authentication. No changes to loyalty-card storage, API, payments or offline capabilities.

Validation: E2E `vita-wallet-visibility.spec.ts` visits the actual exported VITA route on Chromium and WebKit, with synthetic account and life data, checks explicit section order, one entry only, working navigation to the wallet page, an empty life model, and a Life Map failure. Current snapshot screenshots show the entry on an iPhone-sized viewport. No real account data is accessed or modified.


## VITA canonical URL correction (14 October 2026)

The app accidentally served two different screens under `/vita` and `/contesti`: the main navigation pointed to `/vita` (approved `GuidedSetupScreen`), whereas prior loyalty-wallet work was added to a separate older `/contesti` dashboard. This made a feature appear and disappear depending on which VITA link the user opened. **This is a routing/product regression, not a user cache issue.**

Canonical route: **`/vita`**. The actual approved VITA/Conosciamoci screen now includes the `TESSERE FEDELTÀ` card immediately after `I tuoi luoghi` and before the bank summary. Legacy `/contesti` is a permanent *client-side* redirect to `/vita`, preserving existing bookmarks without continuing two independent UIs. The wallet's own back button now returns to `/vita`. No modification to the database, encrypted card records or backend authentication.

Acceptance requirement: a real mobile browser logged into the same account must reach the exact same VITA via either path, see one wallet entry, and open the existing authenticated `/portafoglio` route; the old link must never present its own competing view. E2E fixtures must include the proper `/life-profile/knowledge-map` contract (stars and branches arrays): an empty object crashes the unrelated knowledge-map component and creates a misleading blank page.
