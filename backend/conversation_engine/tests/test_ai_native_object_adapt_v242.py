"""V2.4.2 — Persistent GenerativeObject adaptation (generic, no domain routing)."""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from conversation_engine.ai_core.life_os_context import (
    build_life_os_ai_payload,
    hydrate_life_os_session_state,
    object_ref,
    set_active_object_ref,
)
from conversation_engine.ai_core.loop import (
    _claims_unverified_object_adapt,
    run_cognitive_loop,
)
from conversation_engine.ai_core import state as state_mod
from conversation_engine.models import ConversationSession
from life_os.generative_models import GenerativeObject
from life_os.models import EvidenceRef, LifeOsPlan, PlanItem
from life_os.service import LifeOsService


class FakeColl:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, flt, upd, upsert=False):
        for d in self.docs:
            if _match(d, flt):
                d.update(upd.get("$set") or {})
                return
        if upsert:
            row = dict(flt)
            row.update(upd.get("$set") or {})
            self.docs.append(row)

    async def replace_one(self, flt, doc):
        for i, d in enumerate(self.docs):
            if _match(d, flt):
                self.docs[i] = dict(doc)
                return
        self.docs.append(dict(doc))

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if _match(d, flt):
                return dict(d)
        return None

    def find(self, flt, proj=None):
        matched = [dict(d) for d in self.docs if _match(d, flt)]

        class C:
            def __init__(self, rows):
                self.rows = rows
                self._n = len(rows)

            def sort(self, *a, **k):
                key = a[0] if a else "updated_at"
                rev = True
                if len(a) > 1:
                    rev = a[1] == -1
                self.rows = sorted(
                    self.rows, key=lambda x: x.get(key) or "", reverse=rev
                )
                return self

            def limit(self, n):
                self._n = n
                return self

            async def to_list(self, n):
                return self.rows[:n]

        return C(matched)

    async def create_index(self, *a, **k):
        return None


def _match(d, flt):
    for k, v in flt.items():
        if isinstance(v, dict) and "$in" in v:
            if d.get(k) not in v["$in"]:
                return False
        elif d.get(k) != v:
            return False
    return True


class FakeDB:
    def __init__(self):
        self._c = {}

    def __getitem__(self, name):
        if name not in self._c:
            self._c[name] = FakeColl()
        return self._c[name]

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]


def _sess(uid="u1", **meta_extra) -> ConversationSession:
    return ConversationSession(
        id="ces_test_adapt",
        user_id=uid,
        meta={"ui_mode": "ai_core", "ai_core": {**meta_extra}},
    )


async def _seed_plan_object(db, *, kind_blocks=None):
    svc = LifeOsService(db)
    plan = LifeOsPlan(
        id="lop_adapt",
        user_id="u1",
        summary="Organizzare un trasferimento",
        desired_outcome="Checklist essenziale",
        target_date="2026-09-01",
        conversation_session_id="ces_test_adapt",
        items=[
            PlanItem(id="it1", title="Raccogliere documenti", order=1, status="in_progress")
        ],
        evidence_refs=[
            EvidenceRef(ref="user:notes", kind="USER_PROVIDED_CONTENT", label="user")
        ],
    )
    await svc.repo.insert_plan(plan)
    blocks = kind_blocks or [
        {"type": "heading", "text": "Materiale difficile"},
        {"type": "text", "text": "Concetto avanzato con jargon pesante."},
    ]
    obj = await svc.create_object(
        "u1",
        spec={
            "title": "Materiale trasferimento",
            "purpose": "guida",
            "object_kind": "workspace_object",
            "content": {"blocks": blocks, "schema_version": 1},
        },
        plan_id=plan.id,
        conversation_session_id="ces_test_adapt",
        evidence_refs=[
            {"ref": "user:notes", "kind": "USER_PROVIDED_CONTENT", "label": "user"}
        ],
    )
    return plan, obj


@pytest.mark.asyncio
async def test_a_b_k_active_object_context_hydrated():
    """A/B/K — semantic active object available in life_os payload."""
    db = FakeDB()
    plan, obj = await _seed_plan_object(db)
    sess = _sess()
    st = state_mod.get_ai_state(sess)
    payload = await build_life_os_ai_payload(db, sess, st)
    assert payload["active_plan_id"] == plan.id
    assert payload["active_object_ref"]["id"] == obj.id
    assert payload["current_plan_item_ref"]["id"] == "it1"
    assert "questo" in (payload.get("note") or "").lower() or "active_object" in str(
        payload
    )


@pytest.mark.asyncio
async def test_c_conversational_only_no_forced_persist():
    """C — answer without adaptation claim does not force update_object."""
    assert not _claims_unverified_object_adapt(
        "Certo, la formula misura l'errore relativo.",
        has_active_object=True,
    )


