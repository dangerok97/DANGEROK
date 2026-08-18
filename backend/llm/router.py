"""LLM Provider Manager HTTP API."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import db, get_current_user
from llm.manager import DEFAULT_PRIORITY, VALID_PROVIDERS, get_manager, set_runtime_preferred

router = APIRouter(prefix="/llm", tags=["llm"])


class LLMPreferenceIn(BaseModel):
    provider: Literal["gemini", "openai", "ollama", "emergent", "auto"] = Field(
        ..., description="Preferred provider or auto (priority order)"
    )


async def _user_pref(user_id: str) -> Optional[str]:
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "preferences": 1})
    prefs = (u or {}).get("preferences") or {}
    val = (prefs.get("llm_provider") or "").strip().lower()
    return val or None


@router.get("/providers")
async def list_providers(user=Depends(get_current_user)):
    pref = await _user_pref(user["user_id"])
    status = await get_manager().status(user_preference=pref)
    return {
        **status,
        "user_preference": pref or "auto",
        "note": "Fallback typed con stato runtime process-local; nessun health probe viene eseguito.",
        "default_priority": list(DEFAULT_PRIORITY),
    }


@router.get("/status")
async def llm_status_route(user=Depends(get_current_user)):
    return await list_providers(user)


@router.patch("/preferences")
async def patch_llm_preference(body: LLMPreferenceIn, user=Depends(get_current_user)):
    provider = body.provider
    if provider != "auto" and provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail="Provider non valido")
    store = None if provider == "auto" else provider
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"preferences.llm_provider": store}},
    )
    # Also set process runtime preferred for this instance (dev convenience)
    set_runtime_preferred(store)
    status = await get_manager().status(user_preference=store)
    return {
        "ok": True,
        "user_preference": provider,
        "active": status.get("active"),
        "providers": status.get("providers"),
        "fallback_chain": status.get("fallback_chain"),
    }
