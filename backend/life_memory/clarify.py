"""Memory clarification loop — Gemini interprets; governance writes Profile.

USER LANGUAGE → GEMINI → VALIDATED PROPOSAL → GOVERNANCE → PROFILE → MEMORY RECOMPUTE
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from life_memory.gemini_clarify import (
    deterministic_clarify_question,
    generate_clarify_question,
    heuristic_resolve,
    interpret_clarify_answer,
    validate_resolution,
)
from life_memory.models import (
    ClarificationSession,
    GeminiClarifyResolution,
    MemoryItem,
    now_iso,
)
from life_memory.service import LifeMemoryService

logger = logging.getLogger("ora.life_memory.clarify")

CLARIFY_COLLECTION = "life_memory_clarifications"


def new_clarify_id() -> str:
    return f"lmc_{uuid.uuid4().hex[:14]}"


class ClarificationService:
    def __init__(self, db, memory_svc: Optional[LifeMemoryService] = None):
        self.db = db
        self.memory = memory_svc or LifeMemoryService(db)

    async def ensure_indexes(self) -> None:
        await self.db[CLARIFY_COLLECTION].create_index("id", unique=True)
        await self.db[CLARIFY_COLLECTION].create_index([("user_id", 1), ("created_at", -1)])

    async def _save(self, sess: ClarificationSession) -> None:
        sess.updated_at = now_iso()
        await self.db[CLARIFY_COLLECTION].update_one(
            {"id": sess.id},
            {"$set": sess.model_dump()},
            upsert=True,
        )

    async def get(self, user_id: str, session_id: str) -> Optional[ClarificationSession]:
        doc = await self.db[CLARIFY_COLLECTION].find_one(
            {"id": session_id, "user_id": user_id}, {"_id": 0}
        )
        if not doc:
            return None
        return ClarificationSession.model_validate(doc)

    async def _find_memory(self, user_id: str, memory_id: str) -> Optional[MemoryItem]:
        resp = await self.memory.get_life_memory(user_id, force_refresh=True, enrich=False)
        for m in resp.memories:
            if m.id == memory_id:
                return m
        return None

    async def _link_conversation(
        self, user_id: str, sess: ClarificationSession
    ) -> Optional[str]:
        """Create a CE session for continuity (non-AE). Soft-fail."""
        try:
            from conversation_engine.models import ConversationSession
            from conversation_engine.repository import ConversationRepository

            ces = ConversationSession(
                user_id=user_id,
                origin="memoria",  # type: ignore[arg-type]
                input=sess.belief_statement,
                status="waiting_user",
                summary="Chiarimento memoria",
                meta={
                    "ui_mode": "memory_clarify",
                    "memory_clarify_id": sess.id,
                    "memory_id": sess.memory_id,
                },
            )
            ces.append_history(
                role="assistant",
                kind="question",
                text=sess.question,
                meta={"memory_clarify": True},
            )
            await ConversationRepository(self.db).insert(ces)
            return ces.id
        except Exception as e:
            logger.info("clarify CE link soft-fail: %s", type(e).__name__)
            return None

    async def start(self, user_id: str, memory_id: str) -> Dict[str, Any]:
        item = await self._find_memory(user_id, memory_id)
        if not item:
            return {"ok": False, "error": "memory_not_found"}
        # Known / strong-authority facts must never open clarification
        if item.status == "known" or not item.clarifiable:
            return {"ok": False, "error": "not_clarifiable"}
        if not item.profile_targets:
            return {"ok": False, "error": "no_profile_target"}

        sess = ClarificationSession(
            id=new_clarify_id(),
            user_id=user_id,
            memory_id=item.id,
            slot=item.slot,
            belief_statement=item.belief_statement or item.statement,
            status_before=item.status,
            candidate_values=list(item.candidate_values or []),
            evidence_refs=list(item.evidence_refs or []),
            source_refs=list(item.source_refs or []),
            provenance_label=item.provenance_label,
            profile_targets=list(item.profile_targets or []),
            clarification_goal=item.clarification_goal
            or ClarificationSession.model_fields["clarification_goal"].default,
        )

        question = await generate_clarify_question(sess)
        if not question:
            question = deterministic_clarify_question(sess)
        sess.question = question

        ces_id = await self._link_conversation(user_id, sess)
        sess.conversation_session_id = ces_id
        await self._save(sess)

        pub = sess.public()
        return {"ok": True, "session": pub, "route": pub["route"]}

    async def answer(
        self, user_id: str, session_id: str, text: str
    ) -> Dict[str, Any]:
        sess = await self.get(user_id, session_id)
        if not sess:
            return {"ok": False, "error": "session_not_found"}
        if sess.state != "awaiting_answer":
            return {"ok": False, "error": "session_not_open", "session": sess.public()}

        user_text = " ".join((text or "").split()).strip()
        if not user_text:
            return {"ok": False, "error": "text_required"}

        sess.user_answer = user_text
        gemini_used = True
        raw = await interpret_clarify_answer(sess, user_text=user_text)
        if raw is None:
            gemini_used = False
            raw = heuristic_resolve(sess, user_text=user_text)

        validated = validate_resolution(sess, raw)

        # Gemini down + free text → do not mutate truth
        if (
            not gemini_used
            and validated.resolution == "still_ambiguous"
            and validated.evidence_interpretation == "gemini_unavailable_free_text"
        ):
            sess.state = "awaiting_answer"
            sess.resolution = "still_ambiguous"
            await self._save(sess)
            return {
                "ok": False,
                "error": "gemini_unavailable",
                "message": "Non riesco a interpretare la risposta adesso. Riprova tra poco.",
                "session": sess.public(),
                "memory": None,
            }

        if validated.needs_followup and validated.followup_question:
            sess.question = validated.followup_question
            sess.state = "awaiting_answer"
            sess.resolution = "still_ambiguous"
            await self._save(sess)
            pub = sess.public()
            pub["needs_followup"] = True
            pub["followup_question"] = validated.followup_question
            pub["question"] = validated.followup_question
            return {
                "ok": True,
                "session": pub,
                "resolution": "still_ambiguous",
                "needs_followup": True,
                "memory": None,
            }

        applied = await self._apply_governance(user_id, sess, validated)
        sess.applied = applied
        sess.resolution = validated.resolution
        sess.state = "completed" if validated.resolution != "failed" else "failed"
        await self._save(sess)

        # Invalidate wording cache + recompute memory
        await self.memory.invalidate_cache(user_id)
        memory_resp = await self.memory.get_life_memory(
            user_id, force_refresh=True, enrich=False
        )

        # Append CE history soft
        await self._append_ce_answer(sess, user_text)

        return {
            "ok": True,
            "session": sess.public(),
            "resolution": validated.resolution,
            "applied": applied,
            "gemini": gemini_used,
            "memory": memory_resp.model_dump(),
        }

    async def _append_ce_answer(self, sess: ClarificationSession, text: str) -> None:
        if not sess.conversation_session_id:
            return
        try:
            from conversation_engine.repository import ConversationRepository

            repo = ConversationRepository(self.db)
            ces = await repo.get(sess.user_id, sess.conversation_session_id)
            if not ces:
                return
            ces.append_history(role="user", kind="answer", text=text)
            ces.status = "completed" if sess.state == "completed" else ces.status
            ces.meta["memory_clarify_resolution"] = sess.resolution
            await repo.replace(ces)
        except Exception as e:
            logger.info("clarify CE append soft-fail: %s", type(e).__name__)

    async def _apply_governance(
        self,
        user_id: str,
        sess: ClarificationSession,
        resolution: GeminiClarifyResolution,
    ) -> List[Dict[str, Any]]:
        from life_setup.profile_service import LifeProfileService

        ps = LifeProfileService(self.db)
        applied: List[Dict[str, Any]] = []
        allowed = {(t.domain, t.key) for t in sess.profile_targets}

        for fact in resolution.proposed_facts or []:
            if (fact.domain, fact.key) not in allowed:
                continue
            try:
                value = fact.value
                if value is None and sess.candidate_values:
                    value = sess.candidate_values[0]
                if value is None:
                    await ps.confirm_field(user_id, fact.domain, fact.key)
                else:
                    # User clarification is authoritative → corrected/known
                    await ps.correct_fact(user_id, fact.domain, fact.key, value)
                applied.append(
                    {
                        "domain": fact.domain,
                        "key": fact.key,
                        "action": fact.action,
                        "value": value,
                    }
                )
            except Exception as e:
                logger.info("clarify apply soft-fail: %s", type(e).__name__)

        # Additional facts — suggest only (not known)
        for fact in resolution.additional_facts or []:
            try:
                await ps.apply_facts(
                    user_id,
                    {fact.key: fact.value},
                    source="inferred",
                    domain_hint=fact.domain,
                )
                applied.append(
                    {
                        "domain": fact.domain,
                        "key": fact.key,
                        "action": "suggest",
                        "value": fact.value,
                    }
                )
            except Exception as e:
                logger.info("clarify additional soft-fail: %s", type(e).__name__)

        return applied


def get_clarification_service(db=None) -> ClarificationService:
    if db is None:
        from deps import db as _db

        db = _db
    return ClarificationService(db)
