"""
What a person can do about work ORA is doing on their behalf.

Four of these are real and belong to them: answer a question, say yes to
something prepared, say stop, and see what is going on in human terms. The
rest are a debug surface for watching the loop during development.

There is no endpoint that executes a step directly. Execution is what happens
inside `advance()` when the authority ceiling allows it, and an endpoint that
skipped that would be a way to make ORA act without anybody having decided to.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import get_current_user

router = APIRouter(prefix="/agent", tags=["agent"])


class ConsiderIn(BaseModel):
    # A situation to weigh. Facts only — there is no field here for saying
    # that a goal should be created.
    situation: dict = Field(default_factory=dict)
    opportunity_id: str = Field(default="", max_length=64)
    # user_requested | agent_initiated. Both take exactly the same path.
    origin: str = Field(default="agent_initiated", max_length=20)


class AnswerIn(BaseModel):
    reply: str = Field(max_length=2000)
    # Which question this answers. Left empty, it goes to whatever is blocked
    # — which is right when there is one thing waiting, and would be a guess
    # when there are two.
    step_id: str = Field(default="", max_length=64)


class AuthoriseIn(BaseModel):
    # Left empty, the capability is taken from whatever is blocked.
    capability: str = Field(default="", max_length=60)
    # Whether this yes is also a yes to the next time.
    #
    #     ONE-TIME APPROVAL IS NOT A STANDING PERMISSION.
    #
    # Two different presses on two different controls, and it defaults to the
    # narrow one. There is deliberately no path by which an ordinary approval
    # becomes this: approving five times is five approvals, because the fifth
    # act is not a different act from the first.
    persistent: bool = False


class CancelIn(BaseModel):
    reason: str = Field(default="", max_length=300)


class DenyIn(BaseModel):
    # Left empty, the capability is taken from whatever is blocked.
    capability: str = Field(default="", max_length=60)
    reason: str = Field(default="", max_length=300)


class ModeIn(BaseModel):
    mode: str = Field(max_length=24)


class GrantIn(BaseModel):
    capability: str = Field(max_length=60)
    scope_note: str = Field(default="", max_length=200)


def _dev_only() -> None:
    if os.environ.get("DEV", "").strip().lower() not in ("1", "true", "on"):
        raise HTTPException(status_code=404, detail="not_found")


@router.get("")
async def current(user=Depends(get_current_user)):
    """
    What ORA is working on, in human terms.

    Outcomes and states of affairs — «me ne sto occupando», «mi serve il tuo
    via libera». No steps, no plan status, no capability names.
    """
    from agent.service import AgentService
    from deps import db

    return {"goals": await AgentService(db).for_home(user["user_id"])}


@router.get("/needs/{need_id}")
async def need(need_id: str, user=Depends(get_current_user)):
    """
    What a tap from an agent need lands on.

    Everything a person should see and nothing else: what ORA already did,
    what is missing, and whether they are being asked for something. No kind
    code, no status, no refs, no goal state — a surface cannot show what it
    was never given, and every one of those is workflow wearing a friendly
    name. `goal_id` is the exception, and it is a handle: the answer, the
    approval or the refusal has to be able to go back to the right goal.
    """
    from agent.needs import NeedService
    from deps import db

    from agent.service import AgentService

    found = await NeedService(db).get(user["user_id"], need_id)
    if found is None:
        raise HTTPException(status_code=404, detail="unknown_need")
    # What saying yes for the future would mean here, in one sentence, or
    # nothing at all. Computed rather than assumed: most needs cannot be
    # turned into a standing permission and must not offer to be.
    offer = (
        await AgentService(db).standing_offer(user["user_id"], found.goal_id)
        if found.response_kind == "authority" and found.is_open else None
    )
    return {
        **found.for_human(),
        "goal_id": found.goal_id,
        "asks_for": found.response_kind,
        "already_done": found.work_already_done,
        "missing": found.what_is_missing or None,
        "still_open": found.is_open,
        "can_allow_always": offer,
    }


@router.post("/consider")
async def consider(body: ConsiderIn, user=Depends(get_current_user)):
    """
    Is there an outcome here worth pursuing? Usually not.

    The only way in, for a request and for a noticing alike.
    """
    from agent.service import AgentService
    from deps import db

    return await AgentService(db).consider(
        user["user_id"],
        situation=body.situation,
        origin=body.origin if body.origin in ("user_requested", "agent_initiated")
        else "agent_initiated",
        opportunity_id=body.opportunity_id,
    )


@router.post("/{goal_id}/advance")
async def advance(goal_id: str, user=Depends(get_current_user)):
    """Take it as far as it can go without a person. Development surface."""
    _dev_only()
    from agent.service import AgentService
    from deps import db

    return await AgentService(db).advance(user["user_id"], goal_id)


@router.post("/{goal_id}/answer")
async def answer(goal_id: str, body: AnswerIn, user=Depends(get_current_user)):
    """
    They supplied what only they knew. Carry on from there.

    The reply comes back with one sentence a person can read, because this is
    now reachable from a conversation: somebody who answers «Padova» in the
    thread ORA asked in gets an answer in the thread, not a silent state
    change somewhere else. The sentence is the next question if there is one,
    and otherwise whatever is honestly true about the goal — including «non ho
    ancora cominciato», which is the one a system usually hides.
    """
    from agent.service import AgentService
    from deps import db

    service = AgentService(db)
    result = await service.answer(
        user["user_id"], goal_id, reply=body.reply, step_id=body.step_id
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("reason"))

    says = str(result.get("asks") or "")
    if not says:
        goal = await service.repo.get_goal(user["user_id"], goal_id)
        says = await service._progress_of(user["user_id"], goal) if goal else ""
    return {**result, "says": says}


@router.post("/{goal_id}/authorise")
async def authorise(goal_id: str, body: AuthoriseIn, user=Depends(get_current_user)):
    """
    They said yes to what was prepared.

    The grant is created here, by them. There is no path from the model to
    this endpoint.
    """
    from agent.service import AgentService
    from deps import db

    result = await AgentService(db).authorise(
        user["user_id"], goal_id, capability=body.capability,
        persistent=body.persistent,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("reason"))
    return result


@router.post("/{goal_id}/deny")
async def deny(goal_id: str, body: DenyIn, user=Depends(get_current_user)):
    """
    They said no to what was prepared.

    Nothing is executed, and the refusal is remembered: ORA may find another
    route, wait, or give up, but it may not come back to the same door this
    month. A no that has to be repeated is not a no that was heard.
    """
    from agent.service import AgentService
    from deps import db

    result = await AgentService(db).deny(
        user["user_id"], goal_id, capability=body.capability, reason=body.reason
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("reason"))
    return result


@router.post("/{goal_id}/cancel")
async def cancel(goal_id: str, body: CancelIn, user=Depends(get_current_user)):
    """«Lascia perdere.» Future work stops; what already happened stands."""
    from agent.service import AgentService
    from deps import db

    result = await AgentService(db).cancel(user["user_id"], goal_id, reason=body.reason)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("reason"))
    return result


@router.get("/autonomy")
async def autonomy(user=Depends(get_current_user)):
    """
    How much ORA may do on its own, and what has been allowed.

    `grants` is the answer to «cosa può fare da sola», and each one carries
    the sentence the person actually agreed to rather than the scope it was
    stored as. Somebody reading the list has read the permissions.
    """
    from agent.authority import AuthorityService
    from deps import db

    service = AuthorityService(db)
    policy = await service.policy(user["user_id"])
    return {
        "mode": policy.mode,
        "chosen_by_user": policy.chosen_by_user,
        "grants": await service.grants(user["user_id"]),
    }


@router.post("/autonomy/mode")
async def set_mode(body: ModeIn, user=Depends(get_current_user)):
    from agent.authority import AuthorityService
    from deps import db

    result = await AuthorityService(db).set_mode(user["user_id"], body.mode)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason"))
    return result


@router.post("/autonomy/grant")
async def grant(body: GrantIn, user=Depends(get_current_user)):
    """
    Allow ORA to do one kind of thing without asking each time.

    Owner-bound and revocable. Only a person reaches this.
    """
    from agent.authority import AuthorityService
    from deps import db

    result = await AuthorityService(db).grant(
        user["user_id"], body.capability, scope_note=body.scope_note, by="user"
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason"))
    return result


@router.post("/autonomy/revoke")
async def revoke(body: GrantIn, user=Depends(get_current_user)):
    from agent.authority import AuthorityService
    from deps import db

    return await AuthorityService(db).revoke(user["user_id"], body.capability)


@router.get("/{goal_id}/journal")
async def journal(goal_id: str, user=Depends(get_current_user)):
    """The audit trail. Development only — it holds implementation state."""
    _dev_only()
    from agent.service import AgentService
    from deps import db

    service = AgentService(db)
    return {"history": await service.repo.history(user["user_id"], goal_id)}
