"""Phase 1 — persisted turns resume without re-executing a delivered request.

The main scenarios use the real database boundary, orchestrator, cognitive
loop and memo capability with scripted model decisions. A focused lifecycle
test supplies client-action results; every user and fact is synthetic.
"""
from copy import deepcopy

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.orchestrator import AICoreOrchestrator
from conversation_engine.models import ConversationSession
from conversation_engine.repository import ConversationRepository
from memos.service import RecurringMemoService


async def session_in(db, owner="synthetic-owner"):
    sess = ConversationSession(
        user_id=owner,
        engine_version="ai-core-1.0",
        meta={"ui_mode": "ai_core", "ai_core": {}},
    )
    await ConversationRepository(db).insert(sess)
    return sess


def answer(text):
    return {
        "response_mode": "answer",
        "reasoning_status": "enough_information",
        "message_to_user": text,
        "situation_update": {"operation": "none"},
    }


@pytest.mark.asyncio
async def test_lost_response_retry_after_rehydration_does_not_repeat_model_or_memo(monkeypatch):
    db = AsyncMongoMockClient().phase1_resume_memo
    sess = await session_in(db)
    await RecurringMemoService(db).ensure_indexes()
    await db.memories.insert_one({
        "id": "mem_synthetic_birthday", "user_id": sess.user_id,
        "status": "active", "kind": "birthday",
        "statement": "Il 13 marzo è il compleanno di Elena.",
        "value": {"person": "Elena", "month": 3, "day": 13},
    })
    decisions = 0
    writes = 0
    real_save = RecurringMemoService.save_annual

    async def counted_save(self, *args, **kwargs):
        nonlocal writes
        writes += 1
        return await real_save(self, *args, **kwargs)

    monkeypatch.setattr(RecurringMemoService, "save_annual", counted_save)

    async def decide(system, payload):
        nonlocal decisions
        decisions += 1
        if decisions % 2:
            return {
                "response_mode": "tool",
                "reasoning_status": "needs_tool",
                "tool_call": {
                    "capability": "save_recurring_memo",
                    "arguments": {
                        "memory_ref": "mem_synthetic_birthday", "category": "birthday",
                        "label": "Compleanno di Elena", "person": "Elena",
                        "month": 3, "day": 13, "timezone": "Europe/Rome",
                        "remind_hour_local": 9,
                    },
                },
                "situation_update": {"operation": "none"},
            }
        return answer("Te lo ricorderò ogni 13 marzo.")

    first = await AICoreOrchestrator(db, decision_fn=decide).message(
        sess.user_id, sess.id, text="Ricordami il compleanno di Elena ogni anno.",
        client_message_id="memo-message",
    )
    assert first["ok"] and not first["error"]
    assert writes == 1 and decisions == 2
    stored = await ConversationRepository(db).get(sess.user_id, sess.id)
    assert stored is not sess  # New model parsed from the database document.
    assert len(stored.history) == 2
    memo_before = await db.recurring_memos.find_one({"owner_id": sess.user_id})

    # A new service has no in-memory reference to the completed turn.
    replay = await AICoreOrchestrator(db, decision_fn=decide).message(
        sess.user_id, sess.id, text="Ricordami il compleanno di Elena ogni anno.",
        client_message_id="memo-message",
    )
    assert decisions == 2, "a completed request must not reach the model again"
    assert writes == 1, "the annual schedule must not be rewritten by a retry"
    assert replay == first
    assert await db.recurring_memos.find_one({"owner_id": sess.user_id}) == memo_before
    assert await db.recurring_memos.count_documents({"owner_id": sess.user_id}) == 1
    after = await ConversationRepository(db).get(sess.user_id, sess.id)
    assert after.model_dump() == stored.model_dump()


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["text", "attachments", "response_channel"])
async def test_same_id_with_changed_request_is_rejected_before_cognition(changed):
    db = AsyncMongoMockClient().phase1_resume_conflict
    sess = await session_in(db)
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        return answer("Risposta sintetica.")

    # The mismatch lies beyond the old 400-character history truncation.
    original = {"text": "Contesto " + "x" * 410 + " prima", "response_channel": "text"}
    orch = AICoreOrchestrator(db, decision_fn=decide)
    first = await orch.message(sess.user_id, sess.id, client_message_id="same-id", **original)
    assert first["ok"]
    before = await ConversationRepository(db).get(sess.user_id, sess.id)
    different = dict(original)
    if changed == "text":
        different["text"] = original["text"][:-5] + "dopo"
    elif changed == "attachments":
        different["attachments"] = [{"file_id": "synthetic-new-file"}]
    else:
        different["response_channel"] = "voice"
    rejected = await AICoreOrchestrator(db, decision_fn=decide).message(
        sess.user_id, sess.id, client_message_id="same-id", **different,
    )
    assert rejected == {"ok": False, "error": "client_message_id_conflict"}
    assert calls == 1
    after = await ConversationRepository(db).get(sess.user_id, sess.id)
    assert after.model_dump() == before.model_dump()


