"""Bind user-visible Situation identifiers to committed owner-specific writes.

Model-authored prose is not an identifier ledger. A real create/update returns
an authoritative Situation.context_preview from SituationService.apply. At
the final response boundary, strip IDs and timestamp claims that did not come
from that result, and include the exact persisted receipt. Never guess an ID
from the user's request, another Situation, or the model's own narrative.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

_ID_RE = re.compile(r"(?<![A-Za-z0-9_])sit_[a-zA-Z0-9_-]{4,72}(?![A-Za-z0-9_-])")
_ISO_LINE = re.compile(
    r"(?:\bcreated_at\b|\bstarted_at\b|\bdata\s+di\s+creazione\b|"
    r"\bdata\s+d['’]inizio\b|\bdata\s+inizio\b)",
    flags=re.IGNORECASE,
)
_POSITIVE_CREATE = re.compile(
    r"\b(?:ho\s+(?:creat[oa]|registrat[oa]|salvat[oa]|aggiunt[oa])|"
    r"\b(?:appena|ora)\s+(?:registrat[oa]|creat[oa]))\b"
    r"[^.!?\n]{0,130}\b(?:situazion[ei]|memoria\s+temporanea)\b",
    re.IGNORECASE,
)


def _strip_unproven_model_fields(text: str) -> str:
    """Remove model-authored created_at/started_at lines, not source fields."""
    return "\n".join(
        line for line in (text or "").splitlines()
        if not _ISO_LINE.search(line)
    ).strip()


def verified_situation_receipt(
    model_text: str, result: Optional[Dict[str, Any]], *,
    allow_unverified_text: bool = False,
) -> str:
    """Preserve useful narrative without allowing phantom Situation IDs.

    For an *actual* Situation write the database receipt is authoritative.
    For no write, a first-person creation claim is blocked if it would
    otherwise become a fabricated record. Status-only reads are unaffected.
    """
    original = str(model_text or "").strip()
    write = result or {}
    saved = write.get("situation") or {}
    if not isinstance(saved, dict):
        saved = {}
    status = str(write.get("status") or "")
    operation = str(write.get("operation") or "")
    sid = str(saved.get("id") or "").strip()
    confirmed = status == "success" and operation in ("create", "update") and bool(sid)

    if not confirmed:
        if not allow_unverified_text and _POSITIVE_CREATE.search(original):
            return (
                "Non ho conferma che una nuova Situazione sia stata salvata "
                "nel database in questo turno. Non posso indicare un ID "
                "o una data di creazione senza una conferma verificabile."
            )
        return original

    old_id = str(write.get("previous_situation_id") or "").strip()
    allowed = {sid, old_id}
    unknown_ids = {
        match.group(0) for match in _ID_RE.finditer(original)
        if match.group(0) not in allowed
    }
    text = _ID_RE.sub(
        lambda match: match.group(0)
        if match.group(0) in allowed else "[ID non verificato]",
        original,
    )
    if operation == "create":
        # Model text should never compete with server-owned timestamps.
        text = _strip_unproven_model_fields(text)
        # Owner feedback 23/10: a plain conversational answer ("la seguo io")
        # got an internal id and ISO timestamps appended on every new
        # Situation. The receipt exists to correct record claims; with no id,
        # no creation claim and no timestamp in the text there is nothing to
        # correct, and the person sees the Situation in Aggiornamenti.
        if not (_ID_RE.search(original) or _POSITIVE_CREATE.search(original)
                or _ISO_LINE.search(original)):
            return text
    elif not unknown_ids and not _POSITIVE_CREATE.search(original):
        # Ordinary updates must not clutter every conversational reply with
        # internal identifiers. We only correct fabricated create/ID claims.
        return original
    created = str(saved.get("created_at") or "").strip()
    started = str(saved.get("started_at") or "").strip()
    lifecycle = str(saved.get("status") or "").strip()
    if operation == "create":
        lines = [f"**Conferma archivio ORA — nuova Situazione:** `{sid}`."]
        if created:
            lines.append(f"Creata il: `{created}`.")
        lines.append(f"Inizio dichiarato: `{started}`." if started else
                     "Inizio effettivo non attestato.")
        if lifecycle:
            lines.append(f"Stato salvato: `{lifecycle}`.")
    else:
        lines = [f"**Conferma archivio ORA — Situazione aggiornata:** `{sid}`.",
                 "Nessun nuovo ID creato da questo aggiornamento."]
    if unknown_ids:
        lines.append(
            "Ho escluso identificativi non confermati dal database."
        )
    receipt = " ".join(lines)
    return (text + "\n\n" if text else "") + receipt
