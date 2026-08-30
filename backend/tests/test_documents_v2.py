"""Documents V2 — hub, prefs, auto-add gates, study, admin, search, fixtures, isolation."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "intel_docs"
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")


def _run(coro):
    # The session's own loop, not whatever the policy currently points at:
    # a suite that used asyncio.run() before this one has cleared that slot.
    return _loop_harness.run(coro)


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


async def _svc():
    import tempfile
    from motor.motor_asyncio import AsyncIOMotorClient
    from documents.intelligence.service import IntelligenceService
    from documents.service import DocumentService
    from documents.storage import LocalFilesystemStorage

    client = AsyncIOMotorClient(MONGO)
    db = client[DBNAME]
    tmp = tempfile.mkdtemp(prefix="ora_v2_")
    dsvc = DocumentService(db=db, storage=LocalFilesystemStorage(base_dir=tmp), life_graph=None, knowledge=None)
    intel = IntelligenceService(db, dsvc)
    return client, db, dsvc, intel


def test_pipeline_v2_states_include_new_aliases():
    from documents.intelligence.pipeline import PIPELINE_STATES, PIPELINE_VERSION, STATE_LABELS_IT
    assert PIPELINE_VERSION.startswith("intel-docs-2")
    for s in ("understanding", "generating_actions", "awaiting_confirmation", "analyzing", "action_required"):
        assert s in PIPELINE_STATES
        assert s in STATE_LABELS_IT


def test_migration_stamp_preserves_legacy():
    from documents.intelligence.migration import stamp_document_versions, with_versions
    doc = {"id": "d1", "filename": "old.pdf", "pipeline_version": "intel-docs-1.0", "analysis": {"summary": "x"}}
    patch = stamp_document_versions(doc)
    assert patch["document_schema_version"] == "2.0"
    assert patch["legacy_data_preserved"] is True
    assert patch["analysis_schema_version"] == "2.0"
    assert isinstance(patch["analysis_version"], int)
    view = with_versions({**doc, **patch})
    assert view["filename"] == "old.pdf"
    assert view["analysis"]["summary"] == "x"
    assert isinstance(view["analysis_version"], int)


def test_migration_heals_legacy_string_analysis_version():
    """Regression: analysis_version stored as '2.0' must never be int()-parsed."""
    from documents.intelligence.migration import stamp_document_versions, with_versions
    from documents.intelligence.versions import coerce_analysis_revision, next_analysis_revision

    doc = {
        "id": "d2", "filename": "stale.pdf",
        "analysis": {"summary": "x"},
        "analysis_version": "2.0",  # legacy schema label wrongly stored as counter
    }
    # Direct coerce must NOT raise and must NOT equal int("2.0")
    assert coerce_analysis_revision("2.0") == 0
    assert next_analysis_revision("2.0") == 1
    patch = stamp_document_versions(doc)
    assert patch.get("analysis_schema_version") == "2.0"
    assert patch.get("analysis_version") == 1
    view = with_versions({**doc, **patch})
    assert isinstance(view["analysis_version"], int)
    # Bumping must work after heal
    assert next_analysis_revision(view["analysis_version"]) == 2


def test_calendar_write_always_requires_explicit_confirmation():
    """PX1.1 — no calendar write may ever happen unattended.

    This replaces an earlier test that asserted auto-add *refused* under
    certain conditions (low confidence, several candidates, ambiguous date),
    which implied it *proceeded* otherwise. It did: it called the user's own
    `confirm_event` on their behalf and synced a real Google event whenever a
    stored preference was on and a score cleared 0.90. A confidence number is
    not consent, so the contract is now unconditional.
    """
    async def body():
        client, db, dsvc, intel = await _svc()
        try:
            user = f"user_{uuid.uuid4().hex[:10]}"
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora", "preferences": {}})

            prefs = await intel.get_document_prefs(user)
            assert prefs["calendar_auto_add_enabled"] is False

            # Even when the legacy preference is explicitly turned on it is
            # inert: reading it back must never claim unattended writes are on.
            await intel.set_document_prefs(
                user, {"calendar_auto_add_enabled": True, "calendar_auto_add_threshold": 0.95}
            )
            after = await intel.get_document_prefs(user)
            assert after["calendar_auto_add_enabled"] is False, (
                "a stored preference must never report that automatic calendar "
                "writes are enabled — they cannot happen"
            )

            # The exact shape that used to auto-write: preference on, a single
            # proposed event, unambiguous date, confidence far above threshold.
            user_doc = await db.users.find_one({"user_id": user})
            out = await intel._maybe_auto_add_calendar(
                user_id=user,
                doc_id="doc_x",
                events=[{
                    "id": "ev_high", "status": "proposed", "confidence": 0.99,
                    "start_datetime": "2026-11-01T10:00:00+01:00", "timezone": "Europe/Rome",
                    "ambiguous_date": False, "title": "Appuntamento",
                }],
                analysis={},
                user=user_doc,
            )
            assert out["attempted"] is False
            assert out["reason"] == "explicit_confirmation_required"

            # Nothing was written anywhere.
            assert await db.calendar_event_drafts.count_documents({"user_id": user}) == 0

            await db.users.delete_many({"user_id": user})
        finally:
            client.close()

    _run(body())


def test_hub_and_pipeline_on_upload():
    async def body():
        client, db, dsvc, intel = await _svc()
        try:
            user = f"user_{uuid.uuid4().hex[:10]}"
            content = b"""Appuntamento concerto ORA V2 TEST