@pytest.mark.asyncio
async def test_identical_text_with_new_id_runs_and_old_id_replays_its_own_answer():
    db = AsyncMongoMockClient().phase1_resume_message_identity
    sess = await session_in(db)
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        return answer(f"Risposta sintetica numero {calls}.")

    orch = AICoreOrchestrator(db, decision_fn=decide)
    first = await orch.message(sess.user_id, sess.id, text="Continua.", client_message_id="one")
    second = await orch.message(sess.user_id, sess.id, text="Continua.", client_message_id="two")
    assert calls == 2 and first["ora_text"] != second["ora_text"]
    replay = await AICoreOrchestrator(db, decision_fn=decide).message(
        sess.user_id, sess.id, text="Continua.", client_message_id="one",
    )
    assert replay == first, "the last answer in the session may belong to another message"
    assert calls == 2
    assert len((await ConversationRepository(db).get(sess.user_id, sess.id)).history) == 4


@pytest.mark.asyncio
async def test_replay_and_resume_token_remain_owner_scoped():
    db = AsyncMongoMockClient().phase1_resume_owners
    owner = await session_in(db, "synthetic-a")
    other = await session_in(db, "synthetic-b")
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        return answer(f"Risposta del turno sintetico {calls}.")

    orch = AICoreOrchestrator(db, decision_fn=decide)
    await orch.message(owner.user_id, owner.id, text="Continua.", client_message_id="shared-id")
    before = await ConversationRepository(db).get(owner.user_id, owner.id)
    assert await orch.message(
        other.user_id, owner.id, text="Continua.", client_message_id="shared-id",
    ) == {"ok": False, "error": "not_found"}
    assert await orch.get(other.user_id, owner.id) == {"ok": False, "error": "not_found"}
    assert await ConversationRepository(db).get_by_resume_token(other.user_id, owner.resume_token) is None
    own = await ConversationRepository(db).get_by_resume_token(owner.user_id, owner.resume_token)
    assert own.id == owner.id
    assert calls == 1
    second = await orch.message(other.user_id, other.id, text="Continua.", client_message_id="shared-id")
    assert second["ok"] and calls == 2
    assert (await ConversationRepository(db).get(owner.user_id, owner.id)).model_dump() == before.model_dump()


@pytest.mark.asyncio
async def test_failed_session_save_does_not_publish_a_completed_receipt(monkeypatch):
    db = AsyncMongoMockClient().phase1_resume_save_failure
    sess = await session_in(db)
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        return answer("Risposta sintetica senza effetti esterni.")

    orch = AICoreOrchestrator(db, decision_fn=decide)

    async def unavailable(session):
        raise RuntimeError("synthetic session store unavailable")

    monkeypatch.setattr(orch.repo, "replace", unavailable)
    with pytest.raises(RuntimeError, match="synthetic session store unavailable"):
        await orch.message(sess.user_id, sess.id, text="Continua.", client_message_id="retry-me")
    persisted = await ConversationRepository(db).get(sess.user_id, sess.id)
    assert persisted.history == []
    assert calls == 1
    # No completed result was stored. The new worker must execute this request.
    retried = await AICoreOrchestrator(db, decision_fn=decide).message(
        sess.user_id, sess.id, text="Continua.", client_message_id="retry-me",
    )
    assert retried["ok"] and calls == 2


