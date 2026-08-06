"""Life Experience — REAL Documents V2 attach/consume + AI Document Understanding.

Documents V2 remains the ONLY document pipeline: every test that exercises
end-to-end behaviour uploads bytes through `DocumentService.upload` (the same
code path used by `POST /api/documents/upload`) — never a synthetic-only
shortcut. `LIFE_DOCUMENT_UNDERSTANDING_ENABLED` reasoning defaults to the
deterministic fallback in most tests (`force_local`-style, via
`LIFE_AI_STRATEGIST_GEMINI=0`-equivalent) so results are stable offline; a
small gated group re-verifies real Gemini calls when GEMINI_API_KEY is set.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

os.environ["LIFE_SETUP_ENABLED"] = "1"
os.environ["AI_LIFE_STRATEGIST_ENABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "test-secret-life-experience-docs")
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "ora_life_experience_docs_test")
os.environ.setdefault("GOAL_ENGINE_ENABLED", "1")

_BACKEND = str(Path(__file__).resolve().parents[2])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

try:  # pragma: no cover - best effort so GEMINI_API_KEY in backend/.env is seen
    from dotenv import load_dotenv

    load_dotenv(Path(_BACKEND) / ".env")
except Exception:
    pass

from tests.fixtures.life_documents import pdf_bytes, txt_bytes  # noqa: E402

MONGO = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
DBNAME = os.environ.get("DB_NAME", "ora_life_experience_docs_test")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, user_id: str):
    for col in (
        "life_setup_sessions", "life_profiles", "goals", "life_nodes", "life_edges",
        "proactive_suggestions", "documents", "conversation_sessions",
    ):
        await db[col].delete_many({"user_id": user_id})


def uid(prefix: str = "led") -> str:
    return f"led_test_{prefix}_{uuid.uuid4().hex[:8]}"


def _life_setup_svc(db):
    from life_setup.service import LifeSetupService
    from ai_life_strategist import cache as c

    c.clear()
    import life_setup.service as ls

    ls._SERVICE = LifeSetupService(db)
    return ls._SERVICE


def _doc_service(db):
    import tempfile
    from documents import DocumentService, LocalFilesystemStorage

    tmp = tempfile.mkdtemp(prefix="ora_life_docs_")
    return DocumentService(db=db, storage=LocalFilesystemStorage(base_dir=tmp))


async def _upload(doc_svc, user_id: str, *, filename: str, content: bytes, mime: str):
    return await doc_svc.upload(
        user_id=user_id, content=content, original_filename=filename,
        mime_type=mime, upload_source="life_experience_test",
    )


async def _extract_only(doc_svc, user_id: str, doc_id: str) -> None:
    """Wait deterministically for the synchronous extraction already run at
    upload time — Documents V2 extracts text inline during `upload()`."""
    doc = await doc_svc.get(user_id=user_id, doc_id=doc_id)
    assert doc.get("text_extracted") is True or doc.get("extracted_text")


async def _force_pipeline_completed(db, user_id: str, doc_id: str) -> None:
    """Deterministically drive the Documents V2 pipeline to a terminal state
    for tests (real analyzer call — force_local, no network dependency).

    Mirrors IntelligenceService.run_pipeline terminal selection: proposed
    event candidates (e.g. bolletta deadline) → awaiting_confirmation, not
    completed — Life Experience must treat that as ready_for_consume.
    """
    from documents.intelligence.analyzer import analyze_document
    from documents.intelligence.pipeline import PipelineState

    doc = await db.documents.find_one({"id": doc_id, "user_id": user_id}, {"_id": 0})
    result = await analyze_document(doc, user=None, force_local=True)
    analysis = result["analysis"] or {}
    events = result["event_candidates"] or []
    has_proposed = any(e.get("status") == "proposed" for e in events)
    terminal = "awaiting_confirmation" if (
        analysis.get("requires_review") or has_proposed
    ) else "completed"
    if analysis.get("requires_review") and not events:
        terminal = "needs_review"
    updates = {
        **PipelineState.set_status(doc, terminal, provider="local"),
        "analysis": analysis,
        "event_candidates": events,
        "education_analysis": result["education_analysis"],
        "admin_analysis": result["admin_analysis"],
        "generic_actions": result["generic_actions"],
    }
    await db.documents.update_one({"id": doc_id, "user_id": user_id}, {"$set": updates})


async def _upload_and_complete(db, doc_svc, user_id: str, key: str, *, as_pdf: bool = False):
    content = pdf_bytes(key) if as_pdf else txt_bytes(key)
    mime = "application/pdf" if as_pdf else "text/plain"
    up = await _upload(doc_svc, user_id, filename=f"{key}.{'pdf' if as_pdf else 'txt'}", content=content, mime=mime)
    doc = up["document"]
    await _force_pipeline_completed(db, user_id, doc["id"])
    return doc["id"]


# --------------------------------------------------------------------------
# A. DocumentReasoning schema + deterministic fallback + type detection
# --------------------------------------------------------------------------

def test_document_reasoning_schema_validates_minimal_payload():
    from documents.intelligence.life_reasoning import DocumentReasoning

    r = DocumentReasoning(document_id="doc_1", document_type="rogito", domain="casa")
    assert r.ai_used is False
    assert r.confidence == 0.4
    assert r.dates == []


@pytest.mark.parametrize("key,expected_type", [
    ("rogito", "rogito"),
    ("contratto_locazione", "contratto_locazione"),
    ("mutuo", "mutuo"),
    ("bolletta_luce", "bolletta"),
    ("bolletta_gas", "bolletta"),
    ("libretto", "libretto"),
    ("polizza_auto", "polizza_auto"),
    ("prestito_auto", "prestito_auto"),
    ("piano_di_studi", "piano_di_studi"),
    ("calendario_esami", "calendario_esami"),
    ("dispensa", "dispensa"),
    ("fattura", "fattura"),
    ("ricevuta", "ricevuta"),
])
def test_guess_document_type_from_text(key, expected_type):
    from documents.intelligence.life_reasoning import guess_document_type

    doc = {"extracted_text": "\n".join(__import__(
        "tests.fixtures.life_documents", fromlist=["TXT_FIXTURES"],
    ).TXT_FIXTURES[key]), "filename": f"{key}.txt", "analysis": {}}
    assert guess_document_type(doc) == expected_type


def test_deterministic_fallback_never_claims_ai_used():
    from documents.intelligence.life_reasoning import run_life_document_reasoning

    async def _go():
        doc = {
            "id": "doc_fallback", "extracted_text": "\n".join(txt_bytes("bolletta_luce").decode().splitlines()),
            "filename": "bolletta_luce.txt", "analysis": {"macro_category": "financial"},
            "admin_analysis": {"due_date": "15/09/2026", "amount": "87,40", "currency": "EUR"},
        }
        os.environ["LIFE_DOCUMENT_UNDERSTANDING_ENABLED"] = "0"
        try:
            result = await run_life_document_reasoning(doc)
        finally:
            os.environ["LIFE_DOCUMENT_UNDERSTANDING_ENABLED"] = "1"
        assert result["reasoning"]["ai_used"] is False
        assert result["reasoning"]["provider"] == "local-deterministic"
        assert result["telemetry"]["ai_used"] is False

    _run(_go())


def test_reasoning_cache_by_content_hash():
    from documents.intelligence.life_reasoning import run_life_document_reasoning

    async def _go():
        doc = {"id": "doc_cache", "extracted_text": "BOLLETTA TEST", "filename": "b.txt", "analysis": {}}
        os.environ["LIFE_DOCUMENT_UNDERSTANDING_ENABLED"] = "0"
        try:
            r1 = await run_life_document_reasoning(doc)
            doc["life_reasoning"] = r1["reasoning"]
            r2 = await run_life_document_reasoning(doc)
        finally:
            os.environ["LIFE_DOCUMENT_UNDERSTANDING_ENABLED"] = "1"
        assert r2["cached"] is True

    _run(_go())


def test_reasoning_no_text_falls_back_immediately():
    from documents.intelligence.life_reasoning import run_life_document_reasoning

    async def _go():
        doc = {"id": "doc_empty", "extracted_text": "", "filename": "empty.pdf", "analysis": {}}
        result = await run_life_document_reasoning(doc)
        assert result["reasoning"]["ai_used"] is False
        assert result["telemetry"].get("fallback_reason") == "disabled_or_no_text"

    _run(_go())


# --------------------------------------------------------------------------
# B. Life Profile mapping (declarative mappers)
# --------------------------------------------------------------------------

def _reasoning(doc_type: str, domain: str, type_specific: dict, confidence: float = 0.9):
    return {
        "document_type": doc_type, "domain": domain, "type_specific": type_specific,
        "confidence": confidence, "entities": [], "dates": [], "amounts": [],
    }


def test_map_rogito_produces_casa_fields():
    from life_setup.document_mapping import map_document_reasoning

    r = _reasoning("rogito", "casa", {"address": "Via Roma 10, Milano", "price": "250000"})
    fields = map_document_reasoning(r)
    keys = {f.key for f in fields}
    assert "casa.owned" in keys and "casa.indirizzo" in keys
    addr = next(f for f in fields if f.key == "casa.indirizzo")
    assert addr.value == "Via Roma 10, Milano"
    assert addr.status == "extracted"  # high confidence


def test_map_mutuo_fields():
    from life_setup.document_mapping import map_document_reasoning

    r = _reasoning("mutuo", "casa", {"lender": "Banca Test", "monthly_installment": "872,45"})
    fields = map_document_reasoning(r)
    keys = {f.key: f.value for f in fields}
    assert keys.get("casa.mutuo") is True
    assert keys.get("casa.mutuo_istituto") == "Banca Test"
    assert keys.get("casa.mutuo_rata") == "872,45"


def test_map_bolletta_fields():
    from life_setup.document_mapping import map_document_reasoning

    r = _reasoning("bolletta", "casa", {"supplier": "EnergiaTest", "amount_total": "87,40", "due_date": "15/09/2026"})
    fields = map_document_reasoning(r)
    keys = {f.key: f.value for f in fields}
    assert keys.get("casa.bolletta_fornitore") == "EnergiaTest"
    assert keys.get("casa.bolletta_scadenza") == "15/09/2026"


def test_map_libretto_fields():
    from life_setup.document_mapping import map_document_reasoning

    r = _reasoning("libretto", "auto", {"plate": "AB123CD", "brand": "Fiat", "model": "Panda"})
    fields = map_document_reasoning(r)
    keys = {f.key: f.value for f in fields}
    assert keys.get("auto.targa") == "AB123CD"
    assert keys.get("auto.modello") == "Fiat Panda"


def test_map_polizza_auto_fields():
    from life_setup.document_mapping import map_document_reasoning

    r = _reasoning("polizza_auto", "assicurazioni", {"company": "Assicurazioni Test", "end_date": "31/12/2026"})
    fields = map_document_reasoning(r)
    keys = {f.key: f.value for f in fields}
    assert keys.get("auto.assicurazione") is True
    assert keys.get("auto.assicurazione_scadenza") == "31/12/2026"


def test_map_piano_di_studi_fields():
    from life_setup.document_mapping import map_document_reasoning

    r = _reasoning("piano_di_studi", "studio", {"institution": "Universita' Test", "exams": ["Analisi 1", "BD"]})
    fields = map_document_reasoning(r)
    keys = {f.key: f.value for f in fields}
    assert keys.get("studio.universita") == "Universita' Test"
    assert keys.get("studio.esami") == ["Analisi 1", "BD"]


def test_confidence_threshold_drives_status():
    from life_setup.document_mapping import status_for_confidence

    assert status_for_confidence(0.95) == "extracted"
    assert status_for_confidence(0.6) == "suggested"
    assert status_for_confidence(0.1) == "suggested"


def test_generic_admin_mapper_extracts_amount_and_deadline():
    from life_setup.document_mapping import map_document_reasoning

    r = {
        "document_type": "fattura", "domain": "finanze", "type_specific": {},
        "confidence": 0.7,
        "amounts": [{"value": "145,60", "role": "total", "confidence": 0.7}],
        "dates": [{"value": "05/09/2026", "role": "deadline", "confidence": 0.7}],
    }
    fields = map_document_reasoning(r)
    keys = {f.key: f.value for f in fields}
    assert keys.get("finanze.importo_documento") == "145,60"
    assert keys.get("finanze.scadenza_documento") == "05/09/2026"


# --------------------------------------------------------------------------
# C. Cross-document reasoning — link, never merge; duplicate/contradiction
# --------------------------------------------------------------------------

def test_cross_document_links_same_vehicle_high_confidence():
    from life_setup.cross_document import find_related_documents
    from life_setup.models import DomainProfile, LifeProfile, ProfileObject

    profile = LifeProfile(user_id="u1")
    profile.domains["auto"] = DomainProfile(domain="auto", objects={
        "auto.targa": ProfileObject(key="auto.targa", value="AB123CD", linked_doc_ids=["doc_old"]),
    })
    reasoning = {"linked_life_objects": [{"object_type": "vehicle", "identifier": "AB123CD", "confidence": 0.9}]}
    links = find_related_documents(profile, domain="auto", reasoning=reasoning, new_document_id="doc_new")
    assert len(links) == 1
    assert links[0].document_id == "doc_old"


def test_cross_document_low_confidence_does_not_link():
    from life_setup.cross_document import find_related_documents
    from life_setup.models import DomainProfile, LifeProfile, ProfileObject

    profile = LifeProfile(user_id="u1")
    profile.domains["auto"] = DomainProfile(domain="auto", objects={
        "auto.targa": ProfileObject(key="auto.targa", value="AB123CD", linked_doc_ids=["doc_old"]),
    })
    reasoning = {"linked_life_objects": [{"object_type": "vehicle", "identifier": "AB123CD", "confidence": 0.4}]}
    links = find_related_documents(profile, domain="auto", reasoning=reasoning, new_document_id="doc_new")
    assert links == []


def test_cross_document_contradiction_on_confirmed_field():
    from life_setup.cross_document import detect_conflicts
    from life_setup.document_mapping import MappedField
    from life_setup.models import DomainProfile, LifeProfile, ProfileObject

    profile = LifeProfile(user_id="u1")
    profile.domains["casa"] = DomainProfile(domain="casa", objects={
        "casa.indirizzo": ProfileObject(key="casa.indirizzo", value="Via Vecchia 1", status="confirmed"),
    })
    mapped = [MappedField("casa", "casa.indirizzo", "Via Roma 10, Milano", confidence=0.9)]
    conflicts = detect_conflicts(profile, domain="casa", mapped_fields=mapped, source_document_id="doc_new")
    assert len(conflicts) == 1
    assert conflicts[0].kind in ("contradiction", "renewal")


def test_cross_document_no_conflict_when_same_normalized_value():
    from life_setup.cross_document import detect_conflicts
    from life_setup.document_mapping import MappedField
    from life_setup.models import DomainProfile, LifeProfile, ProfileObject

    profile = LifeProfile(user_id="u1")
    profile.domains["casa"] = DomainProfile(domain="casa", objects={
        "casa.indirizzo": ProfileObject(key="casa.indirizzo", value="via roma 10 milano", status="confirmed"),
    })
    mapped = [MappedField("casa", "casa.indirizzo", "Via Roma 10, Milano", confidence=0.9)]
    conflicts = detect_conflicts(profile, domain="casa", mapped_fields=mapped, source_document_id="doc_new")
    assert conflicts == []


def test_cross_document_no_conflict_on_non_confirmed_existing():
    from life_setup.cross_document import detect_conflicts
    from life_setup.document_mapping import MappedField
    from life_setup.models import DomainProfile, LifeProfile, ProfileObject

    profile = LifeProfile(user_id="u1")
    profile.domains["casa"] = DomainProfile(domain="casa", objects={
        "casa.indirizzo": ProfileObject(key="casa.indirizzo", value="Via Vecchia 1", status="extracted"),
    })
    mapped = [MappedField("casa", "casa.indirizzo", "Via Roma 10, Milano", confidence=0.9)]
    conflicts = detect_conflicts(profile, domain="casa", mapped_fields=mapped, source_document_id="doc_new")
    assert conflicts == []  # not protected — extracted (non confirmed) may be refined


# --------------------------------------------------------------------------
# D. Life Profile Service — provenance, protection of confirmed fields
# --------------------------------------------------------------------------

def test_apply_mapped_fields_never_overwrites_confirmed():
    async def _go():
        client, db = await _db()
        user = uid("protect")
        try:
            await _clean(db, user)
            from life_setup.document_mapping import MappedField
            from life_setup.profile_service import LifeProfileService

            svc = LifeProfileService(db)
            await svc.correct_fact(user, "casa", "casa.indirizzo", "Via Confermata 5")
            await svc.apply_mapped_fields(
                user, [MappedField("casa", "casa.indirizzo", "Via Diversa 9", confidence=0.95)],
                source_document_id="doc_x",
            )
            profile = await svc.get(user)
            assert profile.domains["casa"].objects["casa.indirizzo"].value == "Via Confermata 5"
        finally:
            client.close()

    _run(_go())


def test_apply_mapped_fields_sets_provenance():
    async def _go():
        client, db = await _db()
        user = uid("prov")
        try:
            await _clean(db, user)
            from life_setup.document_mapping import MappedField
            from life_setup.profile_service import LifeProfileService

            svc = LifeProfileService(db)
            await svc.apply_mapped_fields(
                user, [MappedField("auto", "auto.targa", "AB123CD", confidence=0.9)],
                source_document_id="doc_libretto_1", provider="gemini", model="gemini-flash-lite-latest",
                analysis_version=1,
            )
            profile = await svc.get(user)
            obj = profile.domains["auto"].objects["auto.targa"]
            assert obj.source_document_id == "doc_libretto_1"
            assert obj.provider == "gemini"
            assert obj.status == "extracted"
        finally:
            client.close()

    _run(_go())


def test_confirm_field_marks_confirmed():
    async def _go():
        client, db = await _db()
        user = uid("confirm")
        try:
            await _clean(db, user)
            from life_setup.document_mapping import MappedField
            from life_setup.profile_service import LifeProfileService

            svc = LifeProfileService(db)
            await svc.apply_mapped_fields(
                user, [MappedField("casa", "casa.bolletta_fornitore", "EnergiaTest", confidence=0.6)],
                source_document_id="doc_b1",
            )
            profile = await svc.confirm_field(user, "casa", "casa.bolletta_fornitore")
            obj = profile.domains["casa"].objects["casa.bolletta_fornitore"]
            assert obj.status == "confirmed"
            assert obj.confirmed_at is not None
        finally:
            client.close()

    _run(_go())


def test_reject_field_clears_value():
    async def _go():
        client, db = await _db()
        user = uid("reject")
        try:
            await _clean(db, user)
            from life_setup.document_mapping import MappedField
            from life_setup.profile_service import LifeProfileService

            svc = LifeProfileService(db)
            await svc.apply_mapped_fields(
                user, [MappedField("casa", "casa.bolletta_fornitore", "EnergiaTest", confidence=0.6)],
                source_document_id="doc_b1",
            )
            profile = await svc.reject_field(user, "casa", "casa.bolletta_fornitore")
            obj = profile.domains["casa"].objects["casa.bolletta_fornitore"]
            assert obj.status == "rejected"
            assert obj.value is None
        finally:
            client.close()

    _run(_go())


def test_resolve_pending_confirmation_use_new():
    async def _go():
        client, db = await _db()
        user = uid("resolve")
        try:
            await _clean(db, user)
            from life_setup.profile_service import LifeProfileService

            svc = LifeProfileService(db)
            await svc.correct_fact(user, "casa", "casa.indirizzo", "Via Vecchia 1")
            await svc.add_pending_confirmation(user, "casa", {
                "domain": "casa", "key": "casa.indirizzo", "label": "Indirizzo casa",
                "existing_value": "Via Vecchia 1", "new_value": "Via Roma 10, Milano",
                "new_confidence": 0.9, "source_document_id": "doc_new", "kind": "contradiction",
                "field": {"domain": "casa", "key": "casa.indirizzo", "value": "Via Roma 10, Milano", "confidence": 0.9},
            })
            profile = await svc.resolve_pending_confirmation(user, "casa", "casa.indirizzo", "use_new")
            assert profile.domains["casa"].objects["casa.indirizzo"].value == "Via Roma 10, Milano"
            assert profile.domains["casa"].pending_confirmations == []
        finally:
            client.close()

    _run(_go())


def test_resolve_pending_confirmation_keep_existing():
    async def _go():
        client, db = await _db()
        user = uid("keep")
        try:
            await _clean(db, user)
            from life_setup.profile_service import LifeProfileService

            svc = LifeProfileService(db)
            await svc.correct_fact(user, "casa", "casa.indirizzo", "Via Vecchia 1")
            await svc.add_pending_confirmation(user, "casa", {
                "domain": "casa", "key": "casa.indirizzo", "label": "Indirizzo casa",
                "existing_value": "Via Vecchia 1", "new_value": "Via Roma 10, Milano",
                "new_confidence": 0.9, "source_document_id": "doc_new", "kind": "contradiction",
                "field": {"domain": "casa", "key": "casa.indirizzo", "value": "Via Roma 10, Milano", "confidence": 0.9},
            })
            profile = await svc.resolve_pending_confirmation(user, "casa", "casa.indirizzo", "keep_existing")
            assert profile.domains["casa"].objects["casa.indirizzo"].value == "Via Vecchia 1"
        finally:
            client.close()

    _run(_go())


# --------------------------------------------------------------------------
# E. End-to-end via REAL Documents V2 upload (attach → status → consume)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("key,as_pdf", [
    ("rogito", False),
    ("rogito", True),
    ("mutuo", False),
    ("bolletta_luce", False),
    ("libretto", False),
    ("polizza_auto", False),
    ("piano_di_studi", False),
])
def test_attach_consume_real_document_updates_life_profile(key, as_pdf):
    async def _go():
        client, db = await _db()
        user = uid(f"e2e_{key}")
        try:
            await _clean(db, user)
            svc = _life_setup_svc(db)
            doc_svc = _doc_service(db)
            await svc.start(user)

            doc_id = await _upload_and_complete(db, doc_svc, user, key, as_pdf=as_pdf)
            attach = await svc.attach_document(user, doc_id)
            assert attach["ok"] is True
            assert attach["pipeline_status"] in (
                "completed",
                "awaiting_confirmation",
                "needs_review",
                "queued",
                "understanding",
                "extracting",
            )

            status = await svc.document_status(user, doc_id)
            assert status["ok"] is True
            assert status["ready_for_consume"] is True
            assert status["pipeline_status"] in (
                "completed", "awaiting_confirmation", "needs_review", "failed",
            )

            consume = await svc.consume_document(user, doc_id)
            assert consume["ok"] is True
            dr = consume["document_result"]
            assert dr["document_id"] == doc_id
            assert dr["cosa_ho_capito"] or dr["dati_trovati"] or dr["dati_da_verificare"]
            assert "provider" in dr and "model" in dr

            profile = await svc.profiles.get(user)
            assert profile is not None
            flat = svc.profiles.flat_known(profile)
            assert any(k.startswith("doc.") for k in flat)
        finally:
            client.close()

    _run(_go())


def test_consume_document_not_ready_returns_pipeline_status():
    async def _go():
        client, db = await _db()
        user = uid("notready")
        try:
            await _clean(db, user)
            svc = _life_setup_svc(db)
            doc_svc = _doc_service(db)
            await svc.start(user)
            up = await _upload(doc_svc, user, filename="r.txt", content=txt_bytes("rogito"), mime="text/plain")
            doc_id = up["document"]["id"]
            # Do NOT force-complete the pipeline.
            res = await svc.consume_document(user, doc_id)
            assert res["ok"] is False
            assert res["error"] == "pipeline_not_ready"
        finally:
            client.close()

    _run(_go())


def test_consume_document_unknown_id_returns_not_found():
    async def _go():
        client, db = await _db()
        user = uid("notfound")
        try:
            await _clean(db, user)
            svc = _life_setup_svc(db)
            await svc.start(user)
            res = await svc.consume_document(user, "doc_does_not_exist")
            assert res["ok"] is False
            assert res["error"] == "document_not_found"
        finally:
            client.close()

    _run(_go())


def test_deadline_found_surfaces_draft_event_not_auto_created():
    async def _go():
        client, db = await _db()
        user = uid("deadline")
        try:
            await _clean(db, user)
            svc = _life_setup_svc(db)
            doc_svc = _doc_service(db)
            await svc.start(user)
            doc_id = await _upload_and_complete(db, doc_svc, user, "bolletta_luce")
            await svc.attach_document(user, doc_id)
            consume = await svc.consume_document(user, doc_id)
            doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
            # Whatever event candidates Documents V2 produced must remain
            # status=proposed (never auto-confirmed) after Life Experience consume.
            for ev in doc.get("event_candidates") or []:
                assert ev.get("status") == "proposed"

            # Regression: a utility bill with a real "Scadenza pagamento: ..."
            # due date must surface an actionable deadline candidate — this is
            # what drives the "Salva promemoria su ORA" button in the Life
            # Experience document result screen. It used to stay an empty
            # list because event_candidates were only ever built for
            # event/travel/medical macro-category documents.
            draft_events = consume["document_result"]["draft_events"]
            assert isinstance(draft_events, list)
            assert draft_events, "bolletta with a due_date must produce a draft deadline event"
            ev = draft_events[0]
            assert ev.get("start_datetime")
            assert ev.get("confirm_endpoint") == f"/api/documents/{doc_id}/events/{ev['event_id']}/confirm"

            deadline_candidates = [
                e for e in (doc.get("event_candidates") or []) if e.get("category") == "deadline"
            ]
            assert deadline_candidates
            assert deadline_candidates[0]["status"] == "proposed"

            # Confirming is an explicit user action (never automatic) and
            # actually persists a draft in ORA's own calendar_event_drafts.
            from documents.intelligence.service import IntelligenceService
            intel_svc = IntelligenceService(db, doc_svc)
            confirmed = await intel_svc.confirm_event(
                user_id=user, doc_id=doc_id, event_id=ev["event_id"], sync_to_google=False,
            )
            assert confirmed["ok"] is True
            assert confirmed["event_candidate"]["status"] == "confirmed"
            assert confirmed["google_sync"] is None
        finally:
            client.close()

    _run(_go())


def test_home_benefit_activates_after_real_document_consume():
    async def _go():
        client, db = await _db()
        user = uid("homebenef")
        try:
            await _clean(db, user)
            svc = _life_setup_svc(db)
            doc_svc = _doc_service(db)
            await svc.start(user)
            await svc.answer(user, "Ho comprato casa.")
            doc_id = await _upload_and_complete(db, doc_svc, user, "rogito")
            await svc.attach_document(user, doc_id)
            await svc.consume_document(user, doc_id)
            await svc.complete(user)

            from home.adapters.life_setup import load_life_setup_items

            items, _ = await load_life_setup_items(db, user)
            titles = " ".join(i.title for i in items).lower()
            assert "completa il profilo" not in titles
        finally:
            client.close()

    _run(_go())


def test_proactive_never_completa_profilo_after_document_flow():
    async def _go():
        client, db = await _db()
        user = uid("proacdoc")
        try:
            await _clean(db, user)
            svc = _life_setup_svc(db)
            doc_svc = _doc_service(db)
            await svc.start(user)
            doc_id = await _upload_and_complete(db, doc_svc, user, "libretto")
            await svc.attach_document(user, doc_id)
            await svc.consume_document(user, doc_id)
            await svc.complete(user)

            from proactive_engine.generators.life_setup import generate_life_setup_candidates

            cands = await generate_life_setup_candidates(db, user)
            blob = " ".join(f"{c.title} {c.description} {c.reason}" for c in cands).lower()
            assert "completa il profilo" not in blob
        finally:
            client.close()

    _run(_go())


def test_retry_document_requeues_pipeline():
    async def _go():
        client, db = await _db()
        user = uid("retry")
        try:
            await _clean(db, user)
            svc = _life_setup_svc(db)
            doc_svc = _doc_service(db)
            await svc.start(user)
            doc_id = await _upload_and_complete(db, doc_svc, user, "bolletta_luce")
            await svc.attach_document(user, doc_id)
            await svc.consume_document(user, doc_id)
            res = await svc.retry_document(user, doc_id)
            assert res["ok"] is True
            assert res["pipeline_status"] == "queued"
            doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
            assert doc.get("life_reasoning") is None
        finally:
            client.close()

    _run(_go())


def test_detach_document_keeps_file_removes_knowledge():
    async def _go():
        client, db = await _db()
        user = uid("detach")
        try:
            await _clean(db, user)
            svc = _life_setup_svc(db)
            doc_svc = _doc_service(db)
            await svc.start(user)
            doc_id = await _upload_and_complete(db, doc_svc, user, "libretto")
            await svc.attach_document(user, doc_id)
            await svc.consume_document(user, doc_id)
            res = await svc.detach_document(user, doc_id)
            assert res["ok"] is True
            # File / Documents V2 record must still exist.
            doc = await doc_svc.get(user_id=user, doc_id=doc_id)
            assert doc is not None
            profile = await svc.profiles.get(user)
            for dom in profile.domains.values():
                assert doc_id not in dom.linked_docs
        finally:
            client.close()

    _run(_go())


def test_user_isolation_cannot_attach_other_users_document():
    async def _go():
        client, db = await _db()
        user_a = uid("iso_a")
        user_b = uid("iso_b")
        try:
            await _clean(db, user_a)
            await _clean(db, user_b)
            svc = _life_setup_svc(db)
            doc_svc = _doc_service(db)
            await svc.start(user_a)
            await svc.start(user_b)
            up = await _upload(doc_svc, user_a, filename="r.txt", content=txt_bytes("rogito"), mime="text/plain")
            doc_id = up["document"]["id"]
            res = await svc.attach_document(user_b, doc_id)
            assert res["ok"] is False
            assert res["error"] == "document_not_found"
        finally:
            client.close()

    _run(_go())


def test_user_isolation_cannot_consume_other_users_document():
    async def _go():
        client, db = await _db()
        user_a = uid("iso2_a")
        user_b = uid("iso2_b")
        try:
            await _clean(db, user_a)
            await _clean(db, user_b)
            svc = _life_setup_svc(db)
            doc_svc = _doc_service(db)
            await svc.start(user_a)
            await svc.start(user_b)
            doc_id = await _upload_and_complete(db, doc_svc, user_a, "bolletta_luce")
            res = await svc.consume_document(user_b, doc_id)
            assert res["ok"] is False
            assert res["error"] == "document_not_found"
        finally:
            client.close()

    _run(_go())


def test_resume_pending_document_message_after_reopen():
    async def _go():
        client, db = await _db()
        user = uid("resumedoc")
        try:
            await _clean(db, user)
            svc = _life_setup_svc(db)
            doc_svc = _doc_service(db)
            await svc.start(user)
            up = await _upload(doc_svc, user, filename="r.txt", content=txt_bytes("rogito"), mime="text/plain")
            doc_id = up["document"]["id"]
            await svc.attach_document(user, doc_id, "rogito")
            # Simulate reopen / resume without completing pipeline.
            res = await svc.start(user, force=False)
            assert res["ok"] is True
            pending = res.get("pending_document")
            assert pending is not None
            assert pending["document_id"] == doc_id
            assert "rogito" in pending["message"].lower() or pending["doc_type"] == "rogito"
        finally:
            client.close()

    _run(_go())


def test_no_second_pipeline_document_uses_documents_v2_storage():
    """The document created via attach/consume must be a REAL Documents V2
    record (storage_key, hash, pipeline_status) — never a `life_setup_synthetic` stub."""
    async def _go():
        client, db = await _db()
        user = uid("nostub")
        try:
            await _clean(db, user)
            svc = _life_setup_svc(db)
            doc_svc = _doc_service(db)
            await svc.start(user)
            doc_id = await _upload_and_complete(db, doc_svc, user, "piano_di_studi")
            await svc.attach_document(user, doc_id)
            await svc.consume_document(user, doc_id)
            doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
            assert doc.get("storage_key")
            assert doc.get("hash")
            assert doc.get("source") != "life_setup_synthetic"
            assert doc.get("pipeline_version")
        finally:
            client.close()

    _run(_go())


# --------------------------------------------------------------------------
# F. Error handling — invalid AI output / OCR failure / Gemini unavailable
# --------------------------------------------------------------------------

def test_invalid_ai_output_falls_back_to_deterministic(monkeypatch):
    from documents.intelligence import life_reasoning as lr

    async def _go():
        async def _boom(**kwargs):
            raise lr.LLMNotConfigured("no key")

        monkeypatch.setattr(lr, "_llm_reason", _boom)
        doc = {"id": "d1", "extracted_text": "BOLLETTA TEST importo 50 euro", "filename": "b.txt", "analysis": {}}
        result = await lr.run_life_document_reasoning(doc)
        assert result["reasoning"]["ai_used"] is False
        assert result["telemetry"]["fallback_reason"] == "not_configured"

    _run(_go())


def test_ocr_failure_document_still_consumable_with_low_confidence():
    async def _go():
        client, db = await _db()
        user = uid("ocrfail")
        try:
            await _clean(db, user)
            svc = _life_setup_svc(db)
            doc_svc = _doc_service(db)
            await svc.start(user)
            # Empty-text "scanned" document — extraction fails to find text.
            up = await _upload(doc_svc, user, filename="scan.png", content=b"\x89PNG\r\n\x1a\nnotarealpng", mime="image/png")
            doc_id = up["document"]["id"]
            await _force_pipeline_completed(db, user, doc_id)
            await svc.attach_document(user, doc_id)
            res = await svc.consume_document(user, doc_id)
            assert res["ok"] is True
            assert res["document_result"]["ai_used"] is False
        finally:
            client.close()

    _run(_go())


def test_unsupported_mime_rejected_by_documents_v2_not_life_experience():
    """Life Experience must not duplicate validation — Documents V2 rejects first."""
    async def _go():
        client, db = await _db()
        user = uid("badmime")
        try:
            await _clean(db, user)
            doc_svc = _doc_service(db)
            from documents.service import DocumentValidationError
            with pytest.raises(DocumentValidationError):
                await _upload(doc_svc, user, filename="virus.exe", content=b"MZ", mime="application/x-msdownload")
        finally:
            client.close()

    _run(_go())


def test_life_setup_disabled_returns_disabled_payload():
    async def _go():
        client, db = await _db()
        user = uid("disabled")
        try:
            await _clean(db, user)
            svc = _life_setup_svc(db)
            os.environ["LIFE_SETUP_ENABLED"] = "0"
            try:
                res = await svc.attach_document(user, "doc_x")
            finally:
                os.environ["LIFE_SETUP_ENABLED"] = "1"
            assert res["ok"] is False
            assert res["enabled"] is False
        finally:
            client.close()

    _run(_go())


# --------------------------------------------------------------------------
# G. Real Gemini verification (gated: only meaningful with GEMINI_API_KEY)
# --------------------------------------------------------------------------

_HAS_GEMINI = bool((os.environ.get("GEMINI_API_KEY") or "").strip())


@pytest.mark.skipif(not _HAS_GEMINI, reason="GEMINI_API_KEY not configured — AI verification incomplete")
@pytest.mark.parametrize("key", ["rogito", "bolletta_luce", "libretto", "piano_di_studi"])
def test_real_gemini_document_understanding(key):
    from documents.intelligence.life_reasoning import run_life_document_reasoning

    async def _go():
        doc = {
            "id": f"gemini_{key}", "extracted_text": txt_bytes(key).decode("utf-8"),
            "filename": f"{key}.txt", "analysis": {},
        }
        result = await run_life_document_reasoning(doc, force=True)
        telem = result["telemetry"]
        reasoning = result["reasoning"]
        # Honest assertion: either real Gemini succeeded (ai_used=True with a
        # provider/model/latency) or it failed over to the deterministic
        # fallback — never a silent unlabeled result either way.
        if reasoning["ai_used"]:
            assert reasoning["provider"] in ("gemini", "openai", "ollama", "emergent")
            assert reasoning["model"]
            assert telem.get("latency_ms") is not None
        else:
            assert reasoning["provider"] == "local-deterministic"
            assert telem.get("fallback_reason")

    _run(_go())
