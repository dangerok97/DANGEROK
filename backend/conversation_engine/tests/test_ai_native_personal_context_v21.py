"""Prompt 7 V2.1 — personal context retrieval (generic, no name branches)."""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ["AI_CORE_TRACE"] = "1"

_BACKEND = str(Path(__file__).resolve().parents[2])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from conversation_engine.ai_core.context_broker import (
    ContextBroker,
    infer_categories,
    validate_context_query,
)
from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.ai_core.tool_registry import ToolRegistry
from conversation_engine.models import ConversationSession
from life_setup.models import DomainProfile, LifeProfile, ProfileObject


def _scripted(queue: List[Dict[str, Any]]):
    seen_payloads: List[str] = []

    async def fn(system: str, user: str) -> Dict[str, Any]:
        seen_payloads.append(user)
        fn.payloads = seen_payloads  # type: ignore[attr-defined]
        if not queue:
            return {
                "response_mode": "answer",
                "user_intent_summary": "done",
                "reasoning_status": "enough_information",
                "message_to_user": "Ok.",
            }
        return queue.pop(0)

    fn.payloads = seen_payloads  # type: ignore[attr-defined]
    return fn


def _sess(uid="u1") -> ConversationSession:
    return ConversationSession(user_id=uid, meta={"ui_mode": "ai_core", "ai_core": {}})


class _UsersCol:
    def __init__(self, by_uid: Dict[str, dict]):
        self.by_uid = by_uid

    async def find_one(self, q, proj=None):
        uid = q.get("user_id")
        return dict(self.by_uid[uid]) if uid in self.by_uid else None


class _ProfilesCol:
    def __init__(self, by_uid: Dict[str, dict]):
        self.by_uid = by_uid

    async def find_one(self, q, proj=None):
        uid = q.get("user_id")
        return dict(self.by_uid[uid]) if uid in self.by_uid else None

    async def update_one(self, *a, **k):
        return MagicMock()

    async def create_index(self, *a, **k):
        return None


class FakePersonalDB:
    """Minimal Motor-shaped DB for ContextBroker tests."""

    def __init__(
        self,
        *,
        users: Optional[Dict[str, dict]] = None,
        profiles: Optional[Dict[str, dict]] = None,
    ):
        self.users = _UsersCol(users or {})
        self.life_profiles = _ProfilesCol(profiles or {})
        self.life_setup_sessions = MagicMock()
        self.life_memory_snapshots = MagicMock()
        self.memories = MagicMock()
        self.memories.find = MagicMock(
            return_value=MagicMock(sort=MagicMock(return_value=AsyncMock(return_value=[])))
        )


def _profile_doc(
    uid: str,
    *,
    name: Optional[str] = None,
    city: Optional[str] = None,
    role: Optional[str] = None,
    name_source: str = "user_confirmed",
    name_status: str = "confirmed",
    city_source: str = "user_said",
    city_status: str = "confirmed",
    role_source: str = "user_said",
    role_status: str = "confirmed",
    city_confirmed: bool = True,
    role_confirmed: bool = True,
    name_confirmed: bool = True,
) -> dict:
    domains: Dict[str, Any] = {}
    if name is not None:
        domains["mlc"] = {
            "domain": "mlc",
            "objects": {
                "mlc.identity.name": {
                    "key": "mlc.identity.name",
                    "value": name,
                    "source": name_source,
                    "status": name_status,
                    "confirmed": name_confirmed,
                    "confidence": 0.95,
                }
            },
        }
    if city is not None:
        domains["casa"] = {
            "domain": "casa",
            "objects": {
                "casa.citta": {
                    "key": "casa.citta",
                    "value": city,
                    "source": city_source,
                    "status": city_status,
                    "confirmed": city_confirmed,
                    "confidence": 0.9,
                }
            },
        }
    if role is not None:
        domains["lavoro"] = {
            "domain": "lavoro",
            "objects": {
                "lavoro.ruolo": {
                    "key": "lavoro.ruolo",
                    "value": role,
                    "source": role_source,
                    "status": role_status,
                    "confirmed": role_confirmed,
                    "confidence": 0.85,
                }
            },
        }
    return {"user_id": uid, "domains": domains, "version": "life-profile-1.0"}


