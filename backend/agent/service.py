"""
The loop: notice, decide, plan, do what is allowed, check, and stop.

    ORA MAY CREATE A GOAL WITHOUT A USER COMMAND.
    THE USER SHOULD EXPERIENCE OUTCOMES, NOT WORKFLOWS.

One engine, two doors into it. Somebody asking for something and ORA noticing
something both arrive at `consider()` and take exactly the same path — there
is no separate "autonomous" branch, and a test enforces that, because the day
there are two paths one of them stops being maintained.

The loop advances a plan as far as it can go on its own. Reading,
researching, comparing and drafting run for real against engines that already
exist; anything that would change the world stops with the work finished and a
question that is worth asking. What each capability found is kept as evidence
with its provenance, and the next thing to do is chosen from what is now known
rather than taken from the next line of a list.

Three things guard it, and all three are code.

A **claim** — one worker holds a goal at a time, so two processes reaching the
same goal produce one execution and not two.

A **budget** — iterations, model calls, capability calls, research calls and
wall time. An agent loop without a ceiling is a bill without a ceiling, and
the honest response to running out is to arrange to come back rather than to
stop having a plan.

And a **completion gate** — a goal is not closed because the model concluded
`achieved`. It is closed when the model concludes `achieved` and something
that actually happened supports it. A stand-in returning success is not the
world changing, and that is checked in code rather than asked about in a
prompt.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from agent.authority import AuthorityService
from agent.capabilities import CapabilityResolver, is_really_wired
from agent.evidence import EvidenceStore, for_verification, real_support
from agent.execution import MAX_STEP_ATTEMPTS, StepExecutor
from agent.models import (
    ActionPlan,
    ActionEffect,
    CommunicationNeed,
    ActionStep,
    AgentBudget,
    AgentEvidence,
    AgentRun,
    AuthorityAssessment,
    AutonomousGoal,
    ExecutionReceipt,
    ExecutionResult,
    GoalVerification,
    ResultProvenance,
)
from agent.needs import NeedService
from agent.repository import AgentRepository
from agent.visibility import VisibilityService

logger = logging.getLogger(__name__)

# What one pass may cost. Bounds, not judgements: whether to keep going is
# the model's call, whether to keep paying is not.
MAX_ITERATIONS = 6
MAX_MODEL_CALLS = 8
MAX_PLAN_STEPS = 12

# The shortest a `wait` may be before looking again. Without a floor, a model
# that keeps saying "a bit later" produces a loop that looks like diligence.
MIN_WAIT_HOURS = 1
MAX_WAIT_HOURS = 24 * 14

# How long to leave a goal alone when a run ran out of budget rather than out
# of work. Soon enough to be continuing; far enough away to not be a spin.
CONTINUE_IN_HOURS = 2


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AgentService:
    def __init__(self, db):
        self.db = db
        self.repo = AgentRepository(db)
        self.authority = AuthorityService(db)
        self.capabilities = CapabilityResolver(db)
        self.executor = StepExecutor(db)
        self.evidence = EvidenceStore(db)
        self.visibility = VisibilityService(db)
        self.needs = NeedService(db)

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()
        await self.authority.ensure_indexes()
        await self.executor.ensure_indexes()
        await self.evidence.ensure_indexes()
        await self.visibility.ensure_indexes()
        await self.needs.ensure_indexes()

    # --- the way in --------------------------------------------------------

    async def consider(
        self,
        owner_id: str,
        *,
        situation: Dict[str, Any],
        origin: str = "agent_initiated",
        opportunity_id: str = "",
        source_kind: str = "",
        source_refs: Optional[List[str]] = None,
        language: str = "it",
    ) -> Dict[str, Any]:
        """
        Is there an outcome here worth pursuing?

        The only entrance. A request and a noticing produce the same call with
        a different `origin`, so nothing downstream can behave differently
        depending on who started it.
        """
        from agent.reasoning import decide_goal

        if opportunity_id:
            existing = await self.repo.goal_for_opportunity(owner_id, opportunity_id)
            if existing is not None:
                return {"outcome": "already_pursuing", "goal": existing.for_human()}

        answer = await decide_goal(
            {**situation, "who_asked": origin}, language=language
        )
        if answer is None:
            # No judgement was available. Nothing is created and nothing is
            # recorded as a decision that there was nothing to do.
            return {"outcome": "unavailable"}

        decision = answer["outcome"]
        if decision != "create_goal":
            return {
                "outcome": decision,
                "reasoning": str(answer.get("reasoning") or "")[:400],
                "question": str(answer.get("question") or "")[:300] or None,
            }

        goal = AutonomousGoal(
            owner_id=owner_id,
            status="active",
            origin=origin,  # type: ignore[arg-type]
            objective=str(answer.get("objective") or "")[:280],
            desired_outcome=str(answer.get("desired_outcome") or "")[:400],
            why_now=str(answer.get("why_now") or "")[:400],
            success_criteria=[str(c)[:200] for c in (answer.get("success_criteria") or [])][:6],
            stop_conditions=[str(c)[:200] for c in (answer.get("stop_conditions") or [])][:6],
            source_kind=source_kind[:40],
            source_refs=[str(r)[:120] for r in (source_refs or [])][:8],
            opportunity_id=opportunity_id,
            rationale=str(answer.get("reasoning") or "")[:300],
        )
        if not goal.objective or not goal.desired_outcome:
            # A goal that cannot say what it is for is not a goal.
            return {"outcome": "no_goal", "reasoning": "l'obiettivo non era formulabile"}

        created = await self.repo.create_goal(goal)
        if created is None:
            return {"outcome": "already_pursuing"}

        await self.repo.journal(
            owner_id, goal.id, kind="goal_created", note=goal.objective,
            detail={"origin": origin, "opportunity_id": opportunity_id},
        )
        await self._note_ambient(owner_id, "agent_goal_created", goal)
        return {"outcome": "create_goal", "goal": goal.for_human(), "goal_id": goal.id}

    # --- the loop ----------------------------------------------------------

    async def advance(
        self, owner_id: str, goal_id: str, *, language: str = "it",
        worker_id: str = "", budget: Optional[AgentBudget] = None,
    ) -> Dict[str, Any]:
        """
        Take the goal as far as it can go without a person.

        Stops for exactly three reasons: the outcome is reached, something is
        needed that only a person can give, or a bound was hit. Everything
        else, it keeps doing.
        """
        goal = await self.repo.get_goal(owner_id, goal_id)
        if goal is None:
            return {"ok": False, "reason": "unknown_goal"}
        if not goal.is_open:
            return {"ok": True, "state": goal.status, "goal": goal.for_human()}

        # One worker at a time. A wake firing while a request is already
        # advancing the same goal is ordinary, not exceptional, and without
        # this both would research the same question and eventually prepare
        # the same effect twice.
        worker = worker_id or f"w_{uuid.uuid4().hex[:8]}"
        if not await self.repo.claim(owner_id, goal_id, worker_id=worker):
            return {
                "ok": True,
                "state": "already_running",
                "goal": goal.for_human(),
            }

        run = AgentRun(owner_id=owner_id, goal_id=goal.id)
        allowance = budget or AgentBudget()
        try:
            result = await self._work(owner_id, goal, run, allowance, language=language)
        finally:
            await self.repo.release(goal_id, stopped_because=run.stopped_because)

        # Whether any of that was worth their knowing. Asked once, at the end,
        # about the run as a whole — a decision per step would be the
        # narration this is meant to prevent.
        await self._consider_visibility(
            owner_id, goal_id, run, allowance, language=language
        )
        return result

    async def _work(
        self, owner_id, goal, run: AgentRun, budget: AgentBudget, *, language: str
    ) -> Dict[str, Any]:
        """
        Keep going while there is something worth doing and something to spend.

        The plan is loaded rather than rebuilt. That is what makes a restart
        after a crash cheap and correct: everything already done is already
        written down, and a run that comes back finds the work where it left
        it instead of starting the goal again.
        """
        plan = await self.repo.plan_for(owner_id, goal.id)

        if plan is None:
            plan = await self._build_plan(
                owner_id, goal, run, budget, language=language
            )
            if plan is None:
                run.stopped_because = "no_plan"
                return await self._stop(goal, run, "il piano non era formulabile")

        while True:
            if run.iterations >= MAX_ITERATIONS:
                run.stopped_because = "iterations"
                return await self._continue_later(owner_id, goal, plan, run, "iterations")

            run.iterations += 1
            decision, step = await self._next(
                owner_id, goal, plan, run, budget, language=language
            )

            if decision == "finish":
                return await self._finish(
                    owner_id, goal, plan, run, budget, language=language
                )

            if decision == "stalled":
                return await self._pause(
                    owner_id, goal, plan, run, "il giudizio non era disponibile"
                )

            if decision == "wait":
                return await self._wait(
                    owner_id, goal, plan, step, run, hours=int(run.replans and 6 or 6)
                )

            if decision == "ask":
                return await self._ask(owner_id, goal, plan, step, run)

            if decision == "replan":
                outcome = await self._reconsider(
                    owner_id, goal, plan, run, budget,
                    what_happened={
                        "what_was_found": for_verification(
                            await self.evidence.for_goal(owner_id, goal.id)
                        ),
                        "problem": "quello che si è scoperto cambia la strada",
                    },
                    language=language,
                )
                if outcome is not None:
                    return outcome
                continue

            if decision == "skip":
                # The model dropped a step because what was found made it
                # pointless. The step stays in the plan, marked — history is
                # not rewritten, and a skipped step is a fact about the run.
                if step is not None:
                    step.status = "skipped"
                    await self.repo.save_plan(plan)
                    await self.repo.journal(
                        owner_id, goal.id, kind="step_skipped", note=step.intent,
                        detail={"step_id": step.id},
                    )
                continue

            if step is None:
                return await self._finish(
                    owner_id, goal, plan, run, budget, language=language
                )

            if step.step_type == "ask_user":
                return await self._ask(owner_id, goal, plan, step, run)

            if step.step_type == "wait":
                return await self._wait(owner_id, goal, plan, step, run, hours=6)

            # The ceiling is on work done, not on deciding to stop. Checked
            # here rather than at the top of the loop because a goal that has
            # run out of budget must still be able to reach the sentence
            # «this is ready, may I» — a run that spent its allowance and
            # then could not ask would leave somebody waiting on a question
            # nobody was going to put.
            spent = budget.exhausted()
            if spent:
                run.stopped_because = spent
                return await self._continue_later(owner_id, goal, plan, run, spent)

            outcome = await self._do_step(
                owner_id, goal, plan, step, run, budget, language=language
            )
            if outcome is not None:
                return outcome

    async def _next(
        self, owner_id, goal, plan: ActionPlan, run: AgentRun, budget: AgentBudget,
        *, language: str,
    ) -> Tuple[str, Optional[ActionStep]]:
        """
        What is worth doing now — not what comes next in the list.

            A PLAN IS STATE, NOT A SCRIPT.

        Two paths, and the split is a cost decision with a real argument
        behind it. Before anything has been found out, the plan is still its
        own best guess and there is nothing new for a judgement to be about,
        so the first step is taken deterministically and no model is called.
        Once evidence exists it can have made a later step pointless,
        premature or already answered, and walking the list in order would
        carry out a step whose reason evaporated two steps ago.
        """
        pending = [s for s in sorted(plan.steps, key=lambda x: x.ordinal)
                   if s.status == "pending"]
        if not pending:
            return ("finish", None)

        evidence = await self.evidence.for_goal(owner_id, goal.id)
        if not evidence:
            return ("execute", pending[0])

        if budget.cognitive_calls >= budget.max_cognitive_calls:
            # Out of judgement for this run. Taking the next step anyway
            # would be spending capability calls on a choice nobody made.
            return ("finish", None)

        from agent.reasoning import choose_next_action

        budget.cognitive_calls += 1
        run.model_calls = budget.cognitive_calls
        answer = await choose_next_action(
            goal.for_ai(),
            plan=plan.for_ai(),
            candidates=[s.for_ai() for s in pending],
            evidence=for_verification(evidence),
            capabilities=await self.capabilities.available(owner_id),
            language=language,
        )
        if answer is None:
            return ("stalled", None)

        decision = answer["decision"]
        chosen = plan.step(str(answer.get("step_id") or "")) if answer.get("step_id") else None
        await self.repo.journal(
            owner_id, goal.id, kind="chose_next",
            note=str(answer.get("reasoning") or "")[:300],
            detail={"decision": decision, "step_id": (chosen.id if chosen else "")},
        )

        if decision in ("execute", "skip"):
            # A step id that names nothing is not a reason to improvise. The
            # first thing still to do is the honest fallback.
            return (decision, chosen or pending[0])

        if decision == "complete":
            return ("finish", None)

        if decision == "verify":
            return ("finish", None)

        if decision == "ask":
            step = ActionStep(
                ordinal=len(plan.steps),
                intent=str(answer.get("asks") or answer.get("reasoning") or "")[:280],
                step_type="ask_user",
                asks=str(answer.get("asks") or "")[:300],
                ask_kind=(
                    answer.get("ask_kind")
                    if answer.get("ask_kind") in ("knowledge", "authority")
                    else "knowledge"
                ),
            )
            plan.steps.append(step)
            await self.repo.save_plan(plan)
            return ("ask", step)

        return (decision, chosen)

    async def _continue_later(
        self, owner_id, goal, plan: ActionPlan, run: AgentRun, why: str
    ) -> Dict[str, Any]:
        """
        Out of budget, not out of work. Arrange to come back.

            IF THE BUDGET IS SPENT, SCHEDULE A CONTINUATION.

        The alternative — carrying on until it is done — is how one goal
        empties a month's allowance in an afternoon. The alternative to
        *that*, stopping silently, leaves somebody with a goal that says it
        is being handled and nothing that will ever handle it.
        """
        plan.status = "active"
        await self.repo.save_plan(plan)
        await self.repo.journal(
            owner_id, goal.id, kind="continues_later", note=f"tetto raggiunto: {why}",
            detail={"iterations": run.iterations, "steps": run.steps_executed},
        )
        try:
            from ambient.service import AmbientService

            await AmbientService(self.db).schedule(
                owner_id,
                reason="opportunity_revisit",
                when=_now() + timedelta(hours=CONTINUE_IN_HOURS),
                source_ref=f"goal:{goal.id}",
                # A ceiling is a technical fact, not a judgement anybody made.
                provenance="code_schedule",
            )
        except Exception as e:
            logger.info("agent continuation soft-fail: %s", type(e).__name__)
        return {"ok": True, "state": "in_progress", "goal": goal.for_human()}

    # --- one step ----------------------------------------------------------

    async def _do_step(
        self, owner_id, goal, plan, step: ActionStep, run: AgentRun,
        budget: AgentBudget, *, language: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Run one step. Returns a stopping outcome, or None to keep going.
        """
        step.attempts += 1
        if step.attempts > MAX_STEP_ATTEMPTS:
            step.status = "failed"
            step.note = "provato troppe volte"
            await self.repo.save_plan(plan)
            return await self._reconsider(
                owner_id, goal, plan, run, budget,
                what_happened={"step": step.for_ai(), "problem": "troppi tentativi"},
                language=language,
            )

        may_touch = True
        if step.step_type == "execute":
            assessment = await self._authority_for(
                owner_id, goal, step, run, budget, language=language
            )
            if assessment is None:
                return await self._pause(
                    owner_id, goal, plan, run, "il giudizio non era disponibile"
                )

            await self.repo.journal(
                owner_id, goal.id, kind="authority_assessed",
                note=assessment.code_reason or assessment.reasoning,
                detail=assessment.public(),
            )

            if assessment.effective_outcome == "cannot_proceed":
                step.status = "blocked"
                await self.repo.save_plan(plan)
                return await self._reconsider(
                    owner_id, goal, plan, run, budget,
                    what_happened={
                        "step": step.for_ai(),
                        "problem": "non è una cosa che si può fare così",
                        "why": assessment.code_reason or assessment.reasoning,
                    },
                    language=language,
                )

            effective = await self.authority.effective_authority(
                owner_id, self.executor._intent_for(owner_id, goal, step), assessment
            )
            may_touch = effective.may_execute
            await self.repo.journal(
                owner_id, goal.id, kind="authority_effective",
                note=effective.reason_code, detail=effective.public(),
            )
            if not may_touch:
                # Do the preparation, then stop with everything ready.
                result = await self.executor.run(
                    owner_id, goal, step, may_touch_the_world=False, budget=budget
                )
                step.status = "blocked"
                step.ask_kind = "authority"
                step.asks = step.intent
                await self.repo.save_plan(plan)
                await self.repo.journal(
                    owner_id, goal.id, kind="awaiting_authority",
                    note=result.observation, detail={"step_id": step.id},
                )
                return await self._awaiting_authority(owner_id, goal, plan, run, step)

        async def _recheck(intent):
            """
            The same question, asked again in the last moment before the world
            is touched. Ten minutes is long enough for somebody to change
            their mind, and an answer computed then is a claim about then.
            """
            return await self.authority.effective_authority(
                owner_id, intent, assessment
            ) if step.step_type == "execute" else None

        result = await self.executor.run(
            owner_id, goal, step, may_touch_the_world=may_touch, budget=budget,
            recheck=_recheck if step.step_type == "execute" else None,
        )
        budget.steps_executed += 1
        run.steps_executed += 1

        # A one-time yes is spent by the thing it was a yes to.
        #
        #     A ONE-TIME YES IS ONE TIME.
        #
        # Looked up rather than taken from the decision, and the difference is
        # the whole bug. Somebody who approves an act *and* allows it for the
        # future produces two things: a consent for this act and a standing
        # permission. The permission is what the executor then proceeds on —
        # it is checked first — so the consent was never the deciding basis
        # and, when the basis was all that got spent, it stayed unspent for
        # ever. Revoke the permission a week later and that forgotten yes
        # silently authorised the same act again.
        #
        # What is true regardless of which basis won: they said yes to this
        # act, and the act happened. The yes is used up.
        #
        # Here rather than inside the executor, and that is a boundary rather
        # than a preference: the executor may ask what it is allowed to do and
        # may never change it, which is why a guard walks that module for any
        # call into the authority service. Spending is a change.
        #
        # Only after the effect actually happened. A request that never
        # reached the provider has used nobody's permission up.
        if (
            step.step_type == "execute"
            and result.status in ("succeeded", "partial")
            and result.error_type not in ("authority_required", "authority_withdrawn")
        ):
            used, why = await self.authority.find_consent(
                owner_id, self.executor._intent_for(owner_id, goal, step)
            )
            if used is not None and why == "one_time_consent":
                await self.authority.spend_consent(owner_id, used.id)

        # A partial result is not a success. It is a step that got somewhere
        # and not all the way, and calling it done is how a plan sails past
        # the thing it was supposed to establish.
        step.status = {
            "succeeded": "succeeded", "partial": "succeeded",
            "failed": "failed", "unavailable": "failed", "waiting": "waiting",
        }[result.status]
        step.actual_result_ref = result.data_ref or (result.result_refs or [""])[0]
        step.note = result.observation[:200]
        plan.current_step = step.ordinal
        await self.repo.save_plan(plan)
        await self.repo.journal(
            owner_id, goal.id, kind="step_done", note=result.observation,
            detail={
                "step_id": step.id,
                "status": result.status,
                "came_from": result.provenance.source_class,
                "really_happened": result.is_real,
                "evidence": len(result.evidence_refs),
            },
        )

        if result.status in ("failed", "unavailable", "waiting") or result.error_type:
            # Something did not go as the plan assumed — it broke, it was not
            # connected, it found less than was needed. All of those are for
            # the model to weigh, and none of them are for code to route
            # around by trying the same thing again.
            return await self._reconsider(
                owner_id, goal, plan, run, budget,
                what_happened={
                    "step": step.for_ai(),
                    "result": {
                        "status": result.status,
                        "what_happened": result.observation,
                        "problem": result.error_type or None,
                        "worth_retrying": result.retryable,
                        **result.provenance.for_ai(),
                    },
                },
                language=language,
            )
        return None

    async def _authority_for(
        self, owner_id, goal, step: ActionStep, run: AgentRun, budget: AgentBudget,
        *, language: str,
    ) -> Optional[AuthorityAssessment]:
        """
        What kind of act this is, judged then narrowed.

        The model's reading is never used directly: `apply_ceiling` is the
        only thing that produces an effective outcome, and it can only make
        the answer more cautious.
        """
        from agent.reasoning import assess_authority

        resolution = await self.capabilities.resolve(owner_id, step.capability_needed)
        budget.cognitive_calls += 1
        run.model_calls = budget.cognitive_calls
        answer = await assess_authority(
            step.for_ai(),
            goal=goal.for_ai(),
            facts={
                "changes_something_in_the_world": resolution.writes,
                "reaches_somebody_else": resolution.reaches_third_party,
                "involves_money": resolution.financial,
                "how_hard_to_undo": resolution.reversibility,
                "they_have_allowed_this_kind_of_thing": await self.authority.has_grant(
                    owner_id, step.capability_needed
                ),
                "what_they_asked_for": (await self.authority.policy(owner_id)).for_ai(),
            },
            language=language,
        )
        if answer is None:
            return None

        assessment = AuthorityAssessment(
            step_id=step.id,
            capability=step.capability_needed,
            model_outcome=answer["outcome"],
            reasoning=str(answer.get("reasoning") or "")[:400],
            reversibility=(
                answer.get("reversibility")
                if answer.get("reversibility")
                in ("easily", "with_effort", "hardly", "irreversible")
                else "easily"
            ),
            financial_effect=bool(answer.get("financial_effect")),
            external_communication=bool(answer.get("external_communication")),
            third_party_impact=bool(answer.get("third_party_impact")),
            privacy_disclosure=bool(answer.get("privacy_disclosure")),
            legal_effect=bool(answer.get("legal_effect")),
            security_effect=bool(answer.get("security_effect")),
        )
        return await self.authority.apply_ceiling(owner_id, assessment)

    # --- planning and replanning -------------------------------------------

    async def _build_plan(
        self, owner_id, goal, run: AgentRun, budget: AgentBudget, *, language: str
    ) -> Optional[ActionPlan]:
        from agent.reasoning import make_plan

        budget.cognitive_calls += 1
        run.model_calls = budget.cognitive_calls
        answer = await make_plan(
            goal.for_ai(),
            capabilities=await self.capabilities.available(owner_id),
            context={"today": _now().date().isoformat()},
            language=language,
        )
        if answer is None:
            return None

        steps: List[ActionStep] = []
        for ordinal, raw in enumerate(answer.get("steps") or [][:MAX_PLAN_STEPS]):
            step = self._read_step(raw, ordinal)
            if step is not None:
                steps.append(step)
        if not steps:
            return None

        plan = ActionPlan(
            goal_id=goal.id,
            owner_id=owner_id,
            status="active",
            plan_summary=str(answer.get("plan_summary") or "")[:400],
            expected_outcome=str(answer.get("expected_outcome") or "")[:400],
            assumptions=[str(a)[:200] for a in (answer.get("assumptions") or [])][:6],
            known_constraints=[
                str(c)[:200] for c in (answer.get("known_constraints") or [])
            ][:6],
            steps=steps[:MAX_PLAN_STEPS],
        )
        await self.repo.save_plan(plan)
        await self.repo.journal(
            owner_id, goal.id, kind="plan_made", note=plan.plan_summary,
            detail={"steps": len(plan.steps)},
        )
        return plan

    @staticmethod
    def _read_step(raw: Any, ordinal: int) -> Optional[ActionStep]:
        if not isinstance(raw, dict):
            return None
        step_type = str(raw.get("step_type") or "").strip()
        if step_type not in (
            "inspect", "research", "compare", "prepare", "ask_user", "execute",
            "verify", "wait",
        ):
            return None
        intent = str(raw.get("intent") or "").strip()
        if not intent:
            return None
        ask_kind = raw.get("ask_kind")
        return ActionStep(
            ordinal=ordinal,
            intent=intent[:280],
            step_type=step_type,  # type: ignore[arg-type]
            capability_needed=str(raw.get("capability_needed") or "")[:60],
            expected_result=str(raw.get("expected_result") or "")[:300],
            external_effect=bool(raw.get("external_effect")),
            effect_type=(
                raw.get("effect_type")
                if raw.get("effect_type") in (
                    "create", "modify", "cancel", "send", "transfer", "publish", "remove"
                )
                else "create"
            ),
            effect_target=str(raw.get("effect_target") or "")[:200],
            reaches_somebody_else=bool(raw.get("reaches_somebody_else")),
            parameters=(
                raw.get("parameters") if isinstance(raw.get("parameters"), dict) else {}
            ),
            reversibility=(
                raw.get("reversibility")
                if raw.get("reversibility")
                in ("easily", "with_effort", "hardly", "irreversible")
                else "easily"
            ),
            asks=str(raw.get("asks") or "")[:300],
            ask_kind=ask_kind if ask_kind in ("knowledge", "authority") else None,
        )

    async def _reconsider(
        self, owner_id, goal, plan: ActionPlan, run: AgentRun, budget: AgentBudget,
        *, what_happened: Dict[str, Any], language: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Something happened. Change as little of the plan as accounts for it.
        """
        from agent.reasoning import reconsider

        if budget.cognitive_calls >= budget.max_cognitive_calls:
            # Nothing left to think with. Stopping here is honest; carrying
            # on with the old plan after it has just been contradicted is not.
            return await self._continue_later(
                owner_id, goal, plan, run, "cognitive_calls"
            )

        budget.cognitive_calls += 1
        run.model_calls = budget.cognitive_calls
        run.replans += 1
        answer = await reconsider(
            goal.for_ai(),
            plan=plan.for_ai(),
            what_happened=what_happened,
            capabilities=await self.capabilities.available(owner_id),
            language=language,
        )
        if answer is None:
            return await self._pause(owner_id, goal, plan, run, "il giudizio non era disponibile")

        decision = answer["decision"]
        note = str(answer.get("reasoning") or "")[:300]
        plan.revisions += 1
        await self.repo.journal(
            owner_id, goal.id, kind="replanned", note=note, detail={"decision": decision}
        )

        if decision == "continue":
            await self.repo.save_plan(plan)
            return None

        if decision == "modify":
            revised = [
                self._read_step(raw, len(plan.steps) + n)
                for n, raw in enumerate(answer.get("revised_steps") or [])
            ]
            fresh = [s for s in revised if s is not None][: MAX_PLAN_STEPS - len(plan.steps)]
            if not fresh:
                return await self._pause(owner_id, goal, plan, run, note or "senza altra strada")
            # The history stays: finished steps are not rewritten, and what
            # was learned is not thrown away.
            plan.steps.extend(fresh)
            await self.repo.save_plan(plan)
            return None

        if decision == "wait":
            return await self._wait(
                owner_id, goal, plan, None, run,
                hours=int(answer.get("wait_hours") or 6), note=note,
            )

        if decision == "ask":
            step = ActionStep(
                ordinal=len(plan.steps),
                intent=str(answer.get("asks") or note)[:280],
                step_type="ask_user",
                asks=str(answer.get("asks") or "")[:300],
                ask_kind=(
                    answer.get("ask_kind")
                    if answer.get("ask_kind") in ("knowledge", "authority")
                    else "knowledge"
                ),
            )
            plan.steps.append(step)
            await self.repo.save_plan(plan)
            return await self._ask(owner_id, goal, plan, step, run)

        if decision == "abandon":
            return await self._close(owner_id, goal, plan, run, "abandoned", note)

        return await self._finish(owner_id, goal, plan, run, budget, language=language)

    # --- ends --------------------------------------------------------------

    async def _finish(
        self, owner_id, goal, plan: ActionPlan, run: AgentRun, budget: AgentBudget,
        *, language: str,
    ) -> Dict[str, Any]:
        """
        Every step done. That is not the same as the outcome being true.

        Two judgements, and they are not the same kind of thing. The model is
        shown what was actually found — with each piece saying where it came
        from and how old it is — and decides whether the outcome holds. Then
        code decides whether anything real is behind that conclusion, and
        that second decision cannot be argued with because it is never asked.
        """
        from agent.reasoning import verify_goal

        evidence = await self.evidence.for_goal(owner_id, goal.id)
        intents = await self.executor.intents_for(owner_id, goal.id)
        receipts = await self.executor.receipts_for(owner_id, goal.id)

        if budget.cognitive_calls >= budget.max_cognitive_calls:
            return await self._continue_later(
                owner_id, goal, plan, run, "cognitive_calls"
            )

        budget.cognitive_calls += 1
        run.model_calls = budget.cognitive_calls
        answer = await verify_goal(
            goal.for_ai(),
            evidence={
                "what_was_found": for_verification(evidence),
                "steps": [s.for_ai() for s in plan.steps],
                "what_was_prepared": intents,
                # What services said back, and the warning that goes with it.
                "what_the_services_said": [
                    ExecutionReceipt.model_validate(r).for_ai() for r in receipts
                ],
            },
            language=language,
        )
        if answer is None:
            return await self._pause(owner_id, goal, plan, run, "la verifica non era disponibile")

        verification = GoalVerification(
            goal_id=goal.id,
            outcome=answer["outcome"],
            reasoning=str(answer.get("reasoning") or "")[:400],
            what_is_missing=str(answer.get("what_is_missing") or "")[:300],
            revisit_in_hours=answer.get("revisit_in_hours"),
        )
        await self.repo.journal(
            owner_id, goal.id, kind="verified", note=verification.reasoning,
            detail={
                "outcome": verification.outcome,
                "evidence": len(evidence),
                "anything_real": real_support(evidence),
            },
        )

        if verification.outcome == "achieved":
            refusal = _why_not_complete(evidence, intents, receipts)
            if refusal:
                # The gate. Two ways of not being allowed to finish, and both
                # are the same mistake wearing different clothes: concluding
                # that the world changed from something that did not touch
                # it. This is the debt Sprint 1 closed with, and it is paid
                # in code rather than in a prompt, because a prompt can be
                # talked round and a boolean cannot.
                await self.repo.journal(
                    owner_id, goal.id, kind="completion_refused", note=refusal,
                    detail={"model_said": "achieved", "evidence": len(evidence)},
                )
                logger.info(
                    "agent completion refused goal=%s: %s", goal.id, refusal
                )
                return await self._pause(
                    owner_id, goal, plan, run,
                    "quello che è stato fatto non prova che sia davvero risolto",
                )

            await self.executor.mark_verified(owner_id, goal.id)
            result = await self._close(
                owner_id, goal, plan, run, "completed", verification.reasoning
            )
            await self._observe_life_change(owner_id, goal, verification, evidence)
            return result

        if verification.outcome in ("waiting_for_external_result", "needs_followup"):
            return await self._wait(
                owner_id, goal, plan, None, run,
                hours=int(verification.revisit_in_hours or 12),
                note=verification.reasoning,
            )

        if verification.outcome == "not_achieved":
            return await self._close(
                owner_id, goal, plan, run, "failed", verification.reasoning
            )

        # `partially_achieved` and `uncertain` are not endings.
        return await self._pause(
            owner_id, goal, plan, run,
            verification.what_is_missing or verification.reasoning,
        )

    async def _ask(
        self, owner_id, goal, plan: ActionPlan, step: ActionStep, run: AgentRun
    ) -> Dict[str, Any]:
        step.status = "blocked"
        plan.status = "waiting"
        goal.status = "waiting"
        goal.requires_user_input = step.ask_kind == "knowledge"
        goal.requires_user_authority = step.ask_kind == "authority"
        await self.repo.save_plan(plan)
        await self.repo.save_goal(goal)
        await self.repo.journal(
            owner_id, goal.id, kind="asked", note=step.asks or step.intent,
            detail={"kind": step.ask_kind},
        )
        await self._note_ambient(owner_id, "agent_waiting", goal)
        return {
            "ok": True,
            "state": "waiting_for_person",
            "asks": step.asks or step.intent,
            "kind": step.ask_kind,
            "goal": goal.for_human(),
        }

    async def _awaiting_authority(
        self, owner_id, goal, plan: ActionPlan, run: AgentRun, step: ActionStep
    ) -> Dict[str, Any]:
        plan.status = "waiting"
        goal.status = "waiting"
        goal.requires_user_authority = True
        await self.repo.save_plan(plan)
        await self.repo.save_goal(goal)
        await self._note_ambient(owner_id, "agent_preparation_completed", goal)
        return {
            "ok": True,
            "state": "awaiting_authority",
            "asks": step.intent,
            "kind": "authority",
            "goal": goal.for_human(),
        }

    async def _wait(
        self, owner_id, goal, plan: ActionPlan, step: Optional[ActionStep],
        run: AgentRun, *, hours: int, note: str = "",
    ) -> Dict[str, Any]:
        """
        Depend on something that has not happened, and arrange to look again.

            NO POLLING.

        The ambient runtime already knows how to be somewhere at a time. This
        borrows it rather than growing a timer of its own.
        """
        hours = max(MIN_WAIT_HOURS, min(MAX_WAIT_HOURS, int(hours or 6)))
        if step is not None:
            step.status = "waiting"
        plan.status = "waiting"
        goal.status = "waiting"
        await self.repo.save_plan(plan)
        await self.repo.save_goal(goal)

        try:
            from ambient.service import AmbientService

            await AmbientService(self.db).schedule(
                owner_id,
                reason="opportunity_revisit",
                when=_now() + timedelta(hours=hours),
                source_ref=f"goal:{goal.id}",
                provenance="model",
            )
        except Exception as e:
            logger.info("agent wake soft-fail: %s", type(e).__name__)

        await self.repo.journal(owner_id, goal.id, kind="waiting", note=note)
        await self._note_ambient(owner_id, "agent_waiting", goal)
        return {"ok": True, "state": "waiting", "for_hours": hours, "goal": goal.for_human()}

    async def _pause(
        self, owner_id, goal, plan: ActionPlan, run: AgentRun, note: str
    ) -> Dict[str, Any]:
        plan.status = "active"
        await self.repo.save_plan(plan)
        await self.repo.journal(owner_id, goal.id, kind="paused", note=note)
        return {"ok": True, "state": "in_progress", "goal": goal.for_human()}

    async def _stop(self, goal, run: AgentRun, note: str) -> Dict[str, Any]:
        goal.status = "failed"
        goal.rationale = note[:300]
        await self.repo.save_goal(goal)
        return {"ok": False, "state": "failed", "reason": note}

    async def _close(
        self, owner_id, goal, plan: ActionPlan, run: AgentRun, status: str, note: str
    ) -> Dict[str, Any]:
        goal.status = status  # type: ignore[assignment]
        goal.rationale = note[:300]
        goal.completed_at = _now().isoformat()
        plan.status = "completed" if status == "completed" else "cancelled"
        await self.repo.save_goal(goal)
        await self.repo.save_plan(plan)
        await self.repo.journal(owner_id, goal.id, kind=f"goal_{status}", note=note)
        # A goal that ended has no use for the question it was going to ask.
        # What it already told them is history and stays: the two are settled
        # differently because they are different things.
        await self.needs.close_for_goal(
            owner_id, goal.id, why="l'obiettivo si è chiuso",
            kinds={"needs_information", "needs_authority"},
        )
        if status == "completed":
            await self._note_ambient(owner_id, "agent_goal_completed", goal)
            await self._resolve_opportunity(owner_id, goal)
        return {"ok": True, "state": status, "goal": goal.for_human()}


    # --- whether to say anything about it ----------------------------------

    async def _consider_visibility(
        self, owner_id: str, goal_id: str, run: AgentRun, budget: AgentBudget,
        *, language: str = "it",
    ) -> Optional[Any]:
        """
        Ask whether the work just done is worth showing.

            DO NOT CONFUSE AVOIDING INTERRUPTION WITH HIDING USEFUL WORK.

        Asked at the end of a run rather than after each step, because a
        judgement per step is the narration it exists to prevent — and asked
        only when the run actually wrote something down, because a run that
        did nothing offers nothing to judge. That second gate is about
        whether there is any material, never about what the answer should be:
        nothing here reads the goal's status, and a test walks this file to
        keep it that way.
        """
        goal = await self.repo.get_goal(owner_id, goal_id)
        if goal is None:
            return None

        what_happened = await self._run_facts(owner_id, goal, run)
        if not what_happened["refs"]:
            # The run left no trace, so there is nothing that could be shown
            # with proof behind it. Not a decision that it was uninteresting.
            return None

        if budget.cognitive_calls >= budget.max_cognitive_calls:
            logger.info("visibility skipped: budget spent goal=%s", goal_id)
            return None

        budget.cognitive_calls += 1
        decision = await self.visibility.consider(
            owner_id, goal, what_happened=what_happened, language=language
        )
        await self.repo.journal(
            owner_id, goal_id, kind="visibility",
            note=decision.headline or decision.quietened_by_code or decision.reasoning,
            detail={
                "outcome": decision.outcome,
                "decided_by": decision.decided_by,
                "quietened": decision.quietened_by_code or None,
            },
        )
        if decision.is_visible:
            await self.visibility.show(owner_id, goal, decision)
            await self._raise_need(owner_id, goal, decision, what_happened)
        return decision

    async def _raise_need(
        self, owner_id: str, goal, decision, what_happened: Dict[str, Any]
    ) -> Optional[CommunicationNeed]:
        """
        Turn a judgement that this is worth showing into a need that can reach
        somebody — and then hand it to the layer that decides whether it does.

            A NEED FOR THE USER IS NOT AUTOMATICALLY A PUSH.

        `quiet_update` stops at the ambient line above: it is worth finding,
        not worth reaching for anybody, and giving it a need would put it in
        front of a judgement about interrupting that it has no business being
        in front of. Everything louder gets one.

        What this does NOT do is pick a channel. There is no push here, no
        in-app, no timing, and no branch on what delivery answers — the moment
        one existed, somebody would write `if requires_attention: push()`
        underneath it.
        """
        kind = _need_kind(decision.outcome, goal)
        if kind is None:
            return None

        need = CommunicationNeed(
            owner_id=owner_id,
            goal_id=goal.id,
            kind=kind,
            summary=decision.headline[:200],
            reason=decision.reasoning[:400] or decision.headline[:400],
            source_refs=list(decision.refs)[:8],
            visibility=decision.outcome,
            requires_response=kind in ("needs_information", "needs_authority"),
            response_kind=(
                "authority" if kind == "needs_authority"
                else "information" if kind == "needs_information"
                else None
            ),
            work_already_done=[
                str(row.get("what") or "")[:200]
                for row in (what_happened.get("what_ora_did_this_time") or [])
                if row.get("really_happened")
            ][:6],
            what_is_missing=_what_is_missing(goal),
            valid_until=goal.valid_until,
        )
        raised = await self.needs.raise_need(need)
        await self.repo.journal(
            owner_id, goal.id, kind="need_raised", note=raised.summary,
            detail={"need_id": raised.id, "need_kind": raised.kind,
                    "requires_response": raised.requires_response},
        )

        # And now it is out of the agent's hands. Silence is one of the
        # answers, and it changes nothing about the need.
        await self.needs.offer_to_delivery(owner_id, raised)
        return raised

    async def _run_facts(self, owner_id: str, goal, run: AgentRun) -> Dict[str, Any]:
        """
        What this run actually did, in facts and handles.

        Facts, not verdicts: what was done, what was found, whether anything
        is needed from the person, and what they were told before. Nothing
        here weighs any of it — weighing is what is being bought.
        """
        history = await self.repo.history(owner_id, goal.id, limit=30)
        fresh = [row for row in history if str(row.get("at") or "") >= run.at]

        did: List[Dict[str, Any]] = []
        refs: List[str] = []
        for row in fresh:
            detail = row.get("detail") or {}
            if row.get("kind") in ("step_done", "verified", "goal_completed",
                                   "goal_abandoned", "asked", "awaiting_authority",
                                   "completion_refused", "life_observation"):
                did.append({
                    "what": row.get("note", "")[:200],
                    "really_happened": detail.get("really_happened"),
                    "came_from": detail.get("came_from"),
                })
                refs.append(f"journal:{row.get('at')}")

        evidence = await self.evidence.for_goal(owner_id, goal.id)
        found = [e.for_ai() for e in evidence if e.is_real][-6:]
        refs.extend(e.id for e in evidence if e.is_real)

        return {
            "what_ora_did_this_time": did[-8:],
            "what_it_found": found,
            "how_it_stands": {
                # State as a fact about the world, said in the same words a
                # person would hear — not a status code to switch on.
                "still_going": goal.is_open,
                "finished": goal.status == "completed",
                "gave_up": goal.status in ("abandoned", "failed"),
                "needs_something_only_they_know": goal.requires_user_input,
                "needs_their_permission": goal.requires_user_authority,
                "what_it_was_for": goal.desired_outcome,
            },
            "is_there_something_for_them_to_do": (
                goal.requires_user_input or goal.requires_user_authority
            ),
            "refs": refs[:8],
        }

    # --- what a person may do about it -------------------------------------

    async def cancel(self, owner_id: str, goal_id: str, *, reason: str = "") -> Dict[str, Any]:
        """
        "Lascia perdere." Future work stops; what already happened stands.

        The wakes go too — an alarm for a goal nobody is pursuing is a process
        that will wake up, find nothing, and have cost something.
        """
        goal = await self.repo.get_goal(owner_id, goal_id)
        if goal is None:
            return {"ok": False, "reason": "unknown_goal"}

        goal.status = "cancelled"
        goal.decision_provenance = "user"
        goal.rationale = (reason or "l'utente ha detto di lasciar perdere")[:300]
        await self.repo.save_goal(goal)

        plan = await self.repo.plan_for(owner_id, goal_id)
        if plan is not None:
            plan.status = "cancelled"
            await self.repo.save_plan(plan)

        try:
            from ambient.repository import AmbientRepository

            await AmbientRepository(self.db).cancel_for(owner_id)
        except Exception as e:
            logger.info("agent wake cancel soft-fail: %s", type(e).__name__)

        # Nobody is pursuing this any more, so nobody has to answer anything
        # about it. Needs, plans and alarms go together or the leftovers of
        # one keep the others alive.
        await self.needs.close_for_goal(
            owner_id, goal_id, why="l'utente ha lasciato perdere"
        )
        await self.repo.journal(owner_id, goal_id, kind="cancelled", note=goal.rationale)
        return {"ok": True, "state": "cancelled"}

    async def answer(
        self, owner_id: str, goal_id: str, *, reply: str, step_id: str = "",
        language: str = "it",
    ) -> Dict[str, Any]:
        """A person supplied what was missing. Carry on from where it stopped."""
        goal = await self.repo.get_goal(owner_id, goal_id)
        plan = await self.repo.plan_for(owner_id, goal_id)
        if goal is None or plan is None:
            return {"ok": False, "reason": "unknown_goal"}

        # The answer attaches to the blocker it answers, and becomes
        # evidence like anything else — with `user_statement` as its
        # provenance, because somebody saying a thing is a real source and a
        # different kind of source from having looked.
        answered = None
        for step in plan.steps:
            if step.step_type == "ask_user" and step.status == "blocked":
                if step_id and step.id != step_id:
                    continue
                step.status = "succeeded"
                step.note = f"risposta: {reply[:150]}"
                answered = step
                break

        if answered is not None:
            await self.evidence.record(AgentEvidence(
                owner_id=owner_id,
                goal_id=goal_id,
                step_id=answered.id,
                kind="ask_user",
                claim=reply[:600],
                supports=(answered.asks or answered.intent)[:300],
                provenance=ResultProvenance(
                    source_class="user_statement",
                    capability="ask_user",
                    freshness="fresh",
                ),
            ))

        goal.status = "active"
        goal.requires_user_input = False
        plan.status = "active"
        await self.repo.save_goal(goal)
        await self.repo.save_plan(plan)
        # They answered. That settles the need — and only an answer does: a
        # notification that was delivered, or opened, or ignored, leaves it
        # exactly as open as it was.
        for need in await self.needs.open_for_goal(owner_id, goal_id):
            if need.kind == "needs_information":
                await self.needs.satisfy(
                    owner_id, need.id, how="ha risposto", by="user"
                )
        await self.repo.journal(owner_id, goal_id, kind="answered", note=reply[:200])
        return await self.advance(owner_id, goal_id, language=language)

    async def standing_offer(self, owner_id: str, goal_id: str) -> Optional[str]:
        """
        What a standing permission would allow here, if offering one is safe.

            A PERSISTENT GRANT MUST BE EXPLICIT.
            NO GLOBAL AUTONOMY.

        `None` is the ordinary answer and the safe one: nothing is offered
        unless there is a prepared effect small enough that a person reading
        one sentence has read the whole permission. Anything that reaches
        somebody else, costs money, commits them, is public or destroys
        something is never offered — not because the engine could not scope a
        grant for it, but because «puoi farlo anche in futuro» is a decision
        somebody makes in two seconds, and it must not be possible to make it
        about something that deserves longer.

        The sentence is the promise, never the mechanism. A surface cannot
        show a capability name, an effect scope or a grant id because it is
        never given one.
        """
        from agent.authority import effect_is_commandable

        goal = await self.repo.get_goal(owner_id, goal_id)
        plan = await self.repo.plan_for(owner_id, goal_id)
        if goal is None or plan is None:
            return None

        for step in plan.steps:
            if step.status != "blocked" or step.step_type != "execute":
                continue
            intent = self.executor._intent_for(owner_id, goal, step)
            # The same predicate that decides whether an instruction may carry
            # authority. Not a coincidence: both questions are «is this small
            # enough that one sentence from a person settles it», and having
            # two answers to that would be having two safety boundaries.
            allowed, _why = effect_is_commandable(intent.effect)
            if not allowed:
                continue
            if await self.authority.has_grant(owner_id, step.capability_needed):
                # Already allowed. Offering it again would be asking somebody
                # to decide something they have decided.
                continue
            return _grant_sentence(intent.effect)
        return None

    async def authorise(
        self, owner_id: str, goal_id: str, *, capability: str = "",
        persistent: bool = False, language: str = "it",
    ) -> Dict[str, Any]:
        """
        A person said yes to the thing that was prepared.

            APPROVE IS NOT A GENERIC YES.
            ONE-TIME APPROVAL IS NOT A STANDING PERMISSION.

        Two things can happen here and they are deliberately different. A
        plain yes records a **consent**, bound by hash to exactly the effect
        that was shown — change the time or add a guest afterwards and it
        stops matching, and the person is asked again. `persistent` is the
        second thing, and it only ever happens because somebody asked for it:
        approving five times does not quietly become a standing permission,
        because the fifth approval is not a different act from the first.

        The grant, when there is one, is scoped from the effect that was
        actually approved. Nothing here widens it, and there is nowhere for a
        model to reach.
        """
        goal = await self.repo.get_goal(owner_id, goal_id)
        plan = await self.repo.plan_for(owner_id, goal_id)
        if goal is None or plan is None:
            return {"ok": False, "reason": "unknown_goal"}

        approved: List[Dict[str, Any]] = []
        for step in plan.steps:
            if step.status != "blocked" or step.step_type != "execute":
                continue
            if capability and step.capability_needed != capability:
                continue

            intent = self.executor._intent_for(owner_id, goal, step)
            consent = await self.authority.consent(
                owner_id, intent, decision="approved", goal_id=goal_id,
                shown=intent.effect.for_human(),
            )
            step.status = "pending"
            step.attempts = 0
            approved.append({
                "capability": step.capability_needed,
                "consent_id": consent.id,
                "effect": intent.effect.for_human(),
            })

            if persistent:
                # Scoped to what was approved and nothing wider: the kind of
                # change, and every flag that was false stays disallowed.
                await self.authority.grant(
                    owner_id, step.capability_needed, by="user",
                    effect_scope=[intent.effect.effect_type],
                    allows_external_party=intent.effect.external_party,
                    allows_financial=intent.effect.financial_effect,
                    allows_public=intent.effect.public_visibility,
                    allows_destructive=intent.effect.destructive,
                    human_summary=_grant_sentence(intent.effect),
                )

        if not approved:
            return {"ok": False, "reason": "nothing_to_authorise"}

        for need in await self.needs.open_for_goal(owner_id, goal_id):
            if need.kind == "needs_authority":
                await self.needs.satisfy(
                    owner_id, need.id, how="ha dato il via libera", by="user"
                )

        goal.status = "active"
        goal.requires_user_authority = False
        plan.status = "active"
        await self.repo.save_goal(goal)
        await self.repo.save_plan(plan)
        await self.repo.journal(
            owner_id, goal_id, kind="authorised",
            note="; ".join(a["capability"] for a in approved),
            detail={"by": "user", "also_for_the_future": bool(persistent),
                    "consents": [a["consent_id"] for a in approved]},
        )
        return await self.advance(owner_id, goal_id, language=language)

    async def deny(
        self, owner_id: str, goal_id: str, *, capability: str = "", reason: str = "",
        language: str = "it",
    ) -> Dict[str, Any]:
        """
        A person said no to what was prepared.

            A REFUSAL IS AN ANSWER, NOT A ROUND OF NEGOTIATION.

        Nothing is executed. The no is recorded twice, against two different
        things, because they stop two different mistakes: against the *effect*,
        so this exact act is not re-proposed, and against the *capability*, so
        the same door is not knocked on again this month. Then the model gets
        to decide what the goal looks like without that action — another
        route, or no goal at all. What it may not do is come back with the
        same request, because the ceiling now refuses it outright.
        """
        goal = await self.repo.get_goal(owner_id, goal_id)
        plan = await self.repo.plan_for(owner_id, goal_id)
        if goal is None or plan is None:
            return {"ok": False, "reason": "unknown_goal"}

        refused = capability
        for step in plan.steps:
            if step.status == "blocked" and step.step_type == "execute":
                refused = refused or step.capability_needed
                # Against the effect: a no to this act is a no to this act.
                await self.authority.consent(
                    owner_id, self.executor._intent_for(owner_id, goal, step),
                    decision="denied", goal_id=goal_id,
                )
                step.status = "skipped"
                step.note = "l'utente ha detto di no"

        if refused:
            await self.authority.deny(owner_id, refused, reason=reason)

        # A no is an answer. The need is settled, not left hanging — asking
        # again is exactly what the refusal was about.
        for need in await self.needs.open_for_goal(owner_id, goal_id):
            if need.kind == "needs_authority":
                await self.needs.satisfy(
                    owner_id, need.id, how="ha detto di no", by="user"
                )

        goal.requires_user_authority = False
        goal.status = "active"
        plan.status = "active"
        await self.repo.save_goal(goal)
        await self.repo.save_plan(plan)
        await self.repo.journal(
            owner_id, goal_id, kind="authority_denied", note=refused,
            detail={"by": "user", "reason": reason[:200]},
        )

        run = AgentRun(owner_id=owner_id, goal_id=goal_id)
        budget = AgentBudget()
        outcome = await self._reconsider(
            owner_id, goal, plan, run, budget,
            what_happened={
                "problem": "la persona non ha autorizzato questa azione",
                "capability": refused,
                "why": reason[:200] or None,
            },
            language=language,
        )
        if outcome is not None:
            return outcome
        return {"ok": True, "state": "in_progress", "goal": goal.for_human()}

    # --- what a person sees ------------------------------------------------

    async def for_home(self, owner_id: str) -> List[Dict[str, Any]]:
        """
        Outcomes and states of affairs. Never steps, never plan status.

            THE USER SHOULD EXPERIENCE OUTCOMES, NOT WORKFLOWS.
        """
        out: List[Dict[str, Any]] = []
        for goal in await self.repo.open_goals(owner_id, limit=3):
            out.append({
                **goal.for_human(),
                "state": await self._progress_of(owner_id, goal),
            })
        return out

    async def _progress_of(self, owner_id: str, goal) -> str:
        """
        What to say about a goal that is still open, from what really happened.

            NO FAKE PROGRESS.

        «Sto lavorando…» is the sentence a system says when it has nothing to
        report and would rather not admit it. Everything below either comes
        from a state that is true by definition — waiting on a person, done —
        or from a journal line written by work that actually ran, with the
        provenance it was written with. A goal that has done nothing yet says
        so.
        """
        if goal.status == "waiting" and not (
            goal.requires_user_input or goal.requires_user_authority
        ):
            # Waiting on the world, not on them — and «sto aspettando una
            # risposta» is then a false sentence, newly visible now that a
            # person can answer inside the thread and read the reply. What is
            # true is whatever the run wrote down when it decided to wait, so
            # that is what gets said.
            history = await self.repo.history(owner_id, goal.id, limit=20)
            waited = [row for row in history if row.get("kind") == "waiting"]
            note = str((waited[-1].get("note") if waited else "") or "").strip()
            if note:
                return note[:200]
        if not goal.is_open or goal.status == "waiting":
            return _human_state(goal)

        history = await self.repo.history(owner_id, goal.id, limit=20)
        done = [
            row for row in history
            if row.get("kind") == "step_done"
            and (row.get("detail") or {}).get("really_happened")
        ]
        if not done:
            # Nothing real has happened. Saying it is being handled would be
            # the fake presence this whole rule exists against.
            return "Non ho ancora cominciato."

        return _what_was_being_done((done[-1].get("detail") or {}).get("came_from", ""))


    async def _observe_life_change(
        self, owner_id: str, goal, verification, evidence
    ) -> None:
        """
        A verified outcome may have changed something worth remembering.

            ACTION RESULT -> OBSERVATION -> VALIDATION -> LIFE UPDATE.
            NEVER TOOL OUTPUT -> CANONICAL FACT.

        This is the loop that makes the agent worth having: work produces a
        result, the result is checked, and what is now true about somebody's
        life is available the next time anything reasons about them.

        It is also the most dangerous thing in the file, so it does not write
        anything itself. It proposes, through the governance that already
        owns durable learning, and that governance is free to refuse, ask for
        confirmation, or decide this contradicts something already known. The
        two conditions below are checked here anyway rather than delegated:
        an outcome that was not verified, or was verified on nothing real,
        never even becomes a proposal.
        """
        if verification.outcome != "achieved":
            return
        if not real_support(evidence):
            return

        try:
            from conversation_engine.ai_core.models import MemoryCandidate
            from life_memory.governance import MemoryGovernanceService
        except Exception as e:
            logger.info("life observation import soft-fail: %s", type(e).__name__)
            return

        supporting = [e for e in evidence if e.is_real][:6]
        candidate = MemoryCandidate(
            operation="propose",
            summary=goal.desired_outcome[:600],
            kind="agent_outcome",
            authority="structured",
            epistemic_status="asserted",
            confidence=0.7,
            permanence="unknown",
            # Handles, so anybody asking «how do you know» has somewhere to
            # look. Never the content of what was found.
            provenance=[f"agent_goal:{goal.id}"] + [e.id for e in supporting][:6],
            evidence_refs=[e.id for e in supporting][:6],
            reason_for_future_utility=(
                "Risultato di un obiettivo portato a termine e verificato."
            ),
        )

        try:
            outcome = await MemoryGovernanceService(self.db).apply(
                user_id=owner_id,
                session_id=f"agent:{goal.id}",
                # The same goal proposing twice is the same proposal, and
                # governance keys off this to say so rather than duplicating.
                reasoning_epoch=f"agent:{goal.id}",
                candidate=candidate,
                candidate_index=0,
            )
        except Exception as e:
            logger.info("life observation soft-fail: %s", type(e).__name__)
            return

        await self.repo.journal(
            owner_id, goal.id, kind="life_observation",
            note=goal.desired_outcome[:300],
            detail={"decision": outcome.decision, "persisted": outcome.persisted},
        )

    async def _note_ambient(self, owner_id: str, kind: str, goal) -> None:
        """
        Proof of work, written by the work.

        Reuses V3.8's AmbientActivity, which means the same rule applies: the
        record is written because something happened, and a surface that
        wanted a line cannot produce one.

        A finished goal is the one case that carries a sentence and is
        visible. Everything else here is internal, because a goal being
        started or waiting is not news — but a goal that is done disappears
        from the list of what ORA is handling, and disappearing silently is
        indistinguishable from never having happened.
        """
        finished = kind == "agent_goal_completed"
        try:
            from delivery.service import DeliveryService

            await DeliveryService(self.db).note_activity(
                owner_id,
                kind="review_completed",
                summary=goal.desired_outcome[:200] if finished else "",
                source_refs=[goal.id],
                provenance={"agent": kind, "objective": goal.objective[:120]},
                visible=finished,
            )
        except Exception as e:
            logger.info("agent ambient note soft-fail: %s", type(e).__name__)

    async def _resolve_opportunity(self, owner_id: str, goal) -> None:
        """A goal reaching its outcome may settle the concern it came from."""
        if not goal.opportunity_id:
            return
        try:
            from opportunities.service import OpportunityService

            await OpportunityService(self.db).resolve(owner_id, goal.opportunity_id)
        except Exception as e:
            logger.info("opportunity resolve soft-fail: %s", type(e).__name__)


def _grant_sentence(effect) -> str:
    """
    What a standing permission says, in words somebody would recognise.

    Shown back when they ask what they allowed, so it has to be the promise
    rather than the mechanism — and narrow enough that reading it is the same
    as reading the scope.
    """
    # The target names a place; the verb has to name an act that fits inside
    # it. Written as a phrase rather than a bare infinitive because "aggiungere
    # il tuo calendario" is not a sentence anybody would say, and a permission
    # people have to decode is one they cannot weigh.
    act = {
        "create": "posso aggiungere quello che serve",
        "modify": "posso cambiare quello che c'è",
        "cancel": "posso annullare quello che c'è",
        "remove": "posso togliere quello che c'è",
        "send": "posso mandare quello che serve",
        "transfer": "posso spostare quello che serve",
        "publish": "posso pubblicare quello che serve",
    }.get(effect.effect_type, "posso agire")
    where = (effect.target or "questa cosa").strip()

    # Every clause after the first is a *limit*, and they are here because a
    # permission whose boundaries are invisible is one nobody can weigh. What
    # is deliberately absent is any way to say "everything": no branch below
    # produces an unbounded sentence, because there is no unbounded grant for
    # it to describe.
    limits = ["senza chiedertelo ogni volta"]
    if not effect.external_party:
        limits.append("senza coinvolgere altre persone")
    if not effect.destructive and effect.effect_type not in ("cancel", "remove"):
        limits.append("senza cancellare niente")
    head = where[0].upper() + where[1:] if where else where
    return f"{head}: {act}, " + ", ".join(limits) + "."


def _need_kind(visibility: str, goal) -> Optional[str]:
    """
    From "how much is this worth showing" to "why the person is being brought in".

    Two semantic fields, both decided upstream by a model — not a channel.
    `silent` and `quiet_update` produce nothing: the first has nothing to say
    and the second is already where somebody will find it, and putting it in
    front of a judgement about interrupting would be asking the wrong question
    about it.

    Which *kind* of asking follows the agent's own earlier judgement about
    what it is blocked on. Code is not deciding that a waiting goal needs
    permission; it is reading which of the two the reasoning already said.
    """
    if visibility in ("silent", "quiet_update"):
        return None
    if visibility == "inform_user":
        return "useful_result"

    # ask_user and requires_attention both mean somebody is wanted.
    if goal.requires_user_authority:
        return "needs_authority"
    if goal.requires_user_input:
        return "needs_information"
    # Worth their attention, and not a question. A finished thing, or a
    # stopped one.
    return "important_outcome"


def _what_is_missing(goal) -> str:
    """The one thing still wanted, in the words the plan already used."""
    if goal.requires_user_authority:
        return "Serve il tuo via libera."
    if goal.requires_user_input:
        return "Manca una cosa che sai solo tu."
    return ""


def _why_not_complete(evidence, intents, receipts=None) -> str:
    """
    Whether anything real stands behind calling this done. Code's answer.

        NO COMPLETION THEATRE.
        SIMULATED IS NOT OBSERVED.

    Two refusals, and the second is the one that matters most. The first says
    a goal cannot be closed when nothing that happened says anything about
    the world. The second says a goal cannot be closed when the thing that
    was supposed to change the world was a stand-in — even if plenty of real
    reading happened around it, because reading is not doing, and an outcome
    that depended on an act being carried out is not true because the act was
    convincingly imitated.

    Never shown to a model, never passed through a prompt, and deliberately
    dull: it reads a source class and a capability name that the executing
    code wrote down, and returns a string or nothing.
    """
    if not real_support(evidence):
        return "niente di reale sostiene questo esito"
    pretended = sorted({
        str(i.get("capability") or "")
        for i in intents
        if i.get("status") in ("executed", "verified")
        and not is_really_wired(str(i.get("capability") or ""))
    })
    if pretended:
        return f"l'azione che avrebbe cambiato le cose era simulata: {', '.join(pretended)}"

    # The third bar, and the one this sprint added. A service taking a request
    # is not the world changing: an event that was accepted and could not
    # afterwards be found is exactly the case where a system that stops at the
    # receipt tells somebody it is in their calendar when it is not.
    unseen = sorted({
        str(r.get("capability") or "")
        for r in (receipts or [])
        if r.get("provider_status") == "accepted"
    })
    if unseen:
        return (
            "il servizio ha accettato la richiesta ma non risulta ancora fatta: "
            + ", ".join(unseen)
        )
    return ""


def _what_was_being_done(came_from: str) -> str:
    """
    One sentence for the kind of work that last actually happened.

    Keyed on where the last result came from — which is a fact the executing
    code wrote down — and not on anything about the subject. A sentence
    chosen by what the goal is about would be a domain template, and it would
    be wrong the first time somebody's life did not match it.
    """
    return {
        "external_research": "Ho cercato quello che serviva.",
        "deterministic_computation": "Sto confrontando le opzioni.",
        "connected_provider": "Sto controllando come stanno le cose.",
        "internal_observation": "Sto guardando quello che ho già.",
        "user_statement": "Sto tenendo conto di quello che mi hai detto.",
    }.get(came_from, "Me ne sto occupando.")


def _human_state(goal) -> str:
    """
    One sentence a person would say. Never a status.

    `waiting` splits in two because the two mean entirely different things to
    somebody reading it: one is ORA waiting on the world, the other is ORA
    waiting on them.
    """
    if goal.status == "waiting" and goal.requires_user_authority:
        return "È tutto pronto, mi serve solo il tuo via libera."
    if goal.status == "waiting" and goal.requires_user_input:
        return "Mi manca una cosa che sai solo tu."
    if goal.status == "waiting":
        return "Sto aspettando una risposta."
    if goal.status == "completed":
        return "Fatto."
    return "Me ne sto occupando."
