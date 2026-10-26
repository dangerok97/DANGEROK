"""The outcome of a call the person asked for reaches the phone, not only the chat."""
import pytest
from mongomock_motor import AsyncMongoMockClient

from telephone.chat_report import notify_the_result

UID = "usr_call_push_v1"


def _call(**change):
    from telephone.models import Mandate, PhoneCall

    fields = dict(id="tel_push", owner_id=UID, to_number="+393330000042", calling_whom="Giulia Test",
                  mandate=Mandate(why_calling="consegnare un messaggio", message="la amo",
                                  recipient="Giulia Test"),
                  state="failed")
    fields.update(change)
    return PhoneCall(**fields)


@pytest.mark.asyncio
async def test_a_finished_call_is_announced_once_by_code(monkeypatch):
    import telephone.service as service
    from memos import one_shot

    db = AsyncMongoMockClient().call_push_v1
    call = _call()

    async def get(self, owner, cid):
        return call

    monkeypatch.setattr(service.TelephoneService, "get", get)
    import telephone.chat_report as report
    monkeypatch.setattr(report, "what_to_tell_the_chat", lambda c: "Non sono riuscita a parlare con Giulia: non ha risposto.")
    assert await notify_the_result(db, call) is True
    assert await notify_the_result(db, call) is False
    row = await db.reminders.find_one({})
    assert row["origin"] == "phone_call_result" and "Giulia" in row["title"]
    out = await one_shot.fire_due(db)
    assert out["raised"] == 1
    opp = await db.opportunities.find_one({})
    assert opp["evidence"][0]["kind"] == "phone_call"
    from opportunities.models import Opportunity
    decision = one_shot.push_decision(Opportunity(**opp))
    assert decision["copy"]["public_title"] == "Telefonata conclusa"
    assert "Giulia" not in decision["copy"]["public_body"]


@pytest.mark.asyncio
async def test_a_call_still_running_announces_nothing(monkeypatch):
    import telephone.chat_report as report
    import telephone.service as service

    db = AsyncMongoMockClient().call_push_running_v1
    call = _call(state="talking")

    async def get(self, owner, cid):
        return call

    monkeypatch.setattr(service.TelephoneService, "get", get)
    monkeypatch.setattr(report, "what_to_tell_the_chat", lambda c: None)
    assert await notify_the_result(db, call) is False
    assert await db.reminders.count_documents({}) == 0


@pytest.mark.asyncio
async def test_call_results_are_not_shown_as_things_to_do_in_home():
    from home.adapters.reminders import load_reminders

    db = AsyncMongoMockClient().call_push_home_v1
    await db.reminders.insert_many([
        {"id": "rem_call_x", "user_id": UID, "status": "open", "origin": "phone_call_result", "title": "Esito"},
        {"id": "rem_y", "user_id": UID, "status": "open", "title": "Comprare il pane"},
    ])
    items, _ = await load_reminders(db, UID)
    assert [i.title for i in items] == ["Comprare il pane"]


def test_the_end_of_a_call_notifies():
    import inspect
    from telephone import vonage_router

    assert "notify_the_result(db, call)" in inspect.getsource(vonage_router._apply_what_was_agreed)