@pytest.mark.asyncio
async def test_receipt_eviction_preserves_completion_instead_of_repeating_effects(monkeypatch):
    import conversation_engine.ai_core.orchestrator as module

    monkeypatch.setattr(module, "MESSAGE_RECEIPT_LIMIT", 2)
    db = AsyncMongoMockClient().phase1_resume_eviction
    sess = await session_in(db)
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        return answer(f"Risposta sintetica {calls}.")

    orch = AICoreOrchestrator(db, decision_fn=decide)
    results = []
    for mid in ("first", "second", "third"):
        results.append(await orch.message(sess.user_id, sess.id, text="Continua.", client_message_id=mid))
    assert calls == 3
    stored = await ConversationRepository(db).get(sess.user_id, sess.id)
    users = [h for h in stored.history if h.role == "user"]
    assert all(h.meta["result_recorded"] for h in users)
    assert "result_receipt" not in users[0].meta
    assert sum("result_receipt" in h.meta for h in users) == 2
    assert await orch.message(sess.user_id, sess.id, text="Continua.", client_message_id="first") == {
        "ok": False, "error": "message_result_unavailable",
    }
    assert await orch.message(sess.user_id, sess.id, text="Continua.", client_message_id="second") == results[1]
    assert calls == 3


@pytest.mark.asyncio
async def test_oversized_or_legacy_result_never_reexecutes_the_request(monkeypatch):
    import conversation_engine.ai_core.orchestrator as module

    monkeypatch.setattr(module, "MESSAGE_RECEIPT_MAX_BYTES", 1)
    db = AsyncMongoMockClient().phase1_resume_no_receipt
    sess = await session_in(db)
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        return answer("Risposta sintetica.")

    orch = AICoreOrchestrator(db, decision_fn=decide)
    assert (await orch.message(sess.user_id, sess.id, text="Continua.", client_message_id="large"))["ok"]
    assert await orch.message(sess.user_id, sess.id, text="Continua.", client_message_id="large") == {
        "ok": False, "error": "message_result_unavailable",
    }
    loaded = await ConversationRepository(db).get(sess.user_id, sess.id)
    loaded.append_history(role="user", kind="answer", text="Vecchia domanda", step_id="legacy")
    loaded.append_history(role="ora", kind="answer", text="Vecchia risposta")
    await ConversationRepository(db).replace(loaded)
    assert await orch.message(sess.user_id, sess.id, text="Vecchia domanda", client_message_id="legacy") == {
        "ok": False, "error": "message_result_unavailable",
    }
    assert calls == 1


@pytest.mark.asyncio
async def test_saved_client_continuation_replaces_stale_actions_in_the_receipt(monkeypatch):
    import conversation_engine.ai_core.orchestrator as module
    from conversation_engine.ai_core.models import CognitiveTurnResult

    db = AsyncMongoMockClient().phase1_resume_client_continuation
    sess = await session_in(db)
    calls = 0

    async def turn(**kwargs):
        nonlocal calls
        calls += 1
        if not kwargs.get("resume_client"):
            return CognitiveTurnResult(
                mode="answer", ora_text="Aggiorno la posizione.",
                client_actions=[{"type": "refresh_location"}],
            )
        return CognitiveTurnResult(mode="answer", ora_text="Posizione aggiornata.")

    monkeypatch.setattr(module, "run_cognitive_loop", turn)
    orch = AICoreOrchestrator(db)
    first = await orch.message(sess.user_id, sess.id, text="Aggiorna la posizione.", client_message_id="location")
    assert first["client_actions"]
    continued = await AICoreOrchestrator(db).client_resume(sess.user_id, sess.id, completed=[])
    assert continued["ora_text"] == "Posizione aggiornata." and not continued["client_actions"]
    replay = await AICoreOrchestrator(db).message(
        sess.user_id, sess.id, text="Aggiorna la posizione.", client_message_id="location",
    )
    assert replay == continued
    assert calls == 2


@pytest.mark.asyncio
async def test_resume_without_request_pointer_does_not_overwrite_last_receipt(monkeypatch):
    import conversation_engine.ai_core.orchestrator as module
    from conversation_engine.ai_core.models import CognitiveTurnResult

    db = AsyncMongoMockClient().phase1_resume_legacy_client
    sess = await session_in(db)
    calls = 0

    async def turn(**kwargs):
        nonlocal calls
        calls += 1
        return CognitiveTurnResult(mode="answer", ora_text=f"Risposta sintetica {calls}.")

    monkeypatch.setattr(module, "run_cognitive_loop", turn)
    orch = AICoreOrchestrator(db)
    first = await orch.message(sess.user_id, sess.id, text="Continua.", client_message_id="original")
    # The legacy callback can still continue, but has no persisted binding to
    # the original client request, so it cannot replace that request's result.
    continued = await orch.client_resume(sess.user_id, sess.id, completed=[])
    assert continued["ora_text"] != first["ora_text"]
    assert await orch.message(sess.user_id, sess.id, text="Continua.", client_message_id="original") == first
    assert calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "cancelled"])
