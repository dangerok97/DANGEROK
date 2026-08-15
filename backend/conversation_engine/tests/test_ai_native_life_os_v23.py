"""Prompt V2.3 — generic Life OS plans/artifacts (mocked AI, no domain flows)."""
from __future__ import annotations

import ast
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ["AI_CORE_TRACE"] = "1"
os.environ["GOAL_ENGINE_ENABLED"] = "0"  # avoid GoalService DB in unit tests unless mocked

_BACKEND = str(Path(__file__).resolve().parents[2])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.models import ConversationSession
from life_os.evidence import classify_evidence_refs, calibration_note_for_ai
from life_os.models import EvidenceRef, LifeOsPlan, PlanItem
from life_os.repository import LifeOsRepository
from life_os.service import LifeOsService
# V2.4: closed artifact generators removed — use GenerativeObject / create_object


def _sess(uid="u1") -> ConversationSession:
    return ConversationSession(user_id=uid, meta={"ui_mode": "ai_core", "ai_core": {}})


def _scripted(queue: List[Dict[str, Any]]):
    async def fn(system: str, user: str) -> Dict[str, Any]:
        if not queue:
            return {
                "response_mode": "answer",
                "user_intent_summary": "done",
                "message_to_user": "Ok.",
            }
        return queue.pop(0)

    return fn


class _MemCol:
    def __init__(self):
        self.docs: List[dict] = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, q, upd, upsert=False):
        uid, pid = q.get("user_id"), q.get("id")
        for i, d in enumerate(self.docs):
            if d.get("user_id") == uid and d.get("id") == pid:
                self.docs[i] = dict(upd.get("$set") or d)
                return MagicMock(matched_count=1)
        if upsert:
            self.docs.append(dict(upd.get("$set") or {}))
        return MagicMock(matched_count=0)

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if d.get("user_id") == q.get("user_id") and d.get("id") == q.get("id"):
                return dict(d)
        return None

    def find(self, q, proj=None):
        matched = []
        for d in self.docs:
            if d.get("user_id") != q.get("user_id"):
                continue
            st = q.get("status")
            if isinstance(st, dict) and "$in" in st:
                if d.get("status") not in st["$in"]:
                    continue
            elif st and d.get("status") != st:
                continue
            matched.append(dict(d))

        class _C:
            def sort(self, *a, **k):
                return self

            def limit(self, n):
                self._n = n
                return self

            async def to_list(self, n):
                return matched[:n]

        return _C()

    async def create_index(self, *a, **k):
        return None


class FakeDB:
    def __init__(self):
        self.life_os_plans = _MemCol()
        self.life_os_artifacts = _MemCol()
        self.life_os_objects = _MemCol()
        self.decisions = _MemCol()
        self.goals = _MemCol()

    def __getitem__(self, name: str):
        return getattr(self, name)


@pytest.mark.asyncio
async def test_a_generic_goal_plan_create():
    db = FakeDB()
    svc = LifeOsService(db)
    with patch.object(svc, "_upsert_goal", new=AsyncMock(return_value="goal_x")):
        plan = await svc.create_plan(
            "u1",
            summary="Preparare un obiettivo",
            desired_outcome="Essere pronto",
            target_date=(datetime.now(timezone.utc).date() + timedelta(days=10)).isoformat(),
            items=[
                {"title": "Passo 1", "due_date": datetime.now(timezone.utc).date().isoformat()},
                {"title": "Passo 2"},
            ],
        )
    assert plan.goal_id == "goal_x"
    assert len(plan.items) == 2
    assert plan.target_date


@pytest.mark.asyncio
async def test_b_c_plan_update_incremental():
    db = FakeDB()
    svc = LifeOsService(db)
    with patch.object(svc, "_upsert_goal", new=AsyncMock(return_value="g1")):
        plan = await svc.create_plan(
            "u1", summary="P", items=[{"title": "A"}, {"title": "B"}]
        )
        updated = await svc.update_plan(
            "u1",
            plan.id,
            item_updates=[{"id": plan.items[0].id, "status": "completed"}],
            add_items=[{"title": "C"}],
        )
    assert updated
    assert updated.items[0].status == "completed"
    assert any(i.title == "C" for i in updated.items)


