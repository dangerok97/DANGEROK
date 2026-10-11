"""Calendar deletion stays on the selected event's owner/account/calendar.

Real normalization, persistence, consent, authority and API; only Google is a
local recording fake. No OAuth credentials, provider network or real accounts.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from home.calendar_event import delete_event
from ingestion.reading import plain
from permissions.service import PermissionService
from test_calendar_home_month_consistency_v157 import connect, ingest, mirror, tomorrow
from test_ora_native_calendar_v155 import isolated_calendar  # noqa: F401


class RecordingCalendar:
    def __init__(self):
        self.provider = self
        self.calls = []

    async def _get_access_token(self, *, user_id, instance):
        self.calls.append(("token", user_id, instance["id"]))
        return instance["id"]  # synthetic handle, never an OAuth credential

    async def delete_event(self, *, access_token, calendar_id, event_id):
        self.calls.append(("delete", access_token, calendar_id, event_id))

    async def get_event(self, *, access_token, calendar_id, event_id):
        self.calls.append(("read", access_token, calendar_id, event_id))
        return {"id": event_id, "status": "cancelled"}


@pytest.fixture
def provider(monkeypatch):
    import deps

    fake = RecordingCalendar()
    monkeypatch.setattr(deps, "get_google_calendar_service", lambda: fake)
    return fake


async def allow(db, uid, iid):
    await PermissionService(db).grant(
        user_id=uid, capability_id="calendar.write", connector_id="calendar_google",
        connector_instance_id=iid,
    )


async def add_event(db, uid, iid, calendar, *, suffix="", external_id="same_event"):
    when = tomorrow()
    row = await ingest(db, uid, iid, external_id, "Impegno di prova", when, calendar=calendar)
    node = mirror(uid, "node_" + suffix, iid, external_id, "Impegno di prova", when, calendar=calendar)
    draft = {
        "id": "draft_" + suffix, "user_id": uid, "title": "Impegno di prova",
        "connector_instance_id": iid, "google_event_id": external_id,
        "google_calendar_id": calendar, "status": "confirmed",
        "start_datetime": when.isoformat(),
    }
    await db.life_nodes.insert_one(node)
    await db.calendar_event_drafts.insert_one(draft)
    return row, node, draft


async def assert_states(db, event, *, cancelled=False):
    row, node, draft = event
    saved = await db.ingestion_events.find_one({"id": row["id"]})
    assert plain(saved["normalized_payload"])["status"] == ("cancelled" if cancelled else "confirmed")
    saved_node = await db.life_nodes.find_one({"id": node["id"]})
    assert saved_node["status"] == ("archived" if cancelled else "active")
    saved_draft = await db.calendar_event_drafts.find_one({"id": draft["id"]})
    assert saved_draft["status"] == ("cancelled" if cancelled else "confirmed")


@pytest.mark.asyncio
@pytest.mark.parametrize("separate_accounts", [True, False])
async def test_delete_and_receipt_are_bound_to_owner_account_and_calendar(
    isolated_calendar, provider, separate_accounts,
):
    db, identity, app = isolated_calendar
    uid = identity["user_id"]
    first_iid, second_iid = ("a", "b") if separate_accounts else ("a", "a")
    first_cal, second_cal = ("primary", "primary") if separate_accounts else ("work", "personal")
    await connect(db, uid, first_iid, calendars=[first_cal, second_cal])
    await allow(db, uid, first_iid)
    if separate_accounts:
        await connect(db, uid, second_iid, calendars=[second_cal])
        await allow(db, uid, second_iid)
    first = await add_event(db, uid, first_iid, first_cal, suffix="first")
    second = await add_event(db, uid, second_iid, second_cal, suffix="second")
    foreign = await add_event(db, "owner_b", second_iid, second_cal, suffix="foreign")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        result = await http.post("/api/calendar/events/" + second[0]["id"] + "/delete",
                                 json={"confirmed_title": "Impegno di prova"})
        assert result.status_code == 200, result.text
        assert result.json()["verified"] is True
        assert provider.calls == [
            ("token", uid, second_iid), ("delete", second_iid, second_cal, "same_event"),
            ("token", uid, second_iid), ("read", second_iid, second_cal, "same_event"),
        ]
        await assert_states(db, second, cancelled=True)
        await assert_states(db, first)
        await assert_states(db, foreign)

        # Repeating one deletion is idempotent; the identically named event
        # on the other target must still execute as a distinct commanded act.
        repeated = await http.post("/api/calendar/events/" + second[0]["id"] + "/delete",
                                   json={"confirmed_title": "Impegno di prova"})
        assert repeated.status_code == 200
        assert len(provider.calls) == 4
        result = await http.post("/api/calendar/events/" + first[0]["id"] + "/delete",
                                 json={"confirmed_title": "Impegno di prova"})
        assert result.status_code == 200, result.text
        assert result.json()["operation"] == "deleted"
        assert provider.calls[-3] == ("delete", first_iid, first_cal, "same_event")
        await assert_states(db, first, cancelled=True)
        await assert_states(db, foreign)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [
    "revoked", "unavailable", "foreign_instance", "missing_instance",
    "deselected", "missing_calendar", "detached", "consent_revoked",
])
async def test_invalid_or_revoked_target_never_falls_back_to_other_connected_account(
    isolated_calendar, provider, invalid,
):
    db, identity, app = isolated_calendar
    uid = identity["user_id"]
    await connect(db, uid, "healthy")
    await allow(db, uid, "healthy")
    await connect(db, "owner_b" if invalid == "foreign_instance" else uid, "target")
    await allow(db, uid, "target")
    event = await add_event(db, uid, "target", "primary", suffix="target")
    if invalid in {"revoked", "unavailable"}:
        await db.connector_instances.update_one({"id": "target"}, {"$set": {"status": invalid}})
    elif invalid == "missing_instance":
        await db.connector_instances.delete_one({"id": "target"})
    elif invalid == "deselected":
        await db.connector_instances.update_one({"id": "target"}, {"$set": {"selected_resource_ids": ["other"]}})
    elif invalid == "missing_calendar":
        await db.ingestion_events.update_one({"id": event[0]["id"]}, {"$unset": {
            "normalized_payload.calendar_id": "", "raw_reference.calendar_id": "",
        }})
    elif invalid == "detached":
        await db.ingestion_events.update_one({"id": event[0]["id"]}, {"$set": {"source_status": "detached"}})
    elif invalid == "consent_revoked":
        await PermissionService(db).revoke(
            user_id=uid, capability_id="calendar.write", connector_id="calendar_google",
            connector_instance_id="target",
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        result = await http.post("/api/calendar/events/" + event[0]["id"] + "/delete",
                                 json={"confirmed_title": "Impegno di prova"})
    assert result.status_code == 409, result.text
    assert provider.calls == []
    await assert_states(db, event)


@pytest.mark.asyncio
async def test_bare_external_id_and_unbound_legacy_event_fail_closed_with_two_accounts(
    isolated_calendar, provider,
):
    db, identity, app = isolated_calendar
    uid = identity["user_id"]
    await connect(db, uid, "a")
    await connect(db, uid, "b")
    await allow(db, uid, "a")
    await allow(db, uid, "b")
    first = await add_event(db, uid, "a", "primary", suffix="a")
    second = await add_event(db, uid, "b", "primary", suffix="b")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        result = await http.post("/api/calendar/events/same_event/delete", json={"confirmed_title": "Impegno di prova"})
        assert result.status_code == 404
        await db.ingestion_events.update_one({"id": second[0]["id"]}, {"$unset": {"connector_instance_id": ""}})
        # A revoked account is still a possible historical owner of an unbound row.
        await db.connector_instances.update_one({"id": "b"}, {"$set": {"status": "revoked"}})
        result = await http.post("/api/calendar/events/" + second[0]["id"] + "/delete",
                                 json={"confirmed_title": "Impegno di prova"})
        assert result.status_code == 409
        assert result.json()["detail"] == "ambiguous_calendar_target"
        detail = await http.get("/api/calendar/events/" + second[0]["id"])
        assert detail.json()["can_be_changed"] is False
    assert provider.calls == []
    await assert_states(db, first)
    await assert_states(db, second)


@pytest.mark.asyncio
async def test_primary_alias_and_single_account_legacy_draft_keep_the_exact_target(
    isolated_calendar, provider,
):
    db, identity, app = isolated_calendar
    uid = identity["user_id"]
    account = "calendar-owner@example.test"
    await connect(db, uid, "a", calendars=[account])
    await db.connector_instances.update_one({"id": "a"}, {"$set": {"metadata.account_email": account}})
    await allow(db, uid, "a")
    event = await add_event(db, uid, "a", "primary", suffix="legacy")
    await db.calendar_event_drafts.update_one({"id": event[2]["id"]}, {"$unset": {"connector_instance_id": ""}})
    result = await delete_event(db, uid, event[2]["id"], confirmed_title="Impegno di prova")
    assert result["ok"] and result["verified"], result
    assert provider.calls[1] == ("delete", "a", account, "same_event")
    assert provider.calls[-1] == ("read", "a", account, "same_event")
    await assert_states(db, event, cancelled=True)


@pytest.mark.asyncio
async def test_connection_revoked_after_authority_is_checked_again_before_provider(
    isolated_calendar, provider, monkeypatch,
):
    from agent import commanded

    db, identity, app = isolated_calendar
    uid = identity["user_id"]
    await connect(db, uid, "a")
    await allow(db, uid, "a")
    event = await add_event(db, uid, "a", "primary", suffix="race")
    real_begin = commanded.begin

    async def revoke_after_begin(db_, act):
        result = await real_begin(db_, act)
        await db_.connector_instances.update_one({"id": "a"}, {"$set": {"status": "revoked"}})
        return result

    monkeypatch.setattr(commanded, "begin", revoke_after_begin)
    result = await delete_event(db, uid, event[0]["id"], confirmed_title="Impegno di prova")
    assert result["ok"] is False
    assert result["reason"] == "calendar_not_connected"
    assert provider.calls == []
    await assert_states(db, event)
