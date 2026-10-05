from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.service import AgentService
from agent.source_refs import expand_opportunity_source_refs
from situations.models import SituationEvent, SituationState
from situations.repository import SituationRepository


OWNER = "alice"


@pytest.mark.asyncio
async def test_situation_evidence_expands_owned_linked_refs_only():
    db = AsyncMongoMockClient().test
    repo = SituationRepository(db)

    own = SituationState(
        id="sit_owned",
        user_id=OWNER,
        summary="Una cosa temporanea è in corso a Casa.",
        linked_object_refs=[
            "place:home_1",
            "calendar:event_1",
            "not-a-canonical-ref",
        ],
    )
    foreign = SituationState(
        id="sit_foreign",
        user_id="bob",
        summary="Dato di Bob.",
        linked_object_refs=["place:bob_home"],
    )
    await repo.insert(own)
    await repo.insert(foreign)

    own_refs = await expand_opportunity_source_refs(
        db,
        OWNER,
        [{"kind": "situation", "ref": "situation:sit_owned"}],
    )
    assert own_refs == [
        "situation:sit_owned",
        "place:home_1",
        "calendar:event_1",
    ]

    foreign_refs = await expand_opportunity_source_refs(
        db,
        OWNER,
        [{"kind": "situation", "ref": "situation:sit_foreign"}],
    )
    assert foreign_refs == ["situation:sit_foreign"]
    assert "place:bob_home" not in foreign_refs


@pytest.mark.asyncio
async def test_agent_rereads_exact_situation_preview_without_history(monkeypatch):
    from agent import reasoning

    db = AsyncMongoMockClient().test
    repo = SituationRepository(db)
    state = SituationState(
        id="sit_laundry",
        user_id=OWNER,
        session_id="ces_private",
        summary="I panni sono stesi sul balcone di Casa.",
        semantic_kind="attività temporanea",
        temporal_scope="iniziata questa mattina",
        participants=[],
        constraints=["Devono asciugarsi prima di sera."],
        facts=["I panni sono all'aperto."],
        assumptions=["Il balcone è scoperto."],
        linked_object_refs=["place:home_1"],
        history=[
            SituationEvent(
                revision=1,
                operation="create",
                source="user_conversation",
                changes={"private_transcript": "SEGRETO-NON-DEVE-USCIRE"},
            )
        ],
        applied_epochs=["epoch_private"],
    )
    await repo.insert(state)

    captured = {}

    async def decide(payload, *, language="it"):
        captured["payload"] = payload
        return {
            "outcome": "no_goal",
            "reasoning": "Test: nessun goal ulteriore.",
        }

    monkeypatch.setattr(reasoning, "decide_goal", decide)

    result = await AgentService(db).consider(
        OWNER,
        situation={
            "what": "Seguire l'esito della situazione temporanea.",
            "why_it_matters": "Può servire un controllo successivo.",
        },
        origin="agent_initiated",
        source_refs=["situation:sit_laundry"],
    )

    assert result["outcome"] == "no_goal"
    context = captured["payload"]["source_context"]
    assert len(context) == 1
    row = context[0]
    assert row["ref"] == "situation:sit_laundry"
    assert row["summary"] == "I panni sono stesi sul balcone di Casa."
    assert row["facts"] == ["I panni sono all'aperto."]
    assert row["constraints"] == ["Devono asciugarsi prima di sera."]
    assert row["temporal_scope"] == "iniziata questa mattina"
    assert row["linked_object_refs"] == ["place:home_1"]
    assert captured["payload"]["source_context_unavailable"] is False

    serialized = str(context)
    assert "SEGRETO-NON-DEVE-USCIRE" not in serialized
    assert "ces_private" not in serialized
    assert "epoch_private" not in serialized
    assert "history" not in serialized


@pytest.mark.asyncio
async def test_foreign_or_missing_situation_is_never_loaded_as_context(monkeypatch):
    from agent import reasoning

    db = AsyncMongoMockClient().test
    await SituationRepository(db).insert(SituationState(
        id="sit_bob",
        user_id="bob",
        summary="Informazione privata di Bob.",
        facts=["BOB-PRIVATE"],
    ))

    captured = {}

    async def decide(payload, *, language="it"):
        captured["payload"] = payload
        return {"outcome": "no_goal", "reasoning": "Niente da fare."}

    monkeypatch.setattr(reasoning, "decide_goal", decide)

    result = await AgentService(db).consider(
        OWNER,
        situation={"what": "Controllo"},
        source_refs=["situation:sit_bob", "situation:sit_missing"],
    )

    assert result["outcome"] == "no_goal"
    assert captured["payload"]["source_context"] == []
    assert captured["payload"]["source_context_unavailable"] is True
    assert "BOB-PRIVATE" not in str(captured["payload"])
