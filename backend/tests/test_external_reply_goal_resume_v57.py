from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.followups import resume_email_reply
from agent.models import (
    ActionPlan,
    ActionStep,
    AutonomousGoal,
    ExecutionReceipt,
)
from agent.repository import AgentRepository
from connected.models import ConnectedSignal, FieldChange


OWNER = "alice"


def _reply(*, message_id="reply_1", thread_id="thread_1", origin="external"):
    now = datetime.now(timezone.utc).isoformat()
    return ConnectedSignal(
        owner_id=OWNER,
        source_id="gmail_1",
        source_type="email",
        signal_type="email.thread.updated",
        observed_at=now,
        effective_at=now,
        source_object_ref=message_id,
        payload_summary="È arrivata una risposta nel thread.",
        after="Re: richiesta",
        changed_fields=[FieldChange(field="subject", after="Re: richiesta")],
        origin=origin,
        provenance={"thread_ref": thread_id, "instance_id": "gmail_1"},
        confidence="certain",
    )


async def _waiting_goal(db, *, thread_id="thread_1"):
    repo = AgentRepository(db)
    goal = AutonomousGoal(
        id="goal_followup",
        owner_id=OWNER,
        status="waiting",
        origin="agent_initiated",
        objective="Ottenere conferma dallo studio",
        desired_outcome="Sapere se lo studio accetta il nuovo orario",
        source_refs=["mail:sent_1"],
        next_run_at=(datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
    )
    await repo.create_goal(goal)
    plan = ActionPlan(
        id="plan_followup",
        owner_id=OWNER,
        goal_id=goal.id,
        status="waiting",
        plan_summary="Inviare la richiesta e attendere la risposta.",
        steps=[
            ActionStep(
                id="send_done",
                ordinal=0,
                intent="Inviare la richiesta allo studio",
                step_type="execute",
                capability_needed="mail.send",
                status="succeeded",
            ),
            ActionStep(
                id="wait_reply",
                ordinal=1,
                intent="Attendere la risposta dello studio",
                step_type="wait",
                status="waiting",
            ),
        ],
    )
    await repo.save_plan(plan)
    receipt = ExecutionReceipt(
        id="receipt_sent",
        owner_id=OWNER,
        goal_id=goal.id,
        action_intent_id="intent_sent",
        capability="mail.send",
        provider="gmail",
        external_ref="sent_1",
        provider_status="succeeded",
        result_refs=[f"gmail_thread:{thread_id}"],
        answered_at=datetime.now(timezone.utc).isoformat(),
    )
    await db.agent_receipts.insert_one(receipt.model_dump())
    return repo, goal, plan


@pytest.mark.asyncio
async def test_exact_external_reply_wakes_same_goal_and_adds_one_private_mail_read():
    db = AsyncMongoMockClient().test
    repo, goal, _ = await _waiting_goal(db)

    resumed = await resume_email_reply(db, OWNER, _reply())

    assert resumed == 1
    saved_goal = await repo.get_goal(OWNER, goal.id)
    assert saved_goal is not None
    assert saved_goal.status == "active"
    assert saved_goal.next_run_at is not None
    assert "mail:reply_1" in saved_goal.source_refs

    plan = await repo.plan_for(OWNER, goal.id)
    assert plan is not None
    old_wait = next(step for step in plan.steps if step.id == "wait_reply")
    assert old_wait.status == "succeeded"
    assert "risposta esterna" in old_wait.note

    reads = [
        step for step in plan.steps
        if step.capability_needed == "mail.read"
        and "mail:reply_1" in step.input_refs
    ]
    assert len(reads) == 1
    assert reads[0].status == "pending"

    wakes = await db.ambient_wakes.find(
        {"owner_id": OWNER, "source_ref": f"goal:{goal.id}", "status": "pending"},
        {"_id": 0},
    ).to_list(20)
    assert wakes
    assert min(w["scheduled_for"] for w in wakes) <= (
        datetime.now(timezone.utc) + timedelta(minutes=2)
    ).isoformat()

    journal = await db.agent_journal.find_one(
        {"owner_id": OWNER, "goal_id": goal.id, "kind": "external_reply_arrived"},
        {"_id": 0},
    )
    assert journal is not None
    assert journal["detail"]["source_ref"] == "mail:reply_1"
    assert journal["detail"]["thread_ref"] == "gmail_thread:thread_1"


@pytest.mark.asyncio
async def test_followup_resume_is_idempotent_for_same_reply():
    db = AsyncMongoMockClient().test
    repo, goal, _ = await _waiting_goal(db)
    signal = _reply()

    assert await resume_email_reply(db, OWNER, signal) == 1

    # Put the goal back in waiting to prove the same source ref still cannot
    # append a second read or second logical continuation.
    saved = await repo.get_goal(OWNER, goal.id)
    saved.status = "waiting"
    saved.next_run_at = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    await repo.save_goal(saved)

    assert await resume_email_reply(db, OWNER, signal) == 0
    plan = await repo.plan_for(OWNER, goal.id)
    reads = [
        step for step in plan.steps
        if step.capability_needed == "mail.read"
        and "mail:reply_1" in step.input_refs
    ]
    assert len(reads) == 1


@pytest.mark.asyncio
async def test_wrong_thread_or_self_originated_message_never_resumes_goal():
    db = AsyncMongoMockClient().test
    repo, goal, _ = await _waiting_goal(db)

    assert await resume_email_reply(
        db, OWNER, _reply(thread_id="other_thread")
    ) == 0
    assert await resume_email_reply(
        db, OWNER, _reply(origin="self_originated")
    ) == 0

    saved = await repo.get_goal(OWNER, goal.id)
    assert saved.status == "waiting"
    assert "mail:reply_1" not in saved.source_refs
    assert await db.ambient_wakes.count_documents(
        {"owner_id": OWNER, "source_ref": f"goal:{goal.id}"}
    ) == 0


@pytest.mark.asyncio
async def test_goal_waiting_for_person_is_never_resumed_by_mail_thread():
    db = AsyncMongoMockClient().test
    repo, goal, _ = await _waiting_goal(db)
    saved = await repo.get_goal(OWNER, goal.id)
    saved.requires_user_authority = True
    await repo.save_goal(saved)

    assert await resume_email_reply(db, OWNER, _reply()) == 0
    still = await repo.get_goal(OWNER, goal.id)
    assert still.status == "waiting"
    assert still.requires_user_authority is True
