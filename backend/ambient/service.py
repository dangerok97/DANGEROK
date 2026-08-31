"""
What a wake turns out to mean.

    PENDING DELIVERY IS A HYPOTHESIS, NOT A PROMISE.

Yesterday evening the model said "tell them at 07:15". At 07:15 that is not
an instruction to carry out — it is a proposal to re-examine. The document
may have arrived overnight, the meeting may be cancelled, another
notification may have gone out twenty minutes ago, or the person may be
sitting in the app right now reading the very thing it was about.

So a delivery wake never sends. It reloads the plan, rebuilds the moment,
asks again, and sends only if the answer is still yes. The model is free to
change its mind completely: cancel it, hold it for later, rewrite the words,
or decide that what deserved a buzz last night deserves a quiet line today.

Code holds the parts that are not judgement — the plan's lifecycle, the
technical retries, the deep link, and the guarantee that a concern which
closed takes its arranged moments with it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ambient.models import AmbientWake, WakeOutcome
from ambient.repository import AmbientRepository

logger = logging.getLogger(__name__)

# The soonest a `hold` may bring something back. Without a floor, a model that
# holds and asks to be re-asked shortly produces a loop that looks like work
# and is only expense.
MIN_HOLD_MINUTES = 20

# And the furthest out an arranged moment is worth keeping.
MAX_HOLD_HOURS = 72

# A technical retry when something was unreachable. Not a judgement about when
# the thing matters.
RETRY_SECONDS = 300


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AmbientService:
    def __init__(self, db):
        self.db = db
        self.repo = AmbientRepository(db)

    # --- arranging ---------------------------------------------------------

    async def schedule(
        self,
        owner_id: str,
        *,
        reason: str,
        when: datetime,
        opportunity_id: str = "",
        plan_id: str = "",
        source_ref: str = "",
        provenance: str = "code_schedule",
    ) -> Optional[AmbientWake]:
        """
        Arrange a moment to look again, unless one is already arranged.

        Bounded here rather than trusted: a moment in the past would fire
        instantly and a moment next year would sit in the collection until
        somebody wondered what it was.
        """
        floor = _now() + timedelta(seconds=30)
        ceiling = _now() + timedelta(hours=MAX_HOLD_HOURS)
        moment = max(floor, min(ceiling, when))

        return await self.repo.schedule(
            AmbientWake(
                owner_id=owner_id,
                reason=reason,  # type: ignore[arg-type]
                scheduled_for=moment.isoformat(),
                opportunity_id=opportunity_id,
                delivery_plan_id=plan_id,
                source_ref=source_ref,
                provenance=provenance,  # type: ignore[arg-type]
            )
        )

    async def schedule_for_plan(self, plan) -> Optional[AmbientWake]:
        """
        A plan that intends to arrive later needs somebody to be there.

        This is the join Sprint 1 was missing: a decision with a `not_before`
        used to sit in the collection hoping a request would come along.
        """
        if not plan.not_before:
            return None
        try:
            when = datetime.fromisoformat(plan.not_before)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)

        if plan.last_rechecked_at:
            # This plan has already been round once. A model that keeps saying
            # "a bit later" would otherwise produce hold, wake, hold, wake —
            # a loop that looks like attentiveness and is only expense. The
            # judgement stands; how soon it may be re-asked does not.
            floor = _now() + timedelta(minutes=MIN_HOLD_MINUTES)
            when = max(when, floor)

        return await self.schedule(
            plan.owner_id,
            reason="delivery_recheck",
            when=when,
            opportunity_id=plan.opportunity_id,
            plan_id=plan.id,
            provenance="model",
        )

    async def cancel_for_opportunity(self, owner_id: str, opportunity_id: str) -> int:
        """A concern that closed takes its arranged moments with it."""
        return await self.repo.cancel_for(owner_id, opportunity_id=opportunity_id)

    # --- what a wake does --------------------------------------------------

    async def recheck_delivery(self, wake: AmbientWake) -> WakeOutcome:
        """
        The moment arrived. Ask again before anything leaves.

        Every early return here is a case where sending would have been wrong,
        and each one was decided by something other than the original
        judgement: the plan is gone, the concern is closed, the channel is
        unreachable. Only the last step actually asks.
        """
        from delivery.service import DeliveryService
        from opportunities.repository import OpportunityRepository

        out = WakeOutcome(wake_id=wake.id, reason=wake.reason)
        delivery = DeliveryService(self.db)

        plan = await delivery.repo.get_plan(wake.owner_id, wake.delivery_plan_id)
        if plan is None or not plan.is_open:
            out.handled = True
            out.result = "plan_gone"
            return out

        opportunity = await OpportunityRepository(self.db).get(
            wake.owner_id, plan.opportunity_id
        )
        if opportunity is None or opportunity.status != "active":
            # Resolved, dismissed or expired while this was waiting. The
            # notification would be about something already dealt with.
            await delivery.cancel_for_opportunity(
                wake.owner_id, plan.opportunity_id,
                reason="la questione si è chiusa prima dell'invio",
            )
            out.handled = True
            out.result = "cancelled_resolved"
            return out

        if plan.not_after and plan.not_after < _now().isoformat():
            plan.status = "expired"
            plan.decision_provenance = "code_expiry"
            plan.rationale = "il momento utile è passato"
            await delivery.repo.save_plan(plan)
            out.handled = True
            out.result = "expired"
            return out

        # The recheck itself is a fact worth recording: a plan that went out
        # without one and a plan that was re-examined and sent anyway look
        # identical afterwards unless this is stamped.
        plan.last_rechecked_at = _now().isoformat()
        await delivery.repo.save_plan(plan)

        # Ask again, with the moment as it is now — not as it was last night.
        verdict = await delivery.evaluate(
            wake.owner_id,
            plan.opportunity_id,
            app_state=await self.app_state(wake.owner_id),
        )

        if verdict.unavailable:
            # No judgement available. Nothing sent, nothing decided, and the
            # plan keeps standing so the retry has something to re-examine.
            out.retry_after_seconds = RETRY_SECONDS
            out.error = "model_unavailable"
            return out

        out.handled = True
        out.result = verdict.mode if not verdict.blocked_by else f"held:{verdict.blocked_by}"

        if verdict.blocked_by in ("rate_limited", "too_soon_after_last"):
            # Fatigue at send time: right when it was decided, noise now
            # because something else arrived in between. Try later.
            await self.schedule(
                wake.owner_id,
                reason="delivery_recheck",
                when=_now() + timedelta(minutes=MIN_HOLD_MINUTES),
                opportunity_id=plan.opportunity_id,
                plan_id=plan.id,
                provenance="code_schedule",
            )
        return out

    async def retry_delivery(self, wake: AmbientWake) -> WakeOutcome:
        """A technical retry is still a recheck: the world moved meanwhile."""
        return await self.recheck_delivery(wake)

    async def review_life(self, wake: AmbientWake) -> WakeOutcome:
        """
        Look at this life again, and leave a trace of having done so.

        The review's own guards decide whether anything is asked of a model:
        nothing pending and an unchanged fingerprint means one indexed query
        and no inference at all, which is what makes an autonomous runtime
        affordable.
        """
        from opportunities.discovery import OpportunityDiscovery
        from opportunities.surfacing import SurfacingService

        out = WakeOutcome(wake_id=wake.id, reason=wake.reason)
        discovery = OpportunityDiscovery(self.db)

        outcome = await discovery.review(wake.owner_id, reason="opportunity_recheck")
        if not outcome.ran:
            out.handled = True
            out.result = "nothing_to_review"
            return out

        if outcome.unavailable:
            out.retry_after_seconds = RETRY_SECONDS
            out.error = "model_unavailable"
            return out

        # Real work happened. That, and only that, entitles anybody to say so.
        await self._note(wake.owner_id, outcome)

        scan = outcome.scan
        if scan is not None and (scan.created or scan.updated):
            await SurfacingService(self.db).decide(wake.owner_id)
            from delivery.service import DeliveryService

            delivery = DeliveryService(self.db)
            for opportunity in list(scan.created)[:2]:
                verdict = await delivery.evaluate(wake.owner_id, opportunity.id)
                if verdict.plan is not None:
                    await self.schedule_for_plan(verdict.plan)

        out.handled = True
        out.result = "reviewed"
        return out

    async def _note(self, owner_id: str, outcome: Any) -> None:
        """
        Proof of work, written by the work.

            NO FAKE HEARTBEAT.

        A loop being alive is not something ORA did. This is only ever called
        after a review actually ran, and it carries what that review could and
        could not see so the sentence written from it can be honest.
        """
        from delivery.service import DeliveryService

        scan = outcome.scan
        try:
            service = DeliveryService(self.db)
            await service.note_activity(
                owner_id,
                kind="opportunity_created" if (scan and scan.created) else "review_completed",
                source_refs=[o.id for o in (scan.created if scan else [])][:4],
                provenance={
                    "woken_by": "runtime",
                    "changes_reviewed": getattr(outcome, "changes_reviewed", 0),
                    "raised": len(scan.created) if scan else 0,
                    "sources_unavailable": list(
                        getattr(scan, "unavailable_sources", None) or []
                    ),
                },
            )
            await service.summarise_recent(owner_id)
        except Exception as exc:
            logger.info("ambient note soft-fail: %s", type(exc).__name__)

    # --- whether anybody is looking ----------------------------------------

    async def app_state(self, owner_id: str) -> str:
        """
        Foreground, background, or honestly unknown.

            Life Presence is where somebody is.
            App Presence is whether they are looking at this.

        Freshness is part of the answer: a flag written forty minutes ago is
        not evidence that anybody is still here, and treating it as such would
        silence notifications for somebody who left.
        """
        presence = await self.repo.app_presence(owner_id)
        return str(presence.resolved()["state"])

    async def record_app_state(self, owner_id: str, state: str) -> Dict[str, Any]:
        from ambient.models import AppPresence

        if state not in ("foreground", "background"):
            return {"ok": False, "reason": "unknown_state"}
        current = await self.repo.app_presence(owner_id)
        stamp = _now().isoformat()
        current.state = state  # type: ignore[assignment]
        current.updated_at = stamp
        if state == "foreground":
            current.last_foreground_at = stamp
        else:
            current.last_background_at = stamp
        await self.repo.record_presence(current)
        return {"ok": True, "state": state}
