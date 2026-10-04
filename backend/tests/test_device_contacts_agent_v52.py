from unittest.mock import AsyncMock, patch

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent import providers
from agent.models import ActionStep, AutonomousGoal
from contacts.service import DeviceContactsService


def _goal():
    return AutonomousGoal(
        owner_id="alice",
        status="active",
        objective="Trovare il contatto giusto",
        desired_outcome="Sapere se il contatto richiesto è disponibile",
    )


def _step(query="Asia"):
    return ActionStep(
        intent="Cercare Asia nella rubrica",
        step_type="inspect",
        capability_needed="contacts.read",
        parameters={"contact_query": query} if query else {},
        expected_result="Il contatto richiesto è identificato",
    )


@pytest.mark.asyncio
async def test_device_contact_sync_stores_only_minimal_callable_index():
    db = AsyncMongoMockClient().test
    service = DeviceContactsService(db)

    with patch.object(service, "_grant", AsyncMock()):
        result = await service.sync_snapshot(
            "alice",
            permission="granted",
            contacts=[{
                "device_contact_id": "CNContact-very-private-native-id",
                "name": "Asia Rossi",
                "organization": "",
                "aliases": ["Asia", "la mia ragazza"],
                "phones": [
                    {"number": "+39 327 1234567"},
                    {"number": "+39 327 1234567"},
                ],
                "emails": ["asia@example.test"],
                "addresses": ["Via segreta 1"],
                "notes": "non deve arrivare sul server",
                "birthday": "2000-01-01",
            }],
        )

    assert result["stored"] == 1
    row = await db.contacts.find_one({"user_id": "alice"}, {"_id": 0})
    assert row["name"] == "Asia Rossi"
    assert row["aliases"] == ["Asia", "la mia ragazza"]
    assert row["phones"] == ["+393271234567"]
    assert row["phone"] == "+393271234567"
    assert row["id"].startswith("contact_")

    serialized = str(row)
    assert "CNContact-very-private-native-id" not in serialized
    assert "asia@example.test" not in serialized
    assert "Via segreta" not in serialized
    assert "non deve arrivare" not in serialized
    assert "2000-01-01" not in serialized


@pytest.mark.asyncio
async def test_contact_snapshot_is_owner_scoped_and_replaces_removed_rows():
    db = AsyncMongoMockClient().test
    service = DeviceContactsService(db)
    with patch.object(service, "_grant", AsyncMock()):
        await service.sync_snapshot(
            "alice", permission="granted",
            contacts=[
                {"device_contact_id": "a", "name": "Asia", "phones": ["3271234567"]},
                {"device_contact_id": "b", "name": "Luca", "phones": ["3331234567"]},
            ],
        )
        await service.sync_snapshot(
            "bob", permission="granted",
            contacts=[
                {"device_contact_id": "x", "name": "Bob Contact", "phones": ["3341234567"]},
            ],
        )
        await service.sync_snapshot(
            "alice", permission="granted",
            contacts=[
                {"device_contact_id": "a", "name": "Asia", "phones": ["3271234567"]},
            ],
        )

    assert await db.contacts.count_documents({"user_id": "alice"}) == 1
    assert await db.contacts.count_documents({"user_id": "bob"}) == 1
    assert await db.contacts.count_documents({"user_id": "alice", "name": "Luca"}) == 0


@pytest.mark.asyncio
async def test_revoking_contacts_permission_deletes_server_index():
    db = AsyncMongoMockClient().test
    service = DeviceContactsService(db)
    await db.contacts.insert_one({
        "id": "contact_a", "user_id": "alice", "name": "Asia",
        "phone": "+393271234567",
    })

    revoke = AsyncMock()
    fake = type("Permissions", (), {"revoke": revoke})
    with patch("permissions.service.PermissionService", return_value=fake()):
        result = await service.sync_snapshot(
            "alice", permission="denied", contacts=[]
        )

    assert result["deleted"] is True
    assert await db.contacts.count_documents({"user_id": "alice"}) == 0
    revoke.assert_awaited_once()
    assert revoke.await_args.kwargs["capability_id"] == "contacts.read"
    assert revoke.await_args.kwargs["connector_id"] == "contacts_device"


@pytest.mark.asyncio
async def test_agent_contact_read_is_named_and_never_persists_phone_number():
    db = AsyncMongoMockClient().test
    await db.contacts.insert_one({
        "id": "contact_asia",
        "user_id": "alice",
        "name": "Asia Rossi",
        "organization": "",
        "aliases": ["Asia", "la mia ragazza"],
        "relationship": "compagna",
        "phones": ["+393271234567"],
        "phone": "+393271234567",
        "kind": "person",
    })

    check = AsyncMock(return_value=True)
    fake = type("Permissions", (), {"check_access": check})
    with patch("permissions.service.PermissionService", return_value=fake()):
        outcome = await providers.read_contacts(
            db, "alice", _goal(), step=_step("Asia")
        )

    assert outcome.status == "succeeded"
    assert outcome.provenance.capability == "contacts.read"
    assert outcome.provenance.provider == "device_address_book"
    assert len(outcome.claims) == 1
    durable = outcome.observation + " ".join(c.text for c in outcome.claims)
    assert "Asia Rossi" in durable
    assert "recapito telefonico disponibile" in durable
    assert "+393271234567" not in durable
    assert "3271234567" not in durable


@pytest.mark.asyncio
async def test_agent_never_lists_address_book_without_contact_query():
    db = AsyncMongoMockClient().test
    outcome = await providers.read_contacts(
        db, "alice", _goal(), step=_step("")
    )
    assert outcome.status == "unavailable"
    assert outcome.error_type == "contact_query_required"


def test_contacts_read_is_real_agent_capability():
    from agent.capabilities import is_really_wired
    assert is_really_wired("contacts.read") is True
