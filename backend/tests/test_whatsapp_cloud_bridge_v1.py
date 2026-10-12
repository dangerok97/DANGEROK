"""Provider-authenticated WhatsApp ingress, pairing and multiuser fences."""
import hashlib
import hmac
import json
import os

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from whatsapp.cloud import CloudConfig, iter_inbound_messages
from whatsapp.service import WhatsAppService, ensure_indexes


@pytest.fixture
def config(monkeypatch):
    secrets = {
        "WHATSAPP_APP_SECRET": "test-only-webhook-secret",
        "WHATSAPP_VERIFY_TOKEN": "test-only-meta-challenge",
        "WHATSAPP_ACCESS_TOKEN": "test-only-meta-token",
        "WHATSAPP_PHONE_NUMBER_ID": "12345678909876",
        "WHATSAPP_DATA_KEY": Fernet.generate_key().decode(),
        "WHATSAPP_DISPLAY_NUMBER": "393331234567",
    }
    for k, v in secrets.items():
        monkeypatch.setenv(k, v)
    return CloudConfig.load()


@pytest.fixture
def database():
    return AsyncMongoMockClient()["ora_whatsapp_tests"]


def incoming(text="Ciao ORA", mid="wamid.test.111"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": "12345678909876"},
                    "messages": [{"id": mid, "from": "393331112233",
                                  "type": "text", "text": {"body": text}}],
                },
            }],
        }],
    }


def test_cloud_signature_and_provider_number_filter(config):
    payload = json.dumps(incoming()).encode()
    sig = "sha256=" + hmac.new(config.app_secret.encode(), payload, hashlib.sha256).hexdigest()
    assert config.verify_signature(payload, sig)
    assert not config.verify_signature(payload + b" ", sig)
    assert not config.verify_signature(payload, "sha256=wrong")
    assert config.verify_challenge("subscribe", config.verify_token)
    assert not config.verify_challenge("subscribe", "wrong")
    assert len(list(iter_inbound_messages(incoming(), config.phone_number_id))) == 1
    assert not list(iter_inbound_messages(incoming(), "other_business_id"))
    status_only = incoming()
    status_only["entry"][0]["changes"][0]["value"]["messages"] = []
    status_only["entry"][0]["changes"][0]["value"]["statuses"] = [{"id": "test"}]
    assert not list(iter_inbound_messages(status_only, config.phone_number_id))


@pytest.mark.asyncio
async def test_pair_one_account_only_and_never_store_plain_phone(config, database):
    await ensure_indexes(database)
    svc = WhatsAppService(database, config)
    pending = await svc.issue_pairing_code("user_one")
    assert len(pending["code"]) == 10
    assert not await database.whatsapp_link_codes.find_one({"token_hash": pending["code"]})
    answer, owner = await svc.pair("393331112233", pending["code"])
    assert owner == "user_one"
    assert "collegato" in answer.lower()
    linked = await database.whatsapp_links.find_one({"user_id": "user_one"})
    assert linked["phone_enc"] != "393331112233"
    assert linked["phone_hash"] != hashlib.sha256(b"393331112233").hexdigest()
    assert config.decrypt(linked["phone_enc"]) == "393331112233"
    assert (await svc.status("user_one"))["linked"]
    assert not (await svc.status("user_two"))["linked"]

    alternate = await svc.issue_pairing_code("user_two")
    reply, user_id = await svc.pair("393331112233", alternate["code"])
    assert user_id is None
    assert "altro account" in reply
    assert not (await svc.status("user_two"))["linked"]

    await svc.disconnect("user_one")
    assert not (await svc.status("user_one"))["linked"]
    assert not await database.whatsapp_links.find_one({"user_id": "user_one"})


