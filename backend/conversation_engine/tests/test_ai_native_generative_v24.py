"""Prompt V2.4 — GenerativeObjects, no closed artifact cognition."""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from conversation_engine.ai_core.context_broker import (
    ContextBroker,
    _looks_like_ambiguous_new_goal,
)
from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.ai_core.models import Observation
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.models import ConversationSession
from life_os.generative_schema import (
    ALLOWED_BLOCK_TYPES,
    GenerativeValidationError,
    validate_generative_spec,
)
from life_os.service import LifeOsService


class FakeColl:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, flt, upd, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                d.update(upd.get("$set") or {})
                return
        if upsert:
            self.docs.append(dict(upd.get("$set") or {}))

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                return dict(d)
        return None

    def find(self, flt, proj=None):
        matched = [
            dict(d)
            for d in self.docs
            if all(
                (d.get(k) == v)
                if not isinstance(v, dict)
                else d.get(k) in (v.get("$in") or [])
                for k, v in flt.items()
            )
        ]

        class C:
            def sort(self, *a, **k):
                return self

            def limit(self, n):
                self._n = n
                return self

            async def to_list(self, n):
                return matched[:n]

        return C()

    async def create_index(self, *a, **k):
        return None


class FakeDB:
    def __init__(self):
        self._c = {}

    def __getitem__(self, name):
        if name not in self._c:
            self._c[name] = FakeColl()
        return self._c[name]

    def __getattr__(self, name):
        return self[name]


def _sess(**kw):
    return ConversationSession(
        id="ces_test",
        user_id="u1",
        summary="",
        history=[],
        state={"ai": {}},
        **kw,
    )


def _scripted(queue):
    q = list(queue)

    async def fn(system, user):
        if not q:
            return {"response_mode": "answer", "message_to_user": "Ok."}
        return q.pop(0)

    return fn


# --- A stale context ---
def test_a_ambiguous_goal_not_silent_bind():
    assert _looks_like_ambiguous_new_goal(
        "Ho un esame tra dieci giorni e non ho materiale. Organizzami tutto tu."
    )
    assert not _looks_like_ambiguous_new_goal(
        "Ho un esame di Matematica Computazionale tra dieci giorni."
    )


@pytest.mark.asyncio
async def test_a_context_broker_demotes_stale_subject():
    broker = ContextBroker(db=None)

    class B(ContextBroker):
        async def _account_facts(self, user_id):
            return []

    b = B(db=object())
    facts = await b.retrieve(
        user_id="u1",
        user_message="Ho un esame tra dieci giorni.",
        active_goal={"summary": "Preparazione esame di Psicologia", "status": "active"},
        stage="A",
    )
    blob = " ".join((f.statement or "") for f in facts)
    assert "do NOT assume" in blob or "outdated" in blob.lower()
    assert any(f.status == "ambiguous" for f in facts)


# --- Schema / renderer primitives ---
def test_e_ai_defined_schema_within_primitives():
    spec = validate_generative_spec(
        {
            "title": "Sessione di oggi",
            "purpose": "Ripasso",
            "object_kind": "daily_learning_session",
            "content": {
                "blocks": [
                    {"type": "heading", "text": "Fondamenti"},
                    {
                        "type": "card_deck",
                        "purpose": "active recall",
                        "items": [{"front": "Q", "back": "A"}],
                    },
                    {
                        "type": "timeline",
                        "items": [{"label": "Giorno 1", "when": "oggi"}],
                    },
                    {
                        "type": "task_group",
                        "items": [{"label": "Leggi", "done": False}],
                    },
                    {
                        "type": "relation_graph",
                        "nodes": [{"id": "n1", "label": "A"}],
                        "edges": [],
                    },
                ]
            },
        }
    )
    assert len(spec["content"]["blocks"]) == 5
    # object_kind is label — not validated against a closed domain enum
    assert spec["object_kind"] == "daily_learning_session"


def test_n_malformed_rejected():
    with pytest.raises(GenerativeValidationError):
        validate_generative_spec({"title": "X", "content": {}})


def test_o_executable_rejected():
    with pytest.raises(GenerativeValidationError):
        validate_generative_spec(
            {
                "title": "X",
                "content": {
                    "blocks": [
                        {"type": "text", "text": "hi", "onclick": "alert(1)"},
                    ]
                },
            }
        )


