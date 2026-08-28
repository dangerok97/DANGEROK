"""
The guidance cycle.

    reconstruct  →  reconcile  →  next step  →  sufficiency  →  resolve  →  ask?

The reasoning does the semantic half: what the milestones are, which of them
this person is already past, what the next step is, and what it needs. This
service does the constitutional half, and it is deliberately deterministic —
the rules that keep ORA from interrogating people are not judgement calls:

  * only `required` may ever become a question;
  * anything ORA already holds is resolved before anything is asked;
  * an answer already given, including a refusal, is never asked again;
  * what remains is asked once, together;
  * a milestone the person has corrected is believed over any inference.

If the model returns nothing usable, the cycle degrades to "carry on" rather
than to a plan built from noise. Guidance may decline to help; it may not
invent a path.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence

from guidance.models import (
    GoalState,
    GuidanceOutcome,
    Milestone,
    NextStep,
    Sufficiency,
    Variable,
)
from guidance.questioning import build_ask, unresolved_after
from guidance.resolution import (
    mark_declined,
    resolve_from_answers,
    resolve_from_knowledge,
    resolve_from_turn,
)

logger = logging.getLogger("ora.guidance")


class GuidanceService:
    def __init__(self, db: Any = None):
        self.db = db

    # ------------------------------------------------------------------
    # Where am I
    # ------------------------------------------------------------------

    @staticmethod
    def reconstruct(
        raw_state: Optional[Dict[str, Any]],
        *,
        previous: Optional[GoalState] = None,
        corrections: Optional[Dict[str, str]] = None,
    ) -> GoalState:
        """
        Turn the reasoning's reading of the situation into state.

        Two things are enforced here rather than trusted to the model.

        A correction wins. When the person has said a milestone is not done,
        no later inference may quietly mark it done again — that is the moment
        ORA stops being trustworthy about what it thinks it knows.

        And nothing invented survives validation: a malformed reconstruction
        leaves the previous state standing instead of replacing it with a
        guess. Losing an update is recoverable; rebuilding someone's plan from
        noise is not.
        """
        base = previous or GoalState()
        if not isinstance(raw_state, dict):
            return base

        try:
            fresh = GoalState.model_validate(raw_state)
        except Exception:
            logger.info("guidance_revision_failed reason=invalid_state")
            return base

        if not fresh.milestones and base.milestones:
            # A reconstruction with nothing in it is not a reconstruction.
            logger.info("guidance_revision_failed reason=empty_state")
            return base

        # Identity is preserved across revisions: a milestone that survives
        # keeps its ref and its Life OS item, so Workspace, Attività and any
        # open question still point at the same thing.
        by_ref = {m.ref: m for m in base.milestones}
        merged: List[Milestone] = []
        for m in fresh.milestones:
            old = by_ref.get(m.ref)
            if old and not m.plan_item_id:
                m.plan_item_id = old.plan_item_id
            if old and old.basis == "fact" and m.basis != "fact":
                # A stated fact is not downgraded by a later inference.
                m.state, m.basis = old.state, old.basis
                m.evidence_refs = old.evidence_refs
            merged.append(m)

        for ref, state in (corrections or {}).items():
            for m in merged:
                if m.ref == ref:
                    m.state = state  # type: ignore[assignment]
                    m.basis = "fact"
                    m.evidence_refs = ["user_correction"]

        fresh.milestones = merged
        fresh.revision = base.revision + 1
        return fresh

    # ------------------------------------------------------------------
    # Can I proceed
    # ------------------------------------------------------------------

    async def assess(
        self,
        variables: Sequence[Variable],
        *,
        user_id: str,
        user_message: str = "",
        active_goal: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        answered_refs: Iterable[str] = (),
        declined_refs: Iterable[str] = (),
    ) -> Sufficiency:
        """
        Everything ORA can answer for itself, answered before anyone is asked.

        The order is the constitution in §20: what was just said, what has
        already been answered, what the person declined to say, then what ORA
        holds. Only what survives all four can block.
        """
        vars_ = [v.model_copy(deep=True) for v in variables]

        resolve_from_turn(vars_, user_message)
        resolve_from_answers(vars_, answered_refs)
        mark_declined(vars_, declined_refs)

        required_left = [v for v in vars_ if v.blocks]
        if required_left:
            await resolve_from_knowledge(
                required_left,
                db=self.db,
                user_id=user_id,
                user_message=user_message,
                active_goal=active_goal,
                session_id=session_id,
            )
            # `assess` works on copies; fold the resolutions back in.
            by_ref = {v.ref: v for v in required_left}
            for v in vars_:
                found = by_ref.get(v.ref)
                if found is not None and found.resolved:
                    v.origin, v.resolved_note = found.origin, found.resolved_note

        blocking = [v for v in vars_ if v.blocks]
        return Sufficiency(can_proceed=not blocking, variables=vars_)

    # ------------------------------------------------------------------
    # The whole cycle
    # ------------------------------------------------------------------

    async def evaluate(
        self,
        *,
        user_id: str,
        variables: Sequence[Variable],
        state: Optional[GoalState] = None,
        user_message: str = "",
        active_goal: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        answered_refs: Iterable[str] = (),
        declined_refs: Iterable[str] = (),
        fallback_question: str = "",
    ) -> GuidanceOutcome:
        """
        One pass. Returns what to do next, and what it cost to decide.

        `avoided` is the number worth reading in review: required variables
        ORA answered from what it already had rather than asking. It is the
        difference between a guide and an intake form.
        """
        goal_state = state or GoalState()
        step = goal_state.active()
        step_title = step.title if step else ""

        sufficiency = await self.assess(
            variables,
            user_id=user_id,
            user_message=user_message,
            active_goal=active_goal,
            session_id=session_id,
            answered_refs=answered_refs,
            declined_refs=declined_refs,
        )

        required = [v for v in sufficiency.variables if v.necessity == "required"]
        avoided = len([v for v in required if v.resolved])
        blocking = sufficiency.blocking()

        if not blocking:
            reason = (
                "nothing_required_missing" if required else "no_required_variables"
            )
            logger.info(
                "guidance_question_avoided user=%s avoided=%d deferred=%d",
                user_id, avoided, len(sufficiency.deferred()),
            )
            return GuidanceOutcome(
                state=goal_state,
                sufficiency=sufficiency,
                next_step=NextStep(
                    kind="proceed",
                    title=step_title,
                    milestone_ref=step.ref if step else None,
                ),
                avoided=avoided,
                reason=reason,
            )

        next_step = build_ask(
            blocking,
            step_title=step_title,
            milestone_ref=step.ref if step else None,
            fallback_question=fallback_question,
            asked_refs=[v.ref for v in variables],
        )
        logger.info(
            "guidance_blocking_question user=%s asked=%d avoided=%d",
            user_id, len(next_step.requested), avoided,
        )
        return GuidanceOutcome(
            state=goal_state,
            sufficiency=sufficiency,
            next_step=next_step,
            avoided=avoided,
            asked=len(next_step.requested),
            reason="required_missing",
        )

    # ------------------------------------------------------------------
    # After an answer
    # ------------------------------------------------------------------

    @staticmethod
    def remaining_after_answer(
        requested: Sequence[Variable],
        *,
        answered_refs: Sequence[str],
        declined_refs: Sequence[str] = (),
    ) -> List[Variable]:
        """
        What a partial answer left open.

        Someone asked for four things and giving two has answered the question
        they were asked; the next one may only contain what is still missing.
        A declined variable counts as settled — asking it again is the loop the
        design exists to prevent.
        """
        settled = {str(r).strip() for r in (*answered_refs, *declined_refs) if str(r).strip()}
        return [v for v in requested if v.ref not in settled and v.blocks]


_SERVICE: Optional[GuidanceService] = None


def get_guidance_service(db: Any = None) -> GuidanceService:
    global _SERVICE
    if _SERVICE is None or _SERVICE.db is not db:
        _SERVICE = GuidanceService(db)
    return _SERVICE


__all__ = [
    "GuidanceService",
    "get_guidance_service",
    "unresolved_after",
]
