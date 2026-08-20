"""V2.8.5 — Life Context Graph: AI-authored, system-governed relationships
between canonical refs. Deterministic coverage A-T per CPO sprint spec.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from context_graph.models import ContextEdgeUpdate, is_recognized_ref
from context_graph.service import ContextGraphService
from conversation_engine.ai_core.context_sources import (
    GRAPH_MAX_DEPTH,
    GRAPH_MAX_EDGES,
    GRAPH_MAX_SEEDS,
    ContextSourceRegistry,
)
from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.ai_core.models import CognitiveDecision, ContextNeed
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.models import ConversationSession
from conversation_engine.tests.test_ai_native_situation_v281 import FakeDB
from situations.models import SituationUpdate
from situations.service import SituationService


def _edge_update(**kw) -> ContextEdgeUpdate:
    base = dict(
        operation="create",
        subject_ref="goal:goal_house1",
        predicate="depends_on",
        object_ref="plan:lop_house1",
        confidence=0.7,
        authority="structured",
    )
    base.update(kw)
    return ContextEdgeUpdate.model_validate(base)


def _decision(mode="answer", **extra):
    raw = {
        "response_mode": mode,
        "user_intent_summary": "arbitrary life relationship",
        "reasoning_status": "needs_user_input" if mode == "ask" else "enough_information",
        "message_to_user": "Ok." if mode != "ask" else None,
        "question": "Serve un dettaglio?" if mode == "ask" else None,
    }
    raw.update(extra)
    return raw


def _sess(user_id="u-v285"):
    return ConversationSession(user_id=user_id, meta={"ui_mode": "ai_core", "ai_core": {}})


def _scripted(items):
    queue = [deepcopy(x) for x in items]

    async def decide(_system, _user):
        return queue.pop(0)

    return decide


# A — creation between two canonical refs
@pytest.mark.asyncio
async def test_a_creation_between_canonical_refs():
    db = FakeDB()
    svc = ContextGraphService(db)
    results = await svc.apply(
        user_id="u1", session_id="s1", updates=[_edge_update()], reasoning_epoch="e1"
    )
    assert results[0]["decision"] == "CREATED"
    assert results[0]["persisted"] is True
    edge = results[0]["edge"]
    assert edge["subject_ref"] == "goal:goal_house1"
    assert edge["object_ref"] == "plan:lop_house1"
    assert edge["predicate"] == "depends_on"


# B — same-epoch idempotency
@pytest.mark.asyncio
async def test_b_idempotent_same_epoch():
    db = FakeDB()
    svc = ContextGraphService(db)
    r1 = await svc.apply(
        user_id="u1", session_id="s1", updates=[_edge_update()], reasoning_epoch="eX"
    )
    r2 = await svc.apply(
        user_id="u1", session_id="s1", updates=[_edge_update()], reasoning_epoch="eX"
    )
    assert r1[0]["decision"] == "CREATED"
    assert r2[0]["decision"] == "IDEMPOTENT_REPLAY"
    assert r2[0]["edge_id"] == r1[0]["edge_id"]
    assert len(db["context_edges"].docs) == 1


# C — cross-turn update (different epoch bumps revision)
@pytest.mark.asyncio
async def test_c_cross_turn_update_bumps_revision():
    db = FakeDB()
    svc = ContextGraphService(db)
    created = await svc.apply(
        user_id="u1", session_id="s1", updates=[_edge_update()], reasoning_epoch="e1"
    )
    eid = created[0]["edge_id"]
    updated = await svc.apply(
        user_id="u1",
        session_id="s2",
        updates=[_edge_update(operation="update", edge_id=eid, confidence=0.9, subject_ref=None, predicate=None, object_ref=None)],
        reasoning_epoch="e2",
    )
    assert updated[0]["decision"] == "UPDATED"
    assert updated[0]["edge"]["revision"] == 2
    assert updated[0]["edge"]["confidence"] == 0.9


# D — cross-session retrieval (edges are not session-scoped)
@pytest.mark.asyncio
async def test_d_cross_session_retrieval():
    db = FakeDB()
    svc = ContextGraphService(db)
    await svc.apply(
        user_id="u1", session_id="session-A", updates=[_edge_update()], reasoning_epoch="e1"
    )
    # A brand new session/turn queries the same user's graph with no session tie.
    found = await svc.relevant_edges("u1", ["goal:goal_house1"])
    assert len(found) == 1
    assert found[0].object_ref == "plan:lop_house1"


# E — bounded traversal (depth stays 2 hops, does not chase the whole chain)
@pytest.mark.asyncio
async def test_e_bounded_traversal_depth():
    db = FakeDB()
    svc = ContextGraphService(db)
    # Chain: goal -> plan -> object -> document (3 edges)
    await svc.apply(
        user_id="u1", session_id="s1",
        updates=[_edge_update(subject_ref="goal:g1", predicate="depends_on", object_ref="plan:p1")],
        reasoning_epoch="e1",
    )
    await svc.apply(
        user_id="u1", session_id="s1",
        updates=[_edge_update(subject_ref="plan:p1", predicate="produces", object_ref="object:o1")],
        reasoning_epoch="e2",
    )
    await svc.apply(
        user_id="u1", session_id="s1",
        updates=[_edge_update(subject_ref="object:o1", predicate="evidenced_by", object_ref="document:d1")],
        reasoning_epoch="e3",
    )
    registry = ContextSourceRegistry(db)
    facts = await registry._life_context_graph(
        "u1", ContextNeed(query="goal:g1", desired_evidence=["goal:g1"]), None
    )
    refs_touched = {f.statement for f in facts}
    assert any("plan:p1" in s for s in refs_touched)
    assert any("object:o1" in s for s in refs_touched)
    # depth 2 from seed goal:g1 must not reach document:d1 (that is a 3rd hop)
    assert not any("document:d1" in s for s in refs_touched)
    assert GRAPH_MAX_DEPTH == 2


# F — ownership isolation
@pytest.mark.asyncio
async def test_f_ownership_isolation():
    db = FakeDB()
    svc = ContextGraphService(db)
    created = await svc.apply(
        user_id="owner", session_id="s1", updates=[_edge_update()], reasoning_epoch="e1"
    )
    eid = created[0]["edge_id"]
    # Another user cannot retrieve it...
    found = await svc.relevant_edges("intruder", ["goal:goal_house1"])
    assert found == []
    # ...nor mutate it.
    mutated = await svc.apply(
        user_id="intruder",
        session_id="s2",
        updates=[_edge_update(operation="deactivate", edge_id=eid, subject_ref=None, predicate=None, object_ref=None)],
        reasoning_epoch="e2",
    )
    assert mutated[0]["decision"] == "NOT_FOUND_OR_NOT_OWNED"


# G — supersession (conflicting object for same subject+predicate)
@pytest.mark.asyncio
async def test_g_supersession():
    db = FakeDB()
    svc = ContextGraphService(db)
    first = await svc.apply(
        user_id="u1", session_id="s1",
        updates=[_edge_update(subject_ref="goal:g1", predicate="depends_on", object_ref="plan:planA")],
        reasoning_epoch="e1",
    )
    old_id = first[0]["edge_id"]
    conflict = await svc.apply(
        user_id="u1", session_id="s2",
        updates=[_edge_update(subject_ref="goal:g1", predicate="depends_on", object_ref="plan:planB")],
        reasoning_epoch="e2",
    )
    assert conflict[0]["decision"] == "REQUIRES_SUPERSESSION"
    assert conflict[0]["edge_id"] == old_id
    resolved = await svc.apply(
        user_id="u1", session_id="s3",
        updates=[
            _edge_update(
                operation="supersede", edge_id=old_id,
                subject_ref="goal:g1", predicate="depends_on", object_ref="plan:planB",
            )
        ],
        reasoning_epoch="e3",
    )
    assert resolved[0]["decision"] == "SUPERSEDED"
    active = await svc.relevant_edges("u1", ["goal:g1"])
    active_for_pair = [e for e in active if e.predicate == "depends_on" and e.status == "active"]
    assert len(active_for_pair) == 1
    assert active_for_pair[0].object_ref == "plan:planB"


# H — conflict/history preservation (superseded edge is never deleted)
@pytest.mark.asyncio
async def test_h_conflict_history_preserved():
    db = FakeDB()
    svc = ContextGraphService(db)
    first = await svc.apply(
        user_id="u1", session_id="s1",
        updates=[_edge_update(subject_ref="goal:g1", predicate="depends_on", object_ref="plan:planA")],
        reasoning_epoch="e1",
    )
    old_id = first[0]["edge_id"]
    await svc.apply(
        user_id="u1", session_id="s2",
        updates=[
            _edge_update(
                operation="supersede", edge_id=old_id,
                subject_ref="goal:g1", predicate="depends_on", object_ref="plan:planB",
            )
        ],
        reasoning_epoch="e2",
    )
    old_edge = await svc.repo.get("u1", old_id)
    assert old_edge is not None  # never deleted
    assert old_edge.status == "superseded"
    assert old_edge.superseded_by is not None
    assert len(old_edge.history) >= 1


# I — temporary Situation is not auto-promoted to a durable graph edge
@pytest.mark.asyncio
async def test_i_temporary_situation_not_auto_promoted():
    db = FakeDB()
    await SituationService(db).apply(
        user_id="u1", session_id="s1",
        update=SituationUpdate(
            operation="create", summary="Domani vado a un evento",
            source_refs=["user_conversation"],
        ),
        reasoning_epoch="e1",
    )
    assert db["context_edges"].docs == []


# J — inferred authority is preserved honestly, never silently upgraded
@pytest.mark.asyncio
async def test_j_inference_not_silently_promoted():
    db = FakeDB()
    svc = ContextGraphService(db)
    result = await svc.apply(
        user_id="u1", session_id="s1",
        updates=[_edge_update(authority="inferred", confidence=0.4)],
        reasoning_epoch="e1",
    )
    assert result[0]["edge"]["authority"] == "inferred"
    assert result[0]["edge"]["confidence"] == 0.4


# K — a graph edge never bypasses Memory governance
@pytest.mark.asyncio
async def test_k_memory_relationship_no_governance_bypass():
    db = FakeDB()
    svc = ContextGraphService(db)
    await svc.apply(
        user_id="u1", session_id="s1",
        updates=[
            _edge_update(
                subject_ref="situation:sit_1",
                predicate="evidenced_by",
                object_ref="mem_abc123def456",
            )
        ],
        reasoning_epoch="e1",
    )
    # The edge only records a pointer; it never writes/creates a Memory doc.
    assert db["memories"].docs == []


# L — file evidence stays a bounded pointer, never raw untrusted content
def test_l_file_evidence_is_bounded_not_raw_content():
    oversized_summary = "x" * 500
    out = validate_decision(
        _decision(
            context_graph_updates=[
                {
                    "operation": "create",
                    "subject_ref": "situation:sit_1",
                    "predicate": "evidenced_by",
                    "object_ref": "document:doc_1",
                    "semantic_summary": oversized_summary,
                }
            ]
        ),
        tools=ToolRegistry(),
    )
    assert out.ok
    assert out.decision.context_graph_updates == []
    assert "bad_context_graph_update" in out.errors
    assert "content" not in ContextEdgeUpdate.model_fields
    assert "text" not in ContextEdgeUpdate.model_fields


# M — presence is never auto-promoted with raw coordinates
def test_m_presence_never_carries_raw_gps():
    assert is_recognized_ref("presence:current")
    edge = _edge_update(
        subject_ref="situation:sit_1", predicate="located_near", object_ref="presence:current"
    )
    dumped = edge.model_dump()
    for key in dumped:
        assert key.lower() not in ("latitude", "longitude", "lat", "lon", "lng", "coordinates")


# N — persistence-failure honesty: no claim without a persisted observation
@pytest.mark.asyncio
async def test_n_no_false_link_claim_without_persistence():
    sess = _sess()
    result = await run_cognitive_loop(
        sess=sess,
        user_message="Collega questi due elementi.",
        decision_fn=_scripted(
            [
                _decision(message_to_user="Ho collegato i due elementi."),
                _decision(message_to_user="Non ho potuto salvare il collegamento ora."),
            ]
        ),
    )
    assert "collegat" not in result.ora_text.lower()


# O — ContextNeed -> graph retrieval -> reasoning re-entry
@pytest.mark.asyncio
async def test_o_context_need_triggers_graph_retrieval_reentry():
    db = FakeDB()
    svc = ContextGraphService(db)
    await svc.apply(
        user_id="u-v285", session_id="s1",
        updates=[_edge_update(subject_ref="goal:goal_house1", predicate="depends_on", object_ref="plan:lop_house1")],
        reasoning_epoch="e1",
    )
    sess = _sess()
    result = await run_cognitive_loop(
        sess=sess,
        user_message="Cosa manca ancora per quella cosa della casa?",
        db=db,
        decision_fn=_scripted(
            [
                _decision(
                    "context",
                    message_to_user=None,
                    context_need={
                        "query": "relazioni collegate al goal della casa",
                        "source_hints": ["life_context_graph"],
                        "desired_evidence": ["goal:goal_house1"],
                        "max_items": 6,
                    },
                ),
                _decision(message_to_user="Manca ancora il piano finanziario."),
            ]
        ),
    )
    assert result.mode == "answer"
    assert result.trace.get("context_graph_calls", 0) >= 1


# P — uncertainty retrieval strategy uses graph context before asking again
@pytest.mark.asyncio
async def test_p_uncertainty_retrieve_before_clarification():
    db = FakeDB()
    svc = ContextGraphService(db)
    await svc.apply(
        user_id="u-v285", session_id="s1",
        updates=[_edge_update(subject_ref="goal:goal_house1", predicate="depends_on", object_ref="plan:lop_house1")],
        reasoning_epoch="e1",
    )
    sess = _sess()
    result = await run_cognitive_loop(
        sess=sess,
        user_message="Per quella cosa della casa, cosa mi manca ancora?",
        db=db,
        decision_fn=_scripted(
            [
                _decision(
                    "context",
                    message_to_user=None,
                    context_need={
                        "query": "cosa e' collegato al goal della casa",
                        "source_hints": ["life_context_graph"],
                        "desired_evidence": ["goal:goal_house1"],
                    },
                    uncertainty={
                        "level": 0.4,
                        "missing_information": [
                            {
                                "ref": "house-goal-links",
                                "description": "what is linked to the house goal",
                                "importance": 0.6,
                                "blocking": False,
                                "strategy": "retrieve",
                            }
                        ],
                    },
                ),
                _decision(message_to_user="Trovato: manca il piano finanziario."),
            ]
        ),
    )
    assert result.mode == "answer"
    assert result.trace.get("clarification_context_attempts", 0) >= 1
    # Never fell back to asking the user again this turn.
    assert result.mode != "ask"


# Q — arbitrary, deliberately non travel/study/medical/mortgage scenario
@pytest.mark.asyncio
async def test_q_arbitrary_life_scenario_same_code_path():
    db = FakeDB()
    svc = ContextGraphService(db)
    result = await svc.apply(
        user_id="u1", session_id="s1",
        updates=[
            _edge_update(
                subject_ref="situation:sit_dinner1",
                predicate="hosted_with",
                object_ref="goal:goal_evening1",
                semantic_summary="Cena informale organizzata con un amico",
            )
        ],
        reasoning_epoch="e1",
    )
    assert result[0]["decision"] == "CREATED"


# R — no domain router / no closed relationship vocabulary in production code
def test_r_no_domain_router_in_graph_module():
    import re

    banned_words = [
        "travel", "trip", "vacation", "study", "medical", "mortgage",
        "house", "home", "car", "work", "presentation",
    ]
    banned_phrases = [
        "TravelRelationship", "StudyRelationship", "MortgageRelationship",
        "CarRelationship", "WorkRelationship", "MedicalRelationship",
        "RelationType.OWNS", "if predicate ==",
    ]
    root = Path(__file__).resolve().parents[2] / "context_graph"
    for path in root.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        for w in banned_words:
            assert not re.search(rf"\b{w}\b", src, re.IGNORECASE), (
                f"{w!r} found as a whole word in {path.name}"
            )
        for p in banned_phrases:
            assert p not in src, f"{p} found in {path.name}"


# S — payload/edge-count budget respected under load
@pytest.mark.asyncio
async def test_s_payload_budget_respected():
    db = FakeDB()
    svc = ContextGraphService(db)
    for i in range(GRAPH_MAX_EDGES + 8):
        await svc.apply(
            user_id="u1", session_id="s1",
            updates=[
                _edge_update(
                    subject_ref="goal:g_hub", predicate=f"relates_{i}", object_ref=f"plan:p_{i}"
                )
            ],
            reasoning_epoch=f"e{i}",
        )
    registry = ContextSourceRegistry(db)
    facts = await registry._life_context_graph(
        "u1", ContextNeed(query="goal:g_hub", desired_evidence=["goal:g_hub"]), None
    )
    assert len(facts) <= GRAPH_MAX_EDGES
    assert GRAPH_MAX_SEEDS <= 6


# T — legacy CognitiveDecision without context_graph_updates still works
def test_t_legacy_decision_without_graph_updates():
    out = validate_decision(
        {
            "response_mode": "answer",
            "user_intent_summary": "legacy shape, no graph field at all",
            "reasoning_status": "enough_information",
            "message_to_user": "Ok.",
        },
        tools=ToolRegistry(),
    )
    assert out.ok
    assert out.decision.context_graph_updates == []
    decision = CognitiveDecision.model_validate(
        {"response_mode": "answer", "message_to_user": "Ok."}
    )
    assert decision.context_graph_updates == []
