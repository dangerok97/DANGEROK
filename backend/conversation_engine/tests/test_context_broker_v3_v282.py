"""V2.8.2 — AI-owned ContextNeed and bounded Life Context evidence."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conversation_engine.ai_core.context_broker import ContextBroker, validate_context_need
from conversation_engine.ai_core.context_sources import (
    ContextSource,
    ContextSourceRegistry,
    rank_evidence,
)
from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.models import ContextFact, ContextNeed
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.tests.test_ai_native_situation_v281 import FakeDB, _create
from life_os.models import LifeOsPlan, PlanItem
from situations.service import SituationService


def fact(text: str, source: str, authority: str = "user-said") -> ContextFact:
    return ContextFact(
        statement=text,
        fact=text,
        source=source,
        authority=authority,
        ref=f"{source}:{abs(hash(text))}",
        provenance=[source],
    )


def test_context_need_contract_and_legacy_alias_are_backward_compatible():
    need = ContextNeed(
        query="Which current commitments constrain tomorrow morning?",
        purpose="improve timing advice",
        desired_evidence=["commitments", "existing plans"],
        max_items=5,
    )
    assert validate_context_need(need) == (True, "ok")
    out = validate_decision(
        {
            "response_mode": "context",
            "user_intent_summary": "timing advice",
            "context_need": need.model_dump(),
        },
        tools=ToolRegistry(),
    )
    assert out.ok and out.decision.context_need.query == need.query
    legacy = validate_decision(
        {"response_mode": "context", "context_query": "relevant personal timing facts"},
        tools=ToolRegistry(),
    )
    assert legacy.ok and legacy.decision.context_need


@pytest.mark.asyncio
async def test_semantic_need_uses_same_registry_for_unrelated_scenarios():
    registry = ContextSourceRegistry(object())

    async def source_a(user_id, need, session_id):
        return [fact("Morning commitment ending at 09:00", "structured")]

    async def source_b(user_id, need, session_id):
        return [fact("Existing outline has three sections", "artifact", "document-backed")]

    registry._sources = {}
    registry.register(ContextSource(
        "structured", "current commitments and bounded schedules", "system-structured",
        "personal", "temporal", source_a,
    ))
    registry.register(ContextSource(
        "artifact", "saved material and personal work products", "document-backed",
        "sensitive", "mixed", source_b,
    ))
    first, _ = registry.select(ContextNeed(
        query="What constrains my available time tomorrow?", purpose="timing"
    ), maximum=2)
    second, _ = registry.select(ContextNeed(
        query="What material already exists for this work?", purpose="planning"
    ), maximum=2)
    assert {x.name for x in first} == {x.name for x in second}


def test_conflicts_and_authority_remain_distinct():
    candidates = [
        fact("Residence is Tarquinia", "profile", "user-confirmed"),
        fact("Recent device presence label is Roma", "presence", "device-signal"),
        fact("User often stays in Viterbo", "conversation", "user-said"),
    ]
    selected, _ = rank_evidence(
        candidates,
        ContextNeed(query="Where should departure assumptions come from?", purpose="timing"),
        anchor="current situation tomorrow",
        max_items=6,
        max_chars=2000,
    )
    assert len(selected) == 3
    assert len({x.authority for x in selected}) == 3
    assert len({x.source for x in selected}) == 3


def test_budget_and_source_diversity_are_enforced():
    candidates = [fact(f"Similar profile evidence {i}", "profile") for i in range(8)]
    candidates += [fact("Active plan evidence", "life_os", "system-structured")]
    selected, exhausted = rank_evidence(
        candidates,
        ContextNeed(query="relevant evidence", purpose="reasoning", max_items=3),
        anchor="",
        max_items=3,
        max_chars=700,
    )
    assert exhausted and len(selected) <= 3
    assert any(x.source == "life_os" for x in selected)


@pytest.mark.asyncio
async def test_source_failure_is_not_indistinguishable_from_empty():
    db = FakeDB()
    broker = ContextBroker(db)

    async def broken(user_id, need, session_id):
        raise RuntimeError("provider unavailable")

    broker.registry._sources = {
        "broken": ContextSource(
            "broken", "generic personal evidence", "unknown", "personal",
            "mixed", broken,
        )
    }
    result = await broker.retrieve(
        user_id="u1",
        stage="B",
        context_need=ContextNeed(query="relevant personal evidence", purpose="answer"),
    )
    assert result == []
    assert broker.last_report.status == "source_unavailable"
    assert broker.last_report.outcomes[0].status == "source_unavailable"


@pytest.mark.asyncio
async def test_cross_session_situation_is_retrieved_as_semantic_anchor():
    db = FakeDB()
    await SituationService(db).apply(
        user_id="u1", session_id="old_session",
        update=_create("Preparare un impegno importante", temporal_scope="domani"),
        reasoning_epoch="old_turn",
    )
    broker = ContextBroker(db)
    broker.registry._sources = {
        "situations": broker.registry.get("situations")
    }
    result = await broker.retrieve(
        user_id="u1", session_id="new_session", stage="B",
        context_need=ContextNeed(
            query="What active situation constrains tomorrow?",
            purpose="continue reasoning across sessions",
        ),
    )
    assert len(result) == 1
    assert result[0].source == "situations"
    assert "important" in result[0].statement.lower()


@pytest.mark.asyncio
async def test_life_os_source_returns_minimized_user_owned_evidence():
    db = FakeDB()
    await db["life_os_plans"].insert_one(LifeOsPlan(
        id="plan_1", user_id="u1", summary="Prepare current commitment",
        constraints=["five minutes"], items=[PlanItem(id="i1", title="Draft outline")],
    ).model_dump())
    registry = ContextSourceRegistry(db)
    result = await registry.get("life_os").retrieve(
        "u1", ContextNeed(query="What is already planned?", purpose="avoid duplication"), None
    )
    dumped = json.dumps([x.model_dump() for x in result])
    assert len(result) == 1 and "Draft outline" in dumped
    assert "user_id" not in dumped and "meta" not in dumped


def test_presence_is_capability_gated_and_no_raw_gps_can_enter_automatic_sources():
    registry = ContextSourceRegistry(FakeDB())
    selected, excluded = registry.select(
        ContextNeed(query="What context matters now?", purpose="reasoning"), maximum=8
    )
    assert "presence" not in {x.name for x in selected}
    assert excluded["presence"] == "capability_required"


def test_evidence_schema_is_minimized_and_provenance_preserved():
    evidence = fact("User-confirmed constraint", "profile", "user-confirmed")
    dumped = evidence.model_dump()
    assert dumped["provenance"] == ["profile"]
    assert dumped["sensitivity"] == "personal"
    assert not ({"password", "token", "secret", "email"} & set(dumped))


@pytest.mark.asyncio
async def test_stage_a_is_bounded_and_does_not_read_profile_or_memory():
    db = FakeDB()
    await SituationService(db).apply(
        user_id="u1", session_id="s1",
        update=_create("Impegno corrente", temporal_scope="domani"),
        reasoning_epoch="stage_a",
    )
    broker = ContextBroker(db)
    with patch.object(
        broker, "_profile_facts", new=AsyncMock(side_effect=AssertionError)
    ), patch.object(
        broker, "_memory_facts", new=AsyncMock(side_effect=AssertionError)
    ):
        result = await broker.retrieve(user_id="u1", session_id="s1", stage="A")
    assert len(result) <= 4
    assert any(item.source == "situation" for item in result)
    assert "memories" not in db._cols


@pytest.mark.asyncio
async def test_memory_is_read_only_evidence_and_never_auto_written():
    db = FakeDB()
    service = MagicMock()
    service.get_life_memory = AsyncMock(return_value=SimpleNamespace(memories=[
        SimpleNamespace(
            id="m1", statement="Preferenza confermata dall'utente",
            authority="user-confirmed", status="known", updated_at=None,
        )
    ]))
    with patch(
        "life_memory.service.get_life_memory_service", return_value=service
    ):
        result = await ContextSourceRegistry(db).get("memory").retrieve(
            "u1", ContextNeed(query="preferenze rilevanti", purpose="personalizzare"), None
        )
    assert len(result) == 1 and result[0].source == "memory"
    assert result[0].authority == "user-confirmed"
    assert "memories" not in db._cols
