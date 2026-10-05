from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent import providers
from agent.capabilities import CapabilityResolver
from agent.models import ActionStep, AutonomousGoal
from connectors.bank.provider import FakeBankProvider
from permissions.service import PermissionService


def _goal():
    return AutonomousGoal(
        owner_id="alice",
        status="active",
        objective="Capire il contesto economico attuale",
        desired_outcome="Avere un quadro bancario aggiornato e verificabile",
    )


@pytest.mark.asyncio
async def test_pending_bank_connection_is_not_exposed_to_agent(monkeypatch):
    import connectors.bank.service as bank_service

    db = AsyncMongoMockClient().test
    await db.connector_instances.insert_one({
        "id": "bank_pending",
        "user_id": "alice",
        "connector_id": "banking_psd2",
        "status": "pending",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    monkeypatch.setattr(bank_service, "build_bank_provider", lambda: FakeBankProvider())

    assert await bank_service.agent_bank_status(db, "alice") == "unavailable"


@pytest.mark.asyncio
async def test_bank_permission_is_instance_scoped_and_sandbox_is_declared_simulated(monkeypatch):
    import connectors.bank.service as bank_service

    db = AsyncMongoMockClient().test
    await db.connector_instances.insert_one({
        "id": "bank_1",
        "user_id": "alice",
        "connector_id": "banking_psd2",
        "status": "connected",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    await PermissionService(db).grant(
        user_id="alice",
        capability_id="banking.read",
        connector_id="banking_psd2",
        connector_instance_id="bank_1",
        purpose_id="financial_insight",
        scopes=["accounts:read", "transactions:read"],
    )
    monkeypatch.setattr(bank_service, "build_bank_provider", lambda: FakeBankProvider())

    resolved = await CapabilityResolver(db).resolve("alice", "banking.read")

    assert resolved.permitted is True
    assert resolved.executable is True
    assert resolved.status == "available_simulated"
    assert resolved.is_real is False


@pytest.mark.asyncio
async def test_real_bank_read_is_bounded_and_freshness_comes_from_last_observation(monkeypatch):
    from financial import observed
    import connectors.bank.service as bank_service

    db = AsyncMongoMockClient().test
    old = datetime.now(timezone.utc) - timedelta(days=3)

    async def real_status(_db, _owner):
        return "real"

    async def bank_now(_db, _owner):
        return {
            "stato": "collegato",
            "posso_leggere_adesso": True,
            "ultimo_saldo_osservato": {
                "quanto": "€1.250",
                "tipo": "disponibile",
                "letto_quando": old.isoformat(),
                "banca": "Banca reale",
            },
        }

    async def month(_db, _owner):
        return {
            "entrate_osservate": "€2.000",
            "uscite_osservate": "€900",
            "differenza_parziale": "€1.100",
        }

    async def patterns(_db, _owner):
        return {
            "ricorrenti_in_entrata": [{"quante_volte": 3}],
            "ricorrenti_in_uscita": [{"quante_volte": 4}, {"quante_volte": 2}],
        }

    monkeypatch.setattr(bank_service, "agent_bank_status", real_status)
    monkeypatch.setattr(observed, "the_bank_right_now", bank_now)
    monkeypatch.setattr(observed, "this_month", month)
    monkeypatch.setattr(observed, "what_was_seen", patterns)

    outcome = await providers.read_banking(
        db,
        "alice",
        _goal(),
        step=ActionStep(
            intent="Leggere il quadro bancario",
            step_type="inspect",
            capability_needed="banking.read",
        ),
    )

    assert outcome.status == "succeeded"
    assert outcome.provenance.source_class == "connected_provider"
    assert outcome.provenance.freshness == "stale"
    assert len(outcome.claims) <= 3
    surface = " ".join([outcome.observation, *[c.text for c in outcome.claims]])
    assert "€1.250" in surface
    assert "€2.000" in surface
    assert "estratto conto" in outcome.observation
    assert "conto reale collegato" in outcome.provenance.certainty_note


@pytest.mark.asyncio
async def test_unconnected_bank_is_not_empty_success(monkeypatch):
    import connectors.bank.service as bank_service

    db = AsyncMongoMockClient().test

    async def unavailable(_db, _owner):
        return "unavailable"

    monkeypatch.setattr(bank_service, "agent_bank_status", unavailable)

    outcome = await providers.read_banking(
        db,
        "alice",
        _goal(),
        step=ActionStep(
            intent="Leggere il quadro bancario",
            step_type="inspect",
            capability_needed="banking.read",
        ),
    )

    assert outcome.status == "unavailable"
    assert outcome.error_type == "requires_connection"
    assert outcome.claims == []


@pytest.mark.asyncio
async def test_test_bank_connect_mirrors_read_permission_to_exact_instance():
    from connectors.bank.service import BankReadService

    db = AsyncMongoMockClient().test
    permissions = PermissionService(db)
    service = BankReadService(
        db=db,
        permissions=permissions,
        vault=object(),
        provider=FakeBankProvider(),
    )

    linked = await service.connect(user_id="alice", institution="Banca di prova")
    instance_id = linked["instance_id"]

    assert await permissions.check_access(
        user_id="alice",
        capability_id="banking.read",
        connector_id="banking_psd2",
        connector_instance_id=instance_id,
    ) is True
