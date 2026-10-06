from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from situations.models import SituationUpdate
from situations.service import SituationService


OWNER = "alice"


@pytest.mark.asyncio
async def test_conversational_situation_becomes_reviewable_autonomous_goal(monkeypatch):
    """
    Canonical v58 gate:
      user-stated temporary fact -> governed Situation -> factual change envelope
      -> Opportunity AI -> durable autonomous goal -> immediate ambient wake.

    The test uses laundry as a deliberately ordinary example, but no runtime
    branch knows that category or wording. The bridge operates on Situation
    lifecycle only.
    """
    from agent import reasoning as agent_reasoning
    from agent.admission import drain
    from agent.service import AgentService
    from opportunities import reasoning as opportunity_reasoning
    from opportunities import snapshot
    from opportunities.discovery import OpportunityDiscovery
    import life_orchestration.scheduler as scheduler

    db = AsyncMongoMockClient().test
    wake = AsyncMock(return_value=True)
    monkeypatch.setattr(scheduler, "schedule_user_reasoning", wake)

    result = await SituationService(db).apply(
        user_id=OWNER,
        session_id="ces_1",
        reasoning_epoch="epoch_1",
        update=SituationUpdate(
            operation="create",
            summary="Ho steso i panni adesso sul balcone.",
            semantic_kind="attività temporanea con esito atteso",
            temporal_scope=datetime.now(timezone.utc).isoformat(),
            attention_intent="valutare se tempi o condizioni esterne rendono utile ricontrollare i panni",
            facts=["I panni sono stati stesi adesso."],
            source_refs=["user_conversation"],
            source="user_conversation",
        ),
    )
    assert result["status"] == "success"
    assert result["situation"]["attention_intent"] == (
        "valutare se tempi o condizioni esterne rendono utile ricontrollare i panni"
    )
    sid = result["situation"]["id"]
    ref = f"situation:{sid}"

    # The change log stores identity/revision only, not another copy of the
    # conversational content. The Situation remains the governed source.
    change = await db.meaningful_changes.find_one(
        {"owner_id": OWNER, "source": "situations", "entity_ref": ref},
        {"_id": 0},
    )
    assert change is not None
    assert change["kind"] == "situation.created"
    assert change["after"] == "revision:1"
    assert "panni" not in str(change).lower()
    wake.assert_awaited_once_with(OWNER, reason="opportunity_change")

    rows = await snapshot._situations(db, OWNER, datetime.now(timezone.utc))
    assert len(rows) == 1
    assert rows[0]["ref"] == ref
    assert "panni" in rows[0]["what_it_is"].lower()
    assert rows[0]["attention_intent"] == (
        "valutare se tempi o condizioni esterne rendono utile ricontrollare i panni"
    )

    # Keep discovery focused on the real Situation row while exercising its
    # ordinary evidence allow-list and persistence path.
    async def prepared(_db, _owner, *, changes=None):
        situations = await snapshot._situations(_db, _owner, datetime.now(timezone.utc))
        return {
            "situations": situations,
            "what_changed": list(changes or []),
            "temporal": {"hour_bucket": "2026-10-05T10"},
            "unavailable_sources": [],
        }

    monkeypatch.setattr(snapshot, "build", prepared)
    monkeypatch.setattr("opportunities.discovery.COOLDOWN_SECONDS", 0)

    async def scan(state, **kwargs):
        current = state.get("situations") or []
        assert current and current[0]["ref"] == ref
        return {
            "opportunities": [{
                "identity_key": f"temporary-outcome:{sid}",
                "what": "Questa attività ha un esito futuro che ORA può verificare o stimare.",
                "why_it_matters": "Un controllo al momento giusto può evitare una verifica manuale inutile.",
                "why_now": "La situazione è appena iniziata.",
                "initiative": "prepare",
                "what_i_can_do": "Posso seguire il contesto e rivalutare quando serve.",
                "evidence_refs": [ref],
            }]
        }

    monkeypatch.setattr(opportunity_reasoning, "scan", AsyncMock(side_effect=scan))
    reviewed = await OpportunityDiscovery(db).review(OWNER, force=True)
    assert reviewed.ran is True
    assert reviewed.scan is not None
    assert len(reviewed.scan.created) == 1
    opportunity = reviewed.scan.created[0]
    assert opportunity.evidence_refs == [ref]
    assert opportunity.evidence[0].kind == "situation"

    monkeypatch.setattr(agent_reasoning, "decide_goal", AsyncMock(return_value={
        "outcome": "create_goal",
        "objective": "Seguire l'esito futuro della situazione raccontata dall'utente",
        "desired_outcome": "ORA verifica o stima l'esito senza richiedere un nuovo comando",
        "why_now": "La situazione temporanea è appena iniziata.",
        "success_criteria": ["L'esito viene rivalutato usando fonti reali disponibili"],
        "stop_conditions": ["La situazione viene risolta o annullata"],
        "reasoning": "Il follow-up può produrre valore senza chiedere all'utente di dirigere ogni passo.",
    }))
    monkeypatch.setattr(AgentService, "_note_ambient", AsyncMock())

    assert await drain(db, owner_id=OWNER, limit=1) == 1
    goal = await db.agent_goals.find_one(
        {"owner_id": OWNER, "opportunity_id": opportunity.id}, {"_id": 0}
    )
    assert goal is not None
    assert ref in goal["source_refs"]
    assert goal["status"] == "active"
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER,
        "source_ref": f"goal:{goal['id']}",
        "status": "pending",
    }) == 1


