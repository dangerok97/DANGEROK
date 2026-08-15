"""V2.6.1 — Source-grounded reconciliation (generic, no domain handlers)."""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from life_os.evidence import (
    human_display_name,
    merge_evidence_refs,
    public_evidence_sources,
)
from life_os.models import EvidenceRef, LifeOsPlan, PlanItem
from life_os.service import LifeOsService


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
            ok = all(doc.get(k) == v for k, v in q.items() if k != "_id")
            if ok:
                return dict(doc)
        return None

    def find(self, flt, proj=None):
        class C:
            def sort(self, *a, **k):
                return self

            def limit(self, n):
                return self

            async def to_list(self, n):
                return []

        return C()

    async def create_index(self, *a, **k):
        return None


class FakeDB:
    def __init__(self):
        self.life_os_plans = FakeCol()
        self.life_os_objects = FakeCol()
        self.life_os_artifacts = FakeCol()
        self.goals = FakeCol()
        self.conversation_sessions = FakeCol()
        self._c = {
            "life_os_plans": self.life_os_plans,
            "life_os_objects": self.life_os_objects,
            "life_os_artifacts": self.life_os_artifacts,
            "goals": self.goals,
            "conversation_sessions": self.conversation_sessions,
        }

    def __getitem__(self, name):
        if name not in self._c:
            self._c[name] = FakeCol()
        return self._c[name]


@pytest.mark.asyncio
async def test_replace_items_keeps_identity_and_drops_assumptions(monkeypatch):
    db = FakeDB()
    svc = LifeOsService(db)

    async def _noop_goal(user_id, plan):
        return plan.goal_id or "goal_x"

    monkeypatch.setattr(svc, "_upsert_goal", _noop_goal)

    plan = await svc.create_plan(
        "u1",
        summary="Provvisorio",
        target_date="2026-08-23",
        conversation_session_id="ces_abc",
        items=[
            {"title": "Assunzione A", "origin": "model_assumption"},
            {"title": "Assunzione B", "origin": "model_assumption"},
            {"title": "Vincolo utente", "origin": "user_stated", "status": "completed"},
        ],
    )
    # Force session/goal as create may soft-fail goal
    plan.goal_id = "goal_keep"
    plan.conversation_session_id = "ces_abc"
    await svc.repo.save_plan(plan)

    updated = await svc.update_plan(
        "u1",
        plan.id,
        replace_items=[
            {"title": "Modulo 1", "origin": "user_file"},
            {"title": "Modulo 2", "origin": "user_file"},
            {"title": "Vincolo utente", "origin": "user_stated"},
        ],
        reconciliation_mode="rebuild_from_evidence",
        patch={
            "summary": "Riallineato",
            "evidence_refs": [
                {
                    "ref": "doc_1",
                    "kind": "USER_PROVIDED_CONTENT",
                    "display_name": "Programma ufficiale.pdf",
                    "source_type": "user_file",
                    "source_id": "doc_1",
                    "status": "active",
                }
            ],
        },
    )
    assert updated.id == plan.id
    assert updated.target_date == "2026-08-23"
    assert updated.conversation_session_id == "ces_abc"
    assert updated.goal_id == "goal_keep"
    titles = [i.title for i in updated.items]
    assert "Assunzione A" not in titles
    assert "Assunzione B" not in titles
    assert "Modulo 1" in titles and "Modulo 2" in titles
    # progress preserved on matching title
    user_it = next(i for i in updated.items if i.title == "Vincolo utente")
    assert user_it.status == "completed"
    mut = updated.meta.get("last_mutation") or {}
    assert mut.get("op") == "replace_items"
    pubs = public_evidence_sources(updated.evidence_refs)
    assert pubs[0]["display_name"] == "Programma ufficiale.pdf"
    assert "doc_" not in pubs[0]["display_name"]


@pytest.mark.asyncio
async def test_user_stated_not_blindly_removed_on_replace_scope(monkeypatch):
    db = FakeDB()
    svc = LifeOsService(db)

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(svc, "_upsert_goal", _noop)
    plan = await svc.create_plan(
        "u1",
        summary="X",
        items=[
            {"title": "Old guess", "origin": "model_assumption"},
            {"title": "Must keep", "origin": "user_stated"},
        ],
    )
    updated = await svc.update_plan(
        "u1",
        plan.id,
        replace_items=[{"title": "New from evidence", "origin": "user_file"}],
        reconciliation_mode="replace_scope",
    )
    titles = [i.title for i in updated.items]
    assert "Must keep" in titles
    assert "Old guess" not in titles
    assert "New from evidence" in titles


def test_public_sources_never_show_internal_ids():
    refs = [
        EvidenceRef(ref="lcf_abc123", kind="USER_PROVIDED_CONTENT", label=""),
        EvidenceRef(
            ref="doc_xyz",
            kind="USER_PROVIDED_CONTENT",
            display_name="Bolletta luce.pdf",
            source_type="user_file",
            source_id="doc_xyz",
        ),
        EvidenceRef(
            ref="doc_xyz",
            kind="USER_PROVIDED_CONTENT",
            label="Bolletta luce.pdf",
            source_id="doc_xyz",
            status="active",
        ),
        EvidenceRef(
            ref="doc_old",
            kind="USER_PROVIDED_CONTENT",
            display_name="old.txt",
            status="superseded",
            source_id="doc_old",
        ),
    ]
    pubs = public_evidence_sources(refs)
    assert len(pubs) == 1  # dedupe + hide superseded + skip bare id-only
    assert pubs[0]["display_name"] == "Bolletta luce.pdf"
    assert pubs[0]["authority_label"] == "Fornito da te"
    assert human_display_name({"ref": "lcf_zzz"}) == "Fonte"


