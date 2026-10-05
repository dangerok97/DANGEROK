import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.capabilities import CapabilityResolver, is_really_wired
from agent.models import ActionStep, AutonomousGoal
from agent import providers
from contacts.service import (
    device_contacts_state,
    revoke_device_contacts,
    sync_device_contacts,
)
from preparation.contacts import AddressBook


def _goal():
    return AutonomousGoal(
        owner_id="alice",
        status="active",
        objective="Trovare il contatto corretto",
        desired_outcome="Sapere se il contatto esiste in rubrica",
    )


def _step(who="Asia"):
    return ActionStep(
        intent="Cercare il contatto nella rubrica",
        step_type="inspect",
        capability_needed="contacts.read",
        parameters={"who": who} if who else {},
        expected_result="Contatto verificato",
    )


@pytest.mark.asyncio
async def test_device_contacts_sync_persists_only_minimal_fields_and_grants_capability():
    db = AsyncMongoMockClient().test

    result = await sync_device_contacts(
        db,
        "alice",
        contacts=[{
            "id": "ios-1",
            "name": "Asia Rossi",
            "organization": "",
            "aliases": ["Asia"],
            "phones": ["+39 327 1234567", "+39 327 1234567"],
            "emails": ["private@example.test"],
            "address": "Via che non deve essere salvata",
            "birthday": "2000-01-01",
            "notes": "dato non necessario",
        }],
    )

    assert result["status"] == "connected"
    assert result["contact_count"] == 1

    row = await db.contacts.find_one({"user_id": "alice"}, {"_id": 0})
    assert row["name"] == "Asia Rossi"
    assert row["aliases"] == ["Asia"]
    assert row["phone"] == "+393271234567"
    assert row["phones"] == ["+393271234567"]
    assert "emails" not in row
    assert "address" not in row
    assert "birthday" not in row
    assert "notes" not in row

    state = await device_contacts_state(db, "alice")
    assert state["status"] == "connected"
    assert state["contact_count"] == 1

    resolution = await CapabilityResolver(db).resolve("alice", "contacts.read")
    assert resolution.permitted is True
    assert resolution.executable is True
    assert resolution.status == "available_real"
    assert is_really_wired("contacts.read") is True


@pytest.mark.asyncio
async def test_address_book_resolver_reuses_synced_contacts():
    db = AsyncMongoMockClient().test
    await sync_device_contacts(
        db,
        "alice",
        contacts=[{
            "id": "ios-1",
            "name": "Asia Rossi",
            "aliases": ["la mia ragazza"],
            "phones": ["3271234567"],
            "kind": "person",
        }],
    )

    rows = await AddressBook().look_for(
        db, owner_id="alice", who="la mia ragazza"
    )

    assert len(rows) == 1
    assert rows[0].name == "Asia Rossi"
    assert rows[0].number == "+393271234567"
    assert rows[0].source == "address_book"


@pytest.mark.asyncio
async def test_agent_contact_read_requires_specific_query_and_never_persists_number():
    db = AsyncMongoMockClient().test
    await sync_device_contacts(
        db,
        "alice",
        contacts=[{
            "id": "ios-1",
            "name": "Asia Rossi",
            "aliases": ["Asia"],
            "phones": ["+39 327 1234567"],
        }],
    )

    missing = await providers.read_contacts(
        db, "alice", _goal(), step=_step("")
    )
    assert missing.status == "unavailable"
    assert missing.error_type == "contact_query_required"

    outcome = await providers.read_contacts(
        db, "alice", _goal(), step=_step("Asia")
    )
    assert outcome.status == "succeeded"
    assert outcome.provenance.capability == "contacts.read"
    assert outcome.provenance.provider == "device_contacts_cache"
    assert outcome.provenance.source_refs
    surface = " ".join([
        outcome.observation,
        *[claim.text for claim in outcome.claims],
        *outcome.provenance.source_refs,
        outcome.data_ref,
    ])
    assert "Asia Rossi" in surface
    assert "+393271234567" not in surface
    assert "3271234567" not in surface
    assert "recapito telefonico disponibile" in surface


@pytest.mark.asyncio
async def test_contacts_revocation_clears_cache_and_permission():
    db = AsyncMongoMockClient().test
    await sync_device_contacts(
        db,
        "alice",
        contacts=[{
            "id": "ios-1",
            "name": "Asia Rossi",
            "phones": ["3271234567"],
        }],
    )
    assert await db.contacts.count_documents({"user_id": "alice"}) == 1

    result = await revoke_device_contacts(db, "alice")

    assert result["status"] == "disconnected"
    assert await db.contacts.count_documents({"user_id": "alice"}) == 0
    state = await device_contacts_state(db, "alice")
    assert state["status"] == "disconnected"
    resolution = await CapabilityResolver(db).resolve("alice", "contacts.read")
    assert resolution.permitted is False


def test_contacts_step_shows_only_lookup_query_to_agent():
    shown = _step("Asia").for_ai()
    assert shown["execution_parameters"] == {"who": "Asia"}


@pytest.mark.asyncio
async def test_contact_snapshot_cleanup_happens_only_after_new_rows_exist(monkeypatch):
    db = AsyncMongoMockClient().test
    await sync_device_contacts(
        db,
        "alice",
        contacts=[{
            "id": "ios-old",
            "name": "Vecchio Contatto",
            "phones": ["3270000001"],
        }],
    )
    old = await db.contacts.find_one({"user_id": "alice"}, {"_id": 0})
    assert old is not None

    original_update = db.contacts.update_one
    calls = 0

    async def interrupted(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("device sync interrupted")
        return await original_update(*args, **kwargs)

    monkeypatch.setattr(db.contacts, "update_one", interrupted)

    with pytest.raises(RuntimeError):
        await sync_device_contacts(
            db,
            "alice",
            contacts=[
                {"id": "ios-new-1", "name": "Nuovo Uno", "phones": ["3270000002"]},
                {"id": "ios-new-2", "name": "Nuovo Due", "phones": ["3270000003"]},
            ],
        )

    # The old snapshot is still present because stale cleanup is the final
    # operation, after all rows in the replacement snapshot have been written.
    assert await db.contacts.find_one(
        {"user_id": "alice", "id": old["id"]}, {"_id": 0}
    ) is not None