def test_adapt_claim_detects_simplify_assertion():
    assert _claims_unverified_object_adapt(
        "Ho semplificato il materiale nel workspace.",
        has_active_object=True,
    )
    assert not _claims_unverified_object_adapt(
        "Ho semplificato il materiale nel workspace.",
        has_active_object=False,
    )


@pytest.mark.asyncio
async def test_d_e_f_g_h_update_object_revision_and_evidence():
    """D–H — update_object keeps id, bumps revision, preserves evidence."""
    db = FakeDB()
    _, obj = await _seed_plan_object(db)
    assert obj.revision == 1
    before_id = obj.id
    before_ev = list(obj.evidence_refs)
    svc = LifeOsService(db)
    updated = await svc.update_object(
        "u1",
        obj.id,
        replace_content={
            "blocks": [
                {"type": "heading", "text": "Versione semplice"},
                {"type": "text", "text": "Spiegazione chiara con esempio."},
            ],
            "schema_version": 1,
        },
        adaptation_note="user asked for simpler wording",
    )
    assert updated.id == before_id
    assert updated.revision == 2
    assert updated.updated_at
    assert updated.evidence_refs
    assert len(updated.evidence_refs) >= len(before_ev)
    assert (updated.provenance or {}).get("last_adaptation_note")


@pytest.mark.asyncio
async def test_d_loop_uses_update_object_for_durable_adapt():
    """D/N — loop calls update_object; claim without write is nudged."""
    db = FakeDB()
    plan, obj = await _seed_plan_object(db)
    sess = _sess(active_plan_id=plan.id, active_object_ref=object_ref(obj))
    decisions = [
        {
            "response_mode": "answer",
            "user_intent_summary": "simplify material",
            "active_goal_summary": plan.summary,
            "reasoning_status": "enough_information",
            "message_to_user": "Ho semplificato il materiale salvato.",
            "question": None,
            "tool_call": None,
            "context_query": None,
            "state_updates": [],
            "memory_candidates": [],
            "claim_grounding": "INFERENCE",
            "confidence": 0.7,
        },
        {
            "response_mode": "tool",
            "user_intent_summary": "simplify material",
            "active_goal_summary": plan.summary,
            "reasoning_status": "needs_tool",
            "message_to_user": None,
            "question": None,
            "tool_call": {
                "capability": "update_object",
                "operation": "run",
                "arguments": {
                    "object_id": obj.id,
                    "content": {
                        "blocks": [
                            {"type": "text", "text": "Versione più semplice."}
                        ],
                        "schema_version": 1,
                    },
                    "adaptation_note": "simplify",
                },
                "reason": "persist simplification",
            },
            "context_query": None,
            "state_updates": [],
            "memory_candidates": [],
            "claim_grounding": None,
            "confidence": 0.8,
        },
        {
            "response_mode": "answer",
            "user_intent_summary": "simplify material",
            "active_goal_summary": plan.summary,
            "reasoning_status": "enough_information",
            "message_to_user": "Ok, ho aggiornato il materiale in modo più semplice.",
            "question": None,
            "tool_call": None,
            "context_query": None,
            "state_updates": [],
            "memory_candidates": [],
            "claim_grounding": "TOOL_OBSERVATION",
            "confidence": 0.9,
        },
    ]
    i = {"n": 0}

    async def decision_fn(system, user):
        d = decisions[min(i["n"], len(decisions) - 1)]
        i["n"] += 1
        return d

    res = await run_cognitive_loop(
        sess=sess,
        user_message="È troppo difficile, spiegamelo più semplice.",
        db=db,
        decision_fn=decision_fn,
        max_steps=6,
    )
    assert res.ok
    st = state_mod.get_ai_state(sess)
    assert (st.get("active_object_ref") or {}).get("id") == obj.id
    refreshed = await LifeOsService(db).repo.get_object("u1", obj.id)
    assert refreshed.revision >= 2
    assert "semplic" in (res.ora_text or "").lower() or "aggiorn" in (
        res.ora_text or ""
    ).lower()


@pytest.mark.asyncio
async def test_l_workspace_interaction_sets_active_object_ref():
    """L — interaction binds session active_object_ref."""
    db = FakeDB()
    # conversation_sessions collection for repository
    plan, obj = await _seed_plan_object(db)
    from conversation_engine.repository import ConversationRepository

    repo = ConversationRepository(db)
    sess = _sess()
    await repo.insert(sess)
    svc = LifeOsService(db)
    out = await svc.record_object_interaction(
        "u1",
        obj.id,
        event_type="marked_difficult",
        payload={"source": "workspace"},
    )
    assert out and out.get("ok")
    again = await repo.get("u1", "ces_test_adapt")
    st = state_mod.get_ai_state(again)
    assert (st.get("active_object_ref") or {}).get("id") == obj.id