def test_merge_supersedes_prior_user_files():
    prior = [
        {
            "ref": "doc_old",
            "kind": "USER_PROVIDED_CONTENT",
            "display_name": "old.txt",
            "source_id": "doc_old",
            "source_type": "user_file",
        }
    ]
    incoming = [
        {
            "ref": "doc_new",
            "kind": "USER_PROVIDED_CONTENT",
            "display_name": "new.pdf",
            "source_id": "doc_new",
            "source_type": "user_file",
            "status": "active",
        }
    ]
    merged = merge_evidence_refs(prior, incoming, supersede_prior_user_files=True)
    by = {e.source_id or e.ref: e for e in merged}
    assert by["doc_old"].status == "superseded"
    assert by["doc_new"].status == "active"
    pubs = public_evidence_sources(merged)
    assert [p["display_name"] for p in pubs] == ["new.pdf"]


def test_conversational_fact_does_not_supersede_user_file():
    prior = [
        {
            "ref": "doc_pdf",
            "kind": "USER_PROVIDED_CONTENT",
            "display_name": "Brief manager.pdf",
            "source_type": "user_file",
            "source_id": "doc_pdf",
        }
    ]
    incoming = [
        {
            "ref": "conv:s:t",
            "kind": "USER_PROVIDED_CONTENT",
            "display_name": "Tempo ridotto",
            "source_type": "user_conversation",
            "source_id": "conv:s:t",
        }
    ]
    merged = merge_evidence_refs(prior, incoming, supersede_prior_user_files=True)
    by = {e.source_id or e.ref: e for e in merged}
    assert by["doc_pdf"].status == "active"
    pubs = public_evidence_sources(merged)
    names = {p["display_name"] for p in pubs}
    assert "Brief manager.pdf" in names
    assert "Tempo ridotto" in names


def test_no_domain_reconcile_branches():
    from pathlib import Path

    banned = (
        "study_reconcile",
        "exam_reconcile",
        "bill_reconcile",
        "contract_reconcile",
        "syllabus_reconcile",
        "spazi vettoriali",
        "matematica computazionale",
    )
    roots = [
        Path(__file__).resolve().parents[2] / "life_os",
        Path(__file__).resolve().parents[1] / "ai_core" / "tools" / "life_os_caps.py",
    ]
    for root in roots:
        paths = [root] if root.is_file() else list(root.rglob("*.py"))
        for path in paths:
            low = path.read_text(encoding="utf-8").lower()
            for b in banned:
                assert b not in low, f"{b} in {path}"


@pytest.mark.asyncio
async def test_update_plan_cap_observation_replace(monkeypatch):
    from conversation_engine.ai_core.tools import life_os_caps as caps

    db = FakeDB()
    svc = LifeOsService(db)

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(svc, "_upsert_goal", _noop)
    plan = await svc.create_plan(
        "u1",
        summary="P",
        target_date="2026-09-01",
        items=[{"title": "Old", "origin": "model_assumption"}],
    )
    plan.conversation_session_id = "ces_1"
    plan.goal_id = "g1"
    await svc.repo.save_plan(plan)

    monkeypatch.setattr(caps, "_svc", lambda db: svc)
    obs = await caps.update_plan(
        {
            "plan_id": plan.id,
            "replace_items": [{"title": "New A"}, {"title": "New B"}],
            "reconciliation_mode": "rebuild_from_evidence",
        },
        {"user_id": "u1", "db": db},
    )
    assert obs.status == "ok"
    assert obs.payload["operation"] == "replace_items"
    assert obs.payload["identity_preserved"]["plan_id"] is True
    assert obs.payload["identity_preserved"]["target_date"] is True
    assert "Old" in (obs.payload.get("removed") or [])


def test_renderer_uses_theme_not_static_dark():
    from pathlib import Path
    import re

    src = (
        Path(__file__).resolve().parents[3]
        / "frontend"
        / "src"
        / "components"
        / "generative"
        / "GenerativeObjectRenderer.tsx"
    )
    text = src.read_text(encoding="utf-8")
    code = re.sub(r"/\*[\s\S]*?\*/", "", text)
    code = re.sub(r"//.*?$", "", code, flags=re.M)
    assert "useTheme" in code
    assert "const colors = tokens.color" not in code
    assert "tokens.color" not in code


def test_workspace_fonti_uses_public_sources():
    from pathlib import Path

    ws = (
        Path(__file__).resolve().parents[3]
        / "frontend"
        / "app"
        / "goal-workspace"
        / "[planId].tsx"
    )
    text = ws.read_text(encoding="utf-8")
    assert "public_sources" in text
    assert "authority_label" in text or "Fornito da te" in text