@pytest.mark.asyncio
async def test_text_pipeline_reuses_account_ai_core_and_deduplicates(config, database, monkeypatch):
    await ensure_indexes(database)
    svc = WhatsAppService(database, config)
    pending = await svc.issue_pairing_code("owner_account")
    assert (await svc.pair("393331112233", pending["code"]))[1] == "owner_account"
    calls = []
    sent = []

    from conversation_engine.ai_core.orchestrator import AICoreOrchestrator

    async def fake_start(self, user_id, **kwargs):
        calls.append(("start", user_id, kwargs["text"], kwargs["origin"]))
        return {"ok": True, "session_id": "ces_whatsapp_test", "ora_text": "Ciao, ti aiuto."}

    async def fake_message(self, user_id, session_id, **kwargs):
        calls.append(("message", user_id, kwargs["text"], kwargs["client_message_id"]))
        return {"ok": True, "session_id": session_id, "ora_text": "Ricordo ciò che mi hai detto."}

    async def fake_send(self, recipient, text, **kwargs):
        sent.append((recipient, text))

    monkeypatch.setattr(AICoreOrchestrator, "start", fake_start)
    monkeypatch.setattr(AICoreOrchestrator, "message", fake_message)
    monkeypatch.setattr(CloudConfig, "send_text", fake_send)

    assert await svc.persist_incoming({"id": "wamid.first.000001", "from": "393331112233", "type": "text", "text": "Ciao ORA"})
    assert not await svc.persist_incoming({"id": "wamid.first.000001", "from": "393331112233", "type": "text", "text": "Ciao ORA"})
    assert await svc.process_one()
    receipt = await database.whatsapp_inbox.find_one({})
    assert receipt["status"] == "delivered"
    assert receipt["text_enc"] is None
    assert sent == [("393331112233", "Ciao, ti aiuto.")]
    assert calls == [("start", "owner_account", "Ciao ORA", "whatsapp")]

    await svc.persist_incoming({"id": "wamid.second.000002", "from": "393331112233",
                               "type": "text", "text": "Ricordati il compleanno"})
    assert await svc.process_one()
    assert len(sent) == 2
    assert calls[1][:3] == ("message", "owner_account", "Ricordati il compleanno")
    assert calls[1][3].startswith("wa_")
    assert len(calls[1][3]) <= 64


@pytest.mark.asyncio
async def test_unsigned_requests_cannot_inject_messages(config, database, monkeypatch):
    from deps import get_current_user
    from whatsapp import router as handler

    await ensure_indexes(database)
    monkeypatch.setattr(handler, "db", database)
    app = FastAPI()
    app.include_router(handler.router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "owner"}
    payload = json.dumps(incoming()).encode()
    correct = "sha256=" + hmac.new(config.app_secret.encode(), payload, hashlib.sha256).hexdigest()

    with TestClient(app) as client:
        assert client.get("/whatsapp/webhook", params={
            "hub.mode": "subscribe", "hub.verify_token": config.verify_token,
            "hub.challenge": "test-challenge",
        }).text == "test-challenge"
        assert client.get("/whatsapp/webhook", params={
            "hub.mode": "subscribe", "hub.verify_token": "incorrect",
            "hub.challenge": "test-challenge",
        }).status_code == 403
        assert client.post("/whatsapp/webhook", content=payload).status_code == 403
        assert client.post("/whatsapp/webhook", content=payload + b"x",
                           headers={"x-hub-signature-256": correct}).status_code == 403
        assert client.post("/whatsapp/webhook", content=payload,
                           headers={"x-hub-signature-256": correct}).status_code == 200
        assert client.post("/whatsapp/webhook", content=payload,
                           headers={"x-hub-signature-256": correct}).status_code == 200
        assert await database.whatsapp_inbox.count_documents({}) == 1


@pytest.mark.asyncio
async def test_wrong_account_and_unsupported_media_do_not_reach_ai(config, database, monkeypatch):
    await ensure_indexes(database)
    svc = WhatsAppService(database, config)
    sent = []
    async def fake_send(self, recipient, text, **kwargs):
        sent.append(text)
    monkeypatch.setattr(CloudConfig, "send_text", fake_send)
    await svc.persist_incoming({"id": "wamid.unlinked.01", "from": "393337778888",
                                "type": "text", "text": "Leggi il mio calendario"})
    await svc.process_one()
    assert "collega" in sent[0].lower()
    code = (await svc.issue_pairing_code("owner"))["code"]
    await svc.pair("393331112233", code)
    await svc.persist_incoming({"id": "wamid.image.02", "from": "393331112233",
                                "type": "image", "text": ""})
    await svc.process_one()
    assert "foto e vocali" in sent[1]


def test_disabled_without_secrets(monkeypatch):
    for key in ["WHATSAPP_APP_SECRET", "WHATSAPP_VERIFY_TOKEN", "WHATSAPP_ACCESS_TOKEN",
                "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_DATA_KEY"]:
        monkeypatch.delenv(key, raising=False)
    assert not CloudConfig.available()

def test_verification_needs_only_verify_token(monkeypatch):
    """Meta can verify callback before app-secret/API transport provisioning."""
    for key in ("WHATSAPP_APP_SECRET", "WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_DATA_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "preview-independent-webhook-token")
    from whatsapp.router import router
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.get("/whatsapp/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "preview-independent-webhook-token",
            "hub.challenge": "challenge-ok",
        }).text == "challenge-ok"
        assert client.get("/whatsapp/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "challenge-ok",
        }).status_code == 403
        assert client.post("/whatsapp/webhook", json={"object": "whatsapp_business_account"}).status_code == 503