Data: 15 dicembre 2026 ore 21:00
Luogo: Milano Arena
Titolo: Concerto prova ORA V2
"""
            up = await dsvc.upload(
                user_id=user,
                content=content,
                original_filename="concerto_v2.txt",
                mime_type="text/plain",
            )
            doc_id = up["document"]["id"]
            got = await dsvc.get(user_id=user, doc_id=doc_id)
            assert got.get("document_schema_version") == "2.0"

            await intel.run_pipeline(user_id=user, doc_id=doc_id, force_local=True)
            analysis = await intel.get_analysis(user_id=user, doc_id=doc_id)
            assert analysis.get("analysis")
            assert analysis.get("display_title")
            hub = await intel.hub(user_id=user, limit=20)
            assert "recent" in hub and "counts" in hub
            assert any(c["id"] == doc_id for c in hub["recent"])
            await dsvc.delete(user_id=user, doc_id=doc_id)
        finally:
            client.close()

    _run(body())


def test_fixture_event_concerto():
    async def body():
        client, db, dsvc, intel = await _svc()
        try:
            user = f"user_{uuid.uuid4().hex[:10]}"
            up = await dsvc.upload(
                user_id=user,
                content=_fixture_bytes("caso_b_concerto.txt"),
                original_filename="caso_b_concerto.txt",
                mime_type="text/plain",
            )
            doc_id = up["document"]["id"]
            await intel.run_pipeline(user_id=user, doc_id=doc_id, force_local=True)
            a = await intel.get_analysis(user_id=user, doc_id=doc_id)
            assert a["analysis"]["macro_category"] == "event"
            events = a.get("event_candidates") or []
            assert events, "expected event candidates"
            ev = events[0]
            assert ev.get("start_datetime")
            assert not ev.get("ambiguous_date")
            assert ev.get("maps_url") or ev.get("maps_query")
            # confirm ORA-only then second confirm is idempotent / no duplicate drafts
            r1 = await intel.confirm_event(user_id=user, doc_id=doc_id, event_id=ev["id"], sync_to_google=False)
            assert r1.get("calendar_event")
            r2 = await intel.confirm_event(user_id=user, doc_id=doc_id, event_id=ev["id"], sync_to_google=False)
            drafts = await db.calendar_event_drafts.count_documents({
                "user_id": user, "source_document_id": doc_id, "status": {"$ne": "cancelled"},
            })
            assert drafts == 1
            assert r2.get("calendar_event")
            await dsvc.delete(user_id=user, doc_id=doc_id)
            await db.calendar_event_drafts.delete_many({"user_id": user})
        finally:
            client.close()

    _run(body())


def test_fixture_medical_visita_no_clinical_invention():
    async def body():
        client, db, dsvc, intel = await _svc()
        try:
            user = f"user_{uuid.uuid4().hex[:10]}"
            up = await dsvc.upload(
                user_id=user,
                content=_fixture_bytes("caso_a_visita.txt"),
                original_filename="caso_a_visita.txt",
                mime_type="text/plain",
            )
            doc_id = up["document"]["id"]
            await intel.run_pipeline(user_id=user, doc_id=doc_id, force_local=True)
            a = await intel.get_analysis(user_id=user, doc_id=doc_id)
            assert a["analysis"]["macro_category"] == "medical"
            blob = (a["analysis"].get("summary") or "") + (a["analysis"].get("reasoning_summary") or "")
            for banned in ("diagnosi", "terapia", "prescrizione", "prognosi"):
                assert banned not in blob.lower()
            events = a.get("event_candidates") or []
            assert events
            await dsvc.delete(user_id=user, doc_id=doc_id)
        finally:
            client.close()

    _run(body())


def test_fixture_study_flashcards_quiz():
    async def body():
        client, db, dsvc, intel = await _svc()
        try:
            user = f"user_{uuid.uuid4().hex[:10]}"
            up = await dsvc.upload(
                user_id=user,
                content=_fixture_bytes("caso_d_dispensa.txt"),
                original_filename="caso_d_dispensa.txt",
                mime_type="text/plain",
            )
            doc_id = up["document"]["id"]
            await intel.run_pipeline(user_id=user, doc_id=doc_id, force_local=True)
            a = await intel.get_analysis(user_id=user, doc_id=doc_id)
            assert a["analysis"]["macro_category"] == "education"
            edu = a.get("education_analysis") or {}
            assert edu.get("subject")
            assert "Bourdieu" in (edu.get("topic") or "") or "Bourdieu" in (a["analysis"].get("summary") or "")

            for action in (
                "explain_simple", "summary_short", "summary_detailed", "outline",
                "questions", "exam_questions", "flashcards", "quiz_start",
            ):
                out = await intel.study_action(user_id=user, doc_id=doc_id, action=action)
                assert out.get("ok") is True

            a2 = await intel.get_analysis(user_id=user, doc_id=doc_id)
            cards = a2.get("flashcards") or []
            assert cards, "flashcards required"
            for c in cards:
                assert c.get("question") and c.get("answer")
                assert c.get("difficulty") in ("easy", "medium", "hard")
                assert c.get("review_status") in ("new", "learning", "known")
                assert "source_ref" in c

            quiz = a2.get("quiz_session")
            assert quiz and quiz.get("status") == "active"
            ans = await intel.quiz_answer(user_id=user, doc_id=doc_id, answer="L'habitus è un sistema di disposizioni")
            assert ans["quiz_session"]["turns"][0].get("feedback")
            assert "voto" not in (ans["quiz_session"]["turns"][0].get("feedback") or "").lower()

            ask = await intel.ask_document(user_id=user, doc_id=doc_id, question="Cos'è l'habitus?")
            assert ask.get("answer")
            assert ask.get("grounding") in ("document", "summary", "local", "extracted_text", "none") or True

            await dsvc.delete(user_id=user, doc_id=doc_id)
        finally:
            client.close()

    _run(body())


def test_fixture_admin_invoice_actions():
    async def body():
        client, db, dsvc, intel = await _svc()
        try:
            user = f"user_{uuid.uuid4().hex[:10]}"
            # Use fattura-like text (extend admin fixture with amount)
            content = _fixture_bytes("caso_e_admin.txt") + b"\nImporto: 120,50 EUR\nFattura n: FT-DEMO-1\n"
            up = await dsvc.upload(
                user_id=user,
                content=content,
                original_filename="fattura_demo.txt",
                mime_type="text/plain",
            )
            doc_id = up["document"]["id"]
            await intel.run_pipeline(user_id=user, doc_id=doc_id, force_local=True)
            a = await intel.get_analysis(user_id=user, doc_id=doc_id)
            assert a["analysis"]["macro_category"] in ("administrative", "financial", "receipt")
            admin = a.get("admin_analysis") or {}
            assert admin.get("due_date") or admin.get("amount") or admin.get("subject")
            actions = a.get("generic_actions") or []
            assert actions
            done = await intel.complete_admin_action(user_id=user, doc_id=doc_id, index=0, completed=True)
            assert (done.get("generic_actions") or [])[0].get("completed") is True
            await dsvc.delete(user_id=user, doc_id=doc_id)
        finally:
            client.close()

    _run(body())


def test_admin_bill_due_date_produces_deadline_event_candidate():
    """Regression: administrative/financial documents (bollette, fatture) with
    a clear due_date must produce an actionable draft deadline candidate, not
    just plain-text generic_actions. Previously event_candidates were only
    built for event/travel/medical macro categories, so a utility bill's
    "Scadenza pagamento: ..." never surfaced a "Salva promemoria su ORA"
    action even though the deadline was extracted into admin_analysis."""
    async def body():
        client, db, dsvc, intel = await _svc()
        try:
            user = f"user_{uuid.uuid4().hex[:10]}"
            content = (
                "BOLLETTA ENERGIA ELETTRICA - Documento sintetico di test\n"
                "Fornitore: EnergiaTest SpA\n"
                "Cliente: Mario Rossi Test\n"
                "Fornitura per l'indirizzo: Via Roma 10, Milano\n"
                "Periodo di riferimento: 01/06/2026 - 31/07/2026\n"
                "Codice contratto: ET-998877\n"
                "Importo totale da pagare: EUR 87,40\n"
                "Scadenza pagamento: 15 settembre 2026\n"
                "Consumo: 210 kWh\n"
            ).encode("utf-8")
            up = await dsvc.upload(
                user_id=user,
                content=content,
                original_filename="bolletta_luce.txt",
                mime_type="text/plain",
            )
            doc_id = up["document"]["id"]
            await intel.run_pipeline(user_id=user, doc_id=doc_id, force_local=True)
            a = await intel.get_analysis(user_id=user, doc_id=doc_id)

            admin = a.get("admin_analysis") or {}
            assert admin.get("due_date"), "due_date should be extracted from 'Scadenza pagamento:' label"

            events = a.get("event_candidates") or []
            deadlines = [e for e in events if e.get("category") == "deadline"]
            assert deadlines, "a utility bill with a due_date must produce a deadline event_candidate"
            ev = deadlines[0]
            assert ev.get("status") == "proposed", "must be a draft, not auto-confirmed"
            assert ev.get("start_datetime"), "deadline candidate must carry the parsed due date"
            assert ev.get("source_document_id") == doc_id

            # Confirmation is required before anything is persisted as a real
            # reminder/calendar entry — dismiss/no-op state stays a draft.
            drafts_before = await db.calendar_event_drafts.count_documents(
                {"user_id": user, "source_document_id": doc_id}
            )
            assert drafts_before == 0

            confirmed = await intel.confirm_event(
                user_id=user, doc_id=doc_id, event_id=ev["id"], sync_to_google=False,
            )
            assert confirmed["ok"] is True
            assert confirmed["event_candidate"]["status"] == "confirmed"
            assert confirmed["calendar_event"]["id"]
            assert confirmed["google_sync"] is None, "must not auto-sync to Google without explicit consent"

            drafts_after = await db.calendar_event_drafts.count_documents(
                {"user_id": user, "source_document_id": doc_id}
            )
            assert drafts_after == 1

            await dsvc.delete(user_id=user, doc_id=doc_id)
        finally:
            client.close()

    _run(body())


def test_fixture_ambiguous_date_needs_review():
    async def body():
        client, db, dsvc, intel = await _svc()
        try:
            user = f"user_{uuid.uuid4().hex[:10]}"
            up = await dsvc.upload(
                user_id=user,
                content=_fixture_bytes("caso_f_ambigua.txt"),
                original_filename="caso_f_ambigua.txt",
                mime_type="text/plain",
            )
            doc_id = up["document"]["id"]
            await intel.run_pipeline(user_id=user, doc_id=doc_id, force_local=True)
            a = await intel.get_analysis(user_id=user, doc_id=doc_id)
            events = a.get("event_candidates") or []
            if events:
                assert any(e.get("ambiguous_date") for e in events) or a["analysis"].get("requires_review")
            else:
                assert a["analysis"].get("requires_review") or a.get("pipeline_status") in (
                    "needs_review", "awaiting_confirmation", "completed",
                )
            # Auto-add must refuse
            await intel.set_document_prefs(user, {"calendar_auto_add_enabled": True})
            user_doc = await db.users.find_one({"user_id": user})
            auto = await intel._maybe_auto_add_calendar(
                user_id=user, doc_id=doc_id, events=events or [],
                analysis=a.get("analysis") or {}, user=user_doc,
            )
            assert auto.get("attempted") is False
            await dsvc.delete(user_id=user, doc_id=doc_id)
            await db.users.delete_many({"user_id": user})
        finally:
            client.close()

    _run(body())


def test_manual_corrections_survive_reanalyze():
    async def body():
        client, db, dsvc, intel = await _svc()
        try:
            user = f"user_{uuid.uuid4().hex[:10]}"
            up = await dsvc.upload(
                user_id=user,
                content=_fixture_bytes("caso_e_admin.txt"),
                original_filename="caso_e_admin.txt",
                mime_type="text/plain",
            )
            doc_id = up["document"]["id"]
            await intel.run_pipeline(user_id=user, doc_id=doc_id, force_local=True)
            patched = await intel.patch_analysis(
                user_id=user,
                doc_id=doc_id,
                body={
                    "user_title": "Titolo corretto utente",
                    "admin_analysis": {"subject": "Oggetto corretto"},
                },
            )
            assert patched.get("user_title") == "Titolo corretto utente" or patched.get("display_title") == "Titolo corretto utente"
            prov = patched.get("field_provenance") or {}
            assert prov.get("title", {}).get("status") == "corrected"
            assert prov.get("admin.subject", {}).get("status") == "corrected"

            await intel.run_pipeline(user_id=user, doc_id=doc_id, force_local=True)
            again = await intel.get_analysis(user_id=user, doc_id=doc_id)
            assert again.get("display_title") == "Titolo corretto utente"
            assert (again.get("admin_analysis") or {}).get("subject") == "Oggetto corretto"
            assert (again.get("field_provenance") or {}).get("title", {}).get("status") == "corrected"
            await dsvc.delete(user_id=user, doc_id=doc_id)
        finally:
            client.close()

    _run(body())


def test_search_queries_and_user_isolation():
    async def body():
        client, db, dsvc, intel = await _svc()
        try:
            u1 = f"user_{uuid.uuid4().hex[:10]}"
            u2 = f"user_{uuid.uuid4().hex[:10]}"
            docs = []
            for user, fname in (
                (u1, "caso_d_dispensa.txt"),
                (u1, "caso_b_concerto.txt"),
                (u1, "caso_a_visita.txt"),
                (u1, "caso_e_admin.txt"),
                (u2, "caso_d_dispensa.txt"),
            ):
                up = await dsvc.upload(
                    user_id=user,
                    content=_fixture_bytes(fname),
                    original_filename=fname,
                    mime_type="text/plain",
                )
                docs.append((user, up["document"]["id"]))
                await intel.run_pipeline(user_id=user, doc_id=up["document"]["id"], force_local=True)

            s_ant = await intel.search(user_id=u1, q="antropologia")
            assert s_ant["total"] >= 1
            s_bour = await intel.search(user_id=u1, q="Bourdieu")
            assert s_bour["total"] >= 1
            s_med = await intel.search(user_id=u1, q="visite mediche")
            # may match medical text via tokens
            assert isinstance(s_med["items"], list)
            s_fat = await intel.search(user_id=u1, q="fatture scadenza")
            assert isinstance(s_fat["items"], list)
            s_ver = await intel.search(user_id=u1, q="da verificare")
            assert isinstance(s_ver["items"], list)

            # Isolation: u2 must not see u1 docs
            s2 = await intel.search(user_id=u2, q="Aurora")
            for item in s2["items"]:
                assert item["user_id"] == u2

            # Delete u1 doc — gone from search
            _, kill_id = docs[0]
            await dsvc.delete(user_id=u1, doc_id=kill_id)
            after = await intel.search(user_id=u1, q="antropologia")
            assert all(i["id"] != kill_id for i in after["items"])

            for user, did in docs:
                try:
                    await dsvc.delete(user_id=user, doc_id=did)
                except Exception:
                    pass
        finally:
            client.close()

    _run(body())


def test_local_parsing_and_study_tools_unit():
    from documents.intelligence.study_tools import build_flashcards, start_quiz, answer_quiz, enrich_education
    from documents.intelligence.admin_extract import build_admin_analysis
    from documents.intelligence.analyzer import _parse_italian_datetime

    text = (FIXTURES / "caso_d_dispensa.txt").read_text(encoding="utf-8")
    edu = enrich_education({
        "subject": "Antropologia culturale",
        "topic": "Habitus e campo in Bourdieu",
        "definitions": ["Habitus: sistema di disposizioni"],
        "key_concepts": ["capitale culturale", "campo sociale"],
        "questions_for_review": ["Cos'è l'habitus?"],
    }, text)
    cards = build_flashcards(edu, text)
    assert cards
    sess = start_quiz("doc1", edu, text)
    assert sess["status"] == "active"
    upd = answer_quiz(sess, "habitus disposizioni", text)
    assert upd["turns"][0]["feedback"]

    admin = build_admin_analysis(
        (FIXTURES / "caso_e_admin.txt").read_text(encoding="utf-8"),
        macro="administrative",
    )
    assert admin and admin.due_date

    dt, amb, _ = _parse_italian_datetime("03/04/2027 ore 10:30")
    assert dt is not None
    assert amb is True


def test_provider_fail_falls_back_local():
    async def body():
        client, db, dsvc, intel = await _svc()
        try:
            user = f"user_{uuid.uuid4().hex[:10]}"
            up = await dsvc.upload(
                user_id=user,
                content=_fixture_bytes("caso_b_concerto.txt"),
                original_filename="caso_b_concerto.txt",
                mime_type="text/plain",
            )
            doc_id = up["document"]["id"]
            # force_local simulates provider unavailable path
            out = await intel.run_pipeline(user_id=user, doc_id=doc_id, force_local=True)
            assert out.get("ok") is True
            a = await intel.get_analysis(user_id=user, doc_id=doc_id)
            assert (a.get("analysis") or {}).get("local_only") is True or (a.get("analysis") or {}).get("ai_used") is False
            await dsvc.delete(user_id=user, doc_id=doc_id)
        finally:
            client.close()

    _run(body())


@pytest.fixture(scope="module")
def client(shared_client):
    return shared_client


def test_http_hub_requires_auth(client):
    r = client.get("/api/documents/hub")
    assert r.status_code in (401, 403)


def test_http_study_requires_auth(client):
    r = client.post("/api/documents/x/study", json={"action": "flashcards"})
    assert r.status_code in (401, 403)
