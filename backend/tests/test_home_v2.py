"""Home V2 — aggregator, ranking, fixtures A–G, actions, isolation."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")


def _run(coro):
    return asyncio.run(coro)


def _now():
    return datetime.now(timezone.utc)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean_user(db, user_id: str):
    for col in (
        "documents", "decisions", "tasks", "life_nodes", "ingestion_events",
        "connector_instances", "home_item_state", "home_snapshots", "home_insights",
        "link_proposals", "reminders", "users",
    ):
        await db[col].delete_many({"user_id": user_id})


async def _svc(db):
    from home.service import HomeService
    svc = HomeService(db)
    await svc.ensure_indexes()
    return svc


def test_ranking_version_constant():
    from home.models import RANKING_VERSION
    assert RANKING_VERSION == "home-rank-1.4"


def test_empty_home():
    async def body():
        client, db = await _db()
        user = f"u_empty_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            svc = await _svc(db)
            home = await svc.build_home(user)
            assert home.primary_focus is None
            assert home.priorities == []
            assert home.resume_item is None
            assert home.ranking_version == "home-rank-1.4"
            assert home.google_calendar["connected"] is False
            assert home.google_calendar["show_banner"] is True
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_fixture_a_bill_due_3_days():
    async def body():
        client, db = await _db()
        user = f"u_bill_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            due = (_now() + timedelta(days=3)).date().isoformat()
            doc_id = f"doc_{uuid.uuid4().hex[:10]}"
            await db.documents.insert_one({
                "id": doc_id, "user_id": user, "filename": "bolletta.pdf",
                "display_title": "Bolletta luce",
                "analysis": {"macro_category": "financial", "confidence": 0.9, "suggested_title": "Bolletta luce"},
                "admin_analysis": {
                    "subject": "Bolletta luce", "amount": "87.50", "currency": "€",
                    "due_date": due, "completed": False, "confidence": 0.9,
                },
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            svc = await _svc(db)
            home = await svc.build_home(user)
            assert home.primary_focus is not None
            assert home.primary_focus["type"] in ("bill", "payment")
            assert "score" not in home.primary_focus
            assert home.explanation is not None
            assert home.explanation.factors
            assert any(a["kind"] == "complete" for a in home.primary_focus["actions"])
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_fixture_b_concert_tomorrow():
    async def body():
        client, db = await _db()
        user = f"u_concert_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            start = (_now() + timedelta(days=1)).replace(hour=21, minute=0, second=0, microsecond=0).isoformat()
            doc_id = f"doc_{uuid.uuid4().hex[:10]}"
            await db.documents.insert_one({
                "id": doc_id, "user_id": user, "filename": "biglietto.pdf",
                "display_title": "Concerto rock",
                "analysis": {"macro_category": "event", "subcategory": "concert", "confidence": 0.88,
                             "suggested_title": "Concerto rock"},
                "event_candidates": [{
                    "id": "ev1", "title": "Concerto rock", "status": "proposed",
                    "start_datetime": start, "venue_name": "Arena", "city": "Verona",
                    "confidence": 0.88, "category": "concert",
                }],
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            svc = await _svc(db)
            home = await svc.build_home(user)
            assert home.primary_focus is not None
            assert home.primary_focus["type"] in ("event", "needs_review")
            assert any(a["kind"] == "maps" for a in home.primary_focus["actions"]) or home.primary_focus.get("location")
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_fixture_c_anthropology_resume():
    async def body():
        client, db = await _db()
        user = f"u_study_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            doc_id = f"doc_{uuid.uuid4().hex[:10]}"
            await db.documents.insert_one({
                "id": doc_id, "user_id": user, "filename": "antropologia.pdf",
                "display_title": "Antropologia — habitus",
                "analysis": {"macro_category": "education", "confidence": 0.8, "suggested_title": "Habitus"},
                "education_analysis": {
                    "subject": "Antropologia", "topic": "Habitus", "suggested_title": "Habitus",
                    "summary_short": "Bourdieu", "confidence": 0.8,
                },
                "flashcards": [
                    {"id": "c1", "question": "Cos'è l'habitus?", "answer": "...", "review_status": "learning"},
                ],
                "quiz_session": {
                    "id": "q1", "document_id": doc_id, "status": "active",
                    "current_index": 0, "turns": [{"question": "Definisci habitus", "covered": False}],
                    "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
                },
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            svc = await _svc(db)
            home = await svc.build_home(user)
            assert home.resume_item is not None
            assert home.resume_item["type"] == "resume"
            # study should appear in priorities or as focus if sole item
            types = set()
            if home.primary_focus:
                types.add(home.primary_focus["type"])
            for g in home.priorities:
                for it in g.items:
                    types.add(it["type"])
            assert "study" in types or home.resume_item is not None
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_fixture_d_deferred_insight_and_admin():
    async def body():
        client, db = await _db()
        user = f"u_def_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            for i in range(3):
                did = f"doc_def_{i}_{uuid.uuid4().hex[:6]}"
                await db.documents.insert_one({
                    "id": did, "user_id": user, "filename": f"admin{i}.pdf",
                    "analysis": {"macro_category": "administrative", "confidence": 0.7},
                    "admin_analysis": {
                        "subject": f"Pratica {i}", "due_date": (_now() + timedelta(days=10 + i)).date().isoformat(),
                        "completed": False, "deferred": True, "confidence": 0.7,
                    },
                    "generic_actions": [
                        {"id": f"a{i}", "label": f"Completa pratica {i}", "completed": False, "deferred": True},
                    ],
                    "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
                })
            svc = await _svc(db)
            home = await svc.build_home(user)
            waiting = next((g for g in home.priorities if g.key == "waiting"), None)
            assert waiting is not None
            assert len(waiting.items) >= 3
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_fixture_e_google_disconnected_banner():
    async def body():
        client, db = await _db()
        user = f"u_gcal_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            svc = await _svc(db)
            home = await svc.build_home(user)
            assert home.google_calendar["show_banner"] is True
            codes = [w.code for w in home.connection_warnings]
            assert "google_calendar_disconnected" in codes
            await svc.apply_action(user, item_id="__google_banner__", action="dismiss_banner")
            home2 = await svc.build_home(user)
            assert home2.google_calendar["show_banner"] is False
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_fixture_f_medical_visit_discreet():
    async def body():
        client, db = await _db()
        user = f"u_visit_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            start = (_now() + timedelta(hours=30)).isoformat()
            doc_id = f"doc_{uuid.uuid4().hex[:10]}"
            await db.documents.insert_one({
                "id": doc_id, "user_id": user, "filename": "visita.pdf",
                "analysis": {"macro_category": "medical", "subcategory": "visita", "confidence": 0.85,
                             "suggested_title": "Visita di controllo"},
                "event_candidates": [{
                    "id": "v1", "title": "Visita di controllo", "status": "proposed",
                    "start_datetime": start, "venue_name": "Ambulatorio", "confidence": 0.85,
                    "category": "medical",
                }],
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            svc = await _svc(db)
            home = await svc.build_home(user)
            assert home.primary_focus is not None
            assert home.primary_focus["type"] == "visit"
            # no fake energy / 100 score fields
            assert "energy" not in home.primary_focus
            assert "score" not in home.primary_focus
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_fixture_g_ambiguous_doc_needs_review():
    async def body():
        client, db = await _db()
        user = f"u_amb_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            doc_id = f"doc_{uuid.uuid4().hex[:10]}"
            await db.documents.insert_one({
                "id": doc_id, "user_id": user, "filename": "scan_ambiguo.pdf",
                "display_title": "Documento ambiguo",
                "pipeline_status": "needs_review",
                "analysis": {"macro_category": "generic", "confidence": 0.35, "suggested_title": "Documento ambiguo",
                             "requires_review": True},
                "event_candidates": [{
                    "id": "amb1", "title": "Data ambigua", "status": "proposed",
                    "ambiguous_date": True, "confidence": 0.4, "missing_fields": ["start_datetime"],
                }],
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            svc = await _svc(db)
            home = await svc.build_home(user)
            assert home.primary_focus is not None
            assert home.primary_focus["type"] in ("needs_review", "verify")
            assert home.explanation is not None
            assert home.explanation.missing_data or any(
                f.code in ("low_confidence", "needs_review") for f in home.explanation.factors
            )
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_multi_priority_groups_and_primary():
    async def body():
        client, db = await _db()
        user = f"u_multi_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            # overdue bill
            await db.documents.insert_one({
                "id": f"doc_o_{uuid.uuid4().hex[:6]}", "user_id": user, "filename": "over.pdf",
                "analysis": {"macro_category": "financial", "confidence": 0.9},
                "admin_analysis": {
                    "subject": "Fattura scaduta", "amount": "120", "currency": "€",
                    "due_date": (_now() - timedelta(days=2)).date().isoformat(),
                    "completed": False, "confidence": 0.9,
                },
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            # later study
            await db.documents.insert_one({
                "id": f"doc_s_{uuid.uuid4().hex[:6]}", "user_id": user, "filename": "study.pdf",
                "analysis": {"macro_category": "education", "confidence": 0.8},
                "education_analysis": {"topic": "Storia", "suggested_title": "Storia", "confidence": 0.8},
                "flashcards": [{"id": "1", "question": "q", "answer": "a", "review_status": "new"}],
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            # today event
            await db.life_nodes.insert_one({
                "id": f"n_{uuid.uuid4().hex[:6]}", "user_id": user, "type": "event", "status": "active",
                "label": "Call team",
                "attributes": {"starts_at": (_now() + timedelta(hours=5)).isoformat()},
                "created_at": _now().isoformat(),
            })
            svc = await _svc(db)
            home = await svc.build_home(user)
            assert home.primary_focus is not None
            assert home.primary_focus["type"] in ("bill", "payment")
            keys = [g.key for g in home.priorities]
            assert keys == sorted(keys, key=lambda k: ["critical", "today", "this_week", "waiting", "later"].index(k))
            # primary not duplicated in priorities
            for g in home.priorities:
                assert all(it["id"] != home.primary_focus["id"] for it in g.items)
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_google_connected_no_promo():
    async def body():
        client, db = await _db()
        user = f"u_gcon_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            await db.connector_instances.insert_one({
                "id": f"ci_{uuid.uuid4().hex[:8]}", "user_id": user,
                "connector_id": "calendar_google", "status": "connected",
                "last_sync_at": _now().isoformat(),
            })
            svc = await _svc(db)
            home = await svc.build_home(user)
            assert home.google_calendar["connected"] is True
            assert home.google_calendar["show_banner"] is False
            assert not any(w.code == "google_calendar_disconnected" for w in home.connection_warnings)
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_source_error_does_not_block():
    async def body():
        client, db = await _db()
        user = f"u_err_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            # Insert a bill so home still has content even if an adapter fails
            await db.documents.insert_one({
                "id": f"doc_{uuid.uuid4().hex[:8]}", "user_id": user, "filename": "ok.pdf",
                "analysis": {"macro_category": "financial", "confidence": 0.9},
                "admin_analysis": {
                    "subject": "OK bill", "amount": "10", "currency": "€",
                    "due_date": (_now() + timedelta(days=1)).date().isoformat(),
                    "completed": False, "confidence": 0.9,
                },
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            from home import adapters as adapters_mod
            original = adapters_mod.load_reminders

            async def boom(*a, **k):
                raise RuntimeError("boom")

            adapters_mod.load_reminders = boom
            try:
                svc = await _svc(db)
                home = await svc.build_home(user)
                assert home.primary_focus is not None
                assert home.partial is True or any(w.code.startswith("source_error_") for w in home.connection_warnings)
            finally:
                adapters_mod.load_reminders = original
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_user_isolation():
    async def body():
        client, db = await _db()
        a = f"u_a_{uuid.uuid4().hex[:8]}"
        b = f"u_b_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, a)
            await _clean_user(db, b)
            await db.users.insert_one({"user_id": a, "email": f"{a}@t.ora"})
            await db.users.insert_one({"user_id": b, "email": f"{b}@t.ora"})
            await db.documents.insert_one({
                "id": f"doc_a_{uuid.uuid4().hex[:6]}", "user_id": a, "filename": "a.pdf",
                "analysis": {"macro_category": "financial", "confidence": 0.9},
                "admin_analysis": {
                    "subject": "Solo A", "amount": "50", "currency": "€",
                    "due_date": (_now() + timedelta(days=1)).date().isoformat(),
                    "completed": False, "confidence": 0.9,
                },
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            svc = await _svc(db)
            home_a = await svc.build_home(a)
            home_b = await svc.build_home(b)
            assert home_a.primary_focus is not None
            assert home_a.primary_focus["title"] == "Solo A"
            assert home_b.primary_focus is None
        finally:
            await _clean_user(db, a)
            await _clean_user(db, b)
            client.close()
    _run(body())


def test_dedupe_same_event():
    async def body():
        client, db = await _db()
        user = f"u_dup_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            start = (_now() + timedelta(hours=8)).isoformat()
            nid = f"n_{uuid.uuid4().hex[:8]}"
            await db.life_nodes.insert_one({
                "id": nid, "user_id": user, "type": "event", "status": "active",
                "label": "Standup",
                "attributes": {"starts_at": start},
                "created_at": _now().isoformat(),
            })
            await db.decisions.insert_one({
                "id": f"dec_{uuid.uuid4().hex[:8]}", "user_id": user,
                "title": "Standup", "category": "event", "status": "open",
                "starts_at": start, "origin": "user",
                "created_at": _now().isoformat(),
            })
            svc = await _svc(db)
            home = await svc.build_home(user)
            titles = []
            if home.primary_focus:
                titles.append(home.primary_focus["title"].lower())
            for g in home.priorities:
                titles.extend(it["title"].lower() for it in g.items)
            assert titles.count("standup") <= 1
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_snooze_and_complete_update_home():
    async def body():
        client, db = await _db()
        user = f"u_act_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            doc_id = f"doc_{uuid.uuid4().hex[:8]}"
            await db.documents.insert_one({
                "id": doc_id, "user_id": user, "filename": "pay.pdf",
                "analysis": {"macro_category": "financial", "confidence": 0.9},
                "admin_analysis": {
                    "subject": "Da pagare", "amount": "33", "currency": "€",
                    "due_date": (_now() + timedelta(days=2)).date().isoformat(),
                    "completed": False, "confidence": 0.9,
                },
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            svc = await _svc(db)
            home = await svc.build_home(user)
            assert home.primary_focus is not None
            item_id = home.primary_focus["id"]
            until = (_now() + timedelta(hours=6)).isoformat()
            await svc.apply_action(user, item_id=item_id, action="snooze", until=until)
            home2 = await svc.build_home(user)
            # snoozed → waiting group or not primary
            if home2.primary_focus:
                assert home2.primary_focus["id"] != item_id or home2.primary_focus.get("status") == "waiting"
            await svc.apply_action(user, item_id=item_id, action="complete")
            home3 = await svc.build_home(user)
            assert home3.primary_focus is None or home3.primary_focus["id"] != item_id
            doc = await db.documents.find_one({"id": doc_id})
            assert doc["admin_analysis"]["completed"] is True
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_update_after_document_and_free_window():
    async def body():
        client, db = await _db()
        user = f"u_upd_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            svc = await _svc(db)
            h1 = await svc.build_home(user)
            assert h1.primary_focus is None
            await db.documents.insert_one({
                "id": f"doc_{uuid.uuid4().hex[:8]}", "user_id": user, "filename": "new.pdf",
                "pipeline_status": "needs_review",
                "analysis": {"macro_category": "generic", "confidence": 0.4, "suggested_title": "Nuovo doc"},
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            h2 = await svc.build_home(user)
            assert h2.primary_focus is not None
            assert h2.current_situation is not None
            assert len(h2.current_situation.indicators) <= 4
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_overdue_activity_and_invoice():
    async def body():
        client, db = await _db()
        user = f"u_ov_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            await db.tasks.insert_one({
                "id": f"t_{uuid.uuid4().hex[:8]}", "user_id": user, "title": "Attività scaduta",
                "status": "open", "deadline": (_now() - timedelta(days=1)).isoformat(),
                "created_at": _now().isoformat(),
            })
            await db.documents.insert_one({
                "id": f"doc_{uuid.uuid4().hex[:8]}", "user_id": user, "filename": "invoice.pdf",
                "analysis": {"macro_category": "financial", "confidence": 0.95, "suggested_title": "Fattura"},
                "admin_analysis": {
                    "subject": "Fattura 2026", "amount": "240.00", "currency": "€",
                    "due_date": (_now() + timedelta(days=5)).date().isoformat(),
                    "completed": False, "confidence": 0.95,
                },
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            svc = await _svc(db)
            home = await svc.build_home(user)
            assert home.primary_focus is not None
            all_items = []
            if home.primary_focus:
                all_items.append(home.primary_focus)
            for g in home.priorities:
                all_items.extend(g.items)
            assert any(i["type"] == "activity" for i in all_items) or any(i["type"] in ("bill", "payment") for i in all_items)
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_gemini_absent_ranking_still_works(monkeypatch):
    # Ranking must not call LLM
    from home.ranking import rank_items
    from home.models import HomeItem
    items = [
        HomeItem(
            id="1", type="bill", title="X", source_type="document", source_id="d1",
            due_at=(_now() + timedelta(days=1)).isoformat(), amount="10 €",
        ),
        HomeItem(
            id="2", type="study", title="Y", source_type="study", source_id="d2",
            meta={"incomplete_study": True},
        ),
    ]
    ranked = rank_items(items)
    assert ranked[0].type == "bill"
    assert ranked[0].reason_factors
    assert ranked[0].ranking_version == "home-rank-1.4"


def test_api_home_router_registered():
    from routers import ALL_ROUTERS
    prefixes = [getattr(r, "prefix", None) for r in ALL_ROUTERS]
    assert "/home" in prefixes


def test_insight_dedupe_and_ignore():
    async def body():
        client, db = await _db()
        user = f"u_ins_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            await db.documents.insert_one({
                "id": f"doc_{uuid.uuid4().hex[:8]}", "user_id": user, "filename": "late.pdf",
                "analysis": {"macro_category": "financial", "confidence": 0.9},
                "admin_analysis": {
                    "subject": "Scaduta", "amount": "99", "currency": "€",
                    "due_date": (_now() - timedelta(days=3)).date().isoformat(),
                    "completed": False, "confidence": 0.9,
                },
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            svc = await _svc(db)
            h1 = await svc.build_home(user)
            assert len(h1.insights) >= 1
            ins_id = h1.insights[0].id
            await svc.apply_action(user, item_id=ins_id, action="ignore")
            h2 = await svc.build_home(user)
            assert all(i.id != ins_id for i in h2.insights)
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def test_incomplete_flashcard_quiz_sessions():
    async def body():
        client, db = await _db()
        user = f"u_fq_{uuid.uuid4().hex[:8]}"
        try:
            await _clean_user(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            doc_id = f"doc_{uuid.uuid4().hex[:8]}"
            await db.documents.insert_one({
                "id": doc_id, "user_id": user, "filename": "notes.pdf",
                "analysis": {"macro_category": "education", "confidence": 0.8},
                "education_analysis": {"topic": "Notes", "suggested_title": "Notes", "confidence": 0.8},
                "flashcards": [{"id": "c1", "question": "Q", "answer": "A", "review_status": "new"}],
                "quiz_session": {
                    "id": "qz", "document_id": doc_id, "status": "active", "current_index": 1,
                    "turns": [{"question": "Q1"}, {"question": "Q2"}],
                    "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
                },
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            svc = await _svc(db)
            home = await svc.build_home(user)
            assert home.resume_item is not None
            assert home.resume_item["meta"]["resume_kind"] in ("quiz", "flashcards")
        finally:
            await _clean_user(db, user)
            client.close()
    _run(body())


def _assert_no_type_leak(summary: str) -> None:
    low = (summary or "").lower()
    assert "tipo " not in low
    assert "tipo travel" not in low
    assert "; tipo" not in low


def test_reason_summary_human_presentation_and_score_invariant():
    """3.S — human Italian summary from factor codes; scores/order unchanged."""
    from home.models import HomeItem
    from home.ranking import rank_items, score_item

    now = datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc)

    travel_imminent = HomeItem(
        id="tr_im", type="travel", title="Viaggio sud",
        source_type="travel_project", source_id="tp_im",
        start_at=(now + timedelta(hours=2)).isoformat(),
    )
    s1, f1, sum1 = score_item(travel_imminent, now)
    assert "viaggio" in sum1.lower()
    assert "imminente" in sum1.lower()
    _assert_no_type_leak(sum1)
    s1b, f1b, _ = score_item(travel_imminent, now)
    assert s1 == s1b
    assert [x.code for x in f1] == [x.code for x in f1b]
    assert [x.weight for x in f1] == [x.weight for x in f1b]

    travel_prep = HomeItem(
        id="tr_prep", type="travel", title="Viaggio",
        source_type="travel_project", source_id="tp_p",
        start_at=(now + timedelta(hours=2)).isoformat(),
        meta={"missing_prep": ["documenti"]},
    )
    s2, f2, sum2 = score_item(travel_prep, now)
    assert "viaggio" in sum2.lower()
    assert "preparare" in sum2.lower() or "manca" in sum2.lower()
    assert "valigia" not in sum2.lower()
    assert "domani" not in sum2.lower()
    _assert_no_type_leak(sum2)
    assert any(x.code == "missing_prep" for x in f2)
    assert s2 > s1  # prep boost still applied

    study_near = HomeItem(
        id="st_near", type="study", title="Studio",
        source_type="study_plan", source_id="sp1",
        due_at=(now + timedelta(hours=20)).isoformat(),
    )
    s3, f3, sum3 = score_item(study_near, now)
    assert "studio" in sum3.lower()
    assert "vicin" in sum3.lower()
    _assert_no_type_leak(sum3)
    assert any(x.code in ("within_24h", "imminent") for x in f3)

    weak = HomeItem(
        id="weak", type="needs_review", title="Da verificare",
        source_type="document", source_id="d1",
        confidence=0.3,
    )
    s4, f4, sum4 = score_item(weak, now)
    assert len(sum4) < 120
    assert "verific" in sum4.lower() or "incomplet" in sum4.lower() or "dati" in sum4.lower()
    _assert_no_type_leak(sum4)
    assert any(x.code in ("low_confidence", "needs_review", "type") for x in f4)

    # Ranking order/scores invariant across re-rank (same inputs → same scores)
    items = [travel_imminent, travel_prep, study_near, weak]
    ranked_a = rank_items(items, now=now)
    ranked_b = rank_items(items, now=now)
    assert [i.id for i in ranked_a] == [i.id for i in ranked_b]
    assert [i.score for i in ranked_a] == [i.score for i in ranked_b]
    for it in ranked_a:
        _assert_no_type_leak(it.reason_summary or "")
        # Internal type factor label may still say Tipo … for debug — summary must not
        assert not (it.reason_summary or "").startswith("Tipo ")
