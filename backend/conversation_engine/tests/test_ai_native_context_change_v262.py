"""V2.6.2 — Context change & turn-scoped mutation idempotency."""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest

from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.ai_core.models import Observation
from conversation_engine.ai_core.tools.registry import ToolRegistry, tool_signature
from conversation_engine.models import ConversationSession, now_iso
from life_os.evidence import conversational_evidence_ref, public_evidence_sources


class FakeCol:
    def __init__(self):
        self.docs: Dict[str, dict] = {}

    async def insert_one(self, doc):
        self.docs[doc["id"]] = dict(doc)

    async def replace_one(self, q, doc, upsert=False):
        self.docs[doc["id"]] = dict(doc)

    async def update_one(self, flt, upd, upsert=False):
        d = await self.find_one(flt)
        if d:
            d.update(upd.get("$set") or {})
            self.docs[d["id"]] = d
        elif upsert:
            payload = dict(upd.get("$set") or {})
            self.docs[payload["id"]] = payload

    async def find_one(self, q, proj=None, sort=None):
        for doc in self.docs.values():
            if all(doc.get(k) == v for k, v in q.items() if k != "_id"):
                return dict(doc)
        return None

    def find(self, *a, **k):
        class C:
            def sort(self, *a, **k):
                return self

            def limit(self, n):
                return self

            async def to_list(self, n):
                return []

        return C()


class FakeDB:
    def __init__(self):
        self.life_os_plans = FakeCol()
        self.life_os_objects = FakeCol()
        self.life_os_artifacts = FakeCol()
        self.conversation_sessions = FakeCol()
        self.goals = FakeCol()
        self._c = {
            "life_os_plans": self.life_os_plans,
            "life_os_objects": self.life_os_objects,
            "life_os_artifacts": self.life_os_artifacts,
            "conversation_sessions": self.conversation_sessions,
            "goals": self.goals,
        }

    def __getitem__(self, name):
        if name not in self._c:
            self._c[name] = FakeCol()
        return self._c[name]


def _sess(**kwargs):
    return ConversationSession(
        id=kwargs.get("id") or "ces_test",
        user_id=kwargs.get("user_id") or "u1",
        origin="text",
        input="hi",
        status="waiting_user",
        engine_version="ai-core-1.0",
        meta={"ui_mode": "ai_core", "ai_core": dict(kwargs.get("ai_core") or {})},
        created_at=now_iso(),
        updated_at=now_iso(),
    )


def _scripted(queue: List[Dict[str, Any]]):
    async def fn(system: str, user: str) -> Dict[str, Any]:
        assert "NEW conversational facts" in system or "New conversational facts" in system
        if not queue:
            return {
                "response_mode": "answer",
                "user_intent_summary": "done",
                "reasoning_status": "enough_information",
                "message_to_user": "Ok.",
            }
        return queue.pop(0)

    return fn


def test_duplicate_guard_does_not_leak_internal_ux():
    tools = ToolRegistry()
    raw = {
        "response_mode": "tool",
        "user_intent_summary": "x",
        "reasoning_status": "needs_tool",
        "tool_call": {"name": "note_intention", "arguments": {"summary": "same"}},
    }
    sig = tool_signature("note_intention", {"summary": "same"})
    g = validate_decision(raw, tools=tools, recent_tool_signatures={sig})
    assert "duplicate_tool_call" in g.errors
    assert g.decision
    assert g.decision.response_mode == "answer"
    msg = (g.decision.message_to_user or "").lower()
    assert "ripetere" not in msg
    assert "stessa operazione" not in msg


@pytest.mark.asyncio
async def test_same_turn_duplicate_suppressed_once():
    q = [
        {
            "response_mode": "tool",
            "tool_call": {
                "capability": "update_plan",
                "arguments": {"plan_id": "p1", "patch": {"summary": "A"}},
            },
            "reasoning_status": "needs_tool",
        },
        {
            "response_mode": "tool",
            "tool_call": {
                "capability": "update_plan",
                "arguments": {"plan_id": "p1", "patch": {"summary": "A"}},
            },
            "reasoning_status": "needs_tool",
        },
        {
            "response_mode": "answer",
            "message_to_user": "Piano aggiornato.",
            "claim_grounding": "TOOL_OBSERVATION",
        },
    ]
    calls = {"n": 0}

    async def fake_update(arguments, runtime):
        calls["n"] += 1
        return Observation(
            kind="tool",
            name="update_plan",
            status="ok",
            payload={
                "capability": "update_plan",
                "status": "success",
                "plan_id": "p1",
                "operation": "patch",
            },
        )

    with patch(
        "conversation_engine.ai_core.tools.life_os_caps.update_plan",
        new=AsyncMock(side_effect=fake_update),
    ):
        sess = _sess(ai_core={"active_plan_id": "p1"})
        res = await run_cognitive_loop(
            sess=sess,
            user_message="Aggiorna il piano",
            db=FakeDB(),
            decision_fn=_scripted(q),
        )
    assert calls["n"] == 1
    assert res.mode == "answer"
    assert "ripetere" not in (res.ora_text or "").lower()