# A — Account name in Stage A
@pytest.mark.asyncio
async def test_a_account_name_in_stage_a():
    db = FakePersonalDB(users={"u1": {"user_id": "u1", "name": "Alex"}})
    broker = ContextBroker(db)
    facts = await broker.retrieve(user_id="u1", user_message="Come mi chiamo?", stage="A")
    assert any(f.source == "account" and "Alex" in (f.statement or f.fact) for f in facts)
    assert all(f.source in ("account", "goal") for f in facts)
    # payload must stay tiny — no profile dump in Stage A
    assert len(facts) <= 4

    payloads: List[str] = []

    async def decide(system: str, user: str):
        payloads.append(user)
        data = json.loads(user)
        name_fact = next(
            (
                f
                for f in data.get("context_facts") or []
                if "Alex" in str(f.get("statement") or f.get("fact") or "")
            ),
            None,
        )
        assert name_fact is not None
        return {
            "response_mode": "answer",
            "user_intent_summary": "asks name",
            "reasoning_status": "enough_information",
            "message_to_user": "Ti chiami Alex.",
        }

    res = await run_cognitive_loop(
        sess=_sess(), user_message="Come mi chiamo?", db=db, decision_fn=decide
    )
    assert res.mode == "answer"
    assert "Alex" in res.ora_text
    assert res.ai_calls == 1


# B — No account name; Profile known identity → context → answer
@pytest.mark.asyncio
async def test_b_profile_identity_via_context():
    db = FakePersonalDB(
        users={"u1": {"user_id": "u1", "name": ""}},
        profiles={"u1": _profile_doc("u1", name="Blake")},
    )
    # Stage A: no account name
    a = await ContextBroker(db).retrieve(user_id="u1", stage="A")
    assert not any("Blake" in (f.statement or "") for f in a)

    q = [
        {
            "response_mode": "context",
            "user_intent_summary": "asks name",
            "reasoning_status": "needs_context",
            "context_query": "identity / user's name",
        },
        {
            "response_mode": "answer",
            "user_intent_summary": "asks name",
            "reasoning_status": "enough_information",
            "message_to_user": "Ti chiami Blake.",
        },
    ]
    fn = _scripted(q)
    with patch(
        "life_memory.service.LifeMemoryService.get_life_memory",
        new=AsyncMock(
            return_value=MagicMock(memories=[])
        ),
    ):
        res = await run_cognitive_loop(
            sess=_sess(), user_message="Come mi chiamo?", db=db, decision_fn=fn
        )
    assert res.mode == "answer"
    assert "Blake" in res.ora_text
    assert res.ai_calls == 2
    assert res.context_calls >= 2
    # re-entry kept original question
    assert any("Come mi chiamo?" in p for p in fn.payloads)  # type: ignore[attr-defined]
    second = json.loads(fn.payloads[1])  # type: ignore[attr-defined]
    assert second["user_message"] == "Come mi chiamo?"
    assert any(
        "Blake" in str(f.get("statement") or "") for f in second.get("context_facts") or []
    )


# C — Residence via semantic personal-context
@pytest.mark.asyncio
async def test_c_residence_semantic_lookup():
    db = FakePersonalDB(
        users={"u1": {"user_id": "u1"}},
        profiles={"u1": _profile_doc("u1", city="Riverton")},
    )
    with patch(
        "life_memory.service.LifeMemoryService.get_life_memory",
        new=AsyncMock(return_value=MagicMock(memories=[])),
    ):
        facts = await ContextBroker(db).retrieve(
            user_id="u1",
            query="where the user lives / residence",
            stage="B",
        )
    assert any("Riverton" in (f.statement or "") for f in facts)
    assert all(
        f.source in ("profile", "memory", "account", "goal")
        and "study plan" not in (f.statement or "").lower()
        for f in facts
    )


