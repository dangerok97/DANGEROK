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