@pytest.mark.asyncio
async def test_cross_turn_new_fact_allows_second_update():
    """Session-persisted prior signature must NOT block a later turn."""
    from conversation_engine.ai_core import state as state_mod

    sess = _sess(
        ai_core={
            "active_plan_id": "p1",
            # Legacy poison: previous turn stored signatures (pre-V2.6.2 bug)
            "tool_signatures": [
                tool_signature(
                    "update_plan", {"plan_id": "p1", "patch": {"summary": "old"}}
                )
            ],
        }
    )
    q = [
        {
            "response_mode": "tool",
            "tool_call": {
                "capability": "update_plan",
                "arguments": {
                    "plan_id": "p1",
                    "patch": {"summary": "old"},
                    "user_fact_summary": "Vincolo tempo ridotto",
                },
            },
            "reasoning_status": "needs_tool",
        },
        {
            "response_mode": "answer",
            "message_to_user": "Ho adattato il piano al nuovo vincolo.",
            "claim_grounding": "TOOL_OBSERVATION",
        },
    ]
    calls = {"n": 0}

    async def fake_update(arguments, runtime):
        calls["n"] += 1
        assert arguments.get("user_fact_summary")
        return Observation(
            kind="tool",
            name="update_plan",
            status="ok",
            payload={
                "capability": "update_plan",
                "status": "success",
                "plan_id": "p1",
                "operation": "patch",
            },
        )

    with patch(
        "conversation_engine.ai_core.tools.life_os_caps.update_plan",
        new=AsyncMock(side_effect=fake_update),
    ):
        res = await run_cognitive_loop(
            sess=sess,
            user_message="Ho appena saputo che il vincolo e cambiato.",
            db=FakeDB(),
            decision_fn=_scripted(q),
        )
    assert calls["n"] == 1
    assert "ripetere" not in (res.ora_text or "").lower()
    st = state_mod.get_ai_state(sess)
    assert st.get("reasoning_epoch")
    assert st.get("tool_signatures") == []


@pytest.mark.asyncio
async def test_chat_only_no_forced_update():
    q = [
        {
            "response_mode": "answer",
            "message_to_user": "Certo, dimmi pure quando vuoi riprendere.",
            "reasoning_status": "enough_information",
        }
    ]
    with patch(
        "conversation_engine.ai_core.tools.life_os_caps.update_plan",
        new=AsyncMock(),
    ) as upd:
        res = await run_cognitive_loop(
            sess=_sess(ai_core={"active_plan_id": "p1"}),
            user_message="Ok grazie, ci sentiamo dopo",
            db=FakeDB(),
            decision_fn=_scripted(q),
        )
        upd.assert_not_called()
    assert res.tool_calls == 0


def test_conversational_evidence_not_memory_dump():
    ev = conversational_evidence_ref(
        summary="Tempo presentazione ridotto a 5 minuti",
        session_id="ces_1",
        turn_or_epoch="rte_abc",
    )
    assert ev["kind"] == "USER_PROVIDED_CONTENT"
    assert ev["source_type"] == "user_conversation"
    pubs = public_evidence_sources([ev])
    assert pubs and "5 minuti" in pubs[0]["display_name"]
    assert "lcf_" not in pubs[0]["display_name"]


def test_no_presentation_hardcoding_in_prod():
    from pathlib import Path

    banned = (
        "5 minuti",
        "12 minuti",
        "presentation_reconcile",
        "if duration",
        "slide_count ==",
    )
    roots = [
        Path(__file__).resolve().parents[1] / "ai_core" / "loop.py",
        Path(__file__).resolve().parents[1] / "ai_core" / "governance.py",
        Path(__file__).resolve().parents[1] / "ai_core" / "tools" / "life_os_caps.py",
    ]
    for path in roots:
        text = path.read_text(encoding="utf-8").lower()
        for b in banned:
            assert b not in text, f"{b} in {path.name}"


@pytest.mark.asyncio
async def test_persist_before_claim_still_nudges():
    q = [
        {
            "response_mode": "answer",
            "message_to_user": "Ho aggiornato il piano e adattato il materiale.",
            "reasoning_status": "enough_information",
        },
        {
            "response_mode": "answer",
            "message_to_user": "Ti spiego qui senza salvare modifiche al workspace.",
            "reasoning_status": "enough_information",
        },
    ]
    res = await run_cognitive_loop(
        sess=_sess(
            ai_core={
                "active_plan_id": "p1",
                "active_object_ref": {"id": "o1", "title": "Roadmap"},
            }
        ),
        user_message="Adatta tutto",
        db=FakeDB(),
        decision_fn=_scripted(q),
    )
    assert res.mode == "answer"
    assert res.ai_calls >= 2
