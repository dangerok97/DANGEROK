"""V2.8.3 governed learning: AI proposes; policy validates and persists."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from conversation_engine.ai_core.models import MemoryCandidate
from life_memory.models import now_iso

Decision = Literal[
    "PROMOTE", "CLARIFY", "REJECT", "SUPERSEDE", "FORGET_ALLOWED", "FORGET_DENIED"
]


@dataclass
class MemoryGovernanceOutcome:
    decision: Decision
    code: str
    memory_id: Optional[str] = None
    persisted: bool = False

    def public(self) -> Dict[str, Any]:
        payload = {
            "decision": self.decision,
            "code": self.code,
            "memory_id": self.memory_id,
            "persisted": self.persisted,
        }
        if self.code == "EXISTING_MEMORY_REQUIRES_RELATIONSHIP":
            payload["next_step"] = (
                "Decide the relationship to this exact owned memory_id. Emit operation=correct "
                "or supersede with existing_memory_ref, or explicitly cite it in "
                "coexists_with_refs. If the current user message already explicitly resolves "
                "that relationship as a correction/replacement, apply it now without a redundant "
                "confirmation question. Ask only when the relationship remains materially ambiguous. "
                "Do not merely answer and do not repeat an unqualified proposal."
            )
        elif self.decision == "CLARIFY":
            payload["next_step"] = (
                "Ask one natural confirmation question before durable learning."
            )
        return payload


class MemoryGovernanceService:
    MAX_CANDIDATES = 3

    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        await self.db.memories.create_index(
            [("user_id", 1), ("status", 1), ("updated_at", -1)]
        )
        await self.db.memories.create_index(
            [("user_id", 1), ("governance_key", 1)], unique=True, sparse=True
        )

    async def _owned(
        self, user_id: str, ref: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        if not ref:
            return None
        return await self.db.memories.find_one(
            {"user_id": user_id, "id": ref}, {"_id": 0}
        )

    async def evaluate(
        self, *, user_id: str, candidate: MemoryCandidate
    ) -> MemoryGovernanceOutcome:
        target = await self._owned(user_id, candidate.existing_memory_ref)
        if candidate.operation == "forget":
            if not candidate.existing_memory_ref or not target:
                return MemoryGovernanceOutcome("FORGET_DENIED", "TARGET_NOT_OWNED")
            return MemoryGovernanceOutcome(
                "FORGET_ALLOWED", "EXPLICIT_OWNED_TARGET", target["id"]
            )
        if candidate.operation in ("correct", "supersede"):
            if not candidate.existing_memory_ref or not target:
                return MemoryGovernanceOutcome("CLARIFY", "TARGET_REQUIRED")
        if candidate.operation == "propose" and (
            candidate.identity_key or candidate.kind
        ):
            identity_query: Dict[str, Any] = {
                "user_id": user_id,
                "status": "active",
            }
            if candidate.identity_key:
                identity_query["identity_key"] = candidate.identity_key
            else:
                identity_query["kind"] = candidate.kind
            existing = await self.db.memories.find_one(identity_query, {"_id": 0})
            if existing and existing.get("id") not in candidate.coexists_with_refs:
                return MemoryGovernanceOutcome(
                    "CLARIFY",
                    "EXISTING_MEMORY_REQUIRES_RELATIONSHIP",
                    existing.get("id"),
                )
        if candidate.authority == "device":
            return MemoryGovernanceOutcome("REJECT", "DEVICE_SIGNAL_NOT_DURABLE_MEMORY")
        if candidate.permanence == "temporary" or candidate.ends_at:
            return MemoryGovernanceOutcome(
                "REJECT", "TEMPORARY_CONTEXT_BELONGS_TO_SITUATION"
            )
        if (
            candidate.authority == "inferred"
            or candidate.epistemic_status == "inferred"
        ):
            return MemoryGovernanceOutcome("CLARIFY", "INFERENCE_REQUIRES_CONFIRMATION")
        if candidate.epistemic_status == "tentative":
            return MemoryGovernanceOutcome(
                "CLARIFY", "TENTATIVE_STATEMENT_REQUIRES_CONFIRMATION"
            )
        if (
            candidate.authority == "user_stated"
            and candidate.epistemic_status != "confirmed"
            and not candidate.user_authorized
        ):
            return MemoryGovernanceOutcome(
                "CLARIFY", "USER_ASSERTION_REQUIRES_CONFIRMATION"
            )
        if candidate.requires_confirmation or candidate.permanence == "unknown":
            return MemoryGovernanceOutcome("CLARIFY", "CONFIRMATION_REQUIRED")
        if candidate.sensitivity in ("sensitive", "high"):
            return MemoryGovernanceOutcome(
                "CLARIFY", "SENSITIVE_MEMORY_REQUIRES_CONFIRMATION"
            )
        if candidate.confidence < 0.8:
            return MemoryGovernanceOutcome("CLARIFY", "INSUFFICIENT_CONFIDENCE")
        if not candidate.reason_for_future_utility:
            return MemoryGovernanceOutcome("REJECT", "NO_DURABLE_FUTURE_UTILITY")
        if candidate.operation in ("correct", "supersede"):
            return MemoryGovernanceOutcome(
                "SUPERSEDE", "OWNED_CORRECTION", target["id"]
            )
        return MemoryGovernanceOutcome("PROMOTE", "DURABLE_USER_EVIDENCE")

    async def apply(
        self,
        *,
        user_id: str,
        session_id: str,
        reasoning_epoch: str,
        candidate: MemoryCandidate,
        candidate_index: int,
    ) -> MemoryGovernanceOutcome:
        key = f"{reasoning_epoch}:{candidate_index}"
        prior = await self.db.memories.find_one(
            {"user_id": user_id, "governance_key": key}, {"_id": 0}
        )
        if prior:
            return MemoryGovernanceOutcome(
                str(prior.get("last_governance_decision") or "PROMOTE"),  # type: ignore[arg-type]
                "IDEMPOTENT_REPLAY",
                prior.get("id"),
                True,
            )
        outcome = await self.evaluate(user_id=user_id, candidate=candidate)
        if outcome.decision not in ("PROMOTE", "SUPERSEDE", "FORGET_ALLOWED"):
            return outcome
        now = now_iso()
        if outcome.decision == "FORGET_ALLOWED":
            await self.db.memories.update_one(
                {"user_id": user_id, "id": outcome.memory_id},
                {
                    "$set": {
                        "status": "forgotten",
                        "updated_at": now,
                        "governance_key": key,
                        "last_governance_decision": "FORGET_ALLOWED",
                    },
                    "$inc": {"revision": 1},
                    "$push": {
                        "history": {
                            "operation": "forget",
                            "at": now,
                            "session_id": session_id,
                            "reasoning_epoch": reasoning_epoch,
                        }
                    },
                },
            )
            outcome.persisted = True
        else:
            raw_id = hashlib.sha256(f"{user_id}:{key}".encode()).hexdigest()[:20]
            memory_id = f"mem_{raw_id}"
            if outcome.decision == "SUPERSEDE":
                await self.db.memories.update_one(
                    {"user_id": user_id, "id": outcome.memory_id},
                    {
                        "$set": {
                            "status": "superseded",
                            "updated_at": now,
                            "superseded_by": memory_id,
                        },
                        "$inc": {"revision": 1},
                        "$push": {
                            "history": {
                                "operation": "supersede",
                                "at": now,
                                "replacement_id": memory_id,
                                "session_id": session_id,
                            }
                        },
                    },
                )
            doc = {
                "id": memory_id,
                "user_id": user_id,
                "content": candidate.summary,
                "statement": candidate.summary,
                "value": candidate.value,
                "kind": candidate.kind or "fact",
                "identity_key": candidate.identity_key,
                "status": "active",
                "authority": candidate.authority,
                "confidence": candidate.confidence,
                "epistemic_status": candidate.epistemic_status,
                "provenance": candidate.provenance,
                "evidence_refs": candidate.evidence_refs,
                "temporal_scope": {
                    "permanence": candidate.permanence,
                    "starts_at": candidate.starts_at,
                    "ends_at": candidate.ends_at,
                    "recurrence": candidate.recurrence,
                },
                "sensitivity": candidate.sensitivity,
                "supersedes_refs": list(
                    dict.fromkeys(
                        (
                            [candidate.existing_memory_ref]
                            if candidate.existing_memory_ref
                            else []
                        )
                        + candidate.supersedes_refs
                    )
                ),
                "coexists_with_refs": candidate.coexists_with_refs,
                "reason_for_future_utility": candidate.reason_for_future_utility,
                "user_authorized": candidate.user_authorized,
                "session_id": session_id,
                "reasoning_epoch": reasoning_epoch,
                "governance_key": key,
                "revision": 1,
                "history": [],
                "last_governance_decision": outcome.decision,
                "created_at": now,
                "updated_at": now,
            }
            await self.db.memories.insert_one(doc)
            outcome.memory_id = memory_id
            outcome.persisted = True
        try:
            from life_memory.service import LifeMemoryService

            await LifeMemoryService(self.db).invalidate_cache(user_id)
        except Exception:
            pass
        return outcome

    async def process(
        self,
        *,
        user_id: str,
        session_id: str,
        reasoning_epoch: str,
        candidates: List[MemoryCandidate],
    ) -> List[MemoryGovernanceOutcome]:
        results = []
        for index, candidate in enumerate(candidates[: self.MAX_CANDIDATES]):
            results.append(
                await self.apply(
                    user_id=user_id,
                    session_id=session_id,
                    reasoning_epoch=reasoning_epoch,
                    candidate=candidate,
                    candidate_index=index,
                )
            )
        return results
