"""Documents generator — education doc → flashcards if study goal / education linked."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from proactive_engine.dedupe import make_dedupe_key, window_label
from proactive_engine.models import SuggestionAction, SuggestionCandidate


def _parse(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _is_education(doc: dict) -> bool:
    dtype = (doc.get("doc_type") or doc.get("type") or "").lower()
    cat = (doc.get("category") or "").lower()
    intel = doc.get("intelligence") or doc.get("analysis") or {}
    if isinstance(intel, dict):
        if intel.get("is_study") or intel.get("education"):
            return True
        domain = (intel.get("domain") or intel.get("doc_domain") or "").lower()
        if domain in ("education", "study", "school", "university"):
            return True
    if dtype in ("education", "study", "notes", "slide", "textbook"):
        return True
    if cat in ("education", "study"):
        return True
    tags = doc.get("tags") or []
    if any(str(t).lower() in ("education", "study", "esame", "appunti") for t in tags):
        return True
    return False


async def generate_document_candidates(
    db, user_id: str, *, now: Optional[datetime] = None,
) -> List[SuggestionCandidate]:
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=14)).isoformat()
    docs = await db.documents.find(
        {
            "user_id": user_id,
            "$or": [
                {"created_at": {"$gte": since}},
                {"uploaded_at": {"$gte": since}},
                {"updated_at": {"$gte": since}},
            ],
        },
        {"_id": 0},
    ).sort("created_at", -1).to_list(60)

    goals = await db.goals.find(
        {
            "user_id": user_id,
            "goal_type": {"$in": ["study", "education"]},
            "status": {"$nin": ["cancelled", "archived", "merged", "completed"]},
        },
        {"_id": 0},
    ).to_list(40)
    study_goals = goals
    linked_doc_ids = set()
    for g in study_goals:
        for did in g.get("linked_documents") or []:
            linked_doc_ids.add(str(did))

    plans = await db.study_plans.find(
        {"user_id": user_id, "status": {"$in": ["active", "paused"]}},
        {"_id": 0},
    ).to_list(40)
    plan_doc_ids = set()
    for p in plans:
        for did in p.get("document_ids") or []:
            plan_doc_ids.add(str(did))

    out: List[SuggestionCandidate] = []
    win = window_label(now, 48)

    for doc in docs:
        doc_id = str(doc.get("id") or "")
        if not doc_id:
            continue
        if not _is_education(doc):
            continue

        has_flash = bool(doc.get("flashcards")) or bool(
            (doc.get("analysis") or {}).get("flashcards")
        )
        if has_flash:
            continue

        linked = doc_id in linked_doc_ids or doc_id in plan_doc_ids
        # Only suggest when linked to study goal/plan OR explicitly education with active study goal
        if not linked and not study_goals:
            continue
        if not linked and study_goals:
            # soft: education doc + active study goal exists → still grounded enough
            pass

        goal = None
        for g in study_goals:
            if doc_id in [str(x) for x in (g.get("linked_documents") or [])]:
                goal = g
                break
        if goal is None and study_goals:
            goal = study_goals[0]

        title_doc = doc.get("title") or doc.get("filename") or "documento"
        exam = (goal or {}).get("title") or "studio"
        title = f"Crea flashcard da «{title_doc}»"
        desc = (
            f"Hai caricato un documento didattico collegato a {exam}. "
            "Le flashcard aiutano a ripassare senza rileggere tutto."
        )

        out.append(SuggestionCandidate(
            title=title,
            description=desc,
            reason="Documento education senza flashcard + obiettivo studio",
            type="documents",
            source="document",
            goal_id=(goal or {}).get("id"),
            document_id=doc_id,
            study_plan_id=(goal or {}).get("study_plan_id"),
            action=SuggestionAction(
                kind="flashcards",
                label="Genera flashcard",
                route=f"/document/{doc_id}",
                params={"mode": "flashcards", "document_id": doc_id},
            ),
            dedupe_key=make_dedupe_key(
                suggestion_type="documents",
                source="document",
                goal_id=(goal or {}).get("id"),
                action_kind="flashcards",
                entity_id=doc_id,
                window=win,
            ),
            expires_at=(now + timedelta(hours=72)).isoformat(),
            importance_hint=0.62,
            urgency_hint=0.5,
            confidence=0.78 if linked else 0.65,
            evidence={
                "document_id": doc_id,
                "is_education": True,
                "linked_to_study": linked,
                "goal_id": (goal or {}).get("id"),
            },
            meta={"document_title": title_doc},
        ))
        if len(out) >= 3:
            break
    return out
