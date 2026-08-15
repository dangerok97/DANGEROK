"""V2.5 — production ORA surface integration (routing, ownership, no /ora-ai prod links)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from conversation_engine.ai_core.orchestrator import AICoreOrchestrator
from life_os.generative_models import GenerativeObject
from life_os.models import LifeOsPlan
from life_os.repository import LifeOsRepository
from life_os.service import LifeOsService


ROOT = Path(__file__).resolve().parents[3]
FE = ROOT / "frontend"


class FakeCol:
    def __init__(self):
        self.docs: Dict[str, dict] = {}

    async def insert_one(self, doc):
        self.docs[doc["id"]] = dict(doc)

    async def replace_one(self, q, doc, upsert=False):
        key = q.get("id") or doc.get("id")
        self.docs[key] = dict(doc)

    async def update_one(self, flt, upd, upsert=False):
        d = await self.find_one(flt)
        if d:
            d.update(upd.get("$set") or {})
            self.docs[d["id"]] = d

    async def find_one(self, q, proj=None):
        for doc in self.docs.values():
            ok = True
            for k, v in q.items():
                if k == "_id":
                    continue
                if isinstance(v, dict) and "$in" in v:
                    if doc.get(k) not in v["$in"]:
                        ok = False
                        break
                elif doc.get(k) != v:
                    ok = False
                    break
            if ok:
                return dict(doc)
        return None

    def find(self, flt, proj=None):
        matched = []
        for d in self.docs.values():
            ok = True
            for k, v in flt.items():
                if k == "_id":
                    continue
                if isinstance(v, dict) and "$in" in v:
                    if d.get(k) not in v["$in"]:
                        ok = False
                        break
                elif d.get(k) != v:
                    ok = False
                    break
            if ok:
                matched.append(dict(d))

        class C:
            def sort(self, *a, **k):
                return self

            def limit(self, n):
                return self

            async def to_list(self, n):
                return matched[:n]

        return C()

    async def create_index(self, *a, **k):
        return None


class FakeDB:
    def __init__(self):
        self.conversation_sessions = FakeCol()
        self.life_os_plans = FakeCol()
        self.life_os_objects = FakeCol()
        self._c = {
            "conversation_sessions": self.conversation_sessions,
            "life_os_plans": self.life_os_plans,
            "life_os_objects": self.life_os_objects,
        }

    def __getitem__(self, name):
        if name not in self._c:
            self._c[name] = FakeCol()
        return self._c[name]


def _scripted(queue: List[Dict[str, Any]]):
    async def fn(system: str, user: str) -> Dict[str, Any]:
        if not queue:
            return {
                "response_mode": "answer",
                "user_intent_summary": "done",
                "reasoning_status": "enough_information",
                "message_to_user": "Ok.",
            }
        return queue.pop(0)

    return fn


_HELLO = [
    {
        "response_mode": "answer",
        "user_intent_summary": "hi",
        "reasoning_status": "enough_information",
        "message_to_user": "Ciao.",
    }
]


@pytest.mark.asyncio
async def test_ai_core_route_is_production_ora():
    db = FakeDB()
    orch = AICoreOrchestrator(db, decision_fn=_scripted(list(_HELLO)))
    res = await orch.start("u1", text="Ciao", origin="home", entry_point="home")
    assert res["ok"]
    assert res["route"] == f"/ora/{res['session_id']}"
    assert "ora-ai" not in res["route"]
    assert res.get("entry_point") == "home"


@pytest.mark.asyncio
async def test_session_ownership_enforced():
    db = FakeDB()
    orch = AICoreOrchestrator(db, decision_fn=_scripted(list(_HELLO)))
    res = await orch.start("u1", text="Ciao", origin="home")
    sid = res["session_id"]
    other = await orch.get("u2", sid)
    assert other.get("ok") is False
    assert other.get("error") == "not_found"


@pytest.mark.asyncio
async def test_plan_ownership_enforced():
    db = FakeDB()
    svc = LifeOsService(db)
    plan = LifeOsPlan(user_id="u1", summary="X", desired_outcome="Y")
    await svc.repo.insert_plan(plan)
    assert await svc.repo.get_plan("u2", plan.id) is None
    assert await svc.repo.get_plan("u1", plan.id) is not None


@pytest.mark.asyncio
async def test_object_ownership_enforced():
    db = FakeDB()
    repo = LifeOsRepository(db)
    obj = GenerativeObject(user_id="u1", title="T", content={"blocks": []})
    await repo.insert_object(obj)
    assert await repo.get_object("u2", obj.id) is None
    assert await repo.get_object("u1", obj.id) is not None


def test_production_fe_does_not_navigate_to_ora_ai():
    files = [
        FE / "src" / "components" / "home" / "quiet" / "OraInput.tsx",
        FE / "app" / "(tabs)" / "ora.tsx",
        FE / "app" / "goal-workspace" / "[planId].tsx",
        FE / "src" / "ora" / "oraNav.ts",
        FE / "src" / "ora" / "startOraConversation.ts",
        FE / "app" / "ora" / "index.tsx",
        FE / "app" / "ora" / "[sessionId].tsx",
    ]
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert "router.push(`/ora-ai" not in text
        assert 'router.push("/ora-ai' not in text
        assert "router.replace(`/ora-ai" not in text


def test_ora_ai_marked_dev_only():
    idx = (FE / "app" / "ora-ai" / "index.tsx").read_text(encoding="utf-8")
    sess = (FE / "app" / "ora-ai" / "[sessionId].tsx").read_text(encoding="utf-8")
    assert "DEV" in idx
    assert "devHarness" in sess


def test_no_domain_routing_in_ora_nav():
    nav = (FE / "src" / "ora" / "oraNav.ts").read_text(encoding="utf-8").lower()
    for banned in ("studyconversation", "travelflow", "if exam", "if travel", "dogassistant"):
        assert banned not in nav


def test_ora_nav_module_resolvable_for_metro():
    """V2.5.1 — Metro could not resolve a module named nav.ts; use oraNav.ts."""
    assert (FE / "src" / "ora" / "oraNav.ts").is_file()
    assert not (FE / "src" / "ora" / "nav.ts").exists()
    src = (FE / "src" / "ora" / "startOraConversation.ts").read_text(encoding="utf-8")
    assert "oraNav" in src
    assert 'from "./nav"' not in src and "from './nav'" not in src


def test_ora_input_uses_ai_core_not_conversation_engine():
    src = (FE / "src" / "components" / "home" / "quiet" / "OraInput.tsx").read_text(
        encoding="utf-8"
    )
    assert "startOraConversation" in src
    assert "ConversationEngine" not in src


def test_humanize_network_and_auth_messages():
    err_src = (FE / "src" / "utils" / "errors.ts").read_text(encoding="utf-8")
    assert "failed to fetch" in err_src.lower() or "looksNetwork" in err_src
    assert "sessione è scaduta" in err_src or "Accedi di nuovo" in err_src
    assert "raggiungere il server" in err_src


def test_life_map_href_not_ora_ai():
    src = (ROOT / "backend" / "life_map" / "assemble.py").read_text(encoding="utf-8")
    # production fallback must be /ora/{sess} not /ora-ai
    assert '/ora-ai/{sess}' not in src
    assert '/ora/{sess}' in src or '"/ora/' in src
