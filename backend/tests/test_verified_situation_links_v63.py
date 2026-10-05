import pytest
from mongomock_motor import AsyncMongoMockClient

from places.models import LifePlace
from situations.models import SituationUpdate
from situations.service import SituationService


OWNER = "alice"


@pytest.mark.asyncio
async def test_situation_keeps_only_owned_canonical_place_refs():
    db = AsyncMongoMockClient().test
    await db.life_places.insert_many([
        LifePlace(id="plc_home", user_id=OWNER, label="Casa").model_dump(),
        LifePlace(id="plc_bob", user_id="bob", label="Casa Bob").model_dump(),
    ])

    result = await SituationService(db).apply(
        user_id=OWNER,
        session_id="ces_1",
        reasoning_epoch="epoch_1",
        update=SituationUpdate(
            operation="create",
            summary="I panni sono stesi a Casa.",
            linked_object_refs=[
                "place:plc_home",
                "place:plc_bob",
                "place:missing",
                "not-a-ref",
                "calendar:event_1",
            ],
        ),
    )

    refs = result["situation"]["linked_object_refs"]
    assert refs == ["place:plc_home", "calendar:event_1"]

    stored = await db.situations.find_one(
        {"user_id": OWNER, "id": result["situation"]["id"]},
        {"_id": 0},
    )
    assert stored is not None
    assert stored["linked_object_refs"] == refs
    history_blob = str(stored["history"])
    assert "place:plc_bob" not in history_blob
    assert "place:missing" not in history_blob
    assert "not-a-ref" not in history_blob


@pytest.mark.asyncio
async def test_bad_link_does_not_discard_user_situation_or_existing_valid_link():
    db = AsyncMongoMockClient().test
    await db.life_places.insert_one(
        LifePlace(id="plc_home", user_id=OWNER, label="Casa").model_dump()
    )
    service = SituationService(db)

    created = await service.apply(
        user_id=OWNER,
        session_id="ces_1",
        reasoning_epoch="epoch_create",
        update=SituationUpdate(
            operation="create",
            summary="Sto aspettando che asciughi.",
            linked_object_refs=["place:plc_home"],
        ),
    )
    sid = created["situation"]["id"]

    updated = await service.apply(
        user_id=OWNER,
        session_id="ces_1",
        reasoning_epoch="epoch_update",
        update=SituationUpdate(
            operation="update",
            situation_id=sid,
            expected_revision=1,
            facts=["Il bucato è ancora fuori."],
            linked_object_refs=["place:foreign_or_missing"],
        ),
    )

    assert updated["status"] == "success"
    assert updated["situation"]["revision"] == 2
    assert updated["situation"]["linked_object_refs"] == ["place:plc_home"]
    assert "Il bucato è ancora fuori." in updated["situation"]["facts"]


@pytest.mark.asyncio
async def test_dismissed_place_cannot_be_newly_linked():
    db = AsyncMongoMockClient().test
    dismissed = LifePlace(id="plc_old", user_id=OWNER, label="Vecchia casa")
    doc = dismissed.model_dump()
    doc["state"] = "dismissed"
    await db.life_places.insert_one(doc)

    result = await SituationService(db).apply(
        user_id=OWNER,
        session_id="ces_1",
        reasoning_epoch="epoch_1",
        update=SituationUpdate(
            operation="create",
            summary="Situazione valida anche se il link proposto non lo è.",
            linked_object_refs=["place:plc_old"],
        ),
    )

    assert result["status"] == "success"
    assert result["situation"]["linked_object_refs"] == []
