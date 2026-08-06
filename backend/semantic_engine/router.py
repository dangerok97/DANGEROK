"""HTTP API: /api/semantic/*"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from deps import get_current_user, db
from semantic_engine.models import ConfirmEntityBody, ExtractBody, GapsBody, PatchEntitiesBody
from semantic_engine.service import get_semantic_engine

router = APIRouter(prefix="/semantic", tags=["semantic_engine"])
semantic_engine_router = router


@router.post("/extract")
async def semantic_extract(body: ExtractBody, user=Depends(get_current_user)):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text_required")
    eng = get_semantic_engine()
    pref = None
    try:
        pref = (user or {}).get("llm_preference") or (user or {}).get("ai_preference")
    except Exception:
        pass
    result = await eng.extract(
        text,
        intent=body.intent,
        flow=body.flow,
        confirmed_entities=body.confirmed_entities,
        prior_entities=body.prior_entities,
        context=body.context,
        use_gemini=body.use_gemini,
        user_preference=pref,
        timezone=body.timezone,
    )
    # Persist onto conversation session if provided
    if body.conversation_session_id:
        await _patch_conversation(
            user["user_id"],
            body.conversation_session_id,
            extracted=result.public(),
        )
    return {"ok": True, "extraction": result.public(), "user_id": user.get("user_id")}


@router.post("/gaps")
async def semantic_gaps(body: GapsBody, user=Depends(get_current_user)):
    eng = get_semantic_engine()
    pref = (user or {}).get("llm_preference")
    out = await eng.gaps(
        flow=body.flow,
        intent=body.intent,
        entities=body.entities,
        text=body.text,
        confirmed_entities=body.confirmed_entities,
        user_preference=pref,
        timezone=body.timezone,
    )
    return {**out, "user_id": user.get("user_id")}


@router.patch("/conversation/entities")
async def patch_conversation_entities(body: PatchEntitiesBody, user=Depends(get_current_user)):
    if not body.conversation_session_id:
        raise HTTPException(status_code=400, detail="conversation_session_id_required")
    eng = get_semantic_engine()
    sess = await db.conversation_sessions.find_one(
        {"id": body.conversation_session_id, "user_id": user["user_id"]},
        {"_id": 0},
    )
    if not sess:
        raise HTTPException(status_code=404, detail="session_not_found")
    entities = dict(sess.get("extracted_entities") or {})
    entities.update(body.entities or {})
    if body.corrections:
        for slot, val in body.corrections.items():
            patched = eng.correct_entity(entities, slot, val)
            entities = patched["entities"]
    confirmed = dict(sess.get("confirmed_entities") or {})
    if body.confirmed:
        confirmed.update(body.confirmed)
        for slot, val in body.confirmed.items():
            patched = eng.confirm_entity(entities, slot, val)
            entities = patched["entities"]
    await _patch_conversation(
        user["user_id"],
        body.conversation_session_id,
        extracted_entities=entities,
        confirmed_entities=confirmed,
    )
    return {"ok": True, "extracted_entities": entities, "confirmed_entities": confirmed}


@router.post("/confirm-entity")
async def confirm_entity(body: ConfirmEntityBody, user=Depends(get_current_user)):
    sess = await db.conversation_sessions.find_one(
        {"id": body.conversation_session_id, "user_id": user["user_id"]},
        {"_id": 0},
    )
    if not sess:
        raise HTTPException(status_code=404, detail="session_not_found")
    eng = get_semantic_engine()
    entities = dict(sess.get("extracted_entities") or {})
    patched = eng.confirm_entity(entities, body.slot, body.value)
    confirmed = dict(sess.get("confirmed_entities") or {})
    confirmed[body.slot] = body.value
    await _patch_conversation(
        user["user_id"],
        body.conversation_session_id,
        extracted_entities=patched["entities"],
        confirmed_entities=confirmed,
        known_slots=patched.get("known_slots"),
    )
    return {
        "ok": True,
        "slot": body.slot,
        "entities": patched["entities"],
        "confirmed_entities": confirmed,
        "known_slots": patched.get("known_slots"),
    }


async def _patch_conversation(user_id: str, session_id: str, **fields) -> None:
    from semantic_engine.models import EXTRACTION_VERSION, now_iso
    set_fields = {"updated_at": now_iso()}
    if "extracted" in fields:
        pub = fields.pop("extracted")
        set_fields["extracted_entities"] = pub.get("entities")
        set_fields["missing_slots"] = pub.get("missing_slots")
        set_fields["ambiguous_slots"] = pub.get("ambiguous_slots")
        set_fields["known_slots"] = pub.get("known_slots")
        set_fields["extraction_version"] = pub.get("extraction_version") or EXTRACTION_VERSION
        set_fields["last_extraction_at"] = pub.get("extracted_at") or now_iso()
        set_fields["meta.gap"] = {
            "next_slot": (pub.get("meta") or {}).get("next_slot"),
            "next_question": (pub.get("meta") or {}).get("next_question"),
            "reason_summary": pub.get("reason_summary"),
        }
    for k, v in fields.items():
        if v is not None:
            set_fields[k] = v
    if "extracted_entities" in set_fields and "extraction_version" not in set_fields:
        set_fields["extraction_version"] = EXTRACTION_VERSION
        set_fields["last_extraction_at"] = now_iso()
    await db.conversation_sessions.update_one(
        {"id": session_id, "user_id": user_id},
        {"$set": set_fields},
    )
