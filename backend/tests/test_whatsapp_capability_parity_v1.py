"""WhatsApp is another front door to the same ORA AI Core, not a second bot."""
import json

import pytest
from mongomock_motor import AsyncMongoMockClient
from cryptography.fernet import Fernet

from whatsapp.cloud import CloudConfig, iter_inbound_messages
from whatsapp.handoff import render_core_answer_for_whatsapp
from whatsapp.media import _is_meta_media_host, MediaNotUsable
from whatsapp.service import WhatsAppService
from conversation_engine.ai_core.orchestrator import AICoreOrchestrator


@pytest.fixture
def cfg(monkeypatch):
    values = {
        "WHATSAPP_APP_SECRET": "test-app-secret",
        "WHATSAPP_VERIFY_TOKEN": "test-challenge",
        "WHATSAPP_ACCESS_TOKEN": "test-graph-token",
        "WHATSAPP_PHONE_NUMBER_ID": "12345678909876",
        "WHATSAPP_DATA_KEY": Fernet.generate_key().decode(),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return CloudConfig.load()


async def _pair(db, cfg):
    svc = WhatsAppService(db, cfg)
    issued = await svc.issue_pairing_code("account_alpha")
    assert (await svc.pair("393331112233", issued["code"]))[1] == "account_alpha"
    return svc


def _item(cfg, kind, media=None, text="", id="wamid.synthetic.image"):
    return {
        "kind": kind,
        "phone_hash": cfg.fingerprint("phone", "393331112233"),
        "phone_enc": cfg.encrypt("393331112233"),
        "text_enc": cfg.encrypt(text),
        "media_enc": cfg.encrypt(json.dumps(media)) if media else None,
        "provider_message_id": id,
    }


def test_action_links_are_verified_and_device_actions_handoff(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ORA_WEB_URL", "https://ora-web-production-fb67.up.railway.app")
    ai_result = {
        "ora_text": "Ho preparato il percorso.",
        "session_id": "ces_0123456789abcd",
        "navigation": [
            {"label": "Google Maps", "url": "https://www.google.com/maps/dir/?api=1&destination=Colosseo"},
            {"label": "Mappa insicura", "url": "https://www.google.com.evil.example/maps"},
        ],
        "ui_actions": [
            {"kind": "workspace", "plan_id": "lop_abcdef123456"},
        ],
        "client_actions": [{"kind": "request_location"}],
    }
    text = render_core_answer_for_whatsapp(ai_result)
    assert "www.google.com/maps/dir/" in text
    assert "/goal-workspace/lop_abcdef123456" in text
    assert "/ora/ces_0123456789abcd" in text
    assert "evil.example" not in text
    assert text.startswith("Ho preparato")


def test_explicit_whatsapp_link_security_and_no_unauthorized_launch(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ORA_WEB_URL", "https://example.com/redirect")
    msg = render_core_answer_for_whatsapp({
        "ora_text": "Servono i permessi dell'app.",
        "session_id": "ces_0123456789abcd",
        "client_actions": [{"kind": "get_current_location"}],
        "navigation": [{"label": "Il luogo", "url": "javascript:alert(1)"}],
        "ui_actions": [{"kind": "workspace", "plan_id": "lop_1234?uid=other"}],
    })
    assert "javascript:" not in msg
    assert "example.com" not in msg
    assert "www.google.com" not in msg
    assert "/ora/ces_0123456789abcd" in msg
    assert "goal-workspace" not in msg
    assert "Servono i permessi" in msg


def test_meta_media_host_never_allows_arbitrary_urls():
    assert _is_meta_media_host("https://lookaside.fbsbx.com/whatsapp_business/attachments/x")
    assert _is_meta_media_host("https://cdn.fbcdn.net/safe")
    assert not _is_meta_media_host("https://lookaside.fbsbx.com.evil.test/steal")
    assert not _is_meta_media_host("http://lookaside.fbsbx.com/m")
    assert not _is_meta_media_host("https://user@lookaside.fbsbx.com/m")
    assert not _is_meta_media_host("https://localhost/m")


def test_signed_cloud_parser_supports_photo_audio_document_location():
    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{
        "field": "messages", "value": {
            "metadata": {"phone_number_id": "12345678909876"},
            "messages": [
                {"id": "wamid.synthetic.image", "from": "393331112233", "type": "image",
                 "image": {"id": "123456789012345", "mime_type": "image/jpeg",
                           "caption": "Che oggetto è?"}},
                {"id": "wamid.synthetic.audio", "from": "393331112233", "type": "audio",
                 "audio": {"id": "123456789012346", "mime_type": "audio/ogg"}},
                {"id": "wamid.synthetic.doc", "from": "393331112233", "type": "document",
                 "document": {"id": "123456789012347", "filename": "contratto.pdf"}},
                {"id": "wamid.synthetic.loc", "from": "393331112233", "type": "location",
                 "location": {"latitude": 42.254, "longitude": 11.756, "name": "Un luogo"}},
            ]
        }
    }]}]}
    parsed = list(iter_inbound_messages(payload, "12345678909876"))
    assert len(parsed) == 4
    assert parsed[0]["media"]["id"] == "123456789012345"
    assert parsed[0]["text"] == "Che oggetto è?"
    assert parsed[1]["media"]["id"] == "123456789012346"
    assert parsed[2]["media"]["filename"] == "contratto.pdf"
    assert "42.254000" in parsed[3]["text"]
    assert "non posizione GPS" in parsed[3]["text"]
    assert list(iter_inbound_messages(payload, "wrong_phone")) == []