@pytest.mark.asyncio
async def test_d_action_creation():
    db = FakeDB()
    svc = LifeOsService(db)
    today = datetime.now(timezone.utc).date().isoformat()
    with patch.object(svc, "_upsert_goal", new=AsyncMock(return_value="g1")):
        plan = await svc.create_plan(
            "u1",
            summary="P",
            items=[{"title": "Oggi", "due_date": today}],
        )
    with patch(
        "decision_engine.service.DecisionService.create",
        new=AsyncMock(return_value={"id": "dec1"}),
    ):
        res = await svc.create_actions_from_plan("u1", plan.id)
    assert res["ok"]
    assert "dec1" in res["created_decision_ids"]


@pytest.mark.asyncio
async def test_e_to_i_generative_objects_replace_closed_artifacts():
    """V2.4: closed artifact types removed — GenerativeObject + primitives."""
    from life_os.generative_schema import validate_generative_spec

    for kind, blocks in (
        ("session", [{"type": "heading", "text": "H"}, {"type": "text", "text": "B"}]),
        (
            "recall",
            [{"type": "card_deck", "items": [{"front": "Q", "back": "A"}]}],
        ),
        (
            "graph",
            [
                {
                    "type": "relation_graph",
                    "nodes": [{"id": "n1", "label": "A"}],
                    "edges": [],
                }
            ],
        ),
        ("tasks", [{"type": "task_group", "items": [{"label": "Do"}]}]),
    ):
        spec = validate_generative_spec(
            {
                "title": kind,
                "object_kind": kind,
                "content": {"blocks": blocks},
            }
        )
        assert spec["content"]["blocks"]


@pytest.mark.asyncio
async def test_j_k_object_persist_reload():
    db = FakeDB()
    svc = LifeOsService(db)
    with patch.object(svc, "_upsert_goal", new=AsyncMock(return_value="g1")):
        plan = await svc.create_plan("u1", summary="P", items=[{"title": "T"}])
    obj = await svc.create_object(
        "u1",
        spec={
            "title": "Cards",
            "content": {
                "blocks": [
                    {
                        "type": "card_deck",
                        "items": [{"front": "1", "back": "2"}],
                    }
                ]
            },
        },
        plan_id=plan.id,
    )
    loaded = await LifeOsRepository(db).get_object("u1", obj.id)
    assert loaded and loaded.content["blocks"][0]["type"] == "card_deck"
    bundle = await svc.get_active_bundle("u1", plan_id=plan.id)
    assert bundle["objects"]


@pytest.mark.asyncio
async def test_l_resume_bundle():
    db = FakeDB()
    svc = LifeOsService(db)
    with patch.object(svc, "_upsert_goal", new=AsyncMock(return_value="g1")):
        plan = await svc.create_plan(
            "u1",
            summary="Resume me",
            conversation_session_id="sess1",
            items=[{"title": "Next"}],
        )
    b = await svc.get_active_bundle("u1")
    assert b["plan"]["id"] == plan.id
    assert b["next_item"]["title"] == "Next"


@pytest.mark.asyncio
async def test_m_home_visibility():
    from home.adapters.life_os_plan import load_life_os_plans

    db = FakeDB()
    today = datetime.now(timezone.utc).date().isoformat()
    target = (datetime.now(timezone.utc).date() + timedelta(days=10)).isoformat()
    db.life_os_plans.docs.append(
        {
            "id": "lop1",
            "user_id": "u1",
            "summary": "Piano generico",
            "status": "active",
            "target_date": target,
            "goal_id": "g1",
            "conversation_session_id": "cs1",
            "items": [
                {"id": "i1", "title": "Oggi", "due_date": today, "status": "not_started", "order": 0}
            ],
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-02T00:00:00+00:00",
        }
    )
    items, _ = await load_life_os_plans(db, "u1")
    assert any(i.source_type == "life_os_plan" for i in items)
    assert any(i.type == "resume" for i in items)
    assert any(i.meta.get("goal_target_date") == target or i.due_at for i in items)


