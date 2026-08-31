"""
Scanning a life for what deserves attention, and enforcing what may follow.

    AI DECIDES RELEVANCE. CODE ENFORCES BOUNDARIES.

The judgement is entirely the model's: whether anything here matters, how
much, how soon, and whether it would be noise. What this file owns is
everything with a right answer — assembling the facts, checking that a claim
points at one of them, keeping identity stable, applying status transitions,
and refusing every path from an opportunity to work, a notification or an
action.

Those refusals are the point. An opportunity that quietly becomes a task has
put something on somebody's plate that they never accepted, and a system that
does that once will not be trusted again.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from opportunities import snapshot as life_snapshot
from opportunities.models import (
    EvidenceRef,
    Opportunity,
    OpportunityCandidate,
    OpportunityDecision,
    ScanResult,
)
from opportunities.repository import CLOSED, OpportunityRepository

logger = logging.getLogger(__name__)

# An identity key is a slug, and only a slug. Anything else is either a
# sentence the model wrote today — which will not match tomorrow's — or an
# attempt to smuggle structure through a field that has none.
IDENTITY_KEY = re.compile(r"^[a-z0-9][a-z0-9_\-:.]{2,119}$")

# How many one scan may raise. Not a judgement about which are worth it — the
# model already made that — but a bound on how much can arrive at once.
MAX_PER_SCAN = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OpportunityService:
    def __init__(self, db):
        self.db = db
        self.repo = OpportunityRepository(db)

    # --- scanning --------------------------------------------------------

    async def scan(
        self,
        user_id: str,
        *,
        changes: Optional[List[Dict[str, Any]]] = None,
        language: str = "it",
        source_context: str = "manual_scan",
    ) -> ScanResult:
        """
        Ask whether anything in this life is worth raising.

        Most scans end in silence, and silence writes nothing. A scan that
        could not reach the model is reported separately: an outage is not a
        judgement that there was nothing, and recording it as one would be a
        lie told by a network error.
        """
        from opportunities.reasoning import scan as ask

        state = await life_snapshot.build(self.db, user_id, changes=changes)
        # What this scan could not see, carried on every outcome. A silence
        # reached without the calendar is a different statement from a silence
        # reached with it, and anything that later tells a person their life
        # looks quiet has to be able to tell those apart.
        blind_to = list(state.get("unavailable_sources") or [])
        known = await self.repo.list(user_id, limit=25)

        answer = await ask(
            state,
            already_raised=[o.for_ai() for o in known],
            language=language,
        )
        if answer is None:
            logger.info("opportunity scan unavailable for %s", user_id[:8])
            return ScanResult(
                silence=True,
                unavailable=True,
                unavailable_sources=blind_to,
                reason_for_silence="il ragionamento non era disponibile",
            )

        raw = answer.get("opportunities")
        if not isinstance(raw, list) or not raw:
            return ScanResult(
                silence=True,
                unavailable_sources=blind_to,
                reason_for_silence=str(answer.get("reason_for_silence") or "")[:400],
            )

        allowed_refs = life_snapshot.evidence_refs(state)
        by_identity = {o.identity_key: o for o in known}
        result = ScanResult(silence=False, unavailable_sources=blind_to)

        for item in raw[:MAX_PER_SCAN]:
            candidate, why_not = self._read_candidate(item, allowed_refs)
            if candidate is None:
                result.skipped.append({"reason": why_not})
                continue

            existing = by_identity.get(candidate.identity_key) or await self.repo.by_identity(
                user_id, candidate.identity_key
            )
            if existing is not None and existing.status in CLOSED:
                # Already settled. Raising it again would be ORA forgetting an
                # answer it was given.
                result.skipped.append(
                    {"reason": f"già chiusa come «{existing.status}»"}
                )
                continue

            if existing is not None:
                self._apply_candidate(existing, candidate)
                existing.last_reviewed_at = _now().isoformat()
                await self.repo.save(existing)
                result.updated.append(existing)
                continue

            opportunity = Opportunity(
                owner_id=user_id,
                identity_key=candidate.identity_key,
                status="active",
                semantic_summary=candidate.semantic_summary,
                why_it_matters=candidate.why_it_matters,
                why_now=candidate.why_now,
                relevance=candidate.relevance,
                urgency=candidate.urgency,
                time_sensitivity=candidate.time_sensitivity,
                confidence=candidate.confidence,
                evidence=candidate.evidence,
                source_context=source_context[:120],
                requires_clarification=candidate.requires_clarification,
                clarifying_question=candidate.clarifying_question,
                needs_research=candidate.needs_research,
                research_question=candidate.research_question,
                related_goal_id=candidate.related_goal_id,
                related_place_id=candidate.related_place_id,
                valid_until=candidate.valid_until,
                decision_provenance="model",
            )
            await self.repo.save(opportunity)
            result.created.append(opportunity)

        if not result.created and not result.updated:
            result.silence = True
            result.reason_for_silence = (
                result.reason_for_silence or "nulla è sopravvissuto ai controlli"
            )
        return result

    def _read_candidate(
        self, raw: Any, allowed_refs: Dict[str, str]
    ) -> tuple[Optional[OpportunityCandidate], str]:
        """
        Turn one proposal into a candidate, or refuse it and say why.

        Two refusals matter. An identity that is not a stable slug cannot be
        matched against tomorrow's scan, so it would arrive twice. And a claim
        citing a fact that was never supplied has been invented — dropping it
        is the only safe move, because the alternative is telling somebody
        about a deadline that does not exist.
        """
        if not isinstance(raw, dict):
            return None, "proposta non leggibile"

        identity = str(raw.get("identity_key") or "").strip().lower()
        if not IDENTITY_KEY.match(identity):
            return None, "identità non stabile"

        what = str(raw.get("what") or "").strip()
        why = str(raw.get("why_it_matters") or "").strip()
        if not what or not why:
            return None, "senza cosa o senza perché"

        refs = [str(r).strip() for r in (raw.get("evidence_refs") or []) if str(r).strip()]
        grounded = [r for r in refs if r in allowed_refs]
        if not grounded:
            # Fail closed. An opportunity resting on nothing is an opinion
            # about somebody's life, and this system does not hold those.
            return None, "nessun fatto reale a sostegno"

        def word(field: str, allowed: set, fallback: str) -> str:
            value = str(raw.get(field) or "").strip().lower()
            return value if value in allowed else fallback

        try:
            candidate = OpportunityCandidate(
                identity_key=identity,
                semantic_summary=what[:280],
                why_it_matters=why[:600],
                why_now=str(raw.get("why_now") or "").strip()[:400],
                relevance=word("relevance", {"low", "medium", "high"}, "medium"),
                urgency=word("urgency", {"none", "soon", "urgent"}, "none"),
                time_sensitivity=word(
                    "time_sensitivity", {"stable", "changing", "perishable"}, "stable"
                ),
                confidence=word(
                    "confidence", {"weak", "reasonable", "strong"}, "reasonable"
                ),
                evidence=[
                    EvidenceRef(kind=allowed_refs[r], ref=r) for r in grounded[:8]
                ],
                requires_clarification=bool(raw.get("requires_clarification")),
                clarifying_question=str(raw.get("clarifying_question") or "")[:300],
                needs_research=bool(raw.get("needs_research")),
                research_question=str(raw.get("research_question") or "")[:300],
                valid_until=(str(raw.get("valid_until"))[:40] if raw.get("valid_until") else None),
            )
        except Exception:
            return None, "proposta fuori contratto"
        return candidate, ""

    @staticmethod
    def _apply_candidate(existing: Opportunity, candidate: OpportunityCandidate) -> None:
        """Same concern, said again — the wording may move, the identity does not."""
        existing.semantic_summary = candidate.semantic_summary
        existing.why_it_matters = candidate.why_it_matters
        existing.why_now = candidate.why_now
        existing.relevance = candidate.relevance
        existing.urgency = candidate.urgency
        existing.time_sensitivity = candidate.time_sensitivity
        existing.confidence = candidate.confidence
        existing.evidence = candidate.evidence
        existing.needs_research = candidate.needs_research
        existing.research_question = candidate.research_question
        existing.valid_until = candidate.valid_until

    # --- review ----------------------------------------------------------

    async def review(
        self, user_id: str, opportunity_id: str, *, language: str = "it"
    ) -> Dict[str, Any]:
        """
        Ask what became of something already raised.

        The model reads the same life again; code applies whatever it
        concluded and keeps the decision, so a status can always be traced back
        to a reason.
        """
        from opportunities.reasoning import review as ask

        opportunity = await self.repo.get(user_id, opportunity_id)
        if opportunity is None:
            return {"ok": False, "reason": "unknown_opportunity"}
        if opportunity.status in CLOSED:
            return {"ok": True, "outcome": opportunity.status, "unchanged": True}

        state = await life_snapshot.build(self.db, user_id)
        answer = await ask(opportunity.public(), snapshot=state, language=language)
        if answer is None:
            return {"ok": False, "reason": "unavailable"}

        outcome = answer["outcome"]
        rationale = str(answer.get("rationale") or "")[:400]

        if outcome == "update":
            updated = answer.get("updated") or {}
            opportunity.semantic_summary = (
                str(updated.get("what") or opportunity.semantic_summary)[:280]
            )
            opportunity.why_it_matters = (
                str(updated.get("why_it_matters") or opportunity.why_it_matters)[:600]
            )
            opportunity.why_now = str(updated.get("why_now") or opportunity.why_now)[:400]
            for field, allowed in (
                ("relevance", {"low", "medium", "high"}),
                ("urgency", {"none", "soon", "urgent"}),
            ):
                value = str(updated.get(field) or "").strip().lower()
                if value in allowed:
                    setattr(opportunity, field, value)
        elif outcome in {"resolve", "expire", "suppress"}:
            opportunity.status = {
                "resolve": "resolved",
                "expire": "expired",
                "suppress": "suppressed",
            }[outcome]

        opportunity.last_reviewed_at = _now().isoformat()
        opportunity.decision_provenance = "model"
        await self.repo.save(opportunity)
        await self.repo.record_decision(
            OpportunityDecision(
                opportunity_id=opportunity.id,
                owner_id=user_id,
                outcome=outcome,  # type: ignore[arg-type]
                source="model",
                rationale=rationale,
            )
        )
        if opportunity.status in CLOSED:
            # The review closed it, so whatever was still intending to arrive
            # about it is now wrong. Same guarantee as a person dismissing it:
            # code, not judgement.
            await self._close_deliveries(user_id, opportunity.id, rationale or "rivalutata")
        return {"ok": True, "outcome": outcome, "opportunity": opportunity.public()}

    # --- what the person says --------------------------------------------

    async def _close_deliveries(self, user_id: str, opportunity_id: str, why: str) -> None:
        """
        A concern that closed takes its intentions with it.

        Guaranteed here rather than judged anywhere: a notification about
        something already dealt with is never right, so there is nothing to
        decide. Best-effort — refusing to resolve an opportunity because the
        delivery layer is unreachable would be the tail wagging the dog.
        """
        try:
            from delivery.service import DeliveryService

            await DeliveryService(self.db).cancel_for_opportunity(
                user_id, opportunity_id, reason=why
            )
        except Exception as e:
            logger.info("delivery cancel soft-fail: %s", type(e).__name__)

    async def dismiss(
        self, user_id: str, opportunity_id: str, *, suppress: bool = False
    ) -> Dict[str, Any]:
        """
        Not interested — either this time, or ever for this concern.

        `dismiss` and `suppress` are different answers and are kept apart.
        "Not now" should not silence a concern forever, and "stop bringing
        this up" must survive the next scan, which it does because a closed
        identity is never raised again.
        """
        opportunity = await self.repo.get(user_id, opportunity_id)
        if opportunity is None:
            return {"ok": False, "reason": "unknown_opportunity"}

        opportunity.status = "suppressed" if suppress else "dismissed"
        opportunity.decision_provenance = "user"
        opportunity.last_reviewed_at = _now().isoformat()
        await self.repo.save(opportunity)
        await self.repo.record_decision(
            OpportunityDecision(
                opportunity_id=opportunity.id,
                owner_id=user_id,
                outcome="suppress" if suppress else "dismiss",
                source="user",
                rationale="respinta dalla persona",
            )
        )
        await self._close_deliveries(user_id, opportunity.id, "respinta dalla persona")
        return {"ok": True, "status": opportunity.status}

    async def resolve(self, user_id: str, opportunity_id: str) -> Dict[str, Any]:
        """The person says it is dealt with."""
        opportunity = await self.repo.get(user_id, opportunity_id)
        if opportunity is None:
            return {"ok": False, "reason": "unknown_opportunity"}
        opportunity.status = "resolved"
        opportunity.decision_provenance = "user"
        opportunity.last_reviewed_at = _now().isoformat()
        await self.repo.save(opportunity)
        await self.repo.record_decision(
            OpportunityDecision(
                opportunity_id=opportunity.id,
                owner_id=user_id,
                outcome="resolve",
                source="user",
                rationale="chiusa dalla persona",
            )
        )
        await self._close_deliveries(user_id, opportunity.id, "la questione è stata risolta")
        return {"ok": True, "status": opportunity.status}

    async def expire_past(self, user_id: str) -> int:
        """
        Close what its own deadline has outlived.

        The one status change code makes on its own, and only because a date
        passing is arithmetic rather than judgement. It is still recorded as a
        decision, with `code_expiry` as its source.
        """
        now = _now().isoformat()
        closed = 0
        for opportunity in await self.repo.list(user_id, statuses=["active"]):
            if opportunity.valid_until and opportunity.valid_until < now:
                opportunity.status = "expired"
                opportunity.decision_provenance = "code_expiry"
                opportunity.last_reviewed_at = now
                await self.repo.save(opportunity)
                await self.repo.record_decision(
                    OpportunityDecision(
                        opportunity_id=opportunity.id,
                        owner_id=user_id,
                        outcome="expire",
                        source="code_expiry",
                        rationale="il termine indicato è passato",
                    )
                )
                await self._close_deliveries(
                    user_id, opportunity.id, "il termine indicato è passato"
                )
                closed += 1
        return closed

    async def list_active(self, user_id: str) -> List[Opportunity]:
        return await self.repo.list(user_id, statuses=["active"])
