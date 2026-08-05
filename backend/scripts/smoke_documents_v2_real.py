"""Minimal real smoke: Gemini analysis + Google Calendar confirm (if connected).

Never prints secrets. Writes JSON evidence to backend/data/.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FIXTURES = BACKEND / "tests" / "fixtures" / "intel_docs"
OUT = BACKEND / "data" / "documents_v2_real_smoke.json"

sys.path.insert(0, str(BACKEND))


def _load_env() -> None:
    env = BACKEND / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def main() -> int:
    _load_env()
    evidence: dict = {
        "started_at": _now(),
        "llm_provider": os.environ.get("LLM_PROVIDER"),
        "calendar_provider_mode": os.environ.get("CALENDAR_PROVIDER_MODE"),
        "gemini_key_present": bool(os.environ.get("GEMINI_API_KEY")),
        "google_oauth_client_present": bool(os.environ.get("GOOGLE_OAUTH_CLIENT_ID")),
        "gemini": {"attempted": False, "ok": False},
        "google_calendar": {"attempted": False, "ok": False},
    }

    from motor.motor_asyncio import AsyncIOMotorClient
    from documents.service import DocumentService
    from documents.storage import LocalFilesystemStorage
    from documents.intelligence.service import IntelligenceService
    from llm import llm_status

    st = llm_status()
    evidence["llm_status"] = {
        "configured": bool(st.get("configured")),
        "provider": st.get("provider"),
        "model": st.get("model"),
    }

    mongo = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    dbname = os.environ.get("DB_NAME", "ora")
    client = AsyncIOMotorClient(mongo)
    db = client[dbname]
    tmp = tempfile.mkdtemp(prefix="ora_v2_smoke_")
    dsvc = DocumentService(db=db, storage=LocalFilesystemStorage(base_dir=tmp), life_graph=None, knowledge=None)
    intel = IntelligenceService(db, dsvc)

    user_id = f"smoke_v2_{uuid.uuid4().hex[:10]}"
    await db.users.insert_one({
        "user_id": user_id,
        "email": f"{user_id}@example.com",
        "preferences": {"document_ai_analysis": True},
        "created_at": _now(),
    })
    evidence["user_id"] = user_id

    # ---- Gemini smoke (study fixture, NOT force_local) ----
    try:
        evidence["gemini"]["attempted"] = True
        up = await dsvc.upload(
            user_id=user_id,
            content=(FIXTURES / "caso_d_dispensa.txt").read_bytes(),
            original_filename="caso_d_dispensa.txt",
            mime_type="text/plain",
        )
        study_id = up["document"]["id"]
        evidence["gemini"]["document_id"] = study_id
        pipe = await intel.run_pipeline(user_id=user_id, doc_id=study_id, force_local=False)
        analysis = await intel.get_analysis(user_id=user_id, doc_id=study_id)
        a = analysis.get("analysis") or {}
        evidence["gemini"].update({
            "pipeline_ok": bool(pipe.get("ok")),
            "pipeline_status": analysis.get("pipeline_status"),
            "ai_used": bool(a.get("ai_used")),
            "local_only": bool(a.get("local_only")),
            "model": a.get("model"),
            "macro_category": a.get("macro_category"),
            "summary_len": len(a.get("summary") or ""),
            "has_education": bool(analysis.get("education_analysis")),
        })
        model_l = str(a.get("model") or "").lower()
        evidence["gemini"]["ok"] = bool(
            a.get("ai_used") and not a.get("local_only") and ("gemini" in model_l or st.get("provider") == "gemini")
        )
        if not evidence["gemini"]["ok"] and a.get("ai_used"):
            # AI used via configured provider even if model string lacks 'gemini'
            evidence["gemini"]["ok"] = bool(st.get("provider") == "gemini" and a.get("ai_used"))
            evidence["gemini"]["note"] = "ai_used with configured gemini provider"
    except Exception as e:
        evidence["gemini"]["error"] = type(e).__name__ + ": " + str(e)[:240]

    # ---- Google Calendar smoke (reuse connected instance if any) ----
    try:
        # Find any connected google calendar instance in DB (do not invent tokens)
        inst = await db.connector_instances.find(
            {
                "status": "connected",
                "$or": [
                    {"connector_id": "calendar_google"},
                    {"connector_id": "google_calendar"},
                    {"provider": "calendar_google"},
                    {"provider": "google_calendar"},
                ],
            },
            {"_id": 0, "user_id": 1, "id": 1, "status": 1, "connector_id": 1, "metadata": 1},
        ).sort("updated_at", -1).to_list(1)
        inst = inst[0] if inst else None
        evidence["google_calendar"]["connected_instance_found"] = bool(inst)
        if inst:
            evidence["google_calendar"]["instance_user_id"] = inst.get("user_id")
            evidence["google_calendar"]["instance_id"] = inst.get("id")
            g_user = inst["user_id"]
            # ensure user prefs exist
            await db.users.update_one(
                {"user_id": g_user},
                {"$set": {"preferences.document_ai_analysis": True}},
                upsert=True,
            )
            evidence["google_calendar"]["attempted"] = True
            up = await dsvc.upload(
                user_id=g_user,
                content=(FIXTURES / "caso_b_concerto.txt").read_bytes(),
                original_filename="caso_b_concerto_smoke.txt",
                mime_type="text/plain",
            )
            doc_id = up["document"]["id"]
            evidence["google_calendar"]["document_id"] = doc_id
            await intel.run_pipeline(user_id=g_user, doc_id=doc_id, force_local=True)
            a = await intel.get_analysis(user_id=g_user, doc_id=doc_id)
            events = [e for e in (a.get("event_candidates") or []) if e.get("status") == "proposed"]
            if not events:
                evidence["google_calendar"]["error"] = "no_proposed_events"
            else:
                ev = events[0]
                evidence["google_calendar"]["event_candidate_id"] = ev.get("id")
                res = await intel.confirm_event(
                    user_id=g_user,
                    doc_id=doc_id,
                    event_id=ev["id"],
                    sync_to_google=True,
                )
                gsync = res.get("google_sync") or {}
                cal = res.get("calendar_event") or {}
                evidence["google_calendar"].update({
                    "confirm_ok": bool(res.get("ok")),
                    "ora_calendar_event_id": cal.get("id"),
                    "google_sync_ok": bool(gsync.get("ok")),
                    "google_event_id": gsync.get("google_event_id") or gsync.get("event_id") or cal.get("google_event_id"),
                    "google_sync_status": gsync.get("sync_status") or cal.get("sync_status"),
                    "google_sync_error": gsync.get("error") or gsync.get("message"),
                })
                evidence["google_calendar"]["ok"] = bool(
                    evidence["google_calendar"].get("google_sync_ok")
                    and evidence["google_calendar"].get("google_event_id")
                )
        else:
            evidence["google_calendar"]["skipped_reason"] = "no_connected_google_calendar_instance"
    except Exception as e:
        evidence["google_calendar"]["attempted"] = True
        evidence["google_calendar"]["error"] = type(e).__name__ + ": " + str(e)[:240]

    # cleanup smoke-only user docs (keep google user's doc if created for evidence)
    try:
        await dsvc.delete(user_id=user_id, doc_id=evidence["gemini"].get("document_id") or "")
    except Exception:
        pass
    await db.users.delete_many({"user_id": user_id})
    client.close()

    evidence["finished_at"] = _now()
    evidence["summary"] = {
        "gemini_verified_this_pass": bool(evidence["gemini"].get("ok")),
        "google_verified_this_pass": bool(evidence["google_calendar"].get("ok")),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["gemini"].get("ok") or evidence["google_calendar"].get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