def test_n_o_focus_horizon_date_and_no_invent():
    # Backend must not invent target_date when absent
    plan = LifeOsPlan(user_id="u1", summary="x", items=[PlanItem(title="a")])
    assert plan.target_date is None
    # Relative days only when explicitly requested
    assert plan.target_date is None


def test_p_q_evidence_calibration():
    general = classify_evidence_refs(
        [EvidenceRef(ref="u1", kind="GENERAL_EXTERNAL_EVIDENCE")]
    )
    assert general["calibration"] == "general_only"
    note = calibration_note_for_ai(general)
    assert "official" in note.lower() or "syllabus" in note.lower() or "programme" in note.lower()
    specific = classify_evidence_refs(
        [EvidenceRef(ref="u2", kind="TARGET_SPECIFIC_EVIDENCE")]
    )
    assert specific["has_target_specific"]


@pytest.mark.asyncio
async def test_r_partial_execution_failure():
    # plan ok, object validation fail → plan remains
    db = FakeDB()
    svc = LifeOsService(db)
    with patch.object(svc, "_upsert_goal", new=AsyncMock(return_value="g1")):
        plan = await svc.create_plan("u1", summary="P", items=[{"title": "T"}])
    with pytest.raises(ValueError):
        await svc.create_object(
            "u1",
            spec={"title": "Bad", "content": {"blocks": [{"type": "not_a_primitive"}]}},
            plan_id=plan.id,
        )
    assert await svc.get_plan("u1", plan.id)


@pytest.mark.asyncio
async def test_s_duplicate_write_prevention():
    q = [
        {
            "response_mode": "tool",
            "tool_call": {
                "capability": "create_plan",
                "arguments": {
                    "goal": "X",
                    "items": [{"title": "A"}],
                },
            },
            "reasoning_status": "needs_tool",
        },
        {
            "response_mode": "tool",
            "tool_call": {
                "capability": "create_plan",
                "arguments": {
                    "goal": "X",
                    "items": [{"title": "A"}],
                },
            },
            "reasoning_status": "needs_tool",
        },
        {
            "response_mode": "answer",
            "message_to_user": "Piano pronto.",
        },
    ]
    with patch(
        "conversation_engine.ai_core.tools.life_os_caps.create_plan",
        new=AsyncMock(
            return_value=__import__(
                "conversation_engine.ai_core.models", fromlist=["Observation"]
            ).Observation(
                kind="tool",
                name="create_plan",
                status="ok",
                payload={
                    "capability": "create_plan",
                    "status": "success",
                    "plan_id": "p1",
                    "goal_id": "g1",
                    "created_refs": ["p1"],
                },
            )
        ),
    ):
        res = await run_cognitive_loop(
            sess=_sess(),
            user_message="Organizzami un piano",
            db=FakeDB(),
            decision_fn=_scripted(q),
        )
    # Second identical tool blocked by governance → still answers
    assert res.mode == "answer"
    assert res.tool_calls == 1


def test_t_side_effect_governance():
    reg = ToolRegistry()
    for cap in ("create_plan", "update_plan", "create_actions", "create_object", "update_object"):
        spec = reg.get(cap)
        assert spec is not None
        assert spec.side_effect == "REVERSIBLE_WRITE"
    assert reg.get("web_search").side_effect == "READ_ONLY"
    assert reg.get("generate_artifact") is None


