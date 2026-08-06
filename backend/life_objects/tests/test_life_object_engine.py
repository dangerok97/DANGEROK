"""Life Object Engine — shadow mode unit/API tests.

Covers Casa (rogito→mutuo→bolletta = one HOME), Auto (libretto+polizza),
university/job/family, duplicates, merge, flag off, Gemini-absent fallback,
user isolation. Deterministic reasoner by default (LIFE_OBJECT_GEMINI=0).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

os.environ["LIFE_OBJECT_ENGINE_ENABLED"] = "1"
os.environ["LIFE_OBJECT_HOME_UI_ENABLED"] = "0"
os.environ["LIFE_OBJECT_GEMINI"] = "0"  # stable offline
os.environ.setdefault("JWT_SECRET", "test-secret-life-objects")
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "ora_life_objects_test")

_BACKEND = str(Path(__file__).resolve().parents[2])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

MONGO = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
DBNAME = os.environ.get("DB_NAME", "ora_life_objects_test")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, user_id: str):
    for col in ("life_objects", "goals", "documents", "travel_projects", "study_plans"):
        await db[col].delete_many({"user_id": user_id})


def uid(prefix: str = "lo") -> str:
    return f"lo_test_{prefix}_{uuid.uuid4().hex[:8]}"


def _svc(db):
    from life_objects.service import LifeObjectService
    import life_objects.service as los

    los._SERVICE = LifeObjectService(db)
    return los._SERVICE


def _rogito_reasoning(doc_id: str = "doc_rogito") -> dict:
    return {
        "document_id": doc_id,
        "document_type": "rogito",
        "domain": "casa",
        "title": "Rogito Via Roma 10",
        "summary": "Compravendita immobile Via Roma 10 Milano",
        "confidence": 0.85,
        "type_specific": {
            "address": "Via Roma 10, 20100 Milano (MI)",
            "cadastral_data": "Foglio 12 Particella 345 Sub 6",
            "price": "250000",
        },
        "entities": [{"type": "address", "value": "Via Roma 10, 20100 Milano (MI)", "confidence": 0.9}],
        "recommended_actions": [{"title": "Salva indirizzo casa"}],
    }


def _mutuo_reasoning(doc_id: str = "doc_mutuo") -> dict:
    return {
        "document_id": doc_id,
        "document_type": "mutuo",
        "domain": "casa",
        "title": "Mutuo Banca Esempio",
        "summary": "Mutuo ipotecario su Via Roma 10",
        "confidence": 0.8,
        "type_specific": {
            "lender": "Banca Esempio Test SpA",
            "property_address": "Via Roma 10, Milano",
            "monthly_installment": "872,45",
        },
    }


def _bolletta_reasoning(doc_id: str = "doc_bolletta", amount: str = "87,40") -> dict:
    return {
        "document_id": doc_id,
        "document_type": "bolletta",
        "domain": "casa",
        "title": "Bolletta energia",
        "summary": "Bolletta luce Via Roma 10",
        "confidence": 0.75,
        "type_specific": {
            "supplier": "EnergiaTest SpA",
            "utility_type": "energia",
            "amount_total": amount,
            "address": "Via Roma 10, Milano",
            "contract_code": "ET-998877",
        },
    }


def _libretto_reasoning(doc_id: str = "doc_libretto") -> dict:
    return {
        "document_id": doc_id,
        "document_type": "libretto",
        "domain": "auto",
        "title": "Libretto Fiat Panda",
        "summary": "Libretto targa AB123CD",
        "confidence": 0.9,
        "type_specific": {
            "plate": "AB123CD",
            "brand": "Fiat",
            "model": "Panda",
            "vin": "ZFA31200000TEST01",
        },
    }


def _polizza_auto_reasoning(doc_id: str = "doc_polizza") -> dict:
    return {
        "document_id": doc_id,
        "document_type": "polizza_auto",
        "domain": "auto",
        "title": "Polizza RC Auto",
        "summary": "Polizza targa AB123CD",
        "confidence": 0.85,
        "type_specific": {
            "plate": "AB123CD",
            "company": "Assicurazioni Test SpA",
            "policy_number": "POL-AUTO-556677",
            "insured_object": "AB123CD",
        },
    }


# ---------------------------------------------------------------------------
# Casa chain — NEVER second HOME
# ---------------------------------------------------------------------------
def test_casa_rogito_mutuo_bolletta_single_home():
    async def body():
        client, db = await _db()
        user_id = uid("casa")
        await _clean(db, user_id)
        svc = _svc(db)
        await svc.ensure_indexes()

        r1 = await svc.upsert_from_document(
            user_id, {"id": "doc_rogito"}, _rogito_reasoning(),
        )
        assert r1.get("ok") and r1.get("created")
        home_id = r1["object"]["id"]
        assert r1["object"]["type"] == "HOME"
        assert r1["object"]["identity_keys"].get("address_norm")
        assert r1["object"]["identity_keys"].get("cadastral")

        r2 = await svc.upsert_from_document(
            user_id, {"id": "doc_mutuo"}, _mutuo_reasoning(),
        )
        assert r2.get("ok")
        assert r2.get("created") is False
        assert r2["object"]["id"] == home_id
        assert "doc_mutuo" in r2["object"]["documents"]
        assert "doc_rogito" in r2["object"]["documents"]

        r3 = await svc.upsert_from_document(
            user_id, {"id": "doc_bolletta"}, _bolletta_reasoning(),
        )
        assert r3.get("ok")
        assert r3.get("created") is False
        assert r3["object"]["id"] == home_id
        assert "doc_bolletta" in r3["object"]["documents"]

        homes = await svc.list_objects(user_id, object_type="HOME", status="active")
        assert len(homes) == 1, f"expected 1 HOME, got {len(homes)}"
        assert set(homes[0]["documents"]) >= {"doc_rogito", "doc_mutuo", "doc_bolletta"}

        # Trend helper after second bolletta
        await svc.upsert_from_document(
            user_id, {"id": "doc_bolletta2"}, _bolletta_reasoning("doc_bolletta2", "95,00"),
        )
        trend = await svc.trend(user_id, home_id, utility_type="energia")
        assert trend.get("ok")
        assert trend.get("points", 0) >= 2

        await _clean(db, user_id)
        client.close()

    _run(body())


def test_never_title_alone_second_home():
    """Two HOME docs with no shared identity → propose_merge / uncertain, not silent Casa 2 active."""
    async def body():
        client, db = await _db()
        user_id = uid("dup")
        await _clean(db, user_id)
        svc = _svc(db)

        await svc.upsert_from_document(user_id, {"id": "d1"}, _rogito_reasoning("d1"))
        # Different address — different HOME is OK
        other = _rogito_reasoning("d2")
        other["type_specific"] = {
            "address": "Via Verdi 5, Roma",
            "cadastral_data": "Foglio 99 Particella 1 Sub 1",
        }
        other["entities"] = [{"type": "address", "value": "Via Verdi 5, Roma", "confidence": 0.9}]
        r2 = await svc.upsert_from_document(user_id, {"id": "d2"}, other)
        assert r2.get("ok")
        homes = await svc.list_objects(user_id, object_type="HOME", status="active")
        assert len(homes) == 2  # different strong identity → two homes OK

        # Weak doc without identity while one HOME exists → merge proposal, not new active
        weak = {
            "document_id": "d3",
            "document_type": "bolletta",
            "domain": "casa",
            "title": "Casa Bella",  # title alone must NOT create
            "summary": "Bolletta senza indirizzo",
            "confidence": 0.4,
            "type_specific": {"supplier": "X", "amount_total": "10"},
        }
        r3 = await svc.upsert_from_document(user_id, {"id": "d3"}, weak)
        assert r3.get("ok")
        # Should propose merge or update/uncertain — not create a third active HOME from title
        homes_active = await svc.list_objects(user_id, object_type="HOME", status="active")
        assert len(homes_active) == 2
        assert r3.get("merge_proposed") or r3.get("created") is False or r3.get("uncertain")

        await _clean(db, user_id)
        client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Auto — libretto + polizza = one VEHICLE
# ---------------------------------------------------------------------------
def test_auto_libretto_polizza_single_vehicle():
    async def body():
        client, db = await _db()
        user_id = uid("auto")
        await _clean(db, user_id)
        svc = _svc(db)

        r1 = await svc.upsert_from_document(
            user_id, {"id": "doc_lib"}, _libretto_reasoning(),
        )
        assert r1["object"]["type"] == "VEHICLE"
        vid = r1["object"]["id"]
        assert r1["object"]["identity_keys"].get("plate") == "AB123CD"

        r2 = await svc.upsert_from_document(
            user_id, {"id": "doc_pol"}, _polizza_auto_reasoning(),
        )
        assert r2.get("created") is False
        assert r2["object"]["id"] == vid
        vehicles = await svc.list_objects(user_id, object_type="VEHICLE")
        assert len(vehicles) == 1

        await _clean(db, user_id)
        client.close()

    _run(body())


# ---------------------------------------------------------------------------
# University / Job / Family
# ---------------------------------------------------------------------------
def test_university_and_job_and_family_basic():
    async def body():
        client, db = await _db()
        user_id = uid("ujf")
        await _clean(db, user_id)
        svc = _svc(db)

        uni = await svc.upsert_from_document(
            user_id,
            {"id": "doc_piano"},
            {
                "document_type": "piano_di_studi",
                "domain": "studio",
                "title": "Piano di studi",
                "summary": "Informatica Uni Test",
                "confidence": 0.8,
                "type_specific": {
                    "institution": "Universita Test di Milano",
                    "course_name": "Informatica",
                },
            },
        )
        assert uni["object"]["type"] in ("UNIVERSITY", "COURSE")
        assert uni["object"]["identity_keys"].get("institution")

        job = await svc.upsert_from_document(
            user_id,
            {"id": "doc_busta"},
            {
                "document_type": "busta_paga",
                "domain": "finanze",
                "title": "Busta paga",
                "summary": "Lavoro presso ACME",
                "confidence": 0.7,
                "type_specific": {"employer": "ACME Test SpA", "company": "ACME Test SpA"},
            },
        )
        # busta_paga maps to JOB
        assert job["object"]["type"] == "JOB"

        from life_objects.models import LifeObjectCreateBody
        fam = await svc.create(
            user_id,
            LifeObjectCreateBody(
                type="FAMILY_MEMBER",
                title="Familiare — Anna",
                identity_keys={"person_key": "anna_verdi"},
                origin="test",
            ),
        )
        assert fam["object"]["type"] == "FAMILY_MEMBER"

        await _clean(db, user_id)
        client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Merge / link / CRUD
# ---------------------------------------------------------------------------
def test_merge_and_link():
    async def body():
        client, db = await _db()
        user_id = uid("merge")
        await _clean(db, user_id)
        svc = _svc(db)

        from life_objects.models import LifeObjectCreateBody

        a = await svc.create(
            user_id,
            LifeObjectCreateBody(
                type="HOME",
                title="Casa A",
                identity_keys={"address_norm": "via roma 10 milano"},
            ),
        )
        b = await svc.create(
            user_id,
            LifeObjectCreateBody(
                type="HOME",
                title="Casa B",
                identity_keys={"cadastral": "foglio12particella345sub6"},
            ),
        )
        merged = await svc.merge(
            user_id, source_id=b["object"]["id"], target_id=a["object"]["id"],
        )
        assert merged.get("ok")
        assert merged["object"]["id"] == a["object"]["id"]
        assert "cadastral" in merged["object"]["identity_keys"]

        vehicle = await svc.create(
            user_id,
            LifeObjectCreateBody(
                type="VEHICLE", title="Auto", identity_keys={"plate": "XY999ZZ"},
            ),
        )
        linked = await svc.link(
            user_id, a["object"]["id"],
            target_id=vehicle["object"]["id"], relation="owned_by",
        )
        assert linked.get("ok")
        assert any(r["target_id"] == vehicle["object"]["id"] for r in linked["object"]["relationships"])

        await _clean(db, user_id)
        client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Travel / Study / Goal hooks
# ---------------------------------------------------------------------------
def test_travel_study_goal_shadow_hooks():
    async def body():
        client, db = await _db()
        user_id = uid("hooks")
        await _clean(db, user_id)
        svc = _svc(db)

        travel = await svc.upsert_from_travel(
            user_id,
            {
                "id": "tp_1",
                "destination": "Lisbona",
                "start_date": "2026-09-01",
                "end_date": "2026-09-10",
                "title": "Vacanza Lisbona",
            },
        )
        assert travel.get("ok")
        assert travel["object"]["type"] == "TRAVEL"

        study = await svc.upsert_from_study(
            user_id,
            {
                "id": "sp_1",
                "institution": "Politecnico Test",
                "course_name": "Ingegneria",
                "title": "Piano studio",
            },
        )
        assert study.get("ok")
        assert study["object"]["type"] in ("UNIVERSITY", "COURSE")

        # Goal attach
        await db.goals.insert_one({
            "id": "goal_travel_1",
            "user_id": user_id,
            "title": "Viaggio a Lisbona",
            "goal_type": "travel",
            "travel_project_id": "tp_1",
            "status": "active",
        })
        gres = await svc.attach_goal(
            user_id,
            {
                "id": "goal_travel_1",
                "title": "Viaggio a Lisbona",
                "goal_type": "travel",
                "travel_project_id": "tp_1",
            },
        )
        assert gres.get("life_object_id")
        gdoc = await db.goals.find_one({"id": "goal_travel_1"}, {"_id": 0})
        assert gdoc.get("life_object_id") == gres["life_object_id"]

        await _clean(db, user_id)
        client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Flag off / isolation / Gemini fallback
# ---------------------------------------------------------------------------
def test_flag_off_no_writes():
    async def body():
        client, db = await _db()
        user_id = uid("flag")
        await _clean(db, user_id)
        os.environ["LIFE_OBJECT_ENGINE_ENABLED"] = "0"
        try:
            # Reset singleton flag check is env-based each call
            svc = _svc(db)
            res = await svc.upsert_from_document(
                user_id, {"id": "d"}, _rogito_reasoning(),
            )
            assert res.get("skipped")
            homes = await svc.list_objects(user_id, object_type="HOME")
            assert homes == []
        finally:
            os.environ["LIFE_OBJECT_ENGINE_ENABLED"] = "1"
        await _clean(db, user_id)
        client.close()

    _run(body())


def test_user_isolation():
    async def body():
        client, db = await _db()
        u1, u2 = uid("iso1"), uid("iso2")
        await _clean(db, u1)
        await _clean(db, u2)
        svc = _svc(db)

        await svc.upsert_from_document(u1, {"id": "d1"}, _rogito_reasoning())
        homes_u2 = await svc.list_objects(u2, object_type="HOME")
        assert homes_u2 == []
        homes_u1 = await svc.list_objects(u1, object_type="HOME")
        assert len(homes_u1) == 1

        await _clean(db, u1)
        await _clean(db, u2)
        client.close()

    _run(body())


def test_gemini_absent_deterministic_fallback():
    from life_objects.reasoner import deterministic_reason_from_document, reason_from_document

    async def body():
        # No candidates → create HOME with identity
        d = deterministic_reason_from_document(reasoning=_rogito_reasoning())
        assert d.action in ("create", "update")
        assert d.object_type == "HOME"
        assert d.identity_keys.get("address_norm")
        assert d.ai_used is False
        assert d.invented_facts is False

        # Async path with GEMINI=0
        os.environ["LIFE_OBJECT_GEMINI"] = "0"
        d2 = await reason_from_document(reasoning=_libretto_reasoning(), existing_candidates=[])
        assert d2.object_type == "VEHICLE"
        assert d2.identity_keys.get("plate") == "AB123CD"
        assert d2.ai_used is False

    _run(body())


def test_home_ui_flag_default_off():
    from life_objects.service import life_object_home_ui_enabled

    os.environ["LIFE_OBJECT_HOME_UI_ENABLED"] = "0"
    assert life_object_home_ui_enabled() is False


def test_dedup_normalize_helpers():
    from life_objects.deduplication import (
        extract_identity_keys_from_reasoning,
        normalize_plate,
        normalize_text,
    )

    assert normalize_plate("ab 123 cd") == "AB123CD"
    assert "roma" in normalize_text("Via Roma, 10")
    keys = extract_identity_keys_from_reasoning(
        object_type="HOME", reasoning=_rogito_reasoning(),
    )
    assert keys.get("cadastral")
    assert keys.get("address_norm")
    # Title must not appear as identity key
    assert "title" not in keys


# ---------------------------------------------------------------------------
# AI enrichment — narrative / questions / insights / temporal / health
# identity vs state — Gemini-absent fallback — Casa/Auto/Uni/Lavoro
# ---------------------------------------------------------------------------
def test_enrichment_casa_narrative_questions_health_identity_state():
    async def body():
        client, db = await _db()
        user_id = uid("enrich_casa")
        await _clean(db, user_id)
        svc = _svc(db)

        r1 = await svc.upsert_from_document(
            user_id, {"id": "doc_rogito"}, _rogito_reasoning(),
        )
        home = r1["object"]
        assert home["identity"].get("address") or home["identity_keys"].get("address_norm")
        assert "address" in (home["identity"] or {}) or "cadastral_data" in (home["identity"] or {})
        # properties preserved (non-destructive)
        assert home["properties"].get("address") or home["identity"].get("address")

        nar = home.get("narrative") or {}
        assert (nar.get("text") or "").strip()
        assert "casa" in nar["text"].lower() or "via" in nar["text"].lower()
        assert nar.get("version", 0) >= 1
        assert nar.get("source") == "deterministic"  # GEMINI=0

        health = home.get("health") or {}
        assert "completeness" in health
        assert "reliability" in health
        assert "missing_info" in health
        assert "reasons" in health
        assert isinstance(health.get("reasons"), list)

        # mutuo + bollette → state fields + temporal/insights
        await svc.upsert_from_document(user_id, {"id": "doc_mutuo"}, _mutuo_reasoning())
        await svc.upsert_from_document(
            user_id, {"id": "doc_b1"}, _bolletta_reasoning("doc_b1", "80,00"),
        )
        # Supplier change
        bol2 = _bolletta_reasoning("doc_b2", "95,00")
        bol2["type_specific"]["supplier"] = "NuovoFornitore SpA"
        r_final = await svc.upsert_from_document(user_id, {"id": "doc_b2"}, bol2)
        obj = r_final["object"]
        assert obj["state"].get("supplier") == "NuovoFornitore SpA"
        assert obj["state"].get("lender") or obj["properties"].get("lender")

        insights = obj.get("insights") or []
        assert isinstance(insights, list)
        # temporal comparison present
        assert obj.get("temporal") is not None
        assert (obj["temporal"].get("observations") or [])

        # Refresh questions via service API helper
        qres = await svc.get_questions(user_id, obj["id"], refresh=True)
        assert qres.get("ok")
        assert isinstance(qres.get("pending_questions"), list)

        hres = await svc.get_health(user_id, obj["id"], refresh=True)
        assert hres["health"]["completeness"] is not None
        assert hres["health"]["score"] is not None

        await _clean(db, user_id)
        client.close()

    _run(body())


def test_enrichment_auto_university_lavoro():
    async def body():
        client, db = await _db()
        user_id = uid("enrich_avl")
        await _clean(db, user_id)
        svc = _svc(db)

        auto = await svc.upsert_from_document(
            user_id, {"id": "doc_lib"}, _libretto_reasoning(),
        )
        assert auto["object"]["type"] == "VEHICLE"
        assert auto["object"]["identity"].get("plate") or auto["object"]["identity_keys"].get("plate")
        assert "targa" in (auto["object"]["narrative"]["text"] or "").lower() or "panda" in (
            auto["object"]["narrative"]["text"] or ""
        ).lower()
        await svc.upsert_from_document(
            user_id, {"id": "doc_pol"}, _polizza_auto_reasoning(),
        )
        vehicles = await svc.list_objects(user_id, object_type="VEHICLE")
        assert len(vehicles) == 1
        assert vehicles[0]["state"].get("company") or vehicles[0]["properties"].get("company")

        uni = await svc.upsert_from_document(
            user_id,
            {"id": "doc_piano"},
            {
                "document_type": "piano_di_studi",
                "domain": "studio",
                "title": "Piano di studi",
                "summary": "Informatica Uni Test",
                "confidence": 0.8,
                "type_specific": {
                    "institution": "Universita Test di Milano",
                    "course_name": "Informatica",
                },
            },
        )
        assert uni["object"]["narrative"]["text"]
        assert uni["object"]["health"]["reasons"]

        job = await svc.upsert_from_document(
            user_id,
            {"id": "doc_busta"},
            {
                "document_type": "busta_paga",
                "domain": "finanze",
                "title": "Busta paga",
                "summary": "Lavoro presso ACME",
                "confidence": 0.7,
                "type_specific": {"employer": "ACME Test SpA", "company": "ACME Test SpA"},
            },
        )
        assert job["object"]["type"] == "JOB"
        assert job["object"]["identity"].get("employer") or job["object"]["identity_keys"].get("employer")
        assert job["object"]["narrative"]["text"]
        assert job["object"]["pending_questions"] is not None

        await _clean(db, user_id)
        client.close()

    _run(body())


def test_enrichment_gemini_absent_fallback_and_isolation():
    from life_objects.enrichment import (
        deterministic_narrative,
        deterministic_health,
        refresh_enrichment,
    )
    from life_objects.models import LifeObject

    async def body():
        client, db = await _db()
        u1, u2 = uid("en1"), uid("en2")
        await _clean(db, u1)
        await _clean(db, u2)
        svc = _svc(db)
        os.environ["LIFE_OBJECT_GEMINI"] = "0"

        r = await svc.upsert_from_document(u1, {"id": "d"}, _rogito_reasoning())
        obj = r["object"]
        assert obj["narrative"]["source"] == "deterministic"
        assert obj["health"]["source"] == "deterministic"

        # Pure unit deterministic
        lo = LifeObject(
            user_id=u1,
            type="HOME",
            title="Casa",
            identity={"address": "Via Roma 10"},
            state={"supplier": "X"},
            identity_keys={"address_norm": "via roma 10"},
        )
        nar = deterministic_narrative(lo)
        assert nar.ai_used is False
        assert nar.invented_facts is False
        assert "casa" in nar.narrative.lower()
        health = deterministic_health(lo)
        assert 0 <= health.completeness <= 1
        assert health.reasons

        await refresh_enrichment(lo)
        assert lo.narrative.text
        assert lo.temporal is not None

        # Isolation: u2 sees nothing
        assert await svc.list_objects(u2, object_type="HOME") == []

        await _clean(db, u1)
        await _clean(db, u2)
        client.close()

    _run(body())


def test_home_v3_dto_flag_off():
    from life_objects.home_v3 import serialize_home_v3_feed, to_home_v3_card

    os.environ["LIFE_OBJECT_HOME_UI_ENABLED"] = "0"
    feed = serialize_home_v3_feed([{
        "id": "lo_x",
        "type": "HOME",
        "title": "Casa",
        "status": "active",
        "narrative": {"text": "Hai una casa"},
        "health": {"score": 0.8, "label": "healthy", "completeness": 0.9, "reliability": 0.7},
        "insights": [{"title": "ok"}],
        "pending_questions": [{"question": "POD?"}],
        "documents": ["a"],
        "updated_at": "2026-08-07",
    }])
    assert feed["enabled"] is False
    assert feed["cards"] == []
    card = to_home_v3_card({
        "id": "lo_x",
        "type": "HOME",
        "title": "Casa",
        "narrative": {"text": "Hai una casa in Via Roma"},
        "health": {"score": 0.8, "label": "healthy"},
        "insights": [],
        "pending_questions": [],
        "documents": [],
    })
    assert card["narrative"]
    assert "Life Object" not in (card["narrative"] or "")
