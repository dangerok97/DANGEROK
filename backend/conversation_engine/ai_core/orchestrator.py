"""AI Core orchestrator — session lifecycle for the cognitive loop."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from conversation_engine.ai_core.loop import DecisionFn, run_cognitive_loop
from conversation_engine.ai_core import state as state_mod
from conversation_engine.models import ConversationSession, new_session_id, now_iso
from conversation_engine.repository import ConversationRepository

logger = logging.getLogger("ora.ai_core.orchestrator")


class AICoreOrchestrator:
    def __init__(self, db, *, decision_fn: Optional[DecisionFn] = None):
        self.db = db
        self.repo = ConversationRepository(db)
        self.decision_fn = decision_fn

    async def start(
        self,
        user_id: str,
        *,
        text: str,
        origin: str = "text",
        entry_point: Optional[str] = None,
        plan_id: Optional[str] = None,
        object_id: Optional[str] = None,
        attachments: Optional[list] = None,
    ) -> Dict[str, Any]:
        text = (text or "").strip()
        attachments = list(attachments or [])
        if not text and not attachments:
            return {"ok": False, "error": "text_required"}

        ep = (entry_point or origin or "text").strip()[:40]
        sess = ConversationSession(
            id=new_session_id(),
            user_id=user_id,
            origin=origin if origin in (
                "home", "voice", "text", "documents", "notifications",
                "proactive", "life_setup", "memoria",
            ) else "text",
            input=text or "[attachment]",
            status="waiting_user",
            engine_version="ai-core-1.0",
            meta={
                "ui_mode": "ai_core",
                "ai_core": {},
                "entry_point": ep,
            },
        )
        # Soft-bind opaque Life OS refs on in-memory session (ownership enforced on later bind/get)
        if plan_id or object_id:
            st = state_mod.get_ai_state(sess)
            if plan_id:
                st["active_plan_id"] = str(plan_id)[:64]
            if object_id:
                st["active_object_ref"] = {
                    "id": str(object_id)[:64],
                    "source": "entry_bind",
                }
            state_mod.save_ai_state(sess, st)

        # Persist session early so ContextFile can bind ownership-scoped refs
        await self.repo.insert(sess)

        bound: list = []
        if attachments:
            try:
                from conversation_engine.ai_core.files.service import ContextFileService

                bound = await ContextFileService(self.db).bind_message_attachments(
                    sess, attachments
                )
            except Exception:
                logger.exception("start bind attachments soft-fail")

        user_msg = text
        if not user_msg and bound:
            names = ", ".join(
                (b.get("name") or b.get("file_id") or "file")[:60] for b in bound[:3]
            )
            user_msg = f"[Allegato: {names}]"
        sess.append_history(
            role="user",
            kind="start",
            text=(text or user_msg)[:400],
            meta={"attachments": bound} if bound else None,
        )
        result = await run_cognitive_loop(
            sess=sess,
            user_message=user_msg,
            db=self.db,
            decision_fn=self.decision_fn,
        )
        sess.append_history(role="ora", kind=result.mode, text=result.ora_text[:400])
        sess.summary = (result.active_goal.summary if result.active_goal else "") or user_msg[:120]
        sess.status = "waiting_user"
        # Observability (no PII)
        meta = dict(sess.meta or {})
        meta["entry_point"] = ep
        meta["session_created"] = True
        meta["had_plan_ref"] = bool(plan_id)
        meta["had_object_ref"] = bool(object_id)
        meta["had_attachments"] = bool(bound)
        sess.meta = meta
        await self.repo.replace(sess)
        # Authoritative ownership bind after persist (plan/object must belong to user)
        if plan_id or object_id:
            try:
                from life_os.service import LifeOsService

                await LifeOsService(self.db).bind_session_object_focus(
                    user_id,
                    session_id=sess.id,
                    object_id=object_id,
                    plan_id=plan_id,
                    event_type="entry_bind",
                )
            except Exception:
                logger.debug("post-insert entry bind soft-fail", exc_info=True)
        out = self._public(sess, result)
        if bound:
            out["attachments"] = bound
        return out

    async def message(
        self,
        user_id: str,
        session_id: str,
        *,
        text: str,
        attachments: Optional[list] = None,
    ) -> Dict[str, Any]:
        text = (text or "").strip()
        attachments = list(attachments or [])
        if not text and not attachments:
            return {"ok": False, "error": "text_required"}
        sess = await self.repo.get(user_id, session_id)
        if not sess:
            return {"ok": False, "error": "not_found"}
        if sess.status in ("completed", "cancelled"):
            return {"ok": False, "error": "session_closed"}

        # Bind attachments before cognition (ownership enforced)
        bound: list = []
        if attachments:
            try:
                from conversation_engine.ai_core.files.service import ContextFileService

                bound = await ContextFileService(self.db).bind_message_attachments(
                    sess, attachments
                )
            except Exception:
                logger.exception("bind attachments soft-fail")
                bound = []

        user_msg = text
        if not user_msg and bound:
            names = ", ".join(
                (b.get("name") or b.get("file_id") or "file")[:60] for b in bound[:3]
            )
            user_msg = f"[Allegato: {names}]"
        hist_meta = {"attachments": bound} if bound else None
        if hist_meta:
            sess.append_history(
                role="user", kind="answer", text=(text or user_msg)[:400], meta=hist_meta
            )
        else:
            sess.append_history(role="user", kind="answer", text=user_msg[:400])

        result = await run_cognitive_loop(
            sess=sess,
            user_message=user_msg,
            db=self.db,
            decision_fn=self.decision_fn,
        )
        # Memory candidates stay proposals — never auto-promote
        if result.memory_candidates:
            st = state_mod.get_ai_state(sess)
            pending = list(st.get("memory_candidates_pending") or [])
            pending.extend([m.model_dump() for m in result.memory_candidates])
            st["memory_candidates_pending"] = pending[-20:]
            state_mod.save_ai_state(sess, st)

        sess.append_history(role="ora", kind=result.mode, text=result.ora_text[:400])
        sess.status = "waiting_user"
        await self.repo.replace(sess)
        out = self._public(sess, result)
        if bound:
            out["attachments"] = bound
        return out

    async def get(self, user_id: str, session_id: str) -> Dict[str, Any]:
        sess = await self.repo.get(user_id, session_id)
        if not sess:
            return {"ok": False, "error": "not_found"}
        st = state_mod.get_ai_state(sess)
        last = None
        for h in reversed(sess.history or []):
            if h.role == "ora" and h.text:
                last = h.text
                break
        return {
            "ok": True,
            "session_id": sess.id,
            "ora_text": last or "",
            "active_goal": st.get("active_goal"),
            "active_plan_id": st.get("active_plan_id"),
            "active_goal_id": st.get("active_goal_id"),
            "artifact_ids": list(st.get("artifact_ids") or [])[-12:],
            "history": [
                {"role": h.role, "text": h.text, "kind": h.kind}
                for h in (sess.history or [])[-40:]
            ],
            "ui_mode": "ai_core",
            "route": f"/ora/{sess.id}",
            "entry_point": (sess.meta or {}).get("entry_point"),
        }

    def _public(self, sess: ConversationSession, result) -> Dict[str, Any]:
        return {
            "ok": True,
            "session_id": sess.id,
            "ora_text": result.ora_text,
            "question": result.question,
            "mode": result.mode,
            "active_goal": result.active_goal.model_dump() if result.active_goal else None,
            "memory_candidates": [m.model_dump() for m in result.memory_candidates],
            "ui_mode": "ai_core",
            "route": f"/ora/{sess.id}",
            "entry_point": (sess.meta or {}).get("entry_point"),
            "ai_calls": result.ai_calls,
            "tool_calls": result.tool_calls,
            "context_calls": result.context_calls,
            "external_queries": getattr(result, "external_queries", 0) or 0,
            "elapsed_ms": result.elapsed_ms,
            "sources": list(getattr(result, "sources", None) or [])[:5],
            "working_hint": getattr(result, "working_hint", None),
            "trace": result.trace,
            "error": result.error,
            "history": [
                {"role": h.role, "text": h.text, "kind": h.kind}
                for h in (sess.history or [])[-40:]
            ],
        }
