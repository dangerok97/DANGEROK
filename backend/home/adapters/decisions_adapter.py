from __future__ import annotations

from typing import List, Tuple

from home.models import ConnectionWarning, HomeItem

from ._util import now_iso, stable_id


_TYPE_MAP = {
    "bill": "bill",
    "travel": "travel",
    "travel_prep": "travel",
    "exam": "study",
    "study": "study",
    "fitness": "activity",
    "leisure": "activity",
    "hobby": "activity",
    "work_deadline": "activity",
    "event": "event",
    "medical": "visit",
}

_INTENT_HOME = {
    "study": "study",
    "travel": "travel",
    "event": "event",
    "medical": "visit",
    "payment": "bill",
    "financial": "payment",
    "administrative": "generic",
    "document_review": "needs_review",
    "task": "activity",
    "communication": "reply",
    "shopping": "activity",
    "project": "activity",
    "generic": "generic",
}


def _resolve_type(d: dict) -> tuple[str, str | None]:
    """Prefer persisted Intent over legacy category for Home labels."""
    intent = d.get("intent")
    subtype = d.get("intent_subtype")
    conf = float(d.get("intent_confidence") or 0)
    if intent and conf >= 0.55 and not (d.get("metadata") or {}).get("needs_clarify"):
        return _INTENT_HOME.get(str(intent), "generic"), subtype or str(intent)

    # Classify on the fly for legacy decisions without Intent
    title = d.get("title") or ""
    if title and (not intent or conf < 0.55):
        try:
            from intent_engine import classify_text
            ir = classify_text(title, description=d.get("description"))
            if not ir.needs_clarify and ir.confidence >= 0.62:
                # Best-effort persist for next load
                return _INTENT_HOME.get(ir.intent, "generic"), ir.subtype or ir.intent
        except Exception:
            pass

    cat = d.get("category") or "generic"
    return _TYPE_MAP.get(cat, "generic"), cat


async def load_decisions(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    """Include real user decisions; skip demo seed origins for non-demo users."""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1})
    is_demo = (user or {}).get("email") == "demo@ora.app"

    cur = db.decisions.find(
        {"user_id": user_id, "status": {"$in": ["open", "in_progress", "partially_completed", "postponed"]}},
        {"_id": 0},
    ).limit(40)
    docs = await cur.to_list(40)
    items: List[HomeItem] = []
    for d in docs:
        origin = d.get("origin") or ""
        if not is_demo and str(origin).startswith("seed"):
            continue
        itype, subtype = _resolve_type(d)
        st = d.get("status") or "open"
        intent = d.get("intent")
        # If still unresolved, classify now and attach to meta for AE
        dmeta = d.get("metadata") or {}
        intent_meta = {
            "dedupe_key": f"dec:{d.get('id')}",
            "decision_status": st,
            "origin": origin,
            "study_plan_id": dmeta.get("study_plan_id") or d.get("study_plan_id"),
            "travel_project_id": dmeta.get("travel_project_id") or d.get("travel_project_id"),
            "action_session_id": dmeta.get("action_session_id") or d.get("action_session_id"),
            "project_id": dmeta.get("project_id") or d.get("project_id"),
            "goal_id": dmeta.get("goal_id") or d.get("goal_id"),
        }
        if intent:
            intent_meta["intent"] = intent
            intent_meta["intent_subtype"] = d.get("intent_subtype")
            intent_meta["intent_confidence"] = d.get("intent_confidence")
            intent_meta["intent_entities"] = d.get("intent_entities") or {}
            intent_meta["classified_intent"] = {
                "intent": intent,
                "subtype": d.get("intent_subtype"),
                "confidence": d.get("intent_confidence") or 0.9,
                "entities": d.get("intent_entities") or {},
                "needs_clarify": False,
                "reason": d.get("intent_reason") or "persisted",
            }
        else:
            try:
                from intent_engine import classify_text
                ir = classify_text(d.get("title") or "", description=d.get("description"))
                intent_meta["classified_intent"] = ir.public()
                intent_meta["intent"] = ir.intent
                intent_meta["intent_subtype"] = ir.subtype
                intent_meta["intent_confidence"] = ir.confidence
                intent_meta["intent_entities"] = ir.entities.as_dict()
                if not ir.needs_clarify and ir.confidence >= 0.62:
                    itype = _INTENT_HOME.get(ir.intent, itype)
                    subtype = ir.subtype or subtype
            except Exception:
                pass

        items.append(HomeItem(
            id=stable_id("dec", user_id, d.get("id", "")),
            type=itype,  # type: ignore[arg-type]
            subtype=subtype if isinstance(subtype, str) else None,
            title=d.get("title") or "Decisione",
            description=d.get("description"),
            source_type="decision",
            source_id=d.get("id") or "",
            due_at=d.get("deadline"),
            start_at=d.get("starts_at"),
            duration_minutes=d.get("time_required_min"),
            location=d.get("place"),
            status="waiting" if st == "postponed" else "open",
            confidence=float(d.get("intent_confidence") or 0.75),
            created_at=d.get("created_at") or now_iso(),
            updated_at=d.get("updated_at") or now_iso(),
            meta=intent_meta,
        ))
    return items, []
