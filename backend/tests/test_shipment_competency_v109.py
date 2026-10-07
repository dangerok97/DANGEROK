from datetime import datetime, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.tools.registry import ToolRegistry
from shipping import caps


@pytest.mark.asyncio
async def test_shipment_capability_lists_bounded_personal_evidence_without_reading_body(monkeypatch):
    db = AsyncMongoMockClient().test
    uid = "ship_owner"
    other = "ship_other"
    now = datetime.now(timezone.utc).isoformat()

    await db.ingestion_events.insert_many([
        {
            "user_id": uid,
            "source_record_type": "email_message",
            "external_id": "m1",
            "connector_instance_id": "mail_1",
            "ingestion_status": "processed",
            "ingested_at": now,
            "normalized_payload": {
                "subject": "Il tuo ordine è stato spedito",
                "thread_ref": "t1",
                "received_at": now,
                "sender_relationship": "automated",
                "content_available": True,
            },
        },
        {
            "user_id": other,
            "source_record_type": "email_message",
            "external_id": "secret",
            "connector_instance_id": "mail_other",
            "ingestion_status": "processed",
            "ingested_at": now,
            "normalized_payload": {
                "subject": "Pacco segreto",
                "thread_ref": "t2",
                "received_at": now,
                "content_available": True,
            },
        },
    ])
    await db.situations.insert_one({
        "id": "sit1",
        "user_id": uid,
        "status": "active",
        "summary": "Sto aspettando un pacco.",
        "semantic_kind": "Consegna",
        "updated_at": now,
    })

    async def fresh(_db, _uid):
        return {"connected": True, "instances": ["mail_1"], "refresh": [{"ok": True}]}

    monkeypatch.setattr(caps, "_refresh_mail", fresh)

    class Mail:
        async def body_for(self, **kwargs):
            raise AssertionError("candidate listing must not read message bodies")

    monkeypatch.setattr("deps.get_gmail_service", lambda: Mail())

    obs = await caps.get_shipment_status({}, {"db": db, "user_id": uid})

    assert obs.status == "ok"
    rows = obs.payload["recent_message_candidates"]
    assert [x["message_ref"] for x in rows] == ["m1"]
    assert rows[0]["subject"] == "Il tuo ordine è stato spedito"
    assert obs.payload["active_situations"][0]["situation_ref"] == "situation:sit1"
    assert obs.payload["live_carrier_tracking"] is False


@pytest.mark.asyncio
async def test_shipment_exact_message_reads_only_owned_selected_message(monkeypatch):
    db = AsyncMongoMockClient().test
    uid = "ship_exact"
    now = datetime.now(timezone.utc).isoformat()
    await db.ingestion_events.insert_many([
        {
            "user_id": uid,
            "source_record_type": "email_message",
            "external_id": "m_owned",
            "connector_instance_id": "mail_1",
            "ingestion_status": "processed",
            "ingested_at": now,
            "normalized_payload": {
                "subject": "Aggiornamento consegna",
                "received_at": now,
            },
        },
        {
            "user_id": "someone_else",
            "source_record_type": "email_message",
            "external_id": "m_foreign",
            "connector_instance_id": "mail_2",
            "ingestion_status": "processed",
            "ingested_at": now,
            "normalized_payload": {"subject": "Privata"},
        },
    ])

    seen = []

    class Mail:
        async def body_for(self, **kwargs):
            seen.append(kwargs)
            return "Il pacco è in consegna oggi."

    monkeypatch.setattr("deps.get_gmail_service", lambda: Mail())

    owned = await caps.get_shipment_status(
        {"message_ref": "m_owned"}, {"db": db, "user_id": uid}
    )
    assert owned.status == "ok"
    assert owned.payload["exact_message"]["body_excerpt"] == "Il pacco è in consegna oggi."
    assert seen == [{
        "user_id": uid,
        "instance_id": "mail_1",
        "message_id": "m_owned",
    }]

    foreign = await caps.get_shipment_status(
        {"message_ref": "m_foreign"}, {"db": db, "user_id": uid}
    )
    assert foreign.status == "partial"
    assert foreign.payload["status"] == "not_found"
    assert len(seen) == 1


def test_shipment_is_ai_capability_not_ui_button():
    registry = ToolRegistry(None)
    tool = registry.get("get_shipment_status")
    assert tool is not None
    assert tool.side_effect == "READ_ONLY"
    assert "shipment" in tool.tags

    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "frontend"
    rendered = []
    for path in list((root / "app").rglob("*.tsx")) + list((root / "src").rglob("*.tsx")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if 'label="Spedizioni"' in text or ">Spedizioni<" in text:
            rendered.append(str(path))
    assert rendered == [], rendered


def test_connected_reasoning_distinguishes_delivery_states():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "connected" / "reasoning.py").read_text(
        encoding="utf-8"
    )
    lowered = src.lower()
    assert "never promote one state into another" in lowered
    assert "shipped is not out for delivery" in lowered
    assert "out for delivery is not delivered" in lowered
