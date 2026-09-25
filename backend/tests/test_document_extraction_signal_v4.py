import hashlib

import pytest
from mongomock_motor import AsyncMongoMockClient

from connected.documents_sensor import read_changes
from documents.service import DocumentService


@pytest.mark.asyncio
async def test_delayed_text_extraction_is_seen_without_file_change(monkeypatch):
    monkeypatch.setenv("DOCUMENT_EXTRACTION_ENABLED", "true")
    db = AsyncMongoMockClient().test
    await db.documents.insert_one({"id": "d1", "user_id": "alice", "filename": "test.txt", "hash": "same-file"})
    assert (await read_changes(db, "alice"))[0].signal_type == "document.added"
    assert await read_changes(db, "alice") == []
    service = DocumentService(db=db, storage=None)
    text = "Dati sintetici riservati: costo 120 euro."
    await service._extract_and_persist(user_id="alice", doc_id="d1", blob=text.encode(), mime_type="text/plain", life_node_id=None)
    doc = await db.documents.find_one({"id": "d1"})
    assert doc["extracted_text_hash"] == hashlib.sha256(text.encode()).hexdigest()
    changes = await read_changes(db, "alice")
    assert len(changes) == 1 and changes[0].signal_type == "document.updated"
    field = next(c for c in changes[0].changed_fields if c.field == "extracted_content")
    assert field.content_withheld
    assert text not in str(changes[0].model_dump())
    assert await read_changes(db, "bob") == []
    await service._extract_and_persist(user_id="alice", doc_id="d1", blob=text.encode(), mime_type="text/plain", life_node_id=None)
    assert await read_changes(db, "alice") == []
    await service._extract_and_persist(user_id="alice", doc_id="d1", blob=b"Costo corretto: 100 euro.", mime_type="text/plain", life_node_id=None)
    assert (await read_changes(db, "alice"))[0].signal_type == "document.updated"
