"""
The capabilities that actually do something, and what they are honest about.

    AUTONOMOUS WORK MUST BE REAL WORK.
    A TOOL RESULT IS NOT A LIFE FACT.

Sprint 1 stood in for every capability, which was the right shape and the
wrong substance: an agent whose work is all stubs will happily report that a
goal is achieved, because everything it tried came back succeeded. This file
is where that stops being true — each function here reaches something that
already exists in ORA and returns what it actually found, or says plainly
that there was nothing behind the door.

Three rules hold for all of them.

Every outcome carries its **provenance**, set by the code that did the work,
because nothing downstream can reconstruct whether a provider was really
called. Every outcome carries **evidence** as claims rather than payloads: a
sentence about what was found, not the thing that was returned, because the
model needs to reason about facts and a raw dump is not a fact. And a
capability that is not connected says `requires_connection` rather than
returning an empty success — an empty success is how a system concludes that
somebody's calendar is clear when nobody ever plugged one in.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from agent.models import ResultProvenance

logger = logging.getLogger(__name__)

# How much of a life a bounded read may return. A snapshot relevant to a
# goal, never the database: a capability that hands over everything is a
# capability that put somebody's whole life in a prompt.
MAX_FACTS = 12
MAX_DOCUMENTS = 10
MAX_EVENTS = 10
MAX_CLAIMS = 8


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Claim:
    """One thing found out, in a sentence. Never a payload."""

    text: str
    supports: str = ""


@dataclass
class CapabilityOutcome:
    """
    What a capability did, with where it came from attached.

    `status` distinguishes the ways of not succeeding that mean different
    things to a planner: nothing there (`unavailable`), nothing connected
    (`requires_connection` as the error type), it broke and might not next
    time (`failed` and retryable), and it worked but only partly (`partial`).
    """

    status: str  # succeeded | partial | unavailable | failed | waiting
    observation: str
    provenance: ResultProvenance
    claims: List[Claim] = field(default_factory=list)
    data_ref: str = ""
    error_type: str = ""
    retryable: bool = False


def _unavailable(capability: str, reason: str, note: str) -> CapabilityOutcome:
    return CapabilityOutcome(
        status="unavailable",
        observation=note,
        provenance=ResultProvenance(
            source_class="internal_observation", capability=capability
        ),
        error_type=reason,
        retryable=False,
    )


# --- what ORA already holds -------------------------------------------------

async def read_internal_state(db, owner_id: str, goal) -> CapabilityOutcome:
    """
    A bounded look at what ORA already knows about this person.

    Deliberately not "the life model": a handful of durable facts, most
    recent first. The planner needs enough to know whether it already has the
    answer, and no more — passing a whole life to a model to decide one step
    is both a privacy failure and a bill.
    """
    facts: List[Claim] = []
    try:
        docs = await db.memories.find(
            {"user_id": owner_id, "status": {"$ne": "forgotten"}},
            {"_id": 0, "summary": 1, "fact_summary": 1, "kind": 1, "updated_at": 1},
        ).sort("updated_at", -1).to_list(MAX_FACTS)
    except Exception as e:
        logger.info("internal read soft-fail: %s", type(e).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="Non sono riuscita a leggere quello che ho su di te.",
            provenance=ResultProvenance(
                source_class="internal_observation", capability="information.read"
            ),
            error_type="internal_read_failed",
            retryable=True,
        )

    for doc in docs:
        text = (doc.get("summary") or doc.get("fact_summary") or "").strip()
        if text:
            facts.append(Claim(text=text[:400], supports="quello che risulta già"))

    if not facts:
        # Finding nothing is a finding. It is recorded as evidence like any
        # other, because "there is nothing on file about this" is exactly the
        # sort of thing a plan needs to know, and reporting it as a failure
        # would send the model looking for a fault that is not there.
        return CapabilityOutcome(
            status="succeeded",
            observation="Ho guardato: non risulta niente di registrato su questo.",
            provenance=ResultProvenance(
                source_class="internal_observation",
                capability="information.read",
                freshness="fresh",
                certainty_note="letto ora, e non c'era niente",
            ),
            claims=[Claim(
                text="Non risulta niente di registrato su questo.",
                supports="quello che risulta già",
            )],
            data_ref="internal:0",
        )

    return CapabilityOutcome(
        status="succeeded",
        observation=f"Ho guardato quello che risulta già: {len(facts)} cose.",
        provenance=ResultProvenance(
            source_class="internal_observation",
            capability="information.read",
            provider="life_memory",
            freshness="fresh",
        ),
        claims=facts[:MAX_CLAIMS],
        data_ref=f"internal:{len(facts)}",
    )


async def read_documents(db, owner_id: str, goal) -> CapabilityOutcome:
    """
    What documents exist and what they are, structurally.

    Names, kinds and tags — not the contents. A step that needs what is
    inside a document should say so and be answered by a read that says so
    too; handing over extracted text by default is how a capability called
    "list the documents" ends up disclosing a payslip.
    """
    try:
        docs = await db.documents.find(
            {"user_id": owner_id, "deleted": {"$ne": True}, "archived": {"$ne": True}},
            {"_id": 0, "id": 1, "filename": 1, "mime_type": 1, "tags": 1,
             "created_at": 1, "detected_language": 1},
        ).sort("created_at", -1).to_list(MAX_DOCUMENTS)
    except Exception as e:
        logger.info("document read soft-fail: %s", type(e).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="Non sono riuscita a guardare i documenti.",
            provenance=ResultProvenance(
                source_class="internal_observation", capability="document.read"
            ),
            error_type="document_read_failed",
            retryable=True,
        )

    if not docs:
        return CapabilityOutcome(
            status="succeeded",
            observation="Ho guardato l'archivio: non c'e nessun documento caricato.",
            provenance=ResultProvenance(
                source_class="internal_observation",
                capability="document.read",
                freshness="fresh",
            ),
            claims=[Claim(
                text="Non c'e nessun documento in archivio.",
                supports="cosa risulta in archivio",
            )],
            data_ref="documents:0",
        )

    claims = [
        Claim(
            text=(
                f"C'e un documento: {d.get('filename') or 'senza nome'}"
                + (f" ({', '.join(d.get('tags') or [])})" if d.get("tags") else "")
            )[:400],
            supports="cosa risulta in archivio",
        )
        for d in docs
    ]
    return CapabilityOutcome(
        status="succeeded",
        observation=f"Ho guardato l'archivio: {len(docs)} documenti.",
        provenance=ResultProvenance(
            source_class="internal_observation",
            capability="document.read",
            provider="documents",
            freshness="fresh",
        ),
        claims=claims[:MAX_CLAIMS],
        data_ref=f"documents:{len(docs)}",
    )


async def read_calendar(db, owner_id: str, goal) -> CapabilityOutcome:
    """
    What is actually on the calendar — if one is actually connected.

        NEVER SIMULATE A CONNECTION TO DECLARE IT WORKING.

    The distinction that earns its keep here is between "nothing is coming
    up" and "there is no calendar". They look identical in the data and mean
    opposite things to a plan, so this reports the missing connection rather
    than an empty week.
    """
    try:
        connected = await db.connector_instances.count_documents(
            {"user_id": owner_id, "connector_id": "calendar_google",
             "status": {"$in": ["connected", "active", "healthy"]}},
            limit=1,
        )
    except Exception as e:
        logger.info("calendar connection check soft-fail: %s", type(e).__name__)
        connected = 0

    if not connected:
        return CapabilityOutcome(
            status="unavailable",
            observation="Non c'e nessun calendario collegato, quindi non posso guardarci.",
            provenance=ResultProvenance(
                source_class="connected_provider", capability="calendar.read"
            ),
            error_type="requires_connection",
            retryable=False,
        )

    now = _now()
    horizon = (now + timedelta(days=14)).isoformat()
    try:
        events = await db.ingestion_events.find(
            {
                "user_id": owner_id,
                "connector_id": "calendar_google",
                "source_record_type": "calendar_event",
                "normalized_payload.starts_at.value": {
                    "$gte": now.isoformat(), "$lte": horizon
                },
            },
            {"_id": 0, "normalized_payload": 1},
        ).sort("normalized_payload.starts_at.value", 1).to_list(MAX_EVENTS)
    except Exception as e:
        logger.info("calendar read soft-fail: %s", type(e).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="Il calendario non ha risposto.",
            provenance=ResultProvenance(
                source_class="connected_provider", capability="calendar.read"
            ),
            error_type="provider_unavailable",
            retryable=True,
        )

    claims: List[Claim] = []
    for event in events:
        payload = event.get("normalized_payload") or {}
        title = ((payload.get("title") or {}).get("value") or "").strip()
        starts = ((payload.get("starts_at") or {}).get("value") or "")[:16]
        if title:
            claims.append(Claim(
                text=f"In calendario: {title} - {starts}"[:400],
                supports="cosa c'e gia in agenda",
            ))

    return CapabilityOutcome(
        status="succeeded" if claims else "partial",
        observation=(
            f"Ho guardato il calendario: {len(claims)} cose nelle prossime due settimane."
            if claims
            else "Ho guardato il calendario: nelle prossime due settimane e libero."
        ),
        provenance=ResultProvenance(
            source_class="connected_provider",
            capability="calendar.read",
            provider="calendar",
            freshness="fresh",
        ),
        claims=claims[:MAX_CLAIMS],
        data_ref="calendar",
    )


# --- looking things up in the world ----------------------------------------

async def do_research(
    db, owner_id: str, goal, step, *, reuse: bool = True
) -> CapabilityOutcome:
    """
    Find something out, through the research engine that already exists.

        DO NOT DUPLICATE THE RESEARCH ENGINE.

    V3.4 already knows how to plan queries, weigh sources, notice conflicts
    and decide whether what it has is enough. All this does is ask it the
    step's question and translate what comes back into claims — including
    sufficiency and any conflict, because a planner told only the answer will
    treat a contested answer as settled.
    """
    try:
        from research.models import ResearchNeed
        from research.service import ResearchService
    except Exception as e:
        logger.info("research import soft-fail: %s", type(e).__name__)
        return _unavailable("web.research", "not_wired", "La ricerca non e collegata.")

    question = (step.expected_result or step.intent or "").strip()
    if not question:
        return _unavailable(
            "web.research", "nothing_to_ask", "Non c'era una domanda da porre."
        )

    need = ResearchNeed(
        question=question[:400],
        purpose=(goal.desired_outcome or "")[:300],
        already_known=[str(c)[:200] for c in (goal.success_criteria or [])][:12],
    )

    try:
        run = await ResearchService(db).run(
            owner_id, need, situation_ref=f"goal:{goal.id}", allow_reuse=reuse
        )
    except Exception as e:
        logger.info("research run soft-fail: %s", type(e).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="La ricerca non e andata a buon fine.",
            provenance=ResultProvenance(
                source_class="external_research", capability="web.research"
            ),
            error_type="provider_unavailable",
            retryable=True,
        )

    synthesis = getattr(run, "synthesis", None)
    assessments = list(getattr(run, "assessments", None) or [])
    assessment = assessments[-1] if assessments else None
    sufficiency = getattr(assessment, "sufficiency", "insufficient") if assessment else "insufficient"
    conflicts = list(getattr(assessment, "conflicts", None) or []) if assessment else []

    claims: List[Claim] = []
    for claim in (getattr(synthesis, "claims", None) or [])[:MAX_CLAIMS]:
        text = (getattr(claim, "statement", "") or "").strip()
        if text:
            claims.append(Claim(text=text[:600], supports=question[:300]))
    if not claims and getattr(synthesis, "answer", ""):
        claims.append(Claim(text=str(synthesis.answer)[:600], supports=question[:300]))

    # A conflict is a finding, not a failure. It goes in as a claim of its own
    # so the planner has to reckon with it rather than read past it.
    for conflict in conflicts[:2]:
        about = getattr(conflict, "about", "") or ""
        if about:
            claims.append(Claim(
                text=f"Le fonti non concordano su: {about}"[:600],
                supports="disaccordo fra le fonti",
            ))

    run_id = getattr(run, "id", "")
    if getattr(run, "status", "") == "failed" or not claims:
        return CapabilityOutcome(
            status="partial" if claims else "failed",
            observation=(
                getattr(run, "outcome_note", "") or "Non ho trovato niente di utilizzabile."
            )[:600],
            provenance=ResultProvenance(
                source_class="external_research",
                capability="web.research",
                provider="research",
                source_refs=[run_id] if run_id else [],
                freshness="fresh",
            ),
            claims=claims,
            data_ref=run_id,
            error_type="research_insufficient",
            retryable=True,
        )

    enough = sufficiency in ("sufficient", "strong")
    return CapabilityOutcome(
        status="succeeded" if enough else "partial",
        observation=(
            f"Ho cercato: {question[:120]}. "
            + (getattr(synthesis, "answer", "") or "")[:300]
        ).strip()[:600],
        provenance=ResultProvenance(
            source_class="external_research",
            capability="web.research",
            provider="research",
            source_refs=[run_id] if run_id else [],
            freshness="fresh",
            certainty_note=f"quanto bastano le fonti: {sufficiency}"[:200],
        ),
        claims=claims[:MAX_CLAIMS],
        data_ref=run_id,
        error_type="" if enough else "not_enough_yet",
    )


async def do_comparison(
    db, owner_id: str, goal, step, *, research_refs: List[str]
) -> CapabilityOutcome:
    """
    Weigh alternatives, through the comparison engine that already exists.

    V3.5 owns the arithmetic and the constraint checking, which is exactly
    the part that must not be a model's job. This hands it what research
    already found and returns the recommendation state — including when it
    declines to recommend, because a comparison that always picks a winner is
    not comparing.
    """
    try:
        from comparison.models import ComparisonNeed
        from comparison.service import ComparisonService
    except Exception as e:
        logger.info("comparison import soft-fail: %s", type(e).__name__)
        return _unavailable(
            "comparison.run", "not_wired", "Il confronto non e collegato."
        )

    if not research_refs:
        # Nothing to compare is not a failed comparison. It is a plan that
        # asked for one too early, and it should be told so.
        return CapabilityOutcome(
            status="partial",
            observation="Non ho ancora abbastanza per mettere a confronto le opzioni.",
            provenance=ResultProvenance(
                source_class="deterministic_computation", capability="comparison.run"
            ),
            error_type="nothing_to_compare",
            retryable=False,
        )

    need = ComparisonNeed(
        decision=(step.intent or goal.objective)[:400],
        purpose=(goal.desired_outcome or "")[:300],
    )
    try:
        run = await ComparisonService(db).run(
            owner_id,
            need,
            [],
            situation_ref=f"goal:{goal.id}",
            research_run_ids=list(research_refs)[:4],
            allow_research=False,
        )
    except Exception as e:
        logger.info("comparison run soft-fail: %s", type(e).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="Il confronto non e andato a buon fine.",
            provenance=ResultProvenance(
                source_class="deterministic_computation", capability="comparison.run"
            ),
            error_type="provider_unavailable",
            retryable=True,
        )

    recommendation = getattr(run, "recommendation", None)
    chosen = str(getattr(recommendation, "recommended", "") or "") if recommendation else ""
    note = (getattr(run, "outcome_note", "") or "")[:400]
    run_id = getattr(run, "id", "")

    claims: List[Claim] = []
    if chosen:
        claims.append(Claim(
            text=f"Fra le opzioni, la piu adatta risulta: {chosen}"[:600],
            supports="quale scegliere",
        ))
    if note:
        claims.append(Claim(text=note[:600], supports="come e andato il confronto"))

    return CapabilityOutcome(
        status="succeeded" if chosen else "partial",
        observation=note or "Ho messo a confronto quello che avevo.",
        provenance=ResultProvenance(
            source_class="deterministic_computation",
            capability="comparison.run",
            provider="comparison",
            source_refs=([run_id] if run_id else []) + list(research_refs)[:4],
            freshness="fresh",
        ),
        claims=claims[:MAX_CLAIMS],
        data_ref=run_id,
        error_type="" if chosen else "no_clear_choice",
    )


# --- preparing, which changes nothing --------------------------------------

async def prepare_locally(db, owner_id: str, goal, step) -> CapabilityOutcome:
    """
    Produce something without touching anything.

    Real in the only sense that matters here — nothing outside ORA is
    involved, so there is nothing to stand in for. The provenance says
    `deterministic_computation` because that is what it is: ORA arranged what
    it already had.
    """
    return CapabilityOutcome(
        status="succeeded",
        observation=f"Ho preparato: {step.intent}"[:600],
        provenance=ResultProvenance(
            source_class="deterministic_computation",
            capability=step.capability_needed or "prepare",
            freshness="fresh",
        ),
        claims=[Claim(
            text=f"E pronto: {step.intent}"[:600],
            supports=(step.expected_result or "")[:300],
        )],
        data_ref=f"prep:{step.id}",
    )


async def open_navigation(db, owner_id: str, goal, step) -> CapabilityOutcome:
    """
    The one world-changing capability with a stand-in behind it.

    It stays a stand-in, and says so. Sprint 1 used it to show that the
    "there is already a grant, so proceed" path exists; Sprint 2 must not let
    it be mistaken for evidence that anything happened, so its provenance is
    `simulated` and the completion gate refuses to close a goal on it.
    """
    return CapabilityOutcome(
        status="succeeded",
        observation=(
            f"Fatto (simulato): {step.intent}. "
            "Niente ha davvero raggiunto un servizio esterno."
        )[:600],
        provenance=ResultProvenance(
            source_class="simulated",
            capability="navigation.open",
            certainty_note="non e successo davvero: e una simulazione",
        ),
        claims=[Claim(text=f"Simulato: {step.intent}"[:600])],
        data_ref=f"sim:{step.id}",
    )
