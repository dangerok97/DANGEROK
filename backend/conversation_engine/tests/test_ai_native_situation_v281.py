"""V2.8.1 — domain-neutral Situation identity and context continuity."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Dict, List

import pytest

from conversation_engine.ai_core.context_broker import ContextBroker
from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.models import ConversationSession
from situations.models import SituationUpdate
from situations.service import SituationMutationError, SituationService
from life_os.models import LifeOsPlan, PlanItem


class MemCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, field, direction):
        self.docs.sort(key=lambda d: d.get(field) or "", reverse=direction < 0)
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, n):
        return [dict(d) for d in self.docs[:n]]


class MemCol:
    def __init__(self):
        self.docs: List[dict] = []
        self.indexes = []

    async def create_index(self, *a, **k):
        self.indexes.append((a, k))

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def find_one(self, q, proj=None):
        for doc in self.docs:
            if _matches(doc, q):
                return dict(doc)
        return None

    def find(self, q, proj=None):
        return MemCursor([dict(d) for d in self.docs if _matches(d, q)])

    async def update_one(self, q, update, upsert=False):
        for i, doc in enumerate(self.docs):
            if _matches(doc, q):
                self.docs[i] = dict(update.get("$set") or doc)
                return SimpleNamespace(modified_count=1, matched_count=1)
        return SimpleNamespace(modified_count=0, matched_count=0)


def _matches(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(doc, sub) for sub in expected):
                return False
            continue
        actual = doc.get(key)
        if isinstance(expected, dict) and "$in" in expected:
            if actual not in expected["$in"]:
                return False
        elif isinstance(actual, list) and isinstance(expected, str):
            if expected not in actual:
                return False
        elif actual != expected:
            return False
    return True


class FakeDB:
    def __init__(self):
        self._cols: Dict[str, MemCol] = {}
        self.users = MemCol()

    def __getitem__(self, name):
        if name not in self._cols:
            self._cols[name] = MemCol()
        return self._cols[name]


def _create(summary="Evento contestuale", **kw):
    return SituationUpdate(
        operation="create", summary=summary, source_refs=["user_conversation"], **kw
    )


@pytest.mark.asyncio
async def test_a_create_runtime_id_revision_and_provenance():
    db = FakeDB()
    svc = SituationService(db)
    out = await svc.apply(
        user_id="u1",
        session_id="s1",
        update=_create(temporal_scope="domani"),
        reasoning_epoch="e1",
    )
    sit = out["situation"]
    assert (
        sit["id"].startswith("sit_")
        and sit["revision"] == 1
        and sit["status"] == "active"
    )
    raw = db["situations"].docs[0]
    assert raw["history"][0]["source"] == "user_conversation"


@pytest.mark.asyncio
async def test_b_c_update_and_cancel_same_identity_no_duplicate():
    db = FakeDB()
    svc = SituationService(db)
    first = await svc.apply(
        user_id="u1", session_id="s1", update=_create(), reasoning_epoch="e1"
    )
    sid = first["situation"]["id"]
    second = await svc.apply(
        user_id="u1",
        session_id="s1",
        update=SituationUpdate(
            operation="update",
            situation_id=sid,
            expected_revision=1,
            constraints=["presenza richiesta alle 10"],
        ),
        reasoning_epoch="e2",
    )
    third = await svc.apply(
        user_id="u1",
        session_id="s1",
        update=SituationUpdate(
            operation="cancel",
            situation_id=sid,
            expected_revision=2,
            facts=["Una persona raggiunge l'utente"],
            supersedes=["presenza richiesta alle 10"],
        ),
        reasoning_epoch="e3",
    )
    assert second["situation"]["id"] == sid == third["situation"]["id"]
    assert (
        third["situation"]["revision"] == 3
        and third["situation"]["status"] == "cancelled"
    )
    assert len(db["situations"].docs) == 1
    assert "presenza richiesta alle 10" not in third["situation"]["constraints"]


@pytest.mark.asyncio
async def test_d_resolve_and_terminal_cannot_silently_reopen():
    db = FakeDB()
    svc = SituationService(db)
    created = await svc.apply(
        user_id="u1", session_id="s1", update=_create(), reasoning_epoch="e1"
    )
    sid = created["situation"]["id"]
    out = await svc.apply(
        user_id="u1",
        session_id="s1",
        update=SituationUpdate(operation="resolve", situation_id=sid),
        reasoning_epoch="e2",
    )
    assert out["situation"]["status"] == "resolved"
    with pytest.raises(SituationMutationError, match="TERMINAL_REOPEN"):
        await svc.apply(
            user_id="u1",
            session_id="s1",
            update=SituationUpdate(operation="update", situation_id=sid, facts=["x"]),
            reasoning_epoch="e3",
        )


@pytest.mark.asyncio
async def test_f_g_ownership_and_invalid_id():
    db = FakeDB()
    svc = SituationService(db)
    created = await svc.apply(
        user_id="u1", session_id="s1", update=_create(), reasoning_epoch="e1"
    )
    for uid, sid in (("u2", created["situation"]["id"]), ("u1", "sit_missing")):
        with pytest.raises(SituationMutationError, match="NOT_FOUND_OR_NOT_OWNED"):
            await svc.apply(
                user_id=uid,
                session_id="s1",
                update=SituationUpdate(operation="cancel", situation_id=sid),
                reasoning_epoch="x",
            )


@pytest.mark.asyncio
async def test_h_revision_conflict():
    db = FakeDB()
    svc = SituationService(db)
    sid = (
        await svc.apply(
            user_id="u1", session_id="s1", update=_create(), reasoning_epoch="e1"
        )
    )["situation"]["id"]
    with pytest.raises(SituationMutationError, match="REVISION_CONFLICT"):
        await svc.apply(
            user_id="u1",
            session_id="s1",
            update=SituationUpdate(
                operation="update", situation_id=sid, expected_revision=9
            ),
            reasoning_epoch="e2",
        )


@pytest.mark.asyncio
async def test_j_k_same_epoch_dedup_cross_turn_allowed():
    db = FakeDB()
    svc = SituationService(db)
    first = await svc.apply(
        user_id="u1", session_id="s1", update=_create(), reasoning_epoch="e1"
    )
    again = await svc.apply(
        user_id="u1",
        session_id="s1",
        update=_create("different model retry"),
        reasoning_epoch="e1",
    )
    assert again["deduped"] and len(db["situations"].docs) == 1
    sid = first["situation"]["id"]
    changed = await svc.apply(
        user_id="u1",
        session_id="s1",
        update=SituationUpdate(operation="update", situation_id=sid, facts=["new"]),
        reasoning_epoch="e2",
    )
    assert changed["situation"]["revision"] == 2


@pytest.mark.asyncio
async def test_l_context_survives_session_change_and_is_minimized():
    db = FakeDB()
    svc = SituationService(db)
    await svc.apply(
        user_id="u1",
        session_id="old",
        update=_create("Preparare una consegna", linked_plan_id="plan_1"),
        reasoning_epoch="e1",
    )
    facts = await ContextBroker(db).retrieve(user_id="u1", session_id="new", stage="A")
    situation_facts = [f for f in facts if f.source == "situation"]
    assert len(situation_facts) == 1 and "plan_1" not in situation_facts[0].statement


@pytest.mark.asyncio
async def test_l2_client_resume_reuses_reasoning_epoch_and_situation_write():
    db = FakeDB()
    sess = ConversationSession(id="s1", user_id="u1", meta={"ai_core": {}})

    async def decide(system, user):
        return {
            "response_mode": "answer",
            "message_to_user": "Ok.",
            "situation_update": _create("Stato in attesa del client").model_dump(),
        }

    first = await run_cognitive_loop(
        sess=sess, user_message="Continua", db=db, decision_fn=decide
    )
    first_epoch = sess.meta["ai_core"]["reasoning_epoch"]
    second = await run_cognitive_loop(
        sess=sess,
        user_message="Continua",
        db=db,
        decision_fn=decide,
        resume_client=True,
    )
    assert sess.meta["ai_core"]["reasoning_epoch"] == first_epoch
    assert first.situation["id"] == second.situation["id"]
    assert len(db["situations"].docs) == 1


@pytest.mark.asyncio
async def test_m_linked_plan_preserved_unless_ai_changes_it():
    db = FakeDB()
    svc = SituationService(db)
    first = await svc.apply(
        user_id="u1",
        session_id="s1",
        update=_create(linked_plan_id="plan_1", linked_object_refs=["obj_1"]),
        reasoning_epoch="e1",
    )
    sid = first["situation"]["id"]
    changed = await svc.apply(
        user_id="u1",
        session_id="s1",
        update=SituationUpdate(
            operation="update", situation_id=sid, facts=["constraint changed"]
        ),
        reasoning_epoch="e2",
    )
    assert changed["situation"]["linked_plan_id"] == "plan_1"
    assert changed["situation"]["linked_object_refs"] == ["obj_1"]


@pytest.mark.asyncio
async def test_n_loop_never_auto_writes_memory():
    db = FakeDB()
    sess = ConversationSession(id="s1", user_id="u1", meta={"ai_core": {}})

    async def decide(system, user):
        return {
            "response_mode": "answer",
            "message_to_user": "Ricevuto.",
            "user_intent_summary": "temporary event",
            "situation_update": _create("Evento temporaneo").model_dump(),
        }

    result = await run_cognitive_loop(
        sess=sess, user_message="Evento temporaneo", db=db, decision_fn=decide
    )
    assert result.situation and "memories" not in db._cols


@pytest.mark.asyncio
async def test_o_non_domain_specific_three_turn_contract():
    db = FakeDB()
    svc = SituationService(db)
    first = await svc.apply(
        user_id="u1",
        session_id="s1",
        update=_create("Preparare una presentazione", temporal_scope="entro venerdì"),
        reasoning_epoch="p1",
    )
    sid = first["situation"]["id"]
    second = await svc.apply(
        user_id="u1",
        session_id="s1",
        update=SituationUpdate(
            operation="update",
            situation_id=sid,
            constraints=["durata massima 5 minuti"],
        ),
        reasoning_epoch="p2",
    )
    third = await svc.apply(
        user_id="u1",
        session_id="s1",
        update=SituationUpdate(operation="cancel", situation_id=sid),
        reasoning_epoch="p3",
    )
    assert {
        first["situation"]["id"],
        second["situation"]["id"],
        third["situation"]["id"],
    } == {sid}


def test_p_malformed_situation_is_dropped_not_fatal():
    from conversation_engine.ai_core.governance import validate_decision
    from conversation_engine.ai_core.tools.registry import ToolRegistry

    out = validate_decision(
        {
            "response_mode": "answer",
            "message_to_user": "Ok",
            "situation_update": {"operation": "explode"},
        },
        tools=ToolRegistry(),
    )
    assert (
        out.decision
        and out.decision.situation_update is None
        and "bad_situation_update" in out.errors
    )


@pytest.mark.asyncio
async def test_q_persistence_failure_is_observed_before_user_copy():
    db = FakeDB()
    sess = ConversationSession(id="s1", user_id="u1", meta={"ai_core": {}})
    calls = 0

    async def decide(system, user):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "response_mode": "answer",
                "message_to_user": "Ho aggiornato la situazione.",
                "situation_update": {
                    "operation": "update",
                    "situation_id": "sit_missing",
                },
            }
        assert "NOT_FOUND_OR_NOT_OWNED" in user
        return {
            "response_mode": "answer",
            "message_to_user": "Non sono riuscita ad aggiornare lo stato; posso ricostruirlo con te.",
        }

    result = await run_cognitive_loop(
        sess=sess, user_message="Cambio", db=db, decision_fn=decide
    )
    assert calls == 2 and "Non sono riuscita" in result.ora_text


@pytest.mark.asyncio
async def test_cancelled_situation_requires_explicit_linked_plan_decision():
    db = FakeDB()
    plan = LifeOsPlan(
        id="plan_1",
        user_id="u1",
        summary="Temporary plan",
        items=[PlanItem(id="item_1", title="Prepare")],
    )
    await db["life_os_plans"].insert_one(plan.model_dump())
    svc = SituationService(db)
    sid = (
        await svc.apply(
            user_id="u1",
            session_id="s1",
            update=_create("Temporary situation", linked_plan_id="plan_1"),
            reasoning_epoch="seed",
        )
    )["situation"]["id"]
    sess = ConversationSession(id="s1", user_id="u1", meta={"ai_core": {}})
    calls = 0

    async def decide(system, user):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "response_mode": "answer",
                "message_to_user": "Tutto annullato.",
                "situation_update": {"operation": "cancel", "situation_id": sid},
            }
        if calls == 2:
            assert "LINKED_PLAN_DECISION_REQUIRED" in user
            return {
                "response_mode": "tool",
                "tool_call": {
                    "capability": "update_plan",
                    "arguments": {
                        "plan_id": "plan_1",
                        "patch": {"status": "cancelled"},
                    },
                },
            }
        return {
            "response_mode": "answer",
            "message_to_user": "Ho annullato anche il piano collegato.",
        }

    result = await run_cognitive_loop(
        sess=sess, user_message="Non serve più", db=db, decision_fn=decide
    )
    stored_plan = db["life_os_plans"].docs[0]
    assert result.ok and calls == 3 and stored_plan["status"] == "cancelled"


@pytest.mark.asyncio
async def test_prior_plan_update_does_not_satisfy_later_cancel_reconciliation():
    db = FakeDB()
    plan = LifeOsPlan(
        id="plan_1",
        user_id="u1",
        summary="Temporary plan",
        items=[PlanItem(id="item_1", title="Prepare")],
    )
    await db["life_os_plans"].insert_one(plan.model_dump())
    svc = SituationService(db)
    sid = (
        await svc.apply(
            user_id="u1",
            session_id="s1",
            update=_create("Temporary situation", linked_plan_id="plan_1"),
            reasoning_epoch="seed",
        )
    )["situation"]["id"]
    sess = ConversationSession(id="s1", user_id="u1", meta={"ai_core": {}})
    calls = 0

    async def decide(system, user):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "response_mode": "tool",
                "tool_call": {
                    "capability": "update_plan",
                    "arguments": {
                        "plan_id": "plan_1",
                        "patch": {"summary": "Updated before cancellation"},
                    },
                },
            }
        if calls == 2:
            return {
                "response_mode": "answer",
                "message_to_user": "Tutto annullato.",
                "situation_update": {"operation": "cancel", "situation_id": sid},
            }
        if calls == 3:
            assert "LINKED_PLAN_DECISION_REQUIRED" in user
            return {
                "response_mode": "tool",
                "tool_call": {
                    "capability": "update_plan",
                    "arguments": {
                        "plan_id": "plan_1",
                        "patch": {"status": "cancelled"},
                    },
                },
            }
        return {
            "response_mode": "answer",
            "message_to_user": "Ho annullato anche il piano collegato.",
        }

    result = await run_cognitive_loop(
        sess=sess, user_message="Prima aggiorna, poi non serve più", db=db, decision_fn=decide
    )
    stored_plan = db["life_os_plans"].docs[0]
    assert result.ok and calls == 4 and stored_plan["status"] == "cancelled"


@pytest.mark.asyncio
async def test_situation_copy_cannot_claim_durable_memory_write():
    db = FakeDB()
    sess = ConversationSession(id="s1", user_id="u1", meta={"ai_core": {}})
    calls = 0

    async def decide(system, user):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "response_mode": "answer",
                "message_to_user": "Ho memorizzato questa situazione.",
                "situation_update": {
                    "operation": "create",
                    "summary": "Temporary contextual state",
                },
            }
        assert "SITUATION_IS_NOT_MEMORY" in user
        return {
            "response_mode": "answer",
            "message_to_user": "Terrò presente questa situazione corrente.",
        }

    result = await run_cognitive_loop(
        sess=sess, user_message="Temporary context", db=db, decision_fn=decide
    )
    assert calls == 2
    assert "memorizzato" not in result.ora_text.lower()
    assert "memories" not in db._cols


def test_no_closed_domain_contract_in_production():
    source = SituationUpdate.model_json_schema()
    dumped = json.dumps(source).lower()
    assert (
        "travel" not in dumped
        and "study" not in dumped
        and "presentation" not in dumped
    )
