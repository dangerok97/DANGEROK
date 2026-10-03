import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.effects import mail_send
from agent.mail_draft import freeze_for_send
from agent.models import ActionEffect, ActionIntent, ActionStep, AutonomousGoal
from connectors.gmail.provider import FakeGmailProvider
from connectors.gmail.service import GmailReadService
from permissions.errors import ConsentDenied


class _Audit:
    async def log(self, **kwargs):
        return None


class _Permissions:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.audit = _Audit()

    async def check_access(self, **kwargs):
        return bool(self.allowed)


class _Vault:
    async def get(self, ref, *, user_id):
        return {"access_token": "test-token", "refresh_token": "test-refresh"}

    async def rotate(self, ref, *, payload):
        return None


async def _service(db, *, send_scope=True):
    provider = FakeGmailProvider(address="alice@example.com")
    service = GmailReadService(
        db=db, permissions=_Permissions(True), vault=_Vault(), provider=provider
    )
    instance = await service.instances.upsert(
        user_id="alice", connector_id="mail_gmail",
        provider_account_id="alice@example.com", display_label="alice@example.com",
        authorized_scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            *(["https://www.googleapis.com/auth/gmail.send"] if send_scope else []),
        ],
        secret_reference="sec_test", status="connected",
    )
    return service, provider, instance


@pytest.mark.asyncio
async def test_gmail_send_is_read_back_from_sent_mailbox():
    db = AsyncMongoMockClient().test
    service, provider, instance = await _service(db)

    result = await service.send_message(
        user_id="alice", instance_id=instance["id"],
        to="studio@example.com", subject="Cambio appuntamento",
        body="Possiamo spostarlo alle 12?",
    )

    assert result["observed"] is True
    assert result["message_id"]
    assert result["to"] == "studio@example.com"
    assert len(provider.sent_messages) == 1
    stored = await provider.metadata_of(
        access_token="test-token", message_id=result["message_id"]
    )
    headers = {h["name"]: h["value"] for h in stored["payload"]["headers"]}
    assert headers["Subject"] == "Cambio appuntamento"
    assert headers["To"] == "studio@example.com"


@pytest.mark.asyncio
async def test_gmail_send_refuses_readonly_connection_even_with_internal_consent():
    db = AsyncMongoMockClient().test
    service, provider, instance = await _service(db, send_scope=False)

    with pytest.raises(ConsentDenied):
        await service.send_message(
            user_id="alice", instance_id=instance["id"],
            to="studio@example.com", subject="Cambio", body="Alle 12?",
        )
    assert provider.sent_messages == []


@pytest.mark.asyncio
async def test_agent_effect_uses_exact_connected_gmail_and_reports_only_sender_side(monkeypatch):
    db = AsyncMongoMockClient().test
    service, provider, instance = await _service(db)

    import deps
    monkeypatch.setattr(deps, "get_gmail_service", lambda: service)

    goal = AutonomousGoal(
        id="goal_mail", owner_id="alice", objective="Spostare l'appuntamento",
        desired_outcome="Lo studio riceve la richiesta corretta", status="active",
        prepared_text="Possiamo spostarlo alle 12?",
        prepared_sources=["ev_1"],
    )
    step = ActionStep(
        id="step_mail", intent="Inviare una mail allo studio", step_type="execute",
        capability_needed="mail.send", reaches_somebody_else=True,
        reversibility="irreversible",
        parameters={
            "instance_id": instance["id"],
            "to": "studio@example.com",
            "subject": "Cambio appuntamento",
        },
    )
    draft, why = await freeze_for_send(db, "alice", goal, step)
    assert why == "" and draft is not None
    intent = ActionIntent(
        owner_id="alice", goal_id=goal.id, step_id=step.id,
        capability="mail.send", effect_summary="Inviare una mail allo studio",
        target_ref="studio@example.com",
        authority_required="explicit_yes",
        expected_effect="La mail parte dall'account Gmail collegato",
        reversibility="irreversible",
        parameters={
            "instance_id": instance["id"],
            "draft_id": draft["id"],
            "draft_hash": draft["content_hash"],
        },
        effect=ActionEffect(
            effect_type="send", target="studio@example.com",
            external_party=True, reversibility="irreversible",
            effect_binding=draft["content_hash"],
        ),
    )
    outcome = await mail_send(db, "alice", intent)

    assert outcome.observed is True
    assert outcome.receipt.provider_status == "succeeded"
    assert outcome.receipt.external_ref
    assert len(provider.sent_messages) == 1
    assert "destinatario" not in outcome.observation.lower() or "letto" not in outcome.observation.lower()


@pytest.mark.asyncio
async def test_changed_mail_body_changes_authority_fingerprint():
    db = AsyncMongoMockClient().test
    goal = AutonomousGoal(
        id="goal_hash", owner_id="alice", objective="Scrivere allo studio",
        desired_outcome="Richiesta inviata", status="active",
        prepared_text="Prima versione",
        prepared_sources=["ev_1"],
    )
    step = ActionStep(
        id="step_hash", intent="Inviare la richiesta", step_type="execute",
        capability_needed="mail.send", reaches_somebody_else=True,
        reversibility="irreversible",
        parameters={"to": "studio@example.com", "subject": "Richiesta"},
    )
    first, why = await freeze_for_send(db, "alice", goal, step)
    assert why == "" and first

    goal.prepared_text = "Seconda versione"
    second, why = await freeze_for_send(db, "alice", goal, step)
    assert why == "" and second
    assert first["content_hash"] != second["content_hash"]

    a = ActionEffect(
        effect_type="send", target="studio@example.com", external_party=True,
        reversibility="irreversible", effect_binding=first["content_hash"],
    )
    b = ActionEffect(
        effect_type="send", target="studio@example.com", external_party=True,
        reversibility="irreversible", effect_binding=second["content_hash"],
    )
    assert a.fingerprint() != b.fingerprint()