@pytest.mark.asyncio
async def test_whatsapp_photo_ingests_owner_document_before_same_ai_core(cfg, monkeypatch):
    db = AsyncMongoMockClient().whatsapp_parity_image
    svc = await _pair(db, cfg)
    import whatsapp.service as service
    from conversation_engine.ai_core.files.service import ContextFileService

    async def fake_fetch(**kwargs):
        assert kwargs["media_id"] == "123456789012345"
        return b"fake-photo-image-bytes", "image/jpeg"

    async def fake_upload(self, **kwargs):
        assert kwargs["user_id"] == "account_alpha"
        assert kwargs["mime_type"] == "image/jpeg"
        assert kwargs["content"] == b"fake-photo-image-bytes"
        return {"ok": True, "file_id": "lcf_abcdefgh01234"}

    called = []

    async def fake_start(self, user_id, **kwargs):
        called.append((user_id, kwargs))
        return {"ok": True, "session_id": "ces_0123456789abcd",
                "ora_text": "Vedo un oggetto: ecco cosa posso confermare."}

    monkeypatch.setattr(service, "fetch_whatsapp_media", fake_fetch)
    monkeypatch.setattr(ContextFileService, "upload_and_bind", fake_upload)
    monkeypatch.setattr(AICoreOrchestrator, "start", fake_start)
    text, owner = await svc.prepare_reply(_item(
        cfg, "image", {"id": "123456789012345", "mime_type": "image/jpeg"},
        text="Che cosa vedi?", id="wamid.synthetic.photo"
    ))
    assert owner == "account_alpha"
    assert "Vedo un oggetto" in text
    assert called and called[0][0] == "account_alpha"
    assert called[0][1]["attachments"] == [{"file_id": "lcf_abcdefgh01234"}]
    assert called[0][1]["text"] == "Che cosa vedi?"
    assert called[0][1]["origin"] == "whatsapp"


@pytest.mark.asyncio
async def test_whatsapp_voice_transcribes_into_same_ai_core(cfg, monkeypatch):
    db = AsyncMongoMockClient().whatsapp_parity_audio
    svc = await _pair(db, cfg)
    import whatsapp.service as service
    called = []

    async def fake_fetch(**kwargs):
        assert kwargs["kind"] == "audio"
        return b"fake-audio-bytes", "audio/ogg"

    async def fake_transcribe(audio, mime):
        assert audio == b"fake-audio-bytes"
        assert mime == "audio/ogg"
        return "Aggiungi domani un appuntamento dal dentista"

    async def fake_start(self, user_id, **kwargs):
        called.append((user_id, kwargs))
        return {"ok": True, "session_id": "ces_0123456789abcd",
                "ora_text": "Per quale orario devo programmare la visita?"}

    monkeypatch.setattr(service, "fetch_whatsapp_media", fake_fetch)
    monkeypatch.setattr(service, "transcribe_voice", fake_transcribe)
    monkeypatch.setattr(AICoreOrchestrator, "start", fake_start)
    text, owner = await svc.prepare_reply(_item(cfg, "audio", {
        "id": "123456789012346", "mime_type": "audio/ogg",
    }, id="wamid.synthetic.voice"))
    assert owner == "account_alpha"
    assert "quale orario" in text
    assert called[0][1]["text"] == "Aggiungi domani un appuntamento dal dentista"
    assert "attachments" not in called[0][1]


@pytest.mark.asyncio
async def test_no_fake_media_analysis_if_provider_fails(cfg, monkeypatch):
    db = AsyncMongoMockClient().whatsapp_parity_failure
    svc = await _pair(db, cfg)
    import whatsapp.service as service

    async def fake_fetch(**kwargs):
        raise MediaNotUsable("media_download_unavailable")

    async def fake_start(self, user_id, **kwargs):
        pytest.fail("Cannot call AI image analysis without verified media")

    monkeypatch.setattr(service, "fetch_whatsapp_media", fake_fetch)
    monkeypatch.setattr(AICoreOrchestrator, "start", fake_start)
    text, user = await svc.prepare_reply(_item(cfg, "image", {
        "id": "123456789012345", "mime_type": "image/jpeg",
    }))
    assert user == "account_alpha"
    assert "non riesco" in text.lower()