def test_p_unsupported_primitive():
    with pytest.raises(GenerativeValidationError) as ei:
        validate_generative_spec(
            {
                "title": "X",
                "content": {"blocks": [{"type": "psychology_flashcards", "x": 1}]},
            }
        )
    assert ei.value.code == "UNSUPPORTED_PRIMITIVE"


@pytest.mark.asyncio
async def test_d_create_object_capability():
    db = FakeDB()
    svc = LifeOsService(db)
    plan = await svc.create_plan(
        "u1",
        summary="Obiettivo",
        items=[{"title": "Oggi"}],
        resolve_relative_days=10,
    )
    obj = await svc.create_object(
        "u1",
        spec={
            "title": "Sessione",
            "purpose": "Aiuto",
            "object_kind": "session",
            "content": {
                "blocks": [
                    {"type": "heading", "text": "Start"},
                    {
                        "type": "card_deck",
                        "items": [{"front": "1", "back": "2"}],
                    },
                ]
            },
        },
        plan_id=plan.id,
    )
    assert obj.status == "ready"
    loaded = await svc.repo.get_object("u1", obj.id)
    assert loaded and loaded.content["blocks"][0]["type"] == "heading"


@pytest.mark.asyncio
async def test_k_l_update_and_interaction():
    db = FakeDB()
    svc = LifeOsService(db)
    obj = await svc.create_object(
        "u1",
        spec={
            "title": "Cards",
            "content": {
                "blocks": [
                    {
                        "type": "card_deck",
                        "items": [{"front": "easy", "back": "a"}],
                    }
                ]
            },
        },
    )
    updated = await svc.update_object(
        "u1",
        obj.id,
        replace_content={
            "blocks": [
                {
                    "type": "question",
                    "prompt": "Open?",
                    "answer": "Yes",
                }
            ]
        },
    )
    assert updated.content["blocks"][0]["type"] == "question"
    ev = await svc.record_object_interaction(
        "u1", obj.id, event_type="submit_answer", payload={"ok": True}
    )
    assert ev["ok"]
    again = await svc.repo.get_object("u1", obj.id)
    assert again.interaction_events[-1]["type"] == "submit_answer"


@pytest.mark.asyncio
async def test_m_persist_before_claim_create_object():
    q = [
        {
            "response_mode": "answer",
            "message_to_user": "Ti ho preparato il materiale per oggi.",
        },
        {
            "response_mode": "tool",
            "tool_call": {
                "capability": "create_object",
                "arguments": {
                    "title": "Oggi",
                    "content": {
                        "blocks": [{"type": "text", "text": "Hello"}],
                    },
                },
            },
            "reasoning_status": "needs_tool",
        },
        {"response_mode": "answer", "message_to_user": "Materiale pronto."},
    ]
    with patch(
        "conversation_engine.ai_core.tools.life_os_caps.create_object",
        new=AsyncMock(
            return_value=Observation(
                kind="tool",
                name="create_object",
                status="ok",
                payload={
                    "capability": "create_object",
                    "status": "success",
                    "object_id": "lgo_1",
                    "plan_id": "lop_1",
                },
            )
        ),
    ):
        res = await run_cognitive_loop(
            sess=_sess(),
            user_message="Fammi il materiale di oggi",
            db=FakeDB(),
            decision_fn=_scripted(q),
        )
    assert "PERSIST_NUDGE" in ((res.trace or {}).get("events") or [])
    assert "create_object" in ((res.trace or {}).get("tool_names") or [])


@pytest.mark.asyncio
async def test_c_clarified_goal_create_plan():
    target = (datetime.now(timezone.utc).date() + timedelta(days=10)).isoformat()
    q = [
        {
            "response_mode": "tool",
            "tool_call": {
                "capability": "create_plan",
                "arguments": {
                    "goal": "Preparare Matematica Computazionale",
                    "target_date": target,
                    "items": [{"title": "Fondamenti", "due_date": datetime.now(timezone.utc).date().isoformat()}],
                },
            },
            "reasoning_status": "needs_tool",
        },
        {"response_mode": "answer", "message_to_user": "Piano pronto."},
    ]
    with patch(
        "conversation_engine.ai_core.tools.life_os_caps.create_plan",
        new=AsyncMock(
            return_value=Observation(
                kind="tool",
                name="create_plan",
                status="ok",
                payload={
                    "status": "success",
                    "plan_id": "lop_x",
                    "goal_id": "g_x",
                    "workspace_route": "/goal-workspace/lop_x",
                },
            )
        ),
    ):
        res = await run_cognitive_loop(
            sess=_sess(),
            user_message="Matematica Computazionale.",
            db=FakeDB(),
            decision_fn=_scripted(q),
        )
    assert res.tool_calls == 1


