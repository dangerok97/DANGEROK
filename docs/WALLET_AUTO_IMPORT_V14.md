# ORA Wallet — photo-first import (V1.4)

## Product correction

A user uploaded a readable loyalty card but was left with a technical form, a blank code field and two symbology choices. The previous decoder deliberately returned both a UPC-A reading and its equivalent EAN-13 representation; the old UI interpreted them as different cards. That is not a useful question to ask the user.

The new flow is **photo/screenshot → barcode and number preview → Save**. The merchant name is optional; an unnamed card is saved as `Tessera fedeltà` and can be renamed later. No merchant identity is guessed from a barcode prefix. A supplied name is retained during import. No favorites switch, static-card checkbox or format selector is shown on the photo path. Favorites stay available on the existing card tiles. Manual code entry and correction remain explicitly opt-in.

A short notice next to Save defines the scope as fixed-code loyalty cards, excluding payments and changing codes. Pressing Save is the user's declaration; scanning an image does not establish that a card is static or that a merchant will accept it.

## Architecture

`WalletEditor.tsx` owns the foreground import/edit state. `WalletScreen.tsx` retains account-bound gallery, favorites, recents, deletion and cashier behavior. `scanCandidates.ts` groups only checksum-valid UPC-A / zero-prefixed EAN-13 pairs that represent identical physical bars. It prefers the full EAN representation when returned; arbitrary leading zeros and cross-format QR/Code128 contents are not altered or grouped. Two truly different codes require selecting a code preview, not filling a technical form.

`POST /api/wallet/decode` adds an optional inline PNG `image` to each existing candidate. The current deterministic encoder produces it, including exact software read-back. Decode and preview generation run in the threadpool. No AI/OCR provider is involved, and no uploaded photo is persisted. Old clients ignore the extra field; new clients also accept old candidate responses without an image during deployment.

After choosing a new actual file, the previous decoded number/preview is invalidated before the request starts. An unreadable or ambiguous replacement cannot save a stale code. Closing the file picker without choosing another image preserves the existing draft. A synchronous operation lock prevents duplicate submissions. Save remains one explicit action and the existing idempotent revision/account checks remain unchanged.

The scroll content uses the shell's bottom inset with a conservative minimum to keep Save reachable above mobile navigation. The wallet card preview only allows bounded inline PNG URLs, never remote or executable image sources.

## Security and data changes

No new runtime dependency, provider, key or environment variable. No database migration. No change to encryption or account isolation. No user photos or card numbers are committed, uploaded to CI or placed in screenshots. UI/HTTP tests use synthetic cards. A short-lived CI artifact contains only the already-pinned public codec wheel and wallet source so that a supplied photo can be checked in an isolated local environment without sending it to another provider.

Static-code limits, actual merchant acceptance, and lack of persistent offline reopening remain as documented in `LOYALTY_WALLET_V1.md` and issue #288.

## Verification contract

- Existing backend isolation/HTTP/format tests remain; real-codec HTTP tests verify inline previews and that decode saves nothing.
- Pure grouping tests cover both orders of equivalent EAN/UPC, checksum validation, distinct physical codes, preservation of leading zeros and cross-format distinctions, and inline-image safety.
- Browser tests cover real file-picker interaction against synthetic decoder responses, automatic EAN/UPC resolution, barcode preview loading, no mandatory name or technical inputs, preserving a typed name, QR import, exceptional multi-code selection, stale-code invalidation after failed reupload, and an unobstructed Save button.
- Existing VITA discovery, gallery, favorites, cashier, rotation, recent ordering and delete tests remain enabled on Chromium and WebKit.

A passing browser fixture test is not a live merchant scan or a test in the user's production account. Release status and actual CI/deployment IDs belong in the PR after verification, not guessed in this document.
