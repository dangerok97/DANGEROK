"""Documenti — one read model over what ORA holds and has understood.

Presentation only, over stores that already exist: the documents collection and
the analysis the pipeline already wrote onto it, the extracted event candidates,
and the Life Profile facts that already point back at a document. Nothing here
parses, classifies, extracts or infers — the understanding happened upstream,
and this decides what of it a person should see.

Two rules do most of the work:

  * a deadline is a date the extractor actually found and persisted as a
    candidate. It is never derived from a filename, a title or a category;
  * a document belongs to a part of someone's life when a Life Profile fact in
    that domain names it. That link is structured and was written by the
    subsystem that owns it, so it can be shown. A filename that happens to say
    "casa" is not a link and never becomes one.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.documents.library")

# This is a page about what a person has, not an archive browser: bounded reads
# throughout, and the rail panels are short by design.
MAX_DOCUMENTS = 60
MAX_EXPIRING = 5
EXPIRY_HORIZON_DAYS = 120

# The pipeline's own vocabulary. `completed` is the only state that means ORA
# actually understood the file; everything before it is still on its way, and
# `failed` is the one honest bad outcome.
STATUS_READY = "completed"
STATUS_FAILED = "failed"
IN_PROGRESS = {
    "queued",
    "extracting",
    "understanding",
    "classifying",
    "analyzing",
    "generating_actions",
}
# States the pipeline finished in but which still want a person's eye.
NEEDS_ATTENTION = {"needs_review", "awaiting_confirmation", "action_required"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _text(value: Any, limit: int = 200) -> str:
    return str(value or "").strip()[:limit]


def _kind(mime: str, filename: str) -> str:
    """The short badge a person recognises — PDF, DOCX — from what we stored.

    Read off the mime type first because that is what the upload actually
    verified, and only fall back to the extension when the type is generic.
    """
    m = (mime or "").lower()
    table = [
        ("pdf", "PDF"),
        ("wordprocessingml", "DOCX"),
        ("msword", "DOC"),
        ("spreadsheetml", "XLSX"),
        ("ms-excel", "XLS"),
        ("presentationml", "PPTX"),
        ("image/", "Immagine"),
        ("text/plain", "Testo"),
        ("text/markdown", "Testo"),
        ("csv", "CSV"),
    ]
    for needle, label in table:
        if needle in m:
            return label
    ext = (filename or "").rsplit(".", 1)
    return ext[-1].upper()[:6] if len(ext) == 2 and ext[-1] else "File"


def _presentation_status(doc: Dict[str, Any]) -> str:
    """The human state, from the pipeline state — never the raw one.

    Four outcomes are all a person needs: ORA understood it, ORA is still
    working on it, ORA could not read it, or it is sitting there unread. The
    pipeline has a dozen internal phases and none of them belong on a row.
    """
    status = _text(doc.get("pipeline_status"), 40)
    if status == STATUS_FAILED:
        return "failed"
    if status in IN_PROGRESS:
        return "analyzing"
    if status in NEEDS_ATTENTION:
        return "needs_review"
    analysis = doc.get("analysis") or {}
    if status == STATUS_READY or analysis.get("macro_category"):
        return "ready"
    return "pending"


def _expiry_of(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A real deadline, or nothing.

    Only a persisted event candidate the extractor marked as a deadline counts.
    An ordinary event on a document — a concert, an appointment — is a date, not
    an expiry, and calling it one would put "Scade il…" on a ticket.
    """
    for ev in doc.get("event_candidates") or []:
        if (ev.get("category") or "") != "deadline":
            continue
        if (ev.get("status") or "") not in ("proposed", "confirmed"):
            continue
        when = _parse(ev.get("start_datetime"))
        if not when:
            continue
        return {"at": when.isoformat(), "title": _text(ev.get("title"), 120)}
    return None


def _summary_of(doc: Dict[str, Any]) -> str:
    analysis = doc.get("analysis") or {}
    return _text(analysis.get("short_description") or analysis.get("summary"), 220)


async def _areas_by_document(db, user_id: str) -> Dict[str, List[str]]:
    """Which part of a life each document is attached to.

    The Life Profile writes `source_document_id` / `linked_doc_ids` onto a fact
    when a document is what taught it something. That is the only honest link
    available: it was recorded by the subsystem that made the inference, at the
    moment it made it. The domain key it lives under is the same one the Life
    Map turns into an area, so the two surfaces agree about what "Casa" means.
    """
    out: Dict[str, List[str]] = {}
    try:
        profile = await db.life_profiles.find_one(
            {"user_id": user_id}, {"_id": 0, "domains": 1},
        )
    except Exception:
        logger.info("documents library profile read soft-fail")
        return out

    for domain, block in ((profile or {}).get("domains") or {}).items():
        key = _text(domain, 40).lower()
        if not key or key in ("mlc", "doc"):
            continue
        for fact in (block or {}).get("objects", {}).values():
            if not isinstance(fact, dict):
                continue
            refs = list(fact.get("linked_doc_ids") or [])
            if fact.get("source_document_id"):
                refs.append(fact["source_document_id"])
            for ref in refs:
                rid = _text(ref, 80)
                if not rid:
                    continue
                bucket = out.setdefault(rid, [])
                if key not in bucket:
                    bucket.append(key)
    return out


