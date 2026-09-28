"""Home HTTP -> agenda -> AI capability -> HTTP read-back, without provider calls.

Run: PYTHONPATH=backend python -m unittest discover -s backend/tests -p test_home_calendar_lifecycle.py -v
Default database is mongomock-motor; QA_MONGO_URL opts into a disposable real DB.
No LLM answers or Google delivery are simulated by these assertions.
"""
import asyncio
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27018")
os.environ.setdefault("DB_NAME", "ora_calendar_test")
os.environ.setdefault("JWT_SECRET", "isolated-calendar-tests-only")

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from routers import calendar_events as routes
from home.manual_event import home_event_times, update_manual_event
from conversation_engine.ai_core.tools import calendar_caps as caps
from agenda.service import AgendaService


class HomeCalendarLifecycle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if os.getenv("QA_MONGO_URL"):
            from motor.motor_asyncio import AsyncIOMotorClient
            self.mongo = AsyncIOMotorClient(os.environ["QA_MONGO_URL"])
        else:
            from mongomock_motor import AsyncMongoMockClient
            self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["ora_calendar_qa_" + uuid.uuid4().hex]
        self.db_patch = patch("mongo.database", return_value=self.db)
        self.db_patch.start()
        self.user = "calendar-qa-owner"
        self.app = FastAPI()
        self.app.include_router(routes.router, prefix="/api")
        self.app.dependency_overrides[routes.get_current_user] = lambda: {"user_id": self.user}
        self.http = AsyncClient(transport=ASGITransport(app=self.app), base_url="http://test")
        self.day = (datetime.now(ZoneInfo("Europe/Rome")) + timedelta(days=2)).date().isoformat()
        self.body = {"title": "Visita di prova", "day": self.day, "time": "10:15",
                     "duration_minutes": 45, "location": "Studio di prova", "description": "Portare il promemoria",
                     "timezone": "Europe/Rome", "request_id": "test-request-001"}

    async def asyncTearDown(self):
        await self.http.aclose()
        self.db_patch.stop()
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    async def create(self, **changes):
        response = await self.http.post("/api/calendar/events/home", json={**self.body, **changes})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_http_create_read_day_month_detail_and_ambient_signal(self):
        event = await self.create()
        day = await self.http.get("/api/calendar/events/home/day", params={"day": self.day})
        self.assertEqual([e["id"] for e in day.json()], [event["id"]])
        detail = (await self.http.get("/api/calendar/events/" + event["id"])).json()
        self.assertTrue(detail["is_local"])
        self.assertEqual(detail["provider"], "ORA")
        self.assertEqual(detail["location"], self.body["location"])
        self.assertEqual(detail["description"], self.body["description"])
        month = await self.http.get("/api/calendar/events/home/month", params={"month": self.day[:7]})
        self.assertIn(self.day[-2:], month.json())
        agenda = await AgendaService(self.db).days_ahead(self.user, days=7)
        listed = [e for d in agenda["days"] for e in d["events"]]
        self.assertEqual([e["id"] for e in listed], [event["id"]])
        self.assertEqual(listed[0]["time_label"], "10:15 — 11:00")
        self.assertEqual(await self.db.meaningful_changes.count_documents({"owner_id": self.user}), 1)
        self.assertEqual(await self.db.ambient_wakes.count_documents({"owner_id": self.user}), 1)

    async def test_parallel_retry_is_single_event_and_changed_request_is_rejected(self):
        copies = await asyncio.gather(*(self.create() for _ in range(8)))
        self.assertEqual(len({e["id"] for e in copies}), 1)
        self.assertEqual(await self.db.life_nodes.count_documents({}), 1)
        bad = await self.http.post("/api/calendar/events/home", json={**self.body, "time": "11:15"})
        self.assertEqual(bad.status_code, 409)
        self.assertEqual(await self.db.life_nodes.count_documents({}), 1)

    async def test_other_owner_cannot_read_update_or_delete(self):
        event = await self.create()
        self.user = "different-owner"
        self.assertEqual((await self.http.get("/api/calendar/events/" + event["id"])).status_code, 404)
        update = await self.http.patch("/api/calendar/events/" + event["id"], json={**self.body, "expected_updated_at": event["updated_at"]})
        self.assertEqual(update.status_code, 404)
        self.assertEqual((await self.http.post("/api/calendar/events/" + event["id"] + "/delete", json={"confirmed_title": event["title"]})).status_code, 404)
        rows = (await self.http.get("/api/calendar/events/home/day", params={"day": self.day})).json()
        self.assertEqual(rows, [])
        # Same request key belongs to the new owner, never to the old one.
        other = await self.create()
        self.assertNotEqual(other["id"], event["id"])

    async def test_edit_retry_keeps_identity_and_stale_edit_cannot_overwrite(self):
        event = await self.create()
        body = {**self.body, "time": "14:30", "duration_minutes": 90, "expected_updated_at": event["updated_at"]}
        first = await self.http.patch("/api/calendar/events/" + event["id"], json=body)
        self.assertEqual(first.status_code, 200, first.text)
        again = await self.http.patch("/api/calendar/events/" + event["id"], json=body)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(first.json()["id"], event["id"])
        self.assertEqual(first.json()["updated_at"], again.json()["updated_at"])
        stale = await self.http.patch("/api/calendar/events/" + event["id"], json={**body, "time": "15:00"})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(await self.db.life_nodes.count_documents({}), 1)

    async def test_chat_reads_resolves_moves_and_deletes_the_home_event(self):
        event = await self.create()
        read = await caps.get_calendar_events({"time_min": self.day + "T00:00:00+02:00", "time_max": self.day + "T23:59:59+02:00"}, {"db": self.db, "user_id": self.user})
        self.assertEqual(read.status, "ok", read.payload)
        self.assertEqual(read.payload["events"][0]["location"], self.body["location"])
        self.assertEqual(read.payload["events"][0]["description"], self.body["description"])
        self.assertEqual(read.payload["events"][0]["source"], "ora_local")
        match = await caps._named_calendar_ref_resolution(self.db, self.user, event["title"])
        self.assertEqual(match["status"], "ok")
        ref = match["match"]["calendar_ref"]
        spoken = "Sposta Visita di prova alle 15"
        new_start, _ = home_event_times(self.day, "15:00", "Europe/Rome")
        moved = await caps.update_calendar_event({"calendar_ref": ref, "start_datetime": new_start,
            "end_datetime": self.day + "T17:00:00+02:00",
            "user_authority": {"requested_by_user": True, "user_words": spoken, "what_they_asked_for": spoken}},
            {"db": self.db, "user_id": self.user, "user_message": spoken})
        self.assertEqual(moved.status, "ok", moved.payload)
        self.assertTrue(moved.payload["verified"])
        detail = (await self.http.get("/api/calendar/events/" + event["id"])).json()
        self.assertEqual(detail["starts_at"], new_start)
        self.assertEqual(datetime.fromisoformat(detail["ends_at"]) - datetime.fromisoformat(detail["starts_at"]), timedelta(minutes=45))
        self.assertEqual(await self.db.calendar_event_drafts.count_documents({}), 0)
        self.assertEqual(await self.db.life_nodes.count_documents({}), 1)
        removed = await caps.cancel_calendar_event({"calendar_ref": ref}, {"db": self.db, "user_id": self.user, "user_message": "sì", "pending_act": {"kind": "delete"}})
        self.assertTrue(removed.payload.get("verified"), removed.payload)
        day = (await self.http.get("/api/calendar/events/home/day", params={"day": self.day})).json()
        self.assertEqual(day, [])
        self.assertFalse((await self.http.get("/api/calendar/events/" + event["id"])).json()["can_be_changed"])
        replay = await self.http.post("/api/calendar/events/home", json=self.body)
        self.assertEqual(replay.status_code, 409)

    async def test_chat_does_not_move_without_authority_or_to_another_title(self):
        event = await self.create()
        args = {"calendar_ref": "calendar:" + event["id"], "start_datetime": self.day + "T14:00:00+02:00"}
        result = await caps.update_calendar_event(args, {"db": self.db, "user_id": self.user, "user_message": "Che impegni ho?"})
        self.assertNotEqual(result.status, "ok", result.payload)
        result = await caps.update_calendar_event(args, {"db": self.db, "user_id": self.user, "user_message": "Sposta la cena alle 14"})
        self.assertEqual(result.payload["failure_kind"], "target_not_grounded")
        detail = (await self.http.get("/api/calendar/events/" + event["id"])).json()
        self.assertEqual(detail["starts_at"], event["starts_at"])

    async def test_same_titles_are_ambiguous_and_create_guard_sees_home_events(self):
        first = await self.create()
        duplicate = await caps._already_have_one(self.db, self.user, title=first["title"], start=first["starts_at"])
        self.assertEqual(duplicate["id"], first["id"])
        self.assertTrue(duplicate["_starts_at_the_same_time"])
        await self.create(request_id="test-request-002", time="13:00")
        match = await caps._named_calendar_ref_resolution(self.db, self.user, first["title"])
        self.assertEqual(match["status"], "ambiguous")

    async def test_boundary_days_use_viewer_timezone_and_agenda_local_time(self):
        event = await self.create(time="00:30", timezone="Europe/Rome")
        previous = (datetime.fromisoformat(self.day) - timedelta(days=1)).date().isoformat()
        utc_day = await self.http.get("/api/calendar/events/home/day", params={"day": previous, "timezone": "UTC"})
        self.assertEqual([e["id"] for e in utc_day.json()], [event["id"]])
        at = datetime.fromisoformat(event["starts_at"]).astimezone(timezone.utc)
        await self.db.life_nodes.update_one({"id": event["id"]}, {"$set": {"attributes.starts_at": at.isoformat()}})
        agenda = await AgendaService(self.db).days_ahead(self.user, days=7)
        target = next(d for d in agenda["days"] if d["date"] == self.day)
        self.assertEqual(target["events"][0]["time_label"], "00:30 — 01:15")

    async def test_invalid_time_dst_gap_and_wrong_offset_are_rejected(self):
        for changes in ({"day": "2026-02-30"}, {"time": "25:00"}, {"duration_minutes": 0},
                        {"day": "2027-03-28", "time": "02:30"}, {"title": "   "}, {"timezone": "Imaginary/Zone"}):
            result = await self.http.post("/api/calendar/events/home", json={**self.body, **changes})
            self.assertEqual(result.status_code, 422, result.text)
        event = await self.create()
        with self.assertRaises(ValueError):
            await update_manual_event(self.db, self.user, event["id"], {"start_datetime": "2027-03-28T02:30:00"})
        with self.assertRaises(ValueError):
            await update_manual_event(self.db, self.user, event["id"], {"start_datetime": self.day + "T10:15:00-04:00"})

    async def test_preloaded_calendar_keeps_notes_and_computed_weekday(self):
        from conversation_engine.ai_core.calendar_ahead import _one_each, the_next_two_days
        event = await self.create(day="2026-09-30")
        result = await caps.get_calendar_events({"time_min": "2026-09-30T00:00:00+02:00", "time_max": "2026-10-01T00:00:00+02:00"}, {"db": self.db, "user_id": self.user})
        compact = _one_each(result.payload["events"])
        self.assertEqual(compact[0]["description"], self.body["description"])
        self.assertEqual(compact[0]["day_label"], "mercoledì 30 settembre 2026")
        with patch("conversation_engine.ai_core.calendar_ahead.datetime") as clock:
            clock.now.return_value = datetime(2026, 9, 29, tzinfo=timezone.utc)
            ahead = await the_next_two_days(self.db, self.user)
        self.assertEqual(ahead["events"][0]["description"], self.body["description"])
        self.assertEqual(ahead["events"][0]["calendar_ref"], "calendar:" + event["id"])

    async def test_plain_yes_replays_prepared_cancel_without_another_model_call(self):
        from conversation_engine.models import ConversationSession
        from conversation_engine.ai_core.loop import run_cognitive_loop
        event = await self.create()
        sess = ConversationSession(user_id=self.user)
        async def choose_cancel(system, user):
            return {"response_mode": "tool", "confidence": 1.0, "tool_call": {
                "capability": "cancel_calendar_event", "arguments": {"calendar_ref": "calendar:" + event["id"]}}}
        proposal = await run_cognitive_loop(sess=sess, user_message="Elimina Visita di prova", db=self.db, decision_fn=choose_cancel)
        self.assertEqual(proposal.mode, "act", proposal.ora_text)
        self.assertIn(event["title"], proposal.ora_text)
        self.assertEqual(await self.db.life_nodes.count_documents({"status": "active"}), 1)
        async def must_not_generate(system, user):
            raise AssertionError("A plain approval must resume the existing action, not ask the AI to select again")
        result = await run_cognitive_loop(sess=sess, user_message="Sì", db=self.db, decision_fn=must_not_generate)
        self.assertEqual(result.ai_calls, 0)
        self.assertEqual(result.tool_calls, 1)
        self.assertIn("Ho eliminato", result.ora_text)
        self.assertEqual(await self.db.life_nodes.count_documents({"status": "active"}), 0)

    async def test_confirmation_does_not_delete_an_event_edited_since_proposal(self):
        event = await self.create()
        runtime = {"db": self.db, "user_id": self.user, "user_message": "Elimina Visita di prova"}
        proposed = await caps.cancel_calendar_event({"calendar_ref": "calendar:" + event["id"]}, runtime)
        request = proposed.payload["confirmation_request"]
        await update_manual_event(self.db, self.user, event["id"], {"title": "Visita modificata"})
        result = await caps.cancel_calendar_event(request["arguments"], {**runtime, "user_message": "sì", "pending_act": {"kind": "delete"}})
        self.assertEqual(result.payload["failure_kind"], "event_changed")
        self.assertEqual(await self.db.life_nodes.count_documents({"status": "active"}), 1)

    def test_only_plain_approval_resumes_the_bound_cancel(self):
        from conversation_engine.ai_core.calendar_confirmation import next_decision
        pending = {"at": datetime.now(timezone.utc).isoformat(), "calendar_cancel": {
            "arguments": {"calendar_ref": "calendar:test", "confirmation_snapshot": {"title": "Test"}},
            "question": "Elimino Test?"}}
        for text in ("no", "non farlo", "sì ma sposta invece", "quale evento?"):
            self.assertIsNone(next_decision(pending, text, [], 0))
        self.assertEqual(next_decision(pending, "Sì", [], 0)["tool_call"]["arguments"], pending["calendar_cancel"]["arguments"])
        self.assertIsNone(next_decision(None, "Sì", [], 0))

    async def test_move_across_dst_preserves_real_duration(self):
        event = await self.create(day="2026-10-24", time="02:30", duration_minutes=90)
        moved = await update_manual_event(self.db, self.user, event["id"],
                                         {"start_datetime": "2026-10-25T02:30:00+02:00"})
        self.assertEqual(moved["ends_at"], "2026-10-25T03:00:00+01:00")

    async def test_chat_cannot_cancel_without_confirmation_or_after_denial(self):
        from agent.authority import AuthorityService
        event = await self.create()
        args = {"calendar_ref": "calendar:" + event["id"]}
        result = await caps.cancel_calendar_event(args, {"db": self.db, "user_id": self.user, "user_message": "Che impegni ho?"})
        self.assertEqual(result.payload["status"], "authority_required")
        await AuthorityService(self.db).deny(self.user, "calendar.local.write", reason="no")
        result = await caps.cancel_calendar_event(args, {"db": self.db, "user_id": self.user, "user_message": "sì", "pending_act": {"kind": "delete"}})
        self.assertFalse(result.payload.get("verified"))
        self.assertEqual(await self.db.life_nodes.count_documents({"status": "active"}), 1)

    async def test_delete_needs_matching_title_and_can_be_retried(self):
        event = await self.create()
        url = "/api/calendar/events/" + event["id"] + "/delete"
        for title in ("", "altro impegno"):
            self.assertEqual((await self.http.post(url, json={"confirmed_title": title})).status_code, 409)
        for _ in range(2):
            result = await self.http.post(url, json={"confirmed_title": event["title"]})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertTrue(result.json()["verified"])
        self.assertEqual(await self.db.life_nodes.count_documents({"status": "active"}), 0)


if __name__ == "__main__":
    unittest.main()