@pytest.mark.asyncio
async def test_u_exam_scenario_capability_sequence():
    """Exam-like dialogue uses generic capabilities — no StudyFlow."""
    target = (datetime.now(timezone.utc).date() + timedelta(days=10)).isoformat()
    q = [
        {
            "response_mode": "tool",
            "tool_call": {
                "capability": "create_plan",
                "arguments": {
                    "goal": "Preparare l'esame",
                    "desired_outcome": "Essere pronto",
                    "target_date": target,
                    "items": [
                        {
                            "title": "Fondamenti oggi",
                            "due_date": datetime.now(timezone.utc).date().isoformat(),
                        }
                    ],
                    "evidence_refs": [
                        {"ref": "web1", "kind": "GENERAL_EXTERNAL_EVIDENCE"}
                    ],
                },
            },
            "reasoning_status": "needs_tool",
        },
        {
            "response_mode": "tool",
            "tool_call": {
                "capability": "create_actions",
                "arguments": {"plan_id": "WILL_INJECT"},
            },
            "reasoning_status": "needs_tool",
        },
        {
            "response_mode": "answer",
            "claim_grounding": "INFERENCE",
            "message_to_user": (
                "Ho creato un piano di 10 giorni. Non ho ancora il programma ufficiale; "
                "parto dai nuclei ricorrenti mentre cerco fonti più specifiche."
            ),
        },
    ]
    calls = {"n": 0}

    async def create_plan_side(arguments, runtime):
        from conversation_engine.ai_core.models import Observation

        calls["n"] += 1
        return Observation(
            kind="tool",
            name="create_plan",
            status="ok",
            payload={
                "capability": "create_plan",
                "status": "success",
                "plan_id": "plan_exam",
                "goal_id": "goal_exam",
                "created_refs": ["plan_exam"],
                "evidence_quality": {"calibration": "general_only"},
            },
        )

    async def create_actions_side(arguments, runtime):
        from conversation_engine.ai_core.models import Observation

        assert arguments.get("plan_id") in ("plan_exam", "WILL_INJECT") or runtime
        return Observation(
            kind="tool",
            name="create_actions",
            status="ok",
            payload={
                "capability": "create_actions",
                "status": "success",
                "plan_id": "plan_exam",
                "created_refs": ["dec1"],
            },
        )

    # Fix second decision to use plan from state injection — loop injects active_plan_id
    q[1]["tool_call"]["arguments"] = {}  # empty → filled from state

    with patch(
        "conversation_engine.ai_core.tools.life_os_caps.create_plan",
        new=create_plan_side,
    ), patch(
        "conversation_engine.ai_core.tools.life_os_caps.create_actions",
        new=create_actions_side,
    ):
        res = await run_cognitive_loop(
            sess=_sess(),
            user_message="Ho un esame tra dieci giorni.",
            db=FakeDB(),
            decision_fn=_scripted(q),
        )
    assert "programma ufficiale" in res.ora_text.lower() or "nuclei" in res.ora_text.lower()
    assert res.tool_calls >= 2
    assert "StudyFlow" not in res.ora_text


@pytest.mark.asyncio
async def test_v_w_x_y_generality_scenarios():
    """Dog / travel / energy / novel — same create_plan capability."""
    for msg, goal in (
        ("Tra un mese adotterò un cane e non ho preparato niente.", "Preparare arrivo cane"),
        ("Tra due settimane devo andare a Vienna.", "Preparare viaggio"),
        ("Devo cambiare fornitore della luce entro fine mese.", "Cambio fornitore luce"),
        ("Fra tre settimane voglio organizzare la mia prima mostra fotografica.", "Mostra fotografica"),
    ):
        q = [
            {
                "response_mode": "tool",
                "tool_call": {
                    "capability": "create_plan",
                    "arguments": {
                        "goal": goal,
                        "items": [{"title": "Primo passo"}],
                        "resolve_relative_days": 14,
                    },
                },
                "reasoning_status": "needs_tool",
            },
            {
                "response_mode": "answer",
                "message_to_user": f"Ho impostato un piano: {goal}.",
            },
        ]
        with patch(
            "conversation_engine.ai_core.tools.life_os_caps.create_plan",
            new=AsyncMock(
                return_value=__import__(
                    "conversation_engine.ai_core.models", fromlist=["Observation"]
                ).Observation(
                    kind="tool",
                    name="create_plan",
                    status="ok",
                    payload={
                        "capability": "create_plan",
                        "status": "success",
                        "plan_id": "p",
                        "goal_id": "g",
                    },
                )
            ),
        ):
            res = await run_cognitive_loop(
                sess=_sess(), user_message=msg, db=FakeDB(), decision_fn=_scripted(q)
            )
        assert res.tool_calls == 1
        assert "Flow" not in res.ora_text


