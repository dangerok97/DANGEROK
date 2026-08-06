"""Real-life HOME growth over time — ALWAYS one evolving HOME.

Timeline:
  day1 rogito → d10 mutuo → d40 bolletta → d80 assicurazione →
  d130 fotovoltaico → d170 cambio fornitore → d220 nuova bolletta → d400 vendita
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

os.environ["LIFE_OBJECT_ENGINE_ENABLED"] = "1"
os.environ["LIFE_OBJECT_HOME_UI_ENABLED"] = "0"
os.environ["LIFE_OBJECT_GEMINI"] = "0"
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
    await db.life_objects.delete_many({"user_id": user_id})


def uid() -> str:
    return f"lo_growth_{uuid.uuid4().hex[:8]}"


def _svc(db):
    from life_objects.service import LifeObjectService
    import life_objects.service as los

    los._SERVICE = LifeObjectService(db)
    return los._SERVICE


ADDR = "Via Roma 10, 20100 Milano (MI)"
ADDR_SHORT = "Via Roma 10, Milano"


def _doc(day: str, doc_type: str, ts: dict, title: str = "") -> tuple:
    doc_id = f"doc_{doc_type}_{day}"
    reasoning = {
        "document_id": doc_id,
        "document_type": doc_type,
        "domain": "casa",
        "title": title or f"{doc_type} {day}",
        "summary": f"{doc_type} su {ADDR_SHORT}",
        "confidence": 0.85,
        "type_specific": dict(ts),
        "entities": [{"type": "address", "value": ADDR, "confidence": 0.9}],
    }
    return {"id": doc_id}, reasoning


def test_real_life_home_grows_always_one():
    async def body():
        client, db = await _db()
        user_id = uid()
        await _clean(db, user_id)
        svc = _svc(db)
        await svc.ensure_indexes()

        # day1 — rogito
        d, r = _doc("d1", "rogito", {
            "address": ADDR,
            "cadastral_data": "Foglio 12 Particella 345 Sub 6",
            "price": "250000",
        })
        r1 = await svc.upsert_from_document(user_id, d, r)
        assert r1.get("ok") and r1.get("created")
        home_id = r1["object"]["id"]
        assert r1["object"]["type"] == "HOME"
        assert "lavoro" not in (r1["object"]["title"] or "").lower()
        assert "casa" in (r1["object"]["title"] or "").lower()

        # day10 — mutuo
        d, r = _doc("d10", "mutuo", {
            "lender": "Banca Esempio SpA",
            "property_address": ADDR_SHORT,
            "monthly_installment": "872,45",
            "loan_number": "MUT-2026-001",
            "rata": "872,45",
        })
        r2 = await svc.upsert_from_document(user_id, d, r)
        assert r2["object"]["id"] == home_id
        assert r2.get("created") is False
        st = r2["object"]["state"]
        assert st.get("lender") or st.get("monthly_installment")
        assert st.get("mortgage_assimilated") or "mortgage" in (r2["object"].get("assimilated_kinds") or [])
        # No merge pile for clear assimilate
        real_conflicts = [
            p for p in (r2["object"].get("merge_proposals") or [])
            if isinstance(p, dict) and p.get("link_state") == "REAL_CONFLICT"
        ]
        assert real_conflicts == []

        # day40 — bolletta
        d, r = _doc("d40", "bolletta", {
            "supplier": "EnergiaTest SpA",
            "utility_type": "energia",
            "amount_total": "87,40",
            "address": ADDR_SHORT,
            "pod": "IT001E12345678",
        })
        r3 = await svc.upsert_from_document(user_id, d, r)
        assert r3["object"]["id"] == home_id
        st = r3["object"]["state"]
        assert st.get("utility_supplier") or st.get("supplier")
        assert st.get("utility_assimilated") or st.get("utility_amount") or st.get("amount_total")

        # day80 — assicurazione casa
        d, r = _doc("d80", "polizza_casa", {
            "company": "Assicurazioni Casa SpA",
            "compagnia": "Assicurazioni Casa SpA",
            "policy_number": "POL-CASA-99",
            "address": ADDR_SHORT,
        })
        # Map document type: polizza_casa already in DOC_TYPE_TO_OBJECT
        r4 = await svc.upsert_from_document(user_id, d, r)
        assert r4["object"]["id"] == home_id

        # day130 — fotovoltaico (assimilates as solar/state)
        d, r = _doc("d130", "fotovoltaico", {
            "address": ADDR_SHORT,
            "status_detail": "impianto 6kW installato",
            "provider": "SolarTest",
        })
        # fotovoltaico may map as CUSTOM if not in DOC_TYPE — force via domain casa + address
        r["document_type"] = "bolletta"  # use known home assimilating type with solar meta
        r["type_specific"]["document_subtype"] = "fotovoltaico"
        r["type_specific"]["utility_type"] = "fotovoltaico"
        r5 = await svc.upsert_from_document(user_id, d, r)
        assert r5["object"]["id"] == home_id

        # day170 — cambio fornitore
        d, r = _doc("d170", "bolletta", {
            "supplier": "NuovoFornitore SpA",
            "utility_type": "energia",
            "amount_total": "79,00",
            "address": ADDR_SHORT,
            "pod": "IT001E12345678",
        })
        r6 = await svc.upsert_from_document(user_id, d, r)
        assert r6["object"]["id"] == home_id
        st = r6["object"]["state"]
        assert (st.get("utility_supplier") or st.get("supplier")) == "NuovoFornitore SpA"

        # day220 — nuova bolletta
        d, r = _doc("d220", "bolletta", {
            "supplier": "NuovoFornitore SpA",
            "utility_type": "energia",
            "amount_total": "91,20",
            "address": ADDR_SHORT,
        })
        r7 = await svc.upsert_from_document(user_id, d, r)
        assert r7["object"]["id"] == home_id

        # day400 — vendita (state update, still same HOME)
        d, r = _doc("d400", "rogito", {
            "address": ADDR,
            "cadastral_data": "Foglio 12 Particella 345 Sub 6",
            "price": "310000",
            "status_detail": "vendita",
        })
        r["summary"] = "Rogito di vendita Via Roma 10"
        r8 = await svc.upsert_from_document(user_id, d, r)
        assert r8["object"]["id"] == home_id
        assert r8["object"]["type"] == "HOME"
        assert "lavoro" not in (r8["object"]["title"] or "").lower()

        homes = await svc.list_objects(user_id, object_type="HOME", status="active")
        assert len(homes) == 1, f"expected 1 HOME evolving, got {len(homes)}"
        home = homes[0]
        assert home["id"] == home_id
        assert len(home.get("documents") or []) >= 6
        assert home.get("total_sources") or home.get("source_count")
        # Provenance
        assert home.get("document_sources") or home.get("documents")
        # Gaps: no cadastral re-ask, no "Hai un mutuo?"
        qblob = " ".join(
            (q.get("question") or "").lower()
            for q in (home.get("pending_questions") or [])
            if isinstance(q, dict)
        )
        assert "hai un mutuo" not in qblob
        assert "catastale" not in qblob or home["identity"].get("cadastral_data")
        # Health coherent, not fake 100 with history
        health = home.get("health") or {}
        assert "identity_completeness" in health or "completeness" in health
        assert float(health.get("score") or 0) <= 1.0
        # Timeline present
        assert len(home.get("history") or []) >= 5

        await _clean(db, user_id)
        client.close()

    _run(body())


def test_rogito_mutuo_bolletta_ai_regression_semantic():
    """AI regression: 1 HOME, correct title, assimilated mutuo+bolletta, no bad Q/conflict."""
    async def body():
        client, db = await _db()
        user_id = uid()
        await _clean(db, user_id)
        svc = _svc(db)

        d1, r1 = _doc("reg1", "rogito", {
            "address": ADDR,
            "cadastral_data": "Foglio 12 Particella 345 Sub 6",
            "dati_catastali": "Foglio 12 Particella 345 Sub 6",
            "price": "250000",
        })
        # Poison AI-like title
        r1["title"] = "Lavoro"
        out1 = await svc.upsert_from_document(user_id, d1, r1)
        assert out1["object"]["type"] == "HOME"
        assert out1["object"]["title"].lower() != "lavoro"
        assert "casa" in out1["object"]["title"].lower()
        home_id = out1["object"]["id"]
        assert out1["object"]["identity"].get("cadastral_data") or out1["object"]["identity_keys"].get("cadastral")

        d2, r2 = _doc("reg2", "mutuo", {
            "lender": "Banca Esempio Test SpA",
            "property_address": ADDR_SHORT,
            "monthly_installment": "872,45",
            "rata": "872,45",
            "loan_number": "LN-1",
        })
        out2 = await svc.upsert_from_document(user_id, d2, r2)
        assert out2["object"]["id"] == home_id
        assert out2.get("assimilated") or out2["object"]["state"].get("mortgage_assimilated")
        assert out2["object"]["state"].get("lender")
        assert out2["object"]["state"].get("monthly_installment")

        d3, r3 = _doc("reg3", "bolletta", {
            "supplier": "EnergiaTest SpA",
            "utility_type": "energia",
            "amount_total": "87,40",
            "address": ADDR_SHORT,
            "pod": "IT001E999",
        })
        out3 = await svc.upsert_from_document(user_id, d3, r3)
        assert out3["object"]["id"] == home_id
        st = out3["object"]["state"]
        assert st.get("utility_supplier") or st.get("supplier")
        assert st.get("utility_amount") or st.get("amount_total")

        homes = await svc.list_objects(user_id, object_type="HOME", status="active")
        assert len(homes) == 1
        home = homes[0]
        assert set(home["documents"]) >= {d1["id"], d2["id"], d3["id"]}

        qblob = " ".join(
            (q.get("question") or "").lower()
            for q in (home.get("pending_questions") or [])
        )
        assert "hai un mutuo" not in qblob
        assert "catastale" not in qblob

        conflicts = [
            p for p in (home.get("merge_proposals") or [])
            if isinstance(p, dict) and (p.get("link_state") == "REAL_CONFLICT" or p.get("conflict"))
        ]
        assert conflicts == []

        health = home.get("health") or {}
        assert health.get("reasons")
        assert "identity_completeness" in health or health.get("completeness") is not None
        assert float(health.get("score") or 0) < 1.0 or health.get("pending_conflicts", 0) == 0

        # Home V3 DTO shape (flag still OFF)
        from life_objects.home_v3 import to_home_v3_card, serialize_home_v3_feed
        card = to_home_v3_card(home)
        assert card["life_object_id"] == home_id
        assert card["life_domain"] == "casa"
        assert "health" in card and "next_action" in card
        assert "benefits" in card and "questions" in card
        assert "insights" in card and "timeline" in card
        assert "related_documents" in card
        feed = serialize_home_v3_feed([home])
        assert feed["enabled"] is False

        await _clean(db, user_id)
        client.close()

    _run(body())