async def test_closed_session_rejects_retry_before_replaying_client_actions(monkeypatch, status):
    import conversation_engine.ai_core.orchestrator as module
    from conversation_engine.ai_core.models import CognitiveTurnResult

    db = AsyncMongoMockClient().phase1_resume_closed
    sess = await session_in(db)
    calls = 0

    async def turn(**kwargs):
        nonlocal calls
        calls += 1
        return CognitiveTurnResult(mode="answer", ora_text="Aggiorno la posizione.", client_actions=[{"type": "refresh_location"}])

    monkeypatch.setattr(module, "run_cognitive_loop", turn)
    orch = AICoreOrchestrator(db)
    first = await orch.message(sess.user_id, sess.id, text="Aggiorna la posizione.", client_message_id="location")
    assert first["client_actions"]
    await db.conversation_sessions.update_one({"id": sess.id}, {"$set": {"status": status}})
    assert await orch.message(sess.user_id, sess.id, text="Aggiorna la posizione.", client_message_id="location") == {
        "ok": False, "error": "session_closed",
    }
    assert calls == 1


@pytest.mark.asyncio
async def test_retryable_skill_plan_is_rehydrated_before_continuation(monkeypatch):
    from conversation_engine.ai_core.models import Observation
    from conversation_engine.ai_core.tools.registry import ToolRegistry

    db = AsyncMongoMockClient().phase1_resume_skill_plan
    sess = await session_in(db)
    required = ["get_calendar_events", "get_route"]
    executed = []

    async def execute(self, capability, args, *, runtime):
        executed.append(capability)
        failed = capability == "get_route" and executed.count("get_route") == 1
        return Observation(
            kind="tool", name=capability, status="failed" if failed else "ok",
            payload={
                "status": "provider_error", "failure_code": "TEMPORARY_ROUTING_OUTAGE",
                "retryable": True,
            } if failed else {"status": "ok"},
        )

    monkeypatch.setattr(ToolRegistry, "execute", execute)

    def tool(capability, *, ref=None):
        result = {
            "response_mode": "tool", "reasoning_status": "needs_tool",
            "tool_call": {"capability": capability, "arguments": {}},
            "situation_update": {"operation": "none"},
        }
        if capability == "get_calendar_events" or ref:
            result["skill_plan"] = {
                "objective": "Controllare calendario e percorso",
                "required_capabilities": required,
                "completion_condition": "Entrambe le skill hanno esito verificato",
                **({"resume_plan_ref": ref} if ref else {}),
            }
        return result

    first_steps = [tool("get_calendar_events"), tool("get_route"), answer("Il percorso è temporaneamente indisponibile.")]

    async def first_decide(system, payload):
        return first_steps.pop(0) if first_steps else answer("Il provider del percorso è temporaneamente indisponibile.")

    first = await AICoreOrchestrator(db, decision_fn=first_decide).message(
        sess.user_id, sess.id, text="Controlla calendario e percorso.", client_message_id="first",
    )
    assert first["ok"]
    loaded = await ConversationRepository(db).get(sess.user_id, sess.id)
    plan = deepcopy(loaded.meta["ai_core"]["active_skill_plan"])
    assert plan is not None and executed == required, (executed, first)
    resumed_steps = [tool("get_route", ref=plan["plan_ref"]), answer("Ora anche il percorso è verificato.")]

    async def resumed_decide(system, payload):
        return resumed_steps.pop(0) if resumed_steps else answer("Ora anche il percorso è verificato.")

    second = await AICoreOrchestrator(db, decision_fn=resumed_decide).message(
        sess.user_id, sess.id, text="Riprendi il percorso.", client_message_id="second",
    )
    assert second["ok"] and second["tool_calls"] == 1
    assert executed == [*required, "get_route"]
    final = await ConversationRepository(db).get(sess.user_id, sess.id)
    assert final.meta["ai_core"]["active_skill_plan"] is None