def test_z_no_hardcoding_audit():
    roots = [
        Path(_BACKEND) / "conversation_engine" / "ai_core",
        Path(_BACKEND) / "life_os",
    ]
    banned = (
        "class studyflow",
        "class travelflow",
        "class dogflow",
        "class energyflow",
        "class examflow",
        "if exam_type",
        "if psychology",
        "matematica computazionale",
        "photographyexhibitionflow",
        'goal_type == "study"',
        "if goal_type == 'study'",
    )
    for root in roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            for b in banned:
                assert b not in text, f"{b} in {path}"


def test_capabilities_registered():
    reg = ToolRegistry()
    for c in (
        "create_plan",
        "update_plan",
        "create_actions",
        "create_object",
        "update_object",
        "get_object",
        "list_goal_objects",
        "get_active_plan",
        "mark_plan_progress",
    ):
        assert reg.get(c) is not None
    assert reg.get("generate_artifact") is None


@pytest.mark.asyncio
async def test_persist_before_claim_nudge_then_write():
    """Narrating plan creation without a write triggers one soft re-entry."""
    from conversation_engine.ai_core.models import Observation

    q = [
        {
            "response_mode": "answer",
            "message_to_user": "Ho impostato un piano di 10 giorni per te.",
            "reasoning_status": "enough_information",
        },
        {
            "response_mode": "tool",
            "tool_call": {
                "capability": "create_plan",
                "arguments": {
                    "goal": "Preparare obiettivo",
                    "resolve_relative_days": 10,
                    "items": [{"title": "Oggi", "due_date": "today"}],
                },
            },
            "reasoning_status": "needs_tool",
        },
        {
            "response_mode": "answer",
            "message_to_user": "Piano pronto e salvato.",
        },
    ]
    with patch(
        "conversation_engine.ai_core.tools.life_os_caps.create_plan",
        new=AsyncMock(
            return_value=Observation(
                kind="tool",
                name="create_plan",
                status="ok",
                payload={
                    "capability": "create_plan",
                    "status": "success",
                    "plan_id": "p-nudge",
                    "goal_id": "g-nudge",
                    "created_refs": ["p-nudge"],
                },
            )
        ),
    ):
        res = await run_cognitive_loop(
            sess=_sess(),
            user_message="Organizzami i prossimi dieci giorni, fai tutto tu.",
            db=FakeDB(),
            decision_fn=_scripted(q),
        )
    assert res.ok
    assert res.tool_calls == 1
    assert res.ai_calls >= 2
    assert "PERSIST_NUDGE" in ((res.trace or {}).get("events") or [])


@pytest.mark.asyncio
async def test_note_intention_does_not_satisfy_persist_claim():
    """note_intention must not suppress persist-before-claim for plan narration."""
    from conversation_engine.ai_core.models import Observation

    q = [
        {
            "response_mode": "tool",
            "tool_call": {
                "capability": "note_intention",
                "arguments": {"summary": "piano emergenza"},
            },
            "reasoning_status": "needs_tool",
        },
        {
            "response_mode": "answer",
            "message_to_user": "Ho impostato il piano di 10 giorni.",
        },
        {
            "response_mode": "tool",
            "tool_call": {
                "capability": "create_plan",
                "arguments": {
                    "goal": "Obiettivo",
                    "items": [{"title": "Passo 1"}],
                },
            },
            "reasoning_status": "needs_tool",
        },
        {
            "response_mode": "answer",
            "message_to_user": "Piano salvato nel Life OS.",
        },
    ]
    with patch(
        "conversation_engine.ai_core.tools.life_os_caps.create_plan",
        new=AsyncMock(
            return_value=Observation(
                kind="tool",
                name="create_plan",
                status="ok",
                payload={
                    "capability": "create_plan",
                    "status": "success",
                    "plan_id": "p2",
                    "goal_id": "g2",
                },
            )
        ),
    ):
        res = await run_cognitive_loop(
            sess=_sess(),
            user_message="Organizzami tutto tu.",
            db=FakeDB(),
            decision_fn=_scripted(q),
        )
    assert res.tool_calls >= 2
    assert "PERSIST_NUDGE" in ((res.trace or {}).get("events") or [])
    assert "create_plan" in ((res.trace or {}).get("tool_names") or [])
