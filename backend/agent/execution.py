"""
Doing the steps that may be done, and refusing the ones that may not.

    REASONING DOES NOT REQUIRE CONSENT.
    REAL-WORLD EFFECTS MAY REQUIRE AUTHORITY.
    EXECUTOR DOES NOT DECIDE MEANING.

Reading, researching, comparing and drafting run for real — they cost the
person nothing, and asking about them is what turns an agent into a quiz.
Anything that would change something outside ORA stops at `prepared`: an
`ActionIntent` written down, everything up to the door done, and nothing
pushed through it.

Sprint 2 changes what "run for real" means. In Sprint 1 every capability was
a stand-in, so every step succeeded and a verifier had nothing to distinguish.
Now each capability reaches something that already exists and returns what it
actually found — including finding nothing, and including a provider that is
not connected, which is a different answer from an empty one.

What this file will not do is interpret. It calls a capability and reports
facts: what happened, where it came from, and what was found. Whether that
means the goal is achieved, whether to ask, whether to replan — none of that
is decided here, and none of the code below could express it.

Every executable intent carries an idempotency key derived from what the
effect is, not when it was tried, so a retry after a timeout is recognisably
the same intent and the same effect cannot happen twice.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent import providers
from agent import effects
from agent.capabilities import CapabilityResolver, resolution_is_stubbed
from agent.evidence import EvidenceStore
from agent.models import (
    ActionEffect,
    ActionIntent,
    ActionStep,
    AgentEvidence,
    ExecutionReceipt,
    ExecutionResult,
    ResultProvenance,
)

logger = logging.getLogger(__name__)

ATTEMPTS = "agent_action_attempts"
RECEIPTS = "agent_receipts"

# How many times one step is retried before the plan has to find another way.
# A technical bound: whether a failure is worth a different approach is the
# model's call, but whether to keep hammering is not.
MAX_STEP_ATTEMPTS = 3

# What each kind of step is answered by. Deliberately a mapping from step
# *type*, never from anything about the situation: the day this dictionary
# starts keying off a word in the goal is the day it becomes a set of domain
# templates, and a test walks this file to make sure it has not.
_BY_STEP_TYPE = {
    "inspect": "read",
    "research": "research",
    "compare": "compare",
    "prepare": "prepare",
    "verify": "read",
}


# Which read answers which capability. A table, not a decision: adding a
# capability here is wiring, and nothing about the situation reaches it.
_READERS = {
    "calendar.read": providers.read_calendar,
    "document.read": providers.read_documents,
    "information.read": providers.read_internal_state,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StepExecutor:
    def __init__(self, db):
        self.db = db
        self.capabilities = CapabilityResolver(db)
        self.evidence = EvidenceStore(db)

    async def ensure_indexes(self) -> None:
        try:
            await self.db[ATTEMPTS].create_index("idempotency_key", unique=True)
            await self.db[RECEIPTS].create_index("idempotency_key")
            await self.db[RECEIPTS].create_index([("owner_id", 1), ("goal_id", 1)])
        except Exception:
            logger.exception("indice idempotenza non creato (non fatale)")
        await self.evidence.ensure_indexes()

    async def run(
        self,
        owner_id: str,
        goal,
        step: ActionStep,
        *,
        may_touch_the_world: bool,
        budget=None,
        recheck=None,
    ) -> ExecutionResult:
        """
        Carry out one step, as far as it is allowed to go.

        `may_touch_the_world` comes from the authority ceiling and is the only
        thing that opens the door. This function never decides it, and there
        is no other parameter that could.
        """
        resolution = await self.capabilities.resolve(owner_id, step.capability_needed)

        if step.capability_needed and not resolution.known:
            return ExecutionResult(
                step_id=step.id, status="unavailable",
                observation=(
                    f"Non esiste niente che faccia «{step.capability_needed}». "
                    "Serve un'altra strada."
                ),
                error_type="capability_unknown", retryable=False,
                provenance=ResultProvenance(
                    source_class="internal_observation",
                    capability=step.capability_needed,
                ),
            )

        if step.capability_needed and not resolution.permitted:
            return ExecutionResult(
                step_id=step.id, status="unavailable",
                observation=(
                    "L'accesso a questa cosa non è stato concesso, quindi non "
                    "si può passare di lì."
                ),
                error_type="requires_connection", retryable=False,
                provenance=ResultProvenance(
                    source_class="connected_provider",
                    capability=step.capability_needed,
                ),
            )

        if resolution.writes:
            return await self._touch_the_world(
                owner_id, goal, step, may_touch_the_world, budget=budget,
                recheck=recheck,
            )

        return await self._do_harmless(
            owner_id, goal, step, resolution, budget=budget
        )

    # --- the half that runs -----------------------------------------------

    async def _do_harmless(
        self, owner_id, goal, step, resolution, *, budget
    ) -> ExecutionResult:
        """
        Steps that cost the person nothing. These genuinely run.

        Each one reaches an engine or a collection that already exists, and
        what comes back is turned into evidence with its provenance attached
        — set here, by the code that made the call, because nothing later can
        reconstruct whether a provider was really reached.
        """
        if not resolution.executable and step.capability_needed:
            return ExecutionResult(
                step_id=step.id, status="unavailable",
                observation="Questo non è ancora collegato a niente di reale.",
                error_type="not_wired", retryable=False,
                provenance=ResultProvenance(
                    source_class="internal_observation",
                    capability=step.capability_needed,
                ),
            )

        how = _BY_STEP_TYPE.get(step.step_type)
        if how is None:
            return ExecutionResult(
                step_id=step.id, status="unavailable",
                observation=f"Non c'è modo di eseguire un passo di tipo «{step.step_type}».",
                error_type="unsupported_step", retryable=False,
            )

        if budget is not None:
            budget.capability_calls += 1

        outcome = await self._call(owner_id, goal, step, how, budget=budget)
        return await self._as_result(owner_id, goal, step, outcome)

    async def _call(self, owner_id, goal, step, how: str, *, budget):
        """
        Ask the capability. One place, so provenance cannot be forgotten.
        """
        capability = (step.capability_needed or "").strip()

        if how == "research":
            if budget is not None and budget.research_exhausted():
                # A ceiling, not a judgement. The plan is told plainly so it
                # can wait or route around rather than believing there was
                # nothing to find.
                return providers.CapabilityOutcome(
                    status="waiting",
                    observation="Ho già cercato quanto era previsto per questo giro.",
                    provenance=ResultProvenance(
                        source_class="external_research", capability="web.research"
                    ),
                    error_type="research_budget_spent",
                    retryable=True,
                )
            if budget is not None:
                budget.research_calls += 1
            return await providers.do_research(self.db, owner_id, goal, step)

        if how == "compare":
            refs = await self.evidence.research_refs(owner_id, goal.id)
            return await providers.do_comparison(
                self.db, owner_id, goal, step, research_refs=refs
            )

        if how == "prepare":
            return await providers.prepare_locally(self.db, owner_id, goal, step)

        # A read. Which one is settled by the capability the model named, and
        # by nothing else about the case — a lookup rather than a chain of
        # comparisons, so that no branch in this file can ever come to depend
        # on what a goal happens to be about.
        reader = _READERS.get(capability, providers.read_internal_state)
        return await reader(self.db, owner_id, goal)

    async def _as_result(self, owner_id, goal, step, outcome) -> ExecutionResult:
        """
        Turn what a capability found into a result, and keep the evidence.

        The claims are stored rather than passed along in the result, because
        the thing that needs them later is verification, and a result that
        carries its own evidence around is a result that grows until it
        cannot be logged.
        """
        refs: List[str] = []
        for claim in outcome.claims:
            evidence = AgentEvidence(
                owner_id=owner_id,
                goal_id=goal.id,
                step_id=step.id,
                kind=step.step_type,
                claim=claim.text,
                supports=claim.supports or (step.expected_result or "")[:300],
                provenance=outcome.provenance,
            )
            await self.evidence.record(evidence)
            refs.append(evidence.id)

        return ExecutionResult(
            step_id=step.id,
            status=outcome.status,
            observation=outcome.observation[:600],
            result_refs=[outcome.data_ref] if outcome.data_ref else [],
            error_type=outcome.error_type,
            retryable=outcome.retryable,
            provenance=outcome.provenance,
            evidence_refs=refs[:12],
            data_ref=outcome.data_ref,
        )

    # --- the half that stops ----------------------------------------------

    async def _touch_the_world(
        self, owner_id, goal, step: ActionStep, may_touch_the_world: bool, *,
        budget, recheck=None,
    ) -> ExecutionResult:
        """
        Write down exactly what would happen, then — only if allowed — do it.

            REAL-WORLD EFFECTS REQUIRE SUFFICIENT AUTHORITY.
            AUTHORITY IS RECHECKED WHERE IT IS USED, NOT WHERE IT WAS DECIDED.

        The `recheck` callable is the whole TOCTOU story. Authority was judged
        when the plan reached this step; between then and now a person can
        have revoked a permission, or the parameters can have changed. So the
        answer is asked for again in the last moment before the provider is
        touched, and it is asked of code rather than remembered.

        Everything that runs runs behind an atomic claim. Two workers and a
        double-tapped button reach here together, and exactly one gets past.
        """
        intent = self._intent_for(owner_id, goal, step)

        existing = await self._already_done(intent)
        if existing is not None and existing.get("status") in ("executed", "verified"):
            # Already through. Recognised rather than repeated — this is the
            # whole reason the key is built from what the effect is instead of
            # when it was tried, and it is what makes a crash after a provider
            # success safe to restart into.
            return await self._as_done(owner_id, goal, step, intent, existing)

        if existing is None:
            await self._record(intent)
        else:
            intent.id = str(existing.get("id") or intent.id)

        if not may_touch_the_world:
            return ExecutionResult(
                step_id=step.id,
                status="partial",
                observation=(
                    "È tutto pronto fino al punto in cui servirebbe il tuo via libera."
                ),
                result_refs=[intent.id],
                error_type="authority_required",
                retryable=False,
                idempotency_key=intent.idempotency_key,
                provenance=ResultProvenance(
                    source_class="internal_observation",
                    capability=step.capability_needed,
                    certainty_note="preparato, non eseguito",
                ),
            )

        # Nothing real behind this capability. Authorised or not, ORA does not
        # pretend — and the one stand-in that exists says it is one.
        if not effects.is_wired_for_real(step.capability_needed):
            if resolution_is_stubbed(step.capability_needed):
                if budget is not None:
                    budget.capability_calls += 1
                from agent import providers

                outcome = await providers.open_navigation(self.db, owner_id, goal, step)
                await self._mark(intent, "executed")
                result = await self._as_result(owner_id, goal, step, outcome)
                result.idempotency_key = intent.idempotency_key
                return result
            return ExecutionResult(
                step_id=step.id,
                status="partial",
                observation=(
                    "È tutto pronto. L'esecuzione reale di questo tipo di azione "
                    "non è ancora collegata."
                ),
                result_refs=[intent.id],
                error_type="execution_not_wired",
                retryable=False,
                idempotency_key=intent.idempotency_key,
                provenance=ResultProvenance(
                    source_class="internal_observation",
                    capability=step.capability_needed,
                    certainty_note="preparato, non eseguito",
                ),
            )

        # The last moment anything can stop this.
        if recheck is not None:
            authority = await recheck(intent)
            if authority is None or not authority.may_execute:
                await self._mark(intent, "prepared")
                return ExecutionResult(
                    step_id=step.id,
                    status="partial",
                    observation=(
                        "Stavo per farlo, e nel frattempo il permesso non c'è più."
                    ),
                    result_refs=[intent.id],
                    error_type="authority_withdrawn",
                    retryable=False,
                    idempotency_key=intent.idempotency_key,
                    provenance=ResultProvenance(
                        source_class="internal_observation",
                        capability=step.capability_needed,
                        certainty_note="fermato al momento di agire",
                    ),
                )
            # On what basis this is allowed to happen, written down where an
            # audit will look for it. The field held the capability's name
            # until here, which answers "what kind of thing is this" and not
            # "why was it permitted" — and the second question is the one
            # somebody asks afterwards.
            intent.authority_required = authority.reason_code
            await self._note_basis(intent)

        if not await self._claim(intent):
            # Somebody else is doing it, or has done it. Either way not twice.
            return ExecutionResult(
                step_id=step.id,
                status="partial",
                observation="Questa cosa la sta già facendo qualcun altro.",
                result_refs=[intent.id],
                error_type="already_running",
                retryable=False,
                idempotency_key=intent.idempotency_key,
                provenance=ResultProvenance(
                    source_class="internal_observation",
                    capability=step.capability_needed,
                ),
            )

        if budget is not None:
            budget.capability_calls += 1

        outcome = await effects.run_effect(self.db, owner_id, intent)
        if outcome is None:
            await self._mark(intent, "prepared")
            return ExecutionResult(
                step_id=step.id, status="partial",
                observation="L'esecuzione reale non è collegata.",
                error_type="execution_not_wired",
                idempotency_key=intent.idempotency_key,
                result_refs=[intent.id],
            )

        # The receipt carries it too. A receipt is what survives when the
        # attempt row is cleaned up, and "the provider accepted this" is worth
        # much less without "and this is who said it could".
        outcome.receipt.authority_basis = intent.authority_required[:64]
        await self._keep(outcome.receipt)


        went_through = outcome.receipt.provider_status in ("accepted", "succeeded", "partial")
        await self._mark(intent, "executed" if went_through else "prepared")

        refs: List[str] = []
        for claim, supports in outcome.claims:
            evidence = AgentEvidence(
                owner_id=owner_id, goal_id=goal.id, step_id=step.id,
                kind="execute", claim=claim, supports=supports,
                provenance=outcome.provenance,
            )
            await self.evidence.record(evidence)
            refs.append(evidence.id)

        # Accepted without a read-back is `partial`, not success. This is the
        # line that stops "the request went out" from becoming "it is done".
        status = (
            "succeeded" if outcome.receipt.provider_status == "succeeded" and outcome.observed
            else "partial" if went_through
            else "failed"
        )
        return ExecutionResult(
            step_id=step.id,
            status=status,
            observation=outcome.observation[:600],
            result_refs=[outcome.receipt.id],
            error_type=outcome.receipt.error_type or (
                "" if outcome.observed else "accepted_not_observed"
            ),
            retryable=outcome.receipt.retryable,
            idempotency_key=intent.idempotency_key,
            provenance=outcome.provenance,
            evidence_refs=refs[:12],
            data_ref=outcome.receipt.external_ref,
        )

    def _intent_for(self, owner_id, goal, step: ActionStep) -> ActionIntent:
        """
        The effect this step declares, as something authority can be about.

        Built from what the plan said, never from what would be convenient:
        the flags come from the step's own declaration, so a step that did not
        say it reaches somebody else cannot quietly grow an attendee here.
        """
        return ActionIntent(
            owner_id=owner_id,
            goal_id=goal.id,
            step_id=step.id,
            capability=step.capability_needed,
            effect_summary=step.intent[:300],
            target_ref=(step.input_refs[0] if step.input_refs else ""),
            parameter_refs=list(step.input_refs)[:8],
            parameters=dict(step.parameters or {}),
            authority_required=step.authority_requirement or step.capability_needed,
            expected_effect=step.expected_result[:300],
            reversibility=step.reversibility,
            external_effect=True,
            status="prepared",
            effect=ActionEffect(
                effect_type=step.effect_type,
                target=step.effect_target[:200] or step.capability_needed,
                effect_summary=step.intent[:300],
                external_party=step.reaches_somebody_else,
                reversibility=step.reversibility,
                expected_outcome=step.expected_result[:300],
            ),
        )

    async def _as_done(self, owner_id, goal, step, intent, existing) -> ExecutionResult:
        """
        An effect that already happened, reported as what it was.

        The receipt is looked up rather than invented: after a crash this is
        the only thing that knows an event exists, and re-running the write to
        find out would be the duplicate the whole design refuses.
        """
        receipt = await self.receipt_for(owner_id, intent.idempotency_key)
        return ExecutionResult(
            step_id=step.id,
            status="succeeded" if receipt and receipt.get("provider_status") == "succeeded"
            else "partial",
            observation="Questa cosa era già stata fatta: non si rifà.",
            idempotency_key=intent.idempotency_key,
            error_type="already_done",
            result_refs=[str((receipt or {}).get("id") or existing.get("id") or "")],
            data_ref=str((receipt or {}).get("external_ref") or ""),
            provenance=ResultProvenance(
                source_class="connected_provider" if receipt else "internal_observation",
                capability=step.capability_needed,
                certainty_note="ripetizione riconosciuta, non rieseguita",
            ),
        )

    # --- an act somebody asked for directly ------------------------------
    #
    # Two doors into the same machinery, for effects that arrive from a
    # conversation rather than from a plan. They exist so that path cannot
    # grow its own copy of the claim: one atomic claim in the codebase means
    # one place where a duplicate calendar entry can be introduced, and one
    # mutation test that covers every caller of it.

    async def begin_declared(self, intent: ActionIntent) -> str:
        """
        Record the intent and take it, or say why it is not ours to take.

        `already_done` is a success, not a failure. It is the answer to a
        re-sent message, a double-tapped send and a client retry, and the
        whole reason the key is derived from what the effect is.
        """
        existing = await self._already_done(intent)
        if existing is not None and existing.get("status") in ("executed", "verified"):
            return "already_done"
        if existing is None:
            await self._record(intent)
        else:
            intent.id = str(existing.get("id") or intent.id)
        return "go" if await self._claim(intent) else "busy"

    async def settle_declared(
        self, intent: ActionIntent, receipt: ExecutionReceipt, *, executed: bool
    ) -> None:
        """Keep the receipt, and move the intent to where it actually got to."""
        await self._keep(receipt)
        await self._mark(intent, "executed" if executed else "prepared")

    async def _claim(self, intent: ActionIntent) -> bool:
        """
        Take this effect, atomically, or do not do it.

            ONE ACTION INTENT, ONE EFFECT.

        Read-then-write has a window in which two workers both see `prepared`
        and both call the provider, and the result is two entries in somebody's
        calendar. One database operation closes it: the filter names the
        states an unstarted effect can be in, and exactly one caller matches.
        """
        taken = await self.db[ATTEMPTS].find_one_and_update(
            {
                "idempotency_key": intent.idempotency_key,
                "status": {"$in": ["planned", "prepared", "authorized"]},
            },
            {"$set": {"status": "executing", "executing_at": _now().isoformat()}},
            projection={"_id": 0, "id": 1},
        )
        return taken is not None

    async def _keep(self, receipt: ExecutionReceipt) -> None:
        try:
            await self.db[RECEIPTS].insert_one(receipt.model_dump())
        except Exception as e:
            logger.info("receipt keep soft-fail: %s", type(e).__name__)

    async def receipt_for(self, owner_id: str, key: str) -> Optional[Dict[str, Any]]:
        return await self.db[RECEIPTS].find_one(
            {"owner_id": owner_id, "idempotency_key": key}, {"_id": 0}
        )

    async def receipts_for(self, owner_id: str, goal_id: str) -> List[Dict[str, Any]]:
        return await self.db[RECEIPTS].find(
            {"owner_id": owner_id, "goal_id": goal_id}, {"_id": 0}
        ).sort("requested_at", 1).to_list(10)

    async def _already_done(self, intent: ActionIntent) -> Optional[Dict[str, Any]]:
        return await self.db[ATTEMPTS].find_one(
            {"idempotency_key": intent.idempotency_key},
            {"_id": 0, "id": 1, "status": 1},
        )

    async def _record(self, intent: ActionIntent) -> None:
        doc = intent.model_dump()
        doc["idempotency_key"] = intent.idempotency_key
        try:
            await self.db[ATTEMPTS].insert_one(doc)
        except Exception as e:
            # A duplicate key here means somebody else got there first, which
            # is exactly what the key is for.
            logger.info("intent record: %s", type(e).__name__)

    async def _note_basis(self, intent: ActionIntent) -> None:
        """Record why this was allowed, next to what it is."""
        try:
            await self.db[ATTEMPTS].update_one(
                {"idempotency_key": intent.idempotency_key},
                {"$set": {"authority_required": intent.authority_required[:60]}},
            )
        except Exception as e:
            logger.info("intent basis soft-fail: %s", type(e).__name__)

    async def _mark(self, intent: ActionIntent, status: str) -> None:
        """
        Move a declared effect along its lifecycle.

        `executed` and `verified` are set from different places on purpose:
        one when something was done, the other when the world was afterwards
        found to have changed. Nothing sets both at once.
        """
        field = "executed_at" if status == "executed" else "verified_at"
        try:
            await self.db[ATTEMPTS].update_one(
                {"idempotency_key": intent.idempotency_key},
                {"$set": {"status": status, field: _now().isoformat()}},
            )
        except Exception as e:
            logger.info("intent mark soft-fail: %s", type(e).__name__)

    async def mark_verified(self, owner_id: str, goal_id: str) -> int:
        """
        The outcome was checked and found true. Say so about what was done.

        Only ever called after verification, and only for effects that were
        actually executed — a prepared intent that nobody authorised has
        nothing to verify.
        """
        result = await self.db[ATTEMPTS].update_many(
            {"owner_id": owner_id, "goal_id": goal_id, "status": "executed"},
            {"$set": {"status": "verified", "verified_at": _now().isoformat()}},
        )
        return result.modified_count

    async def intents_for(self, owner_id: str, goal_id: str) -> List[Dict[str, Any]]:
        docs = await self.db[ATTEMPTS].find(
            {"owner_id": owner_id, "goal_id": goal_id},
            {"_id": 0, "id": 1, "capability": 1, "effect_summary": 1,
             "reversibility": 1, "created_at": 1, "status": 1},
        ).to_list(20)
        return docs

    async def forget_all(self, owner_id: str) -> int:
        await self.db[RECEIPTS].delete_many({"owner_id": owner_id})
        result = await self.db[ATTEMPTS].delete_many({"owner_id": owner_id})
        await self.evidence.forget_all(owner_id)
        return result.deleted_count
