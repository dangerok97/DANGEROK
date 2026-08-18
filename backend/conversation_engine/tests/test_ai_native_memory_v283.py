"""V2.8.3 — governed, selective and cross-session durable learning."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from conversation_engine.ai_core.models import MemoryCandidate
from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT
from conversation_engine.ai_core.context_broker import ContextBroker
from conversation_engine.ai_core.context_sources import (
    ContextSourceRegistry,
    _memory_fact_payload,
    rank_evidence,
)
from conversation_engine.ai_core.models import ContextFact, ContextNeed
from conversation_engine.models import ConversationSession
from life_memory.governance import MemoryGovernanceService
from life_memory.service import LifeMemoryService


def _matches(doc, query):
    return all(doc.get(key) == value for key, value in query.items())


class Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, field, direction):
        self.docs.sort(key=lambda d: d.get(field) or "", reverse=direction < 0)
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, n):
        return deepcopy(self.docs[:n])


class Collection:
    def __init__(self):
        self.docs = []
        self.indexes = []

    async def create_index(self, *args, **kwargs):
        self.indexes.append((args, kwargs))

    async def insert_one(self, doc):
        self.docs.append(deepcopy(doc))

    async def find_one(self, query, projection=None):
        return next((deepcopy(d) for d in self.docs if _matches(d, query)), None)

    def find(self, query, projection=None):
        return Cursor([deepcopy(d) for d in self.docs if _matches(d, query)])

    async def delete_one(self, query):
        self.docs = [d for d in self.docs if not _matches(d, query)]

    async def update_one(self, query, update, upsert=False):
        target = next((d for d in self.docs if _matches(d, query)), None)
        if target is None and upsert:
            target = deepcopy(query)
            self.docs.append(target)
        if target is None:
            return SimpleNamespace(matched_count=0, modified_count=0)
        target.update(deepcopy(update.get("$set") or {}))
        for key, value in (update.get("$inc") or {}).items():
            target[key] = target.get(key, 0) + value
        for key, value in (update.get("$push") or {}).items():
            target.setdefault(key, []).append(deepcopy(value))
        return SimpleNamespace(matched_count=1, modified_count=1)


class DB:
    def __init__(self):
        self.cols = {}

    def __getitem__(self, name):
        return self.cols.setdefault(name, Collection())

    def __getattr__(self, name):
        return self[name]


def candidate(**overrides):
    data = {
        "summary": "L'utente preferisce comunicazioni concise",
        "kind": "communication_preference",
        "identity_key": "response_detail_preference",
        "confidence": 0.95,
        "authority": "user_stated",
        "epistemic_status": "confirmed",
        "provenance": ["user_conversation"],
        "permanence": "indefinite",
        "reason_for_future_utility": "Migliora la forma delle risposte future",
        "user_authorized": True,
    }
    data.update(overrides)
    return MemoryCandidate(**data)


@pytest.mark.asyncio
async def test_promote_schema_provenance_revision_and_open_kind():
    db = DB()
    svc = MemoryGovernanceService(db)
    out = await svc.apply(
        user_id="u1",
        session_id="s1",
        reasoning_epoch="e1",
        candidate=candidate(),
        candidate_index=0,
    )
    assert out.decision == "PROMOTE" and out.persisted
    doc = db.memories.docs[0]
    assert doc["kind"] == "communication_preference" and doc["revision"] == 1
    assert doc["provenance"] == ["user_conversation"] and doc["user_id"] == "u1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes,decision,code",
    [
        (
            {"permanence": "temporary", "ends_at": "tomorrow"},
            "REJECT",
            "TEMPORARY_CONTEXT_BELONGS_TO_SITUATION",
        ),
        ({"authority": "inferred"}, "CLARIFY", "INFERENCE_REQUIRES_CONFIRMATION"),
        (
            {"epistemic_status": "tentative"},
            "CLARIFY",
            "TENTATIVE_STATEMENT_REQUIRES_CONFIRMATION",
        ),
        (
            {"epistemic_status": "asserted", "user_authorized": False},
            "CLARIFY",
            "USER_ASSERTION_REQUIRES_CONFIRMATION",
        ),
        ({"authority": "device"}, "REJECT", "DEVICE_SIGNAL_NOT_DURABLE_MEMORY"),
        ({"permanence": "unknown"}, "CLARIFY", "CONFIRMATION_REQUIRED"),
        (
            {"sensitivity": "sensitive"},
            "CLARIFY",
            "SENSITIVE_MEMORY_REQUIRES_CONFIRMATION",
        ),
        ({"confidence": 0.4}, "CLARIFY", "INSUFFICIENT_CONFIDENCE"),
        ({"reason_for_future_utility": None}, "REJECT", "NO_DURABLE_FUTURE_UTILITY"),
    ],
)
async def test_governance_is_general_and_conservative(changes, decision, code):
    out = await MemoryGovernanceService(DB()).evaluate(
        user_id="u", candidate=candidate(**changes)
    )
    assert (out.decision, out.code) == (decision, code)


@pytest.mark.asyncio
async def test_same_turn_idempotency_cross_turn_allowed():
    db = DB()
    svc = MemoryGovernanceService(db)
    first = await svc.apply(
        user_id="u",
        session_id="s",
        reasoning_epoch="same",
        candidate=candidate(),
        candidate_index=0,
    )
    replay = await svc.apply(
        user_id="u",
        session_id="s",
        reasoning_epoch="same",
        candidate=candidate(),
        candidate_index=0,
    )
    later = await svc.apply(
        user_id="u",
        session_id="s2",
        reasoning_epoch="later",
        candidate=candidate(
            summary="L'utente usa un tono diretto",
            identity_key="response_tone_preference",
            coexists_with_refs=[first.memory_id],
        ),
        candidate_index=0,
    )
    assert first.memory_id == replay.memory_id and replay.code == "IDEMPOTENT_REPLAY"
    assert later.memory_id != first.memory_id and len(db.memories.docs) == 2


@pytest.mark.asyncio
async def test_correction_supersedes_with_history_without_overwrite():
    db = DB()
    svc = MemoryGovernanceService(db)
    old = await svc.apply(
        user_id="u",
        session_id="s",
        reasoning_epoch="e1",
        candidate=candidate(summary="Preferisce risposte lunghe"),
        candidate_index=0,
    )
    corrected = await svc.apply(
        user_id="u",
        session_id="s",
        reasoning_epoch="e2",
        candidate_index=0,
        candidate=candidate(
            operation="correct",
            existing_memory_ref=old.memory_id,
            summary="Preferisce risposte concise",
        ),
    )
    assert corrected.decision == "SUPERSEDE" and len(db.memories.docs) == 2
    prior = next(d for d in db.memories.docs if d["id"] == old.memory_id)
    assert (
        prior["status"] == "superseded"
        and prior["history"][0]["replacement_id"] == corrected.memory_id
    )


@pytest.mark.asyncio
async def test_identity_key_prevents_duplicate_when_open_kind_label_changes():
    db = DB()
    first = await MemoryGovernanceService(db).apply(
        user_id="u",
        session_id="s1",
        reasoning_epoch="e1",
        candidate=candidate(),
        candidate_index=0,
    )
    outcome = await MemoryGovernanceService(db).evaluate(
        user_id="u",
        candidate=candidate(
            kind="answer_format_preference",
            summary="Preferisce risposte concise",
        ),
    )
    assert outcome.decision == "CLARIFY"
    assert outcome.code == "EXISTING_MEMORY_REQUIRES_RELATIONSHIP"
    assert outcome.memory_id == first.memory_id


@pytest.mark.asyncio
async def test_cross_user_target_cannot_be_corrected_or_forgotten():
    db = DB()
    svc = MemoryGovernanceService(db)
    old = await svc.apply(
        user_id="owner",
        session_id="s",
        reasoning_epoch="e1",
        candidate=candidate(),
        candidate_index=0,
    )
    correction = await svc.evaluate(
        user_id="other",
        candidate=candidate(operation="correct", existing_memory_ref=old.memory_id),
    )
    forgetting = await svc.evaluate(
        user_id="other",
        candidate=candidate(operation="forget", existing_memory_ref=old.memory_id),
    )
    assert correction.decision == "CLARIFY" and forgetting.decision == "FORGET_DENIED"


@pytest.mark.asyncio
async def test_forget_is_owned_non_destructive_tombstone():
    db = DB()
    svc = MemoryGovernanceService(db)
    old = await svc.apply(
        user_id="u",
        session_id="s",
        reasoning_epoch="e1",
        candidate=candidate(),
        candidate_index=0,
    )
    out = await svc.apply(
        user_id="u",
        session_id="s",
        reasoning_epoch="e2",
        candidate_index=0,
        candidate=candidate(operation="forget", existing_memory_ref=old.memory_id),
    )
    assert (
        out.decision == "FORGET_ALLOWED"
        and db.memories.docs[0]["status"] == "forgotten"
    )
    assert len(db.memories.docs) == 1 and db.memories.docs[0]["revision"] == 2


@pytest.mark.asyncio
async def test_cross_session_life_memory_sees_promoted_but_not_superseded_or_forgotten(
    monkeypatch,
):
    db = DB()
    svc = MemoryGovernanceService(db)
    promoted = await svc.apply(
        user_id="u",
        session_id="session-a",
        reasoning_epoch="e1",
        candidate=candidate(summary="Preferisce risposte concise"),
        candidate_index=0,
    )

    # Keep source loading hermetic: only the governed memories collection matters.
    async def sources(_user):
        return {
            "profile": {},
            "study_plans": [],
            "auth_user": {},
            "partial_sources": [],
            "user_notes": list(db.memories.docs),
        }

    lm = LifeMemoryService(db)
    monkeypatch.setattr(lm, "_load_sources", sources)
    response = await lm.get_life_memory("u", enrich=False)
    assert any("concise" in item.statement for item in response.memories)
    await svc.apply(
        user_id="u",
        session_id="session-b",
        reasoning_epoch="e2",
        candidate_index=0,
        candidate=candidate(operation="forget", existing_memory_ref=promoted.memory_id),
    )
    response2 = await lm.get_life_memory("u", force_refresh=True, enrich=False)
    assert not any("concise" in item.statement for item in response2.memories)


@pytest.mark.asyncio
async def test_candidate_budget_is_bounded():
    db = DB()
    svc = MemoryGovernanceService(db)
    results = await svc.process(
        user_id="u",
        session_id="s",
        reasoning_epoch="e",
        candidates=[
            candidate(
                summary=f"Fact {i}", kind=f"fact_kind_{i}", identity_key=f"fact_{i}"
            )
            for i in range(7)
        ],
    )
    assert len(results) == 3 and len(db.memories.docs) == 3


def test_legacy_candidate_remains_valid_but_requires_governance():
    legacy = MemoryCandidate(fact_summary="Likes tea", confidence=0.6)
    assert legacy.summary == "Likes tea" and legacy.permanence == "unknown"


def test_personalization_contract_requires_bounded_context_instead_of_guessing():
    assert (
        "MUST request\nbounded personal context before answering"
        in COGNITIVE_SYSTEM_PROMPT
    )
    assert "Do not imitate personalization by guessing" in COGNITIVE_SYSTEM_PROMPT
    assert 'MUST use source_hints=["memory"]' in COGNITIVE_SYSTEM_PROMPT


def test_stage_b_registry_keeps_governed_memory_as_generic_anchor():
    sources, _ = ContextSourceRegistry(DB()).select(
        ContextNeed(
            query="personal evidence already known", purpose="personalize response"
        ),
        maximum=6,
    )
    assert "memory" in [source.name for source in sources]


@pytest.mark.asyncio
async def test_stage_a_exposes_only_bounded_memory_index_not_content():
    db = DB()
    db.memories.docs.append(
        {"id": "mem_1", "user_id": "u", "status": "active", "content": "private value"}
    )
    facts = await ContextBroker(db).retrieve(user_id="u", stage="A", session_id="s")
    index = next(fact for fact in facts if fact.source == "memory_index")
    assert (
        index.ref == "memory:index"
        and "unresolved_personal_context=true" in index.statement
    )
    assert "private value" not in index.statement


@pytest.mark.asyncio
async def test_promoted_memory_is_retrievable_as_governed_stage_b_target():
    db = DB()
    promoted = await MemoryGovernanceService(db).apply(
        user_id="u",
        session_id="s",
        reasoning_epoch="e",
        candidate=candidate(),
        candidate_index=0,
    )
    broker = ContextBroker(db)
    facts = await broker.retrieve(
        user_id="u",
        context_need=ContextNeed(
            query="existing response preference",
            purpose="update durable personal evidence",
            source_hints=["memory"],
        ),
        stage="B",
        session_id="later",
    )
    governed = [fact for fact in facts if fact.status == "active_governed"]
    assert [fact.ref for fact in governed] == [promoted.memory_id]


def test_stage_b_ranking_respects_ai_source_hint_without_domain_routing():
    facts = [
        ContextFact(
            statement="Active situation with matching personal context",
            source="situations",
        ),
        ContextFact(statement="Current governed preference", source="memory"),
    ]
    selected, _ = rank_evidence(
        facts,
        ContextNeed(query="personal context", source_hints=["memory"], max_items=1),
        anchor="active situation personal context",
        max_items=1,
        max_chars=1000,
    )
    assert [fact.source for fact in selected] == ["memory"]


def test_context_distinguishes_governed_memory_target_from_read_only_evidence():
    governed = SimpleNamespace(
        id="view_1", statement="governed fact", source_refs=["user_memory:mem_owned"]
    )
    readonly = SimpleNamespace(
        id="view_2", statement="derived fact", source_refs=["profile:x"]
    )
    governed_payload = _memory_fact_payload(governed)
    readonly_payload = _memory_fact_payload(readonly)
    assert governed_payload[1:3] == ("mem_owned", "active_governed")
    assert readonly_payload[1].startswith("memory_read_only:")
    assert readonly_payload[2] == "read_only_evidence"


@pytest.mark.asyncio
async def test_loop_reasons_again_from_successful_governance_observation():
    db = DB()
    sess = ConversationSession(id="s", user_id="u", meta={"ai_core": {}})
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "response_mode": "answer",
                "message_to_user": "Lo ricorderò.",
                "memory_candidates": [candidate().model_dump()],
            }
        assert '"decision": "PROMOTE"' in payload and '"persisted": true' in payload
        return {
            "response_mode": "answer",
            "message_to_user": "Terrò presente questa preferenza.",
        }

    result = await run_cognitive_loop(
        sess=sess, user_message="Preferisco risposte concise", db=db, decision_fn=decide
    )
    assert calls == 2 and len(db.memories.docs) == 1
    assert result.ora_text == "Terrò presente questa preferenza."


@pytest.mark.asyncio
async def test_loop_rejects_unpersisted_memory_claim_and_reenters_governance():
    db = DB()
    sess = ConversationSession(id="s", user_id="u", meta={"ai_core": {}})
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"response_mode": "answer", "message_to_user": "Ho preso nota."}
        if calls == 2:
            assert "MEMORY_PERSIST_REQUIRED" in payload
            return {
                "response_mode": "answer",
                "message_to_user": "Procedo con la memoria governata.",
                "memory_candidates": [candidate().model_dump()],
            }
        assert '"decision": "PROMOTE"' in payload and '"persisted": true' in payload
        return {
            "response_mode": "answer",
            "message_to_user": "Terrò presente questa preferenza.",
        }

    result = await run_cognitive_loop(
        sess=sess, user_message="Conserva questa preferenza", db=db, decision_fn=decide
    )
    assert calls == 3 and len(db.memories.docs) == 1
    assert result.ora_text == "Terrò presente questa preferenza."


@pytest.mark.asyncio
async def test_loop_rejects_unpersisted_forget_claim_and_requires_tombstone():
    db = DB()
    existing = await MemoryGovernanceService(db).apply(
        user_id="u",
        session_id="old",
        reasoning_epoch="old",
        candidate=candidate(),
        candidate_index=0,
    )
    sess = ConversationSession(id="s", user_id="u", meta={"ai_core": {}})
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "response_mode": "answer",
                "message_to_user": "Ho rimosso la preferenza memorizzata.",
            }
        if calls == 2:
            assert "MEMORY_PERSIST_REQUIRED" in payload
            return {
                "response_mode": "answer",
                "message_to_user": "Procedo con la rimozione governata.",
                "memory_candidates": [
                    candidate(
                        operation="forget", existing_memory_ref=existing.memory_id
                    ).model_dump()
                ],
            }
        assert (
            '"decision": "FORGET_ALLOWED"' in payload and '"persisted": true' in payload
        )
        return {
            "response_mode": "answer",
            "message_to_user": "La memoria è stata dimenticata.",
        }

    result = await run_cognitive_loop(
        sess=sess, user_message="Dimentica questa preferenza", db=db, decision_fn=decide
    )
    assert calls == 3 and db.memories.docs[0]["status"] == "forgotten"
    assert result.ora_text == "La memoria è stata dimenticata."


@pytest.mark.asyncio
async def test_loop_does_not_contradict_successful_forget_after_active_lookup_is_empty():
    db = DB()
    existing = await MemoryGovernanceService(db).apply(
        user_id="u",
        session_id="old",
        reasoning_epoch="old",
        candidate=candidate(),
        candidate_index=0,
    )
    sess = ConversationSession(id="s", user_id="u", meta={"ai_core": {}})
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "response_mode": "answer",
                "message_to_user": "Procedo.",
                "memory_candidates": [
                    candidate(
                        operation="forget", existing_memory_ref=existing.memory_id
                    ).model_dump()
                ],
            }
        if calls == 2:
            assert '"decision": "FORGET_ALLOWED"' in payload
            return {
                "response_mode": "answer",
                "message_to_user": "Non ho trovato alcuna memoria specifica da dimenticare.",
            }
        assert "MEMORY_RESULT_CONTRADICTION" in payload
        return {
            "response_mode": "answer",
            "message_to_user": "La memoria è stata dimenticata.",
        }

    result = await run_cognitive_loop(
        sess=sess, user_message="Dimentica questa preferenza", db=db, decision_fn=decide
    )
    assert calls == 3 and db.memories.docs[0]["status"] == "forgotten"
    assert result.ora_text == "La memoria è stata dimenticata."


@pytest.mark.asyncio
async def test_loop_persistence_failure_is_observed_before_claim():
    class Broken(Collection):
        async def insert_one(self, doc):
            raise RuntimeError("database unavailable")

    db = DB()
    db.cols["memories"] = Broken()
    sess = ConversationSession(id="s", user_id="u", meta={"ai_core": {}})
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "response_mode": "answer",
                "message_to_user": "Salvato.",
                "memory_candidates": [candidate().model_dump()],
            }
        assert "MEMORY_PERSISTENCE_ERROR" in payload
        return {
            "response_mode": "answer",
            "message_to_user": "Non sono riuscita a salvarlo in memoria; possiamo riprovare.",
        }

    result = await run_cognitive_loop(
        sess=sess, user_message="Ricorda questa preferenza", db=db, decision_fn=decide
    )
    assert calls == 2 and "Non sono riuscita" in result.ora_text


@pytest.mark.asyncio
async def test_terminal_reasoning_budget_never_leaks_unpersisted_memory_claim():
    db = DB()
    sess = ConversationSession(id="s", user_id="u", meta={"ai_core": {}})

    async def decide(system, payload):
        return {
            "response_mode": "answer",
            "message_to_user": "Ho preso nota per il futuro.",
        }

    result = await run_cognitive_loop(
        sess=sess,
        user_message="Ricorda questa preferenza",
        db=db,
        decision_fn=decide,
        max_steps=1,
    )
    assert len(db.memories.docs) == 0
    assert "Non sono riuscita" in result.ora_text
    assert "Ho preso nota" not in result.ora_text