# D — Employment via same mechanism
@pytest.mark.asyncio
async def test_d_employment_semantic_lookup():
    db = FakePersonalDB(
        users={"u1": {"user_id": "u1"}},
        profiles={"u1": _profile_doc("u1", role="Analyst")},
    )
    with patch(
        "life_memory.service.LifeMemoryService.get_life_memory",
        new=AsyncMock(return_value=MagicMock(memories=[])),
    ):
        facts = await ContextBroker(db).retrieve(
            user_id="u1",
            query="current work / employment",
            stage="B",
        )
    assert any("Analyst" in (f.statement or "") for f in facts)


# E — Unknown fact → AI may ask
@pytest.mark.asyncio
async def test_e_unknown_fact_may_ask():
    db = FakePersonalDB(users={"u1": {"user_id": "u1"}}, profiles={"u1": _profile_doc("u1")})
    q = [
        {
            "response_mode": "context",
            "user_intent_summary": "asks pets",
            "reasoning_status": "needs_context",
            "context_query": "pets / animals",
        },
        {
            "response_mode": "ask",
            "user_intent_summary": "asks pets",
            "reasoning_status": "needs_user_input",
            "question": "Non ho ancora questa informazione — hai animali domestici?",
        },
    ]
    with patch(
        "life_memory.service.LifeMemoryService.get_life_memory",
        new=AsyncMock(return_value=MagicMock(memories=[])),
    ):
        res = await run_cognitive_loop(
            sess=_sess(),
            user_message="Che animali ho?",
            db=db,
            decision_fn=_scripted(q),
        )
    assert res.mode == "ask"
    assert res.question and "?" in res.question


# F — Ambiguous fact not promoted to certain answer (broker status)
@pytest.mark.asyncio
async def test_f_ambiguous_not_known():
    db = FakePersonalDB(
        users={"u1": {"user_id": "u1"}},
        profiles={
            "u1": _profile_doc(
                "u1",
                city="Somewhere",
                city_source="inferred",
                city_status="suggested",
                city_confirmed=False,
            )
        },
    )
    with patch(
        "life_memory.service.LifeMemoryService.get_life_memory",
        new=AsyncMock(return_value=MagicMock(memories=[])),
    ):
        facts = await ContextBroker(db).retrieve(
            user_id="u1", query="residence", stage="B"
        )
    city_facts = [f for f in facts if "Somewhere" in (f.statement or "")]
    assert city_facts
    assert all(f.status in ("likely", "ambiguous") for f in city_facts)
    assert all(f.status != "known" or f.authority == "ai_inferred" for f in city_facts) or all(
        f.status != "known" for f in city_facts
    )


# G — Context query returns only relevant items
@pytest.mark.asyncio
async def test_g_relevant_only():
    db = FakePersonalDB(
        users={"u1": {"user_id": "u1", "name": "Alex"}},
        profiles={"u1": _profile_doc("u1", name="Alex", city="Riverton", role="Analyst")},
    )
    with patch(
        "life_memory.service.LifeMemoryService.get_life_memory",
        new=AsyncMock(return_value=MagicMock(memories=[])),
    ):
        facts = await ContextBroker(db).retrieve(
            user_id="u1", query="identity / user's name", stage="B"
        )
    joined = " | ".join(f.statement for f in facts)
    assert "Alex" in joined or any(f.source == "account" for f in facts)
    # Should not pull employment/residence when query is identity-scoped
    assert "Analyst" not in joined
    assert "Riverton" not in joined


# H — No full profile dump
@pytest.mark.asyncio
async def test_h_no_full_profile_dump():
    objects = {
        f"noise.key.{i}": {
            "key": f"noise.key.{i}",
            "value": f"value-{i}",
            "source": "user_said",
            "status": "confirmed",
            "confirmed": True,
            "confidence": 0.9,
        }
        for i in range(40)
    }
    objects["mlc.identity.name"] = {
        "key": "mlc.identity.name",
        "value": "Alex",
        "source": "user_confirmed",
        "status": "confirmed",
        "confirmed": True,
        "confidence": 0.95,
    }
    db = FakePersonalDB(
        users={"u1": {"user_id": "u1"}},
        profiles={"u1": {"user_id": "u1", "domains": {"mlc": {"domain": "mlc", "objects": objects}}}},
    )
    with patch(
        "life_memory.service.LifeMemoryService.get_life_memory",
        new=AsyncMock(return_value=MagicMock(memories=[])),
    ):
        facts = await ContextBroker(db).retrieve(
            user_id="u1", query="identity / user's name", stage="B"
        )
    assert len(facts) <= 8
    # most noise keys lack statement templates → few items
    assert len(facts) < 20