@pytest.mark.asyncio
async def test_situation_replay_does_not_enqueue_duplicate_opportunity_change(monkeypatch):
    import life_orchestration.scheduler as scheduler

    db = AsyncMongoMockClient().test
    wake = AsyncMock(return_value=True)
    monkeypatch.setattr(scheduler, "schedule_user_reasoning", wake)
    service = SituationService(db)
    update = SituationUpdate(
        operation="create",
        summary="Sto aspettando un esito.",
        temporal_scope="oggi",
        source_refs=["user_conversation"],
    )

    first = await service.apply(
        user_id=OWNER, session_id="ces_1", update=update, reasoning_epoch="epoch_same"
    )
    replay = await service.apply(
        user_id=OWNER, session_id="ces_1", update=update, reasoning_epoch="epoch_same"
    )

    assert first["status"] == "success"
    assert replay.get("deduped") is True
    assert await db.meaningful_changes.count_documents({"owner_id": OWNER}) == 1
    assert wake.await_count == 1



def test_user_sees_what_ora_will_do_with_a_persisted_situation():
    from conversation_engine.ai_core.loop import _with_situation_handoff

    result = {
        "status": "success",
        "operation": "create",
        "situation": {
            "id": "sit_laundry",
            "attention_intent": (
                "valutare se tempi o condizioni esterne rendono utile "
                "ricontrollare i panni"
            ),
        },
    }

    visible = _with_situation_handoff("Ok.", result)

    assert not visible.lower().startswith("ok")
    assert "non risulta ancora un controllo automatico programmato" in visible.lower()
    assert "sotto controllo" not in visible.lower()
    assert "tempi o condizioni esterne" in visible.lower()
    assert "ricontrollare i panni" in visible.lower()


def test_situation_handoff_still_explains_generic_review_without_attention_intent():
    from conversation_engine.ai_core.loop import _with_situation_handoff

    result = {
        "status": "success",
        "operation": "create",
        "situation": {"id": "sit_plain", "attention_intent": None},
    }

    visible = _with_situation_handoff("Ok.", result)
    assert not visible.lower().startswith("ok")
    assert "situazione" in visible.lower()
    assert "non risulta ancora un controllo automatico programmato" in visible.lower()
    assert "rivaluter" not in visible.lower()


def test_resolved_situation_does_not_claim_future_attention():
    from conversation_engine.ai_core.loop import _with_situation_handoff

    result = {
        "status": "success",
        "operation": "resolve",
        "situation": {
            "id": "sit_done",
            "attention_intent": "ricontrollare qualcosa in futuro",
        },
    }

    assert _with_situation_handoff("Fatto.", result) == "Fatto."