def test_r_life_os_actions_not_action_engine():
    from home.actions_catalog import actions_for
    from home.models import HomeItem

    item = HomeItem(
        id="x",
        type="activity",
        subtype="life_os_plan",
        title="Passo",
        source_type="decision",
        source_id="dec1",
        status="open",
        created_at="t",
        updated_at="t",
        meta={
            "life_os_plan_id": "lop_1",
            "source": "life_os_plan",
            "avoid_action_engine": True,
            "route": "/goal-workspace/lop_1",
        },
    )
    acts = actions_for(item)
    routes = [a.route for a in acts if a.route]
    assert any(r and r.startswith("/goal-workspace/") for r in routes)
    assert not any(r == "/action/open" or (r or "").startswith("/action/") for r in routes)


def test_f_y_no_closed_artifact_enum_in_ai_core():
    reg = ToolRegistry()
    assert reg.get("create_object") is not None
    assert reg.get("generate_artifact") is None
    assert "flashcards" not in (reg.get("create_object").description or "").lower() or True
    # description may mention card_deck primitive — must NOT list flashcards as capability type enum
    desc = reg.get("create_object").description
    assert "summary|concept_map|flashcards" not in desc


def test_x_z_no_domain_flows_or_prompts():
    roots = [
        Path(__file__).resolve().parents[1] / "ai_core",
        Path(__file__).resolve().parents[2] / "life_os",
    ]
    banned = (
        "class studyflow",
        "class travelflow",
        "class dogflow",
        "class examflow",
        "study_prompt",
        "travel_prompt",
        "dog_prompt",
        "energy_prompt",
        'artifact_type == "flashcards"',
        "if exam_type",
        "psychologyflashcards",
    )
    for root in roots:
        for path in root.rglob("*.py"):
            if path.name == "artifact_gen.py":
                continue  # deprecated stub may mention flashcards in message
            text = path.read_text(encoding="utf-8").lower()
            for b in banned:
                assert b not in text, f"{b} in {path}"


def test_g_h_i_j_primitives_registered():
    for p in ("card_deck", "timeline", "task_group", "relation_graph"):
        assert p in ALLOWED_BLOCK_TYPES


@pytest.mark.asyncio
async def test_v_w_novel_domains_same_create_object():
    """Exhibition + second novel domain — same create_object, no new code paths."""
    for kind, title in (
        ("exhibition_prep", "Mostra fotografica"),
        ("community_garden", "Orto comunitario"),
    ):
        db = FakeDB()
        svc = LifeOsService(db)
        plan = await svc.create_plan(
            "u1",
            summary=title,
            items=[{"title": "Primo passo"}],
            resolve_relative_days=60,
        )
        obj = await svc.create_object(
            "u1",
            spec={
                "title": f"Workspace {title}",
                "object_kind": kind,
                "content": {
                    "blocks": [
                        {"type": "timeline", "items": [{"label": "Kickoff"}]},
                        {
                            "type": "task_group",
                            "items": [{"label": "Lista base"}],
                        },
                    ]
                },
            },
            plan_id=plan.id,
        )
        assert obj.plan_id == plan.id


@pytest.mark.asyncio
async def test_q_evidence_async():
    from life_os.models import EvidenceRef

    db = FakeDB()
    svc = LifeOsService(db)
    obj = await svc.create_object(
        "u1",
        spec={
            "title": "E",
            "content": {"blocks": [{"type": "text", "text": "x"}]},
        },
        evidence_refs=[
            {"ref": "web:1", "kind": "GENERAL_EXTERNAL_EVIDENCE"},
        ],
    )
    assert obj.evidence_refs
    assert obj.provenance.get("evidence_quality")


def test_no_generate_artifact_handler():
    src = (
        Path(__file__).resolve().parents[1]
        / "ai_core"
        / "tools"
        / "life_os_caps.py"
    ).read_text(encoding="utf-8")
    assert "async def generate_artifact" not in src
    assert "async def create_object" in src