@pytest.mark.asyncio
async def test_m_malformed_update_rejected():
    db = FakeDB()
    _, obj = await _seed_plan_object(db)
    svc = LifeOsService(db)
    with pytest.raises(ValueError):
        await svc.update_object(
            "u1",
            obj.id,
            replace_content={"blocks": [{"type": "not_a_real_primitive", "text": "x"}]},
        )


@pytest.mark.asyncio
async def test_o_replacement_is_new_object_when_create():
    """O — create_object yields new id (intentional replacement path)."""
    db = FakeDB()
    plan, obj = await _seed_plan_object(db)
    svc = LifeOsService(db)
    other = await svc.create_object(
        "u1",
        spec={
            "title": "Replacement",
            "purpose": "new",
            "content": {
                "blocks": [{"type": "text", "text": "nuovo"}],
                "schema_version": 1,
            },
        },
        plan_id=plan.id,
    )
    assert other.id != obj.id


@pytest.mark.asyncio
async def test_p_q_r_s_t_generic_primitives_same_path():
    """P–T — text / card_deck / timeline / task_group / novel via same update_object."""
    db = FakeDB()
    svc = LifeOsService(db)
    cases = [
        [{"type": "text", "text": "long"}],
        [
            {
                "type": "card_deck",
                "items": [{"front": "a", "back": "b"}, {"front": "c", "back": "d"}],
            }
        ],
        [
            {
                "type": "timeline",
                "items": [
                    {"label": "Day 1", "detail": "x"},
                    {"label": "Day 2", "detail": "y"},
                ],
            }
        ],
        [
            {
                "type": "task_group",
                "items": [
                    {"label": "A", "done": False},
                    {"label": "B", "done": False},
                    {"label": "C", "done": False},
                ],
            }
        ],
        [
            {
                "type": "relation_graph",
                "nodes": [{"id": "1", "label": "A"}],
                "edges": [],
            }
        ],
    ]
    for blocks in cases:
        _plan, obj = await _seed_plan_object(db, kind_blocks=blocks)
        obj2 = await svc.update_object(
            "u1",
            obj.id,
            replace_content={
                "blocks": [{"type": "text", "text": "adapted"}],
                "schema_version": 1,
            },
            adaptation_note="generic adapt",
        )
        assert obj2.revision >= 2
        assert obj2.id == obj.id


@pytest.mark.asyncio
async def test_append_and_remove_blocks():
    db = FakeDB()
    _, obj = await _seed_plan_object(
        db,
        kind_blocks=[
            {"id": "b1", "type": "text", "text": "keep"},
            {"id": "b2", "type": "text", "text": "drop"},
        ],
    )
    svc = LifeOsService(db)
    updated = await svc.update_object(
        "u1",
        obj.id,
        remove_block_ids=["b2"],
        append_blocks=[{"id": "b3", "type": "text", "text": "example"}],
    )
    ids = [b.get("id") for b in (updated.content or {}).get("blocks") or []]
    assert "b2" not in ids
    assert "b3" in ids


def test_u_v_no_domain_or_phrase_router():
    """U/V — adaptation path has no domain branches / phrase→action router."""
    root = Path(__file__).resolve().parents[1] / "ai_core"
    scoped = [
        root / "life_os_context.py",
        root / "prompt.py",
        root / "tools" / "life_os_caps.py",
    ]
    banned = ("flashcard_adapt", "exam_adapt", "if study", "studyflow")
    for path in scoped:
        text = path.read_text(encoding="utf-8").lower()
        for b in banned:
            assert b not in text, f"{path.name} contains {b}"
    assert not (root / "adaptation_router.py").exists()
    prompt = (root / "prompt.py").read_text(encoding="utf-8").lower()
    # Must not hardcode the live Italian user phrase as a product rule
    assert "è troppo difficile, spiegamelo più semplice" not in prompt
    # No if/elif phrase → capability routing table
    caps = (root / "tools" / "life_os_caps.py").read_text(encoding="utf-8")
    tree = ast.parse(caps)
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            src = ast.get_source_segment(caps, node) or ""
            assert "update_object" not in src or "troppo" not in src.lower()


@pytest.mark.asyncio
async def test_session_focus_bind_api_shape():
    db = FakeDB()
    plan, obj = await _seed_plan_object(db)
    from conversation_engine.repository import ConversationRepository

    repo = ConversationRepository(db)
    await repo.insert(_sess())
    res = await LifeOsService(db).bind_session_object_focus(
        "u1",
        session_id="ces_test_adapt",
        object_id=obj.id,
        plan_id=plan.id,
        plan_item_id="it1",
        event_type="object_opened",
    )
    assert res["ok"]
    assert res["active_object_ref"]["id"] == obj.id
    assert res["current_plan_item_ref"]["id"] == "it1"