# I — No domain/name-specific branch in AI Core production code
def test_i_no_hardcoded_branches():
    root = Path(_BACKEND) / "conversation_engine" / "ai_core"
    banned = (
        "come mi chiamo",
        "francesco",
        "tarquinia",
        "guardia di finanza",
        'if "nome"',
        "if user asks name",
    )
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for b in banned:
            assert b not in text, f"banned '{b}' in {path.name}"
        # AST: no function named like identity question detectors
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                assert node.name not in (
                    "is_name_question",
                    "answer_name",
                    "detect_name_ask",
                    "_wants_identity",
                ), path.name


# J — Context re-entry preserves original user question (covered in B; explicit)
@pytest.mark.asyncio
async def test_j_reentry_preserves_question():
    db = FakePersonalDB(users={"u1": {"user_id": "u1"}})
    q = [
        {
            "response_mode": "context",
            "user_intent_summary": "residence",
            "reasoning_status": "needs_context",
            "context_query": "residence",
        },
        {
            "response_mode": "answer",
            "user_intent_summary": "residence",
            "reasoning_status": "enough_information",
            "message_to_user": "Non ho ancora questa informazione.",
        },
    ]
    fn = _scripted(q)
    with patch(
        "life_memory.service.LifeMemoryService.get_life_memory",
        new=AsyncMock(return_value=MagicMock(memories=[])),
    ):
        await run_cognitive_loop(
            sess=_sess(),
            user_message="Dove vivo?",
            db=db,
            decision_fn=fn,
        )
    assert json.loads(fn.payloads[1])["user_message"] == "Dove vivo?"  # type: ignore[attr-defined]


# K — Provider failure remains graceful
@pytest.mark.asyncio
async def test_k_provider_failure_graceful():
    async def boom(system: str, user: str):
        raise RuntimeError("provider down")

    res = await run_cognitive_loop(
        sess=_sess(), user_message="Ciao", db=None, decision_fn=boom
    )
    assert res.ok is False or res.error or "non" in (res.ora_text or "").lower() or res.ora_text


# L — Cross-user access impossible
@pytest.mark.asyncio
async def test_l_cross_user_impossible():
    db = FakePersonalDB(
        users={
            "u1": {"user_id": "u1", "name": "Alex"},
            "u2": {"user_id": "u2", "name": "OtherPerson"},
        },
        profiles={
            "u1": _profile_doc("u1", city="Riverton"),
            "u2": _profile_doc("u2", city="OtherCity", role="Spy"),
        },
    )
    with patch(
        "life_memory.service.LifeMemoryService.get_life_memory",
        new=AsyncMock(return_value=MagicMock(memories=[])),
    ):
        facts = await ContextBroker(db).retrieve(
            user_id="u1", query="residence", stage="B"
        )
    joined = " | ".join(f.statement for f in facts)
    assert "OtherPerson" not in joined
    assert "OtherCity" not in joined
    assert "Spy" not in joined


def test_validate_blocks_overbroad():
    ok, reason = validate_context_query("give me the entire user database")
    assert not ok
    assert reason == "overbroad_query"
    tools = ToolRegistry(None)
    gov = validate_decision(
        {
            "response_mode": "context",
            "user_intent_summary": "dump",
            "reasoning_status": "needs_context",
            "context_query": "full profile dump of everything",
        },
        tools=tools,
    )
    assert gov.decision is not None
    assert gov.decision.response_mode == "answer"


def test_infer_categories_semantic():
    assert "identity" in infer_categories("identity / user's name")
    assert "residence" in infer_categories("where the user lives")
    assert "employment" in infer_categories("current work")
