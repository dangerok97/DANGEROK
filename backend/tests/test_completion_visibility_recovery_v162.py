"""Completion keeps a bounded communication handoff across technical failure.

The Situation, goal, source checks, closure, Visibility ledger and Need stores
are real and owned by one synthetic account. Only the already verified work
and model reply are fixtures. No work is repeated, and no provider is called.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent import completion_handoff as handoff
from agent.models import ActionPlan, AgentBudget, AgentEvidence, AgentRun, ResultProvenance
from agent.needs import NeedService
from agent.prepared_review import capture_prepared_result
from agent.service import AgentService
from delivery import admission
from places.models import Coordinates
from places.service import PlacesService

from test_situation_outcome_visibility_v160 import OWNER, scenario


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("No socket or real model is allowed in this synthetic test.")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr("research.reasoning._ask_model", AsyncMock(side_effect=blocked))


async def world(monkeypatch):
    db, service, state, goal, run, evidence, raw, answer = await scenario(
        monkeypatch, status="action_now",
    )
    await service.repo.ensure_indexes()
    await service.needs.ensure_indexes()
    place = await PlacesService(db).save_place(
        OWNER, label="Luogo sintetico", role="other", locality="Tarquinia",
        coordinates=Coordinates(latitude=42.249, longitude=11.756),
    )
    await db.situations.update_one({"id": state.id, "user_id": OWNER}, {
        "$set": {"linked_object_refs": [f"place:{place.id}"]},
    })
    now = datetime.now(timezone.utc)
    weather = AgentEvidence(
        owner_id=OWNER, goal_id=goal.id, claim="Condizioni sintetiche del luogo confermato.",
        provenance=ResultProvenance(
            capability="weather.read", provider="synthetic_weather", source_class="external_research",
            source_refs=[f"situation:{state.id}:revision:1", f"place:{place.id}",
                         f"place_snapshot:{place.id}:{place.updated_at}"],
            observed_at=now.isoformat(), freshness="fresh",
            weather_valid_until=(now + timedelta(minutes=45)).isoformat(),
        ),
    )
    await service.evidence.record(weather)
    assert await service._record_situation_outcome(
        OWNER, goal, {**raw, "evidence_ids": [evidence.id, weather.id]}, run,
    )
    plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active")
    await service.repo.save_plan(plan)
    work_calls = []

    async def verified_work(owner, current, current_run, budget, *, language, revisit_due=False):
        work_calls.append(current_run.id)
        return await service._close(owner, current, plan, current_run, "completed",
            "Il risultato sintetico è stato verificato.", visibility_budget=budget, language=language)

    monkeypatch.setattr(service, "_work", verified_work)
    offered = AsyncMock()
    monkeypatch.setattr(NeedService, "offer_to_delivery", offered)
    return SimpleNamespace(db=db, service=service, state=state, goal=goal, run=run,
        evidence=evidence, weather=weather, plan=plan, place=place, answer=answer,
        work_calls=work_calls, offered=offered)


async def checkpoint(w):
    return (await w.db.agent_goals.find_one({"id": w.goal.id, "owner_id": OWNER}))[handoff.FIELD]


async def recover(w):
    state = await checkpoint(w)
    assert state["pending"] and state["due_at"]
    return await handoff.drain(w.db, now=datetime.fromisoformat(state["due_at"]) + timedelta(microseconds=1))


def temporary_place_failure(monkeypatch, w, *, enabled=False):
    fault = {"enabled": enabled}
    original = PlacesService.get_place

    async def flaky(self, owner, place_id):
        goal = await self.db.agent_goals.find_one({"id": w.goal.id, "owner_id": OWNER})
        if fault["enabled"] and goal and goal["status"] == "completed":
            raise TimeoutError("Synthetic place read timeout")
        return await original(self, owner, place_id)

    monkeypatch.setattr(PlacesService, "get_place", flaky)
    return fault


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["before_judgement", "after_candidate", "after_home"])
async def test_completed_result_recovers_to_one_need_after_source_timeout_and_restart(monkeypatch, boundary):
    w = await world(monkeypatch)
    fault = temporary_place_failure(monkeypatch, w, enabled=boundary == "before_judgement")
    reply = deepcopy(w.answer.return_value)
    if boundary == "after_candidate":
        async def respond(*args, **kwargs):
            fault["enabled"] = True
            return reply
        w.answer.side_effect = respond
    elif boundary == "after_home":
        original = w.service.visibility.show
        async def show(*args, **kwargs):
            shown = await original(*args, **kwargs)
            assert shown
            fault["enabled"] = True
            return shown
        monkeypatch.setattr(w.service.visibility, "show", show)

    result = await w.service.advance(OWNER, w.goal.id)
    saved = await w.service.repo.get_goal(OWNER, w.goal.id)
    state = await checkpoint(w)
    assert result["state"] == saved.status == "completed" and saved.next_run_at is None
    assert state["pending"] and state["attempts"] == 1 and state["due_at"]
    assert bool(state.get("candidate")) == (boundary != "before_judgement")
    assert bool(state.get("decision")) == (boundary == "after_home")
    assert await w.db.agent_needs.count_documents({}) == 0
    assert await w.db.agent_updates.count_documents({}) == (boundary == "after_home")

    fault["enabled"] = False
    w.answer.side_effect = None
    # A new service cannot advance terminal work. The existing admission slot
    # resumes its saved communication alone, including any model candidate.
    reloaded = AgentService(w.db)
    assert (await reloaded.advance(OWNER, w.goal.id))["state"] == "completed"
    assert await recover(w) == 1
    assert w.answer.await_count == 1 and len(w.work_calls) == 1
    assert w.offered.await_count == 0, "Recovery registers delivery; it does not buy another judgement."
    need = await w.db.agent_needs.find_one({"owner_id": OWNER, "goal_id": w.goal.id})
    assert need["kind"] == "important_outcome" and need["delivery_review_state"] == "pending"
    assert need["goal_completed_at"] == saved.completed_at
    assert need["summary"] == saved.situation_outcome.headline
    assert f"situation_outcome:{saved.situation_outcome.id}" in need["source_refs"]
    assert await w.db.agent_updates.count_documents({}) == 1
    assert await w.db.agent_needs.count_documents({}) == 1
    assert (await checkpoint(w))["state"] == "settled"
    assert await handoff.drain(w.db, now=datetime.now(timezone.utc) + timedelta(days=1)) == 0
    assert await w.db.agent_action_attempts.count_documents({}) == 0
    assert await w.db.delivery_plans.count_documents({}) == 0


@pytest.mark.asyncio
async def test_model_unavailable_retries_three_times_without_becoming_model_silence(monkeypatch):
    w = await world(monkeypatch)
    w.answer.return_value = None
    assert (await w.service.advance(OWNER, w.goal.id))["state"] == "completed"
    first = await checkpoint(w)
    assert first["attempts"] == 1 and not first.get("candidate")
    assert 55 < (datetime.fromisoformat(first["due_at"]) - datetime.now(timezone.utc)).total_seconds() <= 60
    assert await recover(w) == 1
    second = await checkpoint(w)
    assert second["attempts"] == 2
    assert 295 < (datetime.fromisoformat(second["due_at"]) - datetime.now(timezone.utc)).total_seconds() <= 300
    assert await recover(w) == 1
    final = await checkpoint(w)
    assert final["attempts"] == admission.MAX_ATTEMPTS == 3
    assert final["state"] == "paused" and final["due_at"] is None and not final["pending"]
    assert await handoff.drain(w.db, now=datetime.now(timezone.utc) + timedelta(days=1)) == 0
    assert w.answer.await_count == 3 and len(w.work_calls) == 1
    assert await w.db.agent_needs.count_documents({}) == 0
    assert await w.db.agent_updates.count_documents({}) == 0
    assert (await w.service.repo.get_goal(OWNER, w.goal.id)).status == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["silent", "quiet_update"])
async def test_a_model_chosen_quiet_outcome_is_terminal_for_this_handoff(monkeypatch, outcome):
    w = await world(monkeypatch)
    w.answer.return_value["outcome"] = outcome
    assert (await w.service.advance(OWNER, w.goal.id))["state"] == "completed"
    state = await checkpoint(w)
    assert state["state"] == "settled" and not state["pending"] and state["due_at"] is None
    assert await handoff.drain(w.db, now=datetime.now(timezone.utc) + timedelta(hours=1)) == 0
    assert w.answer.await_count == 1 and await w.db.agent_needs.count_documents({}) == 0
    assert await w.db.agent_updates.count_documents({}) == (outcome == "quiet_update")


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["source_resolved", "place_missing", "source_revision", "assessment_expired",
                                    "new_assessment", "new_preparation", "foreign_goal", "retention_expired"])
async def test_a_saved_candidate_never_borrows_a_changed_or_revoked_result(monkeypatch, change):
    w = await world(monkeypatch)
    fault = temporary_place_failure(monkeypatch, w)
    reply = deepcopy(w.answer.return_value)
    async def respond(*args, **kwargs):
        fault["enabled"] = True
        return reply
    w.answer.side_effect = respond
    await w.service.advance(OWNER, w.goal.id)
    assert (await checkpoint(w))["candidate"] and await w.db.agent_needs.count_documents({}) == 0
    fault["enabled"] = False
    if change == "source_resolved":
        await w.db.situations.update_one({"id": w.state.id}, {"$set": {"status": "resolved"}})
    elif change == "place_missing":
        await w.db.life_places.delete_one({"id": w.place.id})
    elif change == "source_revision":
        await w.db.situations.update_one({"id": w.state.id}, {"$inc": {"revision": 1}})
    elif change in ("assessment_expired", "new_assessment", "new_preparation", "retention_expired"):
        update = {
            "assessment_expired": {"situation_outcome.valid_until": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()},
            "new_assessment": {"situation_outcome.id": "sout_new_synthetic_result"},
            "new_preparation": {"prepared_text": "Una nuova preparazione distinta.", "prepared_result_id": "prep_new"},
            "retention_expired": {f"{handoff.FIELD}.expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()},
        }[change]
        await w.db.agent_goals.update_one({"id": w.goal.id}, {"$set": update})
    else:
        await w.db.agent_goals.update_one({"id": w.goal.id}, {"$set": {"owner_id": "foreign-synthetic"}})
        old = {"id": w.goal.id, "owner_id": OWNER, "due_at": (await w.db.agent_goals.find_one({"id": w.goal.id}))[handoff.FIELD]["due_at"]}
        assert await handoff.drain(w.db, now=datetime.now(timezone.utc) + timedelta(hours=1), candidate=old) == 0
        assert await w.db.agent_needs.count_documents({}) == 0 and w.answer.await_count == 1
        return
    assert await recover(w) == 1
    assert (await checkpoint(w))["state"] == "stale"
    assert w.answer.await_count == 1 and await w.db.agent_needs.count_documents({}) == 0
    assert await w.db.agent_updates.count_documents({}) == 0


@pytest.mark.asyncio
async def test_registration_failure_reuses_the_same_need_after_restart_and_after_a_lost_ack(monkeypatch):
    w = await world(monkeypatch)
    original = admission.register_need
    registration = AsyncMock(side_effect=ConnectionError("Synthetic registration unavailable"))
    monkeypatch.setattr(admission, "register_need", registration)
    await w.service.advance(OWNER, w.goal.id)
    first = await w.db.agent_needs.find_one({"owner_id": OWNER})
    assert first and (await checkpoint(w))["pending"]
    assert not first.get("delivery_review_state")
    monkeypatch.setattr(admission, "register_need", original)
    assert await recover(w) == 1
    second = await w.db.agent_needs.find_one({"owner_id": OWNER})
    assert second["id"] == first["id"] and second["delivery_review_state"] == "pending"
    assert w.answer.await_count == 1 and w.offered.await_count == 0
    # Recreate only the lost acknowledgement. An already settled intent is
    # attested without buying or scheduling another delivery judgement.
    await w.db.agent_needs.update_one({"id": second["id"]}, {"$set": {"delivery_review_state": "settled"}})
    await w.db.agent_goals.update_one({"id": w.goal.id}, {"$set": {
        f"{handoff.FIELD}.pending": True, f"{handoff.FIELD}.due_at": datetime.now(timezone.utc).isoformat(),
    }})
    assert await recover(w) == 1
    current = await w.db.agent_needs.find_one({"id": second["id"]})
    assert current["delivery_review_state"] == "settled" and current["delivery_review_attempts"] == 0
    assert await w.db.agent_needs.count_documents({}) == 1 and w.answer.await_count == 1


@pytest.mark.asyncio
async def test_crash_before_terminal_write_never_activates_the_staged_handoff(monkeypatch):
    w = await world(monkeypatch)
    original = w.service.repo.save_goal
    async def fail_terminal(goal):
        if goal.status == "completed":
            raise ConnectionError("Synthetic crash before terminal save")
        return await original(goal)
    monkeypatch.setattr(w.service.repo, "save_goal", fail_terminal)
    with pytest.raises(ConnectionError):
        await w.service.advance(OWNER, w.goal.id)
    saved = await AgentService(w.db).repo.get_goal(OWNER, w.goal.id)
    assert saved.status == "active" and saved.next_run_at
    assert (await checkpoint(w))["pending"]
    assert await handoff.drain(w.db, now=datetime.now(timezone.utc) + timedelta(days=1)) == 0
    assert w.answer.await_count == 0 and await w.db.agent_needs.count_documents({}) == 0


@pytest.mark.asyncio
async def test_losing_the_prepared_terminal_cas_cannot_announce_a_newer_artifact(monkeypatch):
    w = await world(monkeypatch)
    w.goal.prepared_text = "Vecchio testo sintetico."
    w.goal.prepared_sources = [w.evidence.id]
    w.goal.prepared_result_id = "prep_old"
    await w.service.repo.save_goal(w.goal)
    snapshot = capture_prepared_result(w.goal)
    await w.db.agent_goals.update_one({"id": w.goal.id}, {"$set": {
        "prepared_text": "Nuovo testo sintetico.", "prepared_result_id": "prep_new",
    }})
    result = await w.service._close(OWNER, w.goal, w.plan, w.run, "completed", "Esito del vecchio testo",
                                    prepared_snapshot=snapshot)
    assert result["verification_superseded"]
    saved = await AgentService(w.db).repo.get_goal(OWNER, w.goal.id)
    assert saved.status == "active" and saved.prepared_result_id == "prep_new"
    assert saved.prepared_text == "Nuovo testo sintetico."
    assert (await checkpoint(w))["pending"]
    assert await handoff.drain(w.db, now=datetime.now(timezone.utc) + timedelta(days=1)) == 0
    assert w.answer.await_count == 0 and await w.db.agent_needs.count_documents({}) == 0


@pytest.mark.asyncio
async def test_cancellation_keeps_the_checkpoint_and_stale_lease_cannot_acknowledge(monkeypatch):
    w = await world(monkeypatch)
    w.answer.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await w.service.advance(OWNER, w.goal.id)
    assert (await checkpoint(w))["pending"]
    candidate = await handoff.next_due(w.db, now=datetime.now(timezone.utc) + timedelta(minutes=2))
    old_row = await handoff._claim(w.db, candidate, datetime.now(timezone.utc) + timedelta(minutes=2))
    assert old_row
    old = handoff.CompletionHandoff(w.db, old_row)
    assert await handoff._claim(w.db, candidate, datetime.now(timezone.utc) + timedelta(minutes=2)) is None
    newer = await handoff._claim(w.db, candidate, datetime.now(timezone.utc) + timedelta(minutes=5))
    assert newer and newer[handoff.FIELD]["token"] != old.token
    with pytest.raises(handoff.HandoffUnavailable):
        await old.save(pending=False, state="settled")
    assert (await checkpoint(w))["pending"]
    assert w.answer.await_count == 1 and await w.db.agent_needs.count_documents({}) == 0


@pytest.mark.asyncio
async def test_an_explicit_candidate_still_requires_its_due_time_and_owner(monkeypatch):
    w = await world(monkeypatch)
    w.answer.return_value = None
    await w.service.advance(OWNER, w.goal.id)
    state = await checkpoint(w)
    candidate = {"id": w.goal.id, "owner_id": OWNER, "due_at": state["due_at"]}
    assert await handoff.drain(w.db, candidate=candidate) == 0
    assert await handoff.drain(w.db, candidate={**candidate, "owner_id": "foreign"},
                               now=datetime.now(timezone.utc) + timedelta(hours=1)) == 0
    assert (await checkpoint(w))["attempts"] == 1 and w.answer.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["reopened", "completed_at", "result_identity"])
async def test_a_result_changed_during_visibility_cannot_enter_home_or_need(monkeypatch, change):
    w = await world(monkeypatch)
    reply = deepcopy(w.answer.return_value)

    async def mutate_during_model(*args, **kwargs):
        update = {
            "reopened": {"status": "active"},
            "completed_at": {"completed_at": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()},
            "result_identity": {"situation_outcome.id": "sout_new_synthetic_result"},
        }[change]
        await w.db.agent_goals.update_one({"id": w.goal.id, "owner_id": OWNER}, {"$set": update})
        return reply

    w.answer.side_effect = mutate_during_model
    await w.service.advance(OWNER, w.goal.id)
    assert w.answer.await_count == 1 and len(w.work_calls) == 1
    assert await w.db.agent_updates.count_documents({}) == 0
    assert await w.db.agent_needs.count_documents({}) == 0
    assert (await checkpoint(w))["state"] == "stale"
