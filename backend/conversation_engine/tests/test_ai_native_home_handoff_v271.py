"""V2.7.1 — Home → ORA first-turn handoff (pending_turn + message identity)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest

os.environ["AI_CORE_TRACE"] = "1"

_BACKEND = str(Path(__file__).resolve().parents[2])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from conversation_engine.ai_core import state as state_mod
from conversation_engine.ai_core.orchestrator import AICoreOrchestrator
from location.place_label import ResolvedPlace
from location.service import LocationService


class _MemCol:
    def __init__(self):
        self.docs: List[dict] = []
        self.indexes: List[Any] = []

    async def create_index(self, *args, **kwargs):
        self.indexes.append((args, kwargs))

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def find_one(self, q, proj=None, sort=None):
        matches = [d for d in self.docs if all(d.get(k) == v for k, v in q.items())]
        if sort:
            field, direction = sort[0]
            matches.sort(key=lambda d: d.get(field) or "", reverse=direction < 0)
        return dict(matches[0]) if matches else None

    async def replace_one(self, q, doc, upsert=False):
        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in q.items()):
                self.docs[i] = dict(doc)
                return
        if upsert:
            self.docs.append(dict(doc))

    async def update_one(self, q, update, upsert=False):
        def _apply_set(doc: dict, sets: dict) -> dict:
            out = dict(doc)
            for k, v in sets.items():
                if "." in k:
                    parts = k.split(".")
                    cur = out
                    for p in parts[:-1]:
                        nxt = cur.get(p)
                        if not isinstance(nxt, dict):
                            nxt = {}
                            cur[p] = nxt
                        cur = nxt
                    cur[parts[-1]] = v
                else:
                    out[k] = v
            return out

        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in q.items()):
                if "$set" in update:
                    self.docs[i] = _apply_set(d, update["$set"])
                return
        if upsert:
            base = dict(q)
            if "$set" in update:
                base = _apply_set(base, update["$set"])
            self.docs.append(base)


class FakeDB:
    def __init__(self):
        self._cols: Dict[str, _MemCol] = {}
        self.users = _MemCol()
        self.conversation_sessions = _MemCol()

    def __getitem__(self, name: str) -> _MemCol:
        if name == "users":
            return self.users
        if name == "conversation_sessions":
            return self.conversation_sessions
        if name not in self._cols:
            self._cols[name] = _MemCol()
        return self._cols[name]


@pytest.fixture
def db():
    return FakeDB()


@pytest.mark.asyncio
async def test_home_start_server_only_persists_assistant(db):
    async def decision_fn(system: str, user: str):
        return {
            "response_mode": "answer",
            "user_intent_summary": "name",
            "reasoning_status": "enough_information",
            "message_to_user": "Ti chiami Francesco.",
        }

    orch = AICoreOrchestrator(db, decision_fn=decision_fn)
    started = await orch.start(
        "u1", text="Come mi chiamo?", origin="home", entry_point="home"
    )
    assert started["ok"]
    assert "Francesco" in (started.get("ora_text") or "")
    assert not (started.get("client_actions") or [])
    got = await orch.get("u1", started["session_id"])
    roles = [h["role"] for h in got["history"]]
    assert roles.count("user") == 1
    assert roles.count("ora") == 1
    assert got["history"][0]["message_id"]
    assert (got.get("pending_turn") or {}).get("status") != "awaiting_client"


@pytest.mark.asyncio
async def test_home_start_location_pending_survives_get(db):
    """Home start pauses on client_action; GET must expose pending_turn for ORA mount."""
    await LocationService(db).set_preference("u1", "while_using")

    async def decision_fn(system: str, user: str):
        return {
            "response_mode": "tool",
            "user_intent_summary": "where",
            "reasoning_status": "needs_tool",
            "tool_call": {
                "capability": "get_current_location",
                "operation": "run",
                "arguments": {},
                "reason": "need",
            },
        }

    orch = AICoreOrchestrator(db, decision_fn=decision_fn)
    started = await orch.start(
        "u1", text="Dove sono adesso?", origin="home", entry_point="home"
    )
    assert started["ok"]
    assert started.get("client_actions")
    assert (started.get("pending_turn") or {}).get("status") == "awaiting_client"
    assert (started.get("ora_text") or "") == ""

    got = await orch.get("u1", started["session_id"])
    assert len([h for h in got["history"] if h["role"] == "user"]) == 1
    assert not any(h["role"] == "ora" and h.get("text") for h in got["history"])
    pt = got.get("pending_turn") or {}
    assert pt.get("status") == "awaiting_client"
    assert pt.get("id")
    assert got.get("client_actions")
    assert got["client_actions"][0]["type"] == "request_foreground_location"


@pytest.mark.asyncio
async def test_client_resume_after_home_pending(db):
    await LocationService(db).set_preference("u1", "while_using")

    step = {"n": 0}

    async def decision_fn(system: str, user: str):
        step["n"] += 1
        if step["n"] == 1:
            return {
                "response_mode": "tool",
                "user_intent_summary": "where",
                "reasoning_status": "needs_tool",
                "tool_call": {
                    "capability": "get_current_location",
                    "operation": "run",
                    "arguments": {},
                    "reason": "need",
                },
            }
        return {
            "response_mode": "answer",
            "user_intent_summary": "where",
            "reasoning_status": "enough_information",
            "message_to_user": "Ti trovi a Vibo Marina.",
        }

    orch = AICoreOrchestrator(db, decision_fn=decision_fn)
    started = await orch.start("u1", text="Dove sono adesso?", origin="home")
    assert (started.get("pending_turn") or {}).get("status") == "awaiting_client"

    svc = LocationService(db)
    with patch.object(
        svc,
        "_reverse_place",
        AsyncMock(
            return_value=ResolvedPlace(
                display_label="Vibo Marina",
                locality="Vibo Marina",
                municipality="Vibo Valentia",
                precision="locality",
            )
        ),
    ):
        await svc.ingest_foreground_signal("u1", latitude=38.715, longitude=16.13)

    step["n"] = 0
    resumed = await orch.client_resume(
        "u1",
        started["session_id"],
        completed=["request_foreground_location"],
    )
    assert "Vibo Marina" in (resumed.get("ora_text") or "")
    got = await orch.get("u1", started["session_id"])
    users = [h for h in got["history"] if h["role"] == "user"]
    assert len(users) == 1
    assert (got.get("pending_turn") or {}).get("status") != "awaiting_client"


@pytest.mark.asyncio
async def test_identical_text_two_turns_both_persist(db):
    async def decision_fn(system: str, user: str):
        return {
            "response_mode": "answer",
            "user_intent_summary": "ack",
            "reasoning_status": "enough_information",
            "message_to_user": "Ok.",
        }

    orch = AICoreOrchestrator(db, decision_fn=decision_fn)
    started = await orch.start("u1", text="ciao")
    sid = started["session_id"]
    await orch.message("u1", sid, text="ciao", client_message_id="cmsg_a")
    await orch.message("u1", sid, text="ciao", client_message_id="cmsg_b")
    got = await orch.get("u1", sid)
    user_texts = [h["text"] for h in got["history"] if h["role"] == "user"]
    assert user_texts.count("ciao") == 3
    ids = [h["message_id"] for h in got["history"] if h["role"] == "user"]
    assert len(ids) == len(set(ids))


@pytest.mark.asyncio
async def test_message_id_idempotency(db):
    async def decision_fn(system: str, user: str):
        return {
            "response_mode": "answer",
            "user_intent_summary": "ack",
            "reasoning_status": "enough_information",
            "message_to_user": "Ok.",
        }

    orch = AICoreOrchestrator(db, decision_fn=decision_fn)
    started = await orch.start("u1", text="primo")
    sid = started["session_id"]
    await orch.message("u1", sid, text="stesso", client_message_id="cmsg_same")
    await orch.message("u1", sid, text="stesso", client_message_id="cmsg_same")
    got = await orch.get("u1", sid)
    assert len([h for h in got["history"] if h.get("message_id") == "cmsg_same"]) == 1


def test_public_pending_turn_reconstructs_actions():
    st = {
        "pending_turn": {
            "id": "pt_abc",
            "status": "awaiting_client",
            "capability": "get_current_location",
            "client_actions": [],
        },
        "pending_client_capability": {
            "capability": "get_current_location",
            "action": "request_foreground_location",
            "refresh": True,
        },
        "pending_client_resume_message": "Dove sono adesso?",
    }
    pub = state_mod.public_pending_turn(st)
    assert pub["status"] == "awaiting_client"
    assert pub["client_actions"][0]["type"] == "request_foreground_location"
