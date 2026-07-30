"""CONTEXT ASSEMBLER router."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from context_assembler import ASSEMBLER_VERSION
from deps import context_asm, db, get_current_user

router = APIRouter(prefix="/context", tags=["context"])


@router.post("/decisions/{decision_id}/assemble")
async def context_assemble(decision_id: str, user=Depends(get_current_user)):
    snap = await context_asm.assemble(user["user_id"], decision_id, force=False)
    if snap is None:
        raise HTTPException(status_code=404, detail="Decision non trovata")
    return snap


@router.post("/decisions/{decision_id}/refresh")
async def context_refresh(decision_id: str, user=Depends(get_current_user)):
    snap = await context_asm.refresh(user["user_id"], decision_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Decision non trovata")
    return snap


@router.get("/decisions/{decision_id}/latest")
async def context_latest(decision_id: str, user=Depends(get_current_user)):
    """Uniform envelope response.

    Returns strictly:
        { "snapshot": ContextSnapshot | null,
          "status":   "available" | "not_found",
          "generated_at": iso_datetime | null,
          "assembler_version": str }

    - 404 → the Decision does NOT belong to the user (hard error).
    - 200 + status="not_found" → the Decision exists but no snapshot has been
      assembled yet (soft, expected state).
    """
    d = await db.decisions.find_one(
        {"id": decision_id, "user_id": user["user_id"]},
        {"_id": 0, "id": 1},
    )
    if not d:
        raise HTTPException(status_code=404, detail="Decision non trovata")
    snap = await context_asm.latest(user["user_id"], decision_id)
    if not snap:
        return {
            "snapshot": None,
            "status": "not_found",
            "generated_at": None,
            "assembler_version": ASSEMBLER_VERSION,
        }
    return {
        "snapshot": snap,
        "status": "available",
        "generated_at": snap.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        "assembler_version": snap.get("assembler_version") or ASSEMBLER_VERSION,
    }


@router.get("/decisions/{decision_id}/history")
async def context_history(decision_id: str, limit: int = 20, user=Depends(get_current_user)):
    d = await db.decisions.find_one({"id": decision_id, "user_id": user["user_id"]}, {"_id": 0, "id": 1})
    if not d:
        raise HTTPException(status_code=404, detail="Decision non trovata")
    items = await context_asm.history(user["user_id"], decision_id, limit=limit)
    return {"items": items, "assembler_version": ASSEMBLER_VERSION}


@router.get("/snapshots/{snapshot_id}")
async def context_get(snapshot_id: str, user=Depends(get_current_user)):
    snap = await context_asm.get_snapshot(user["user_id"], snapshot_id)
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot non trovato")
    return snap