async def _documents_ora_is_proposing(db, user_id: str, *, now: datetime) -> Dict[str, int]:
    """
    How many things ORA is actually putting to this person, per document.

    "Azione suggerita" has to mean the same thing on this page as everywhere
    else: something ORA is proposing that the person do. What ORA proposes is
    decided in exactly one place — `home.work_admission` — so this asks it
    rather than keeping a second opinion that can drift from the first.

    What it replaced was a count of proposed event candidates. A candidate is a
    proposal the pipeline makes to the rest of ORA, not to anybody: it is how
    the extractor hands a date onward. Counting those told a person that a
    policy ORA had read perfectly, and deliberately said nothing about, came
    with an action suggested to them.
    """
    try:
        from home.adapters.document_actions import load_document_actions
        from home.adapters.documents import load_documents
        from home.adapters.event_candidates import load_event_candidates
        from home.work_admission import reason_to_act
    except Exception as e:  # pragma: no cover - the page renders regardless
        logger.warning("work admission unavailable: %s", type(e).__name__)
        return {}

    counts: Dict[str, int] = {}
    for load in (load_documents, load_document_actions, load_event_candidates):
        try:
            items, _ = await load(db, user_id)
        except Exception as e:
            logger.warning("%s read failed: %s", load.__name__, type(e).__name__)
            continue
        for item in items:
            if not reason_to_act(item, now=now):
                continue
            key = str(getattr(item, "source_id", "") or "")
            if key:
                counts[key] = counts.get(key, 0) + 1
    return counts


async def build_library(db, user_id: str, *, domain_labels: Dict[str, str]) -> Dict[str, Any]:
    """Everything the Documenti page shows, in one request.

    `domain_labels` is passed in rather than imported so the area names stay
    the Life Map's to define: this module never decides that a domain called
    `casa` is displayed as "Casa", it only knows the two are the same key.
    """
    now = _now()
    partial: List[str] = []

    docs: List[Dict[str, Any]] = []
    try:
        docs = (
            await db.documents.find(
                {"user_id": user_id, "deleted": {"$ne": True}, "archived": {"$ne": True}},
                {"_id": 0, "extracted_text": 0},
            )
            .sort("created_at", -1)
            .limit(MAX_DOCUMENTS)
            .to_list(MAX_DOCUMENTS)
        )
    except Exception as e:
        logger.warning("documents library read failed: %s", type(e).__name__)
        partial.append("documents")

    areas_by_doc = await _areas_by_document(db, user_id)
    proposing = await _documents_ora_is_proposing(db, user_id, now=now)

    items: List[Dict[str, Any]] = []
    for d in docs:
        did = _text(d.get("id"), 80)
        if not did:
            continue
        analysis = d.get("analysis") or {}
        title = (
            _text(d.get("display_title"))
            or _text(d.get("user_title"))
            or _text(analysis.get("suggested_title"))
            or _text(d.get("original_filename") or d.get("filename"))
        )
        if not title:
            continue
        expiry = _expiry_of(d)
        areas = [
            {"key": k, "label": domain_labels.get(k) or k.capitalize()}
            for k in areas_by_doc.get(did, [])
            if domain_labels.get(k) or k
        ]
        items.append({
            "id": did,
            "title": title,
            "kind": _kind(_text(d.get("mime_type"), 120), _text(d.get("original_filename"), 200)),
            "uploaded_at": _text(d.get("created_at"), 40),
            "status": _presentation_status(d),
            "summary": _summary_of(d),
            "areas": areas,
            "expiry": expiry,
            "open_actions": proposing.get(did, 0),
        })

    # --- rail -------------------------------------------------------------
    expiring = [
        {
            "id": it["id"],
            "title": it["expiry"]["title"] or it["title"],
            "at": it["expiry"]["at"],
        }
        for it in items
        if it["expiry"]
    ]
    horizon = EXPIRY_HORIZON_DAYS * 86400
    expiring = [
        e
        for e in expiring
        if (_parse(e["at"]) or now) >= now
        and ((_parse(e["at"]) or now) - now).total_seconds() <= horizon
    ]
    expiring.sort(key=lambda e: e["at"])
    expiring = expiring[:MAX_EXPIRING]

    ready = sum(1 for it in items if it["status"] == "ready")
    waiting = sum(1 for it in items if it["status"] in ("pending", "analyzing"))
    with_actions = sum(1 for it in items if it["open_actions"] > 0)
    failed = sum(1 for it in items if it["status"] == "failed")

    # Only counts a person can check against the list beside them.
    summary: List[Dict[str, Any]] = []
    if items:
        summary.append({"label": "Tutti i documenti", "value": len(items), "icon": "all"})
    if ready:
        summary.append({"label": "Analizzati da ORA", "value": ready, "icon": "ready"})
    if waiting:
        summary.append({"label": "In attesa di analisi", "value": waiting, "icon": "waiting"})
    if expiring:
        summary.append({"label": "In scadenza", "value": len(expiring), "icon": "expiring"})
    if with_actions:
        summary.append({"label": "Con azioni suggerite", "value": with_actions, "icon": "actions"})
    if failed:
        summary.append({"label": "Non analizzati", "value": failed, "icon": "failed"})

    # The filter options are the ones the data can actually satisfy, so no
    # control on this page can ever return an empty list by construction.
    kinds = sorted({it["kind"] for it in items})

    return {
        "ok": True,
        "items": items,
        "expiring": expiring,
        "summary": summary,
        "kinds": kinds,
        "partial": bool(partial),
        "partial_sources": partial,
        "generated_at": now.isoformat(),
    }
