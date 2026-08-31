"""
Deciding is one job; sending is another, later, and only if it is still true.

    OPPORTUNITY != NOTIFICATION.
    NOTIFICATION != ACTION.
    CODE ORCHESTRATES. AI REASONS.

The dangerous thing about a scheduled notification is the gap between the
decision and the moment. Everything can change in it: the document arrives,
the meeting is cancelled, the person deals with it themselves and would be
puzzled to be told about it at eight the next morning. So a plan is an
intention, `deliver_due` re-examines it before anything leaves, and an
opportunity that closes takes every open plan with it.

The split is strict. The model chooses the mode, the timing, the words and
what a lock screen may carry. This file persists that, enforces bounds it can
enforce without an opinion — no push without permission, no push after the
moment has passed, no second plan for a concern that already has one, a
technical ceiling on how many interruptions can arrive in an hour — and calls
a provider that knows nothing about any of it.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from delivery import context as delivery_context
from delivery.models import (
    AmbientActivity,
    DeliveryDecision,
    DeliveryPlan,
    DeliveryResult,
    PushCopy,
)
from delivery.repository import DeliveryRepository

logger = logging.getLogger(__name__)

# The furthest ahead an intention is worth holding. Past this the life it was
# about has moved, and the right thing is to decide again rather than to fire
# a judgement made in a different week.
MAX_PLAN_HORIZON_HOURS = 72

# A technical ceiling, not a view about relevance: however good each one is,
# this many uninvited interruptions in an hour is a malfunction. The model is
# shown the same history and usually stops long before here.
MAX_PUSHES_PER_HOUR = 2

# The shortest gap between two pushes that is not effectively one burst.
MIN_MINUTES_BETWEEN_PUSHES = 10

# How often the ambient line is rewritten. A sentence that changes every few
# minutes reads as fidgeting rather than as presence, and each rewrite costs
# a model call for something nobody asked to be updated.
AMBIENT_REFRESH_HOURS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DeliveryService:
    def __init__(self, db):
        self.db = db
        self.repo = DeliveryRepository(db)

    # --- deciding ---------------------------------------------------------

    async def evaluate(
        self,
        user_id: str,
        opportunity_id: str,
        *,
        app_state: str = "unknown",
        language: str = "it",
    ) -> DeliveryResult:
        """
        How should this reach them, if at all?

        Most of the time the answer is `silence` or `in_app`, and neither
        writes a plan. A plan is only for something that intends to arrive.
        """
        from delivery.reasoning import decide_delivery
        from opportunities.repository import OpportunityRepository

        opportunity = await OpportunityRepository(self.db).get(user_id, opportunity_id)
        if opportunity is None:
            return DeliveryResult(blocked_by="unknown_opportunity")
        if opportunity.status != "active":
            # A concern that is settled has nothing to announce, and any
            # intention left standing for it is now wrong.
            await self.cancel_for_opportunity(
                user_id, opportunity_id, reason="la questione non è più aperta"
            )
            return DeliveryResult(blocked_by="opportunity_not_active")

        if await self._muted(user_id, opportunity_id):
            # "Non notificarmi per questa cosa." Checked before anything is
            # spent: a person saying stop should not depend on a model
            # agreeing, and asking one anyway would be paying to be told
            # something already decided. Not a dismissal — the concern goes on
            # living wherever it was living, so this lands on the screen.
            await self.cancel_for_opportunity(
                user_id, opportunity_id,
                reason="l'utente ha chiesto di non essere avvisato",
            )
            return DeliveryResult(
                mode="in_app",
                blocked_by="muted_by_user",
                reason="l'utente ha chiesto di non essere avvisato per questa cosa",
            )

        moment = await delivery_context.build(
            self.db, user_id, opportunity=opportunity, app_state=app_state
        )
        answer = await decide_delivery(moment, language=language)

        if answer is None:
            # No judgement was available. Nothing is sent, nothing is
            # recorded as silence, and the next pass tries again.
            logger.info("delivery judgement unavailable for %s", user_id[:8])
            return DeliveryResult(unavailable=True, reason="il giudizio non era disponibile")

        decision = self._read(answer)

        if decision.mode != "push":
            # Quiet, in-app or nothing: no intention to arrive anywhere, so no
            # plan — and any plan that was standing is no longer what we think.
            await self.cancel_for_opportunity(
                user_id, opportunity_id, reason="non è più il caso di interrompere"
            )
            return DeliveryResult(
                mode=decision.mode,
                reason=decision.reason_to_interrupt or "",
                what_decided_the_mode=decision.what_decided_the_mode,
            )

        allowed, why_not = await self._may_push(user_id, moment)
        if not allowed:
            # A technical refusal, named as one. The judgement stands; the
            # channel is unavailable, so it lands on the screen instead.
            plan = await self._hold(user_id, opportunity_id, decision, why_not)
            return DeliveryResult(
                mode="in_app", blocked_by=why_not, plan=plan,
                reason="l'interruzione non era possibile adesso",
                what_decided_the_mode=decision.what_decided_the_mode,
            )

        plan = await self._plan(user_id, opportunity, decision)
        result = DeliveryResult(
            mode="push", plan=plan, reason=decision.reason_to_interrupt,
            what_decided_the_mode=decision.what_decided_the_mode,
        )

        if plan.not_before:
            # Somebody has to be there at that hour. Sprint 1 wrote the
            # intention and then waited for a request to come along; this is
            # the alarm that makes a future decision actually happen.
            await self._arrange_wake(plan)

        if plan.status == "pending" and self._due(plan):
            # Decided for now, so now. Everything else waits for its moment
            # and gets re-examined when it arrives.
            await self._send(user_id, plan)
        return result

    def _read(self, raw: Dict[str, Any]) -> DeliveryDecision:
        """The model's answer, trimmed to the contract and bounded in time."""
        copy = raw.get("copy") if isinstance(raw.get("copy"), dict) else {}
        decision = DeliveryDecision(
            mode=raw["mode"],
            timing=(
                str(raw.get("timing") or "now").strip().lower()
                if str(raw.get("timing") or "now").strip().lower()
                in ("now", "at", "window", "hold")
                else "now"
            ),
            not_before=_bounded(raw.get("not_before")),
            not_after=_bounded(raw.get("not_after")),
            reason_to_interrupt=str(raw.get("reason_to_interrupt") or "")[:400],
            reason_to_open=str(raw.get("reason_to_open") or "")[:400],
            what_decided_the_mode=str(raw.get("what_decided_the_mode") or "")[:300],
            copy_intent=str(raw.get("copy_intent") or "")[:300],
            confidence=(
                raw.get("confidence")
                if raw.get("confidence") in ("weak", "reasonable", "strong")
                else "reasonable"
            ),
            sensitivity=(
                raw.get("sensitivity")
                if raw.get("sensitivity") in ("ordinary", "personal", "private")
                else "ordinary"
            ),
            requires_recheck=bool(raw.get("requires_recheck", True)),
        )
        if decision.mode == "push":
            decision.words = PushCopy(
                title=str(copy.get("title") or "")[:80],
                body=str(copy.get("body") or "")[:200],
                public_title=str(copy.get("public_title") or "")[:80],
                public_body=str(copy.get("public_body") or "")[:200],
            )
        return decision

    # --- intentions -------------------------------------------------------

    async def _plan(
        self, user_id: str, opportunity, decision: DeliveryDecision
    ) -> DeliveryPlan:
        """
        Write down the intention — updating the one that exists, never adding.

        Three re-evaluations of the same concern are three judgements about
        one thing, and a person should hear about it once. So an open plan is
        found and rewritten with what we now think.
        """
        existing = await self.repo.open_plan_for(user_id, opportunity.id)
        plan = existing or DeliveryPlan(
            owner_id=user_id, opportunity_id=opportunity.id, mode="push"
        )

        plan.mode = "push"
        plan.status = "pending"
        plan.not_before = decision.not_before
        plan.not_after = decision.not_after or _default_not_after(opportunity)
        plan.words = decision.words or PushCopy()
        plan.reason_to_interrupt = decision.reason_to_interrupt
        plan.reason_to_open = decision.reason_to_open
        # Rewritten on every re-evaluation: the trade-off that held last night
        # is not necessarily the one that holds this morning.
        plan.what_decided_the_mode = decision.what_decided_the_mode
        plan.sensitivity = decision.sensitivity
        plan.deep_link = _deep_link(opportunity.id)
        plan.decision_provenance = "model"
        plan.rationale = decision.reason_to_interrupt[:300]
        return await self.repo.save_plan(plan)

    async def _hold(
        self, user_id: str, opportunity_id: str, decision: DeliveryDecision, why: str
    ) -> DeliveryPlan:
        existing = await self.repo.open_plan_for(user_id, opportunity_id)
        plan = existing or DeliveryPlan(
            owner_id=user_id, opportunity_id=opportunity_id, mode="push"
        )
        plan.status = "held"
        plan.decision_provenance = "code_safety"
        plan.rationale = why
        plan.reason_to_open = decision.reason_to_open
        plan.what_decided_the_mode = decision.what_decided_the_mode
        plan.words = decision.words or plan.words
        plan.deep_link = _deep_link(opportunity_id)
        return await self.repo.save_plan(plan)

    # --- sending, much later ----------------------------------------------

    async def deliver_due(self, user_id: str, *, language: str = "it") -> Dict[str, Any]:
        """
        Send what is due, having first checked it is still true.

            RECHECK BEFORE DELIVERY.

        This is the whole reason plans exist rather than immediate sends. The
        classic failure is a notification that was correct when it was decided
        and embarrassing by the time it fired — the missing document arrived
        last night, and ORA says good morning by asking about it.
        """
        from opportunities.repository import OpportunityRepository

        opportunities = OpportunityRepository(self.db)
        sent, cancelled, held = 0, 0, 0

        for plan in await self.repo.open_plans(user_id):
            if self._expired(plan):
                plan.status = "expired"
                plan.decision_provenance = "code_expiry"
                plan.rationale = "il momento utile è passato"
                # Never `dismissed`: we know the moment passed, not that
                # anybody refused it. Calling one the other would put a
                # decision in somebody's mouth.
                if plan.outcome is None and plan.delivered_at:
                    plan.outcome = "expired"
                await self.repo.save_plan(plan)
                cancelled += 1
                continue

            if not self._due(plan):
                held += 1
                continue

            opportunity = await opportunities.get(user_id, plan.opportunity_id)
            if opportunity is None or opportunity.status != "active":
                await self._cancel(
                    plan, "la questione si è chiusa prima dell'invio", "code_cancel"
                )
                cancelled += 1
                continue

            plan.last_rechecked_at = _now().isoformat()
            moment = await delivery_context.build(self.db, user_id)
            moment["they_muted_this_concern"] = await self._muted(
                user_id, plan.opportunity_id
            )
            allowed, why_not = await self._may_push(user_id, moment)
            if not allowed:
                plan.status = "held"
                plan.decision_provenance = "code_safety"
                plan.rationale = why_not
                await self.repo.save_plan(plan)
                held += 1
                continue

            await self._send(user_id, plan)
            sent += 1

        return {"sent": sent, "cancelled": cancelled, "held": held}

    async def _send(self, user_id: str, plan: DeliveryPlan) -> None:
        from delivery.provider import get_provider

        public = plan.words.public()
        outcome = await get_provider().send(
            owner_id=user_id,
            plan_id=plan.id,
            title=plan.words.title,
            body=plan.words.body,
            public_title=public["title"],
            public_body=public["body"],
            deep_link=plan.deep_link,
        )
        if not outcome.get("ok"):
            plan.status = "held"
            plan.rationale = "il canale non era disponibile"
            plan.decision_provenance = "code_safety"
            await self.repo.save_plan(plan)
            return

        plan.status = "delivered"
        plan.delivered_at = _now().isoformat()
        plan.outcome = "delivered"
        plan.last_rechecked_at = plan.last_rechecked_at or plan.delivered_at
        await self.repo.save_plan(plan)

    # --- what happens to it afterwards ------------------------------------

    async def record_outcome(
        self, user_id: str, plan_id: str, outcome: str
    ) -> Dict[str, Any]:
        """Opened, ignored, gone. Kept as a fact, never turned into a score."""
        if outcome not in ("opened", "dismissed", "expired"):
            return {"ok": False, "reason": "unknown_outcome"}
        plan = await self.repo.get_plan(user_id, plan_id)
        if plan is None:
            return {"ok": False, "reason": "unknown_plan"}

        # Idempotent, and `opened` is not overwritten by anything later: a
        # person who opened a notification opened it, whatever happened after.
        if plan.outcome == "opened" and outcome != "opened":
            return {"ok": True, "outcome": plan.outcome, "opportunity_id": plan.opportunity_id}

        if outcome == "opened" and plan.opened_at is None:
            plan.opened_at = _now().isoformat()
        plan.outcome = outcome
        await self.repo.save_plan(plan)
        return {"ok": True, "outcome": outcome, "opportunity_id": plan.opportunity_id}

    async def cancel_for_opportunity(
        self, user_id: str, opportunity_id: str, *, reason: str
    ) -> int:
        """
        A concern that closed takes its intentions with it.

        Guaranteed by code rather than left to a judgement: a notification
        about something already dealt with is never right, so there is nothing
        to decide.
        """
        cancelled = 0
        for plan in await self.repo.plans_for(user_id, opportunity_id):
            if plan.is_open:
                await self._cancel(plan, reason, "code_cancel")
                cancelled += 1
        return cancelled

    async def _cancel(self, plan: DeliveryPlan, reason: str, source: str) -> None:
        from delivery.provider import get_provider

        plan.status = "cancelled"
        plan.cancelled_at = _now().isoformat()
        plan.decision_provenance = source
        plan.rationale = reason[:300]
        await self.repo.save_plan(plan)
        # An alarm set for a notification that is no longer going to happen is
        # a process that will wake up, find nothing, and have cost something.
        await self._cancel_wakes(plan.owner_id, plan.opportunity_id)
        try:
            await get_provider().cancel(owner_id=plan.owner_id, plan_id=plan.id)
        except Exception as e:
            logger.info("provider cancel soft-fail: %s", type(e).__name__)

    # --- arranging to be there --------------------------------------------

    async def _arrange_wake(self, plan) -> None:
        """
        Ask the runtime to be awake when this plan's moment arrives.

        Best-effort in both directions: a failure here must not fail the
        decision, and the wake it creates promises nothing — what happens at
        that hour is decided then, by asking again.
        """
        try:
            from ambient.service import AmbientService

            await AmbientService(self.db).schedule_for_plan(plan)
        except Exception as e:
            logger.info("wake schedule soft-fail: %s", type(e).__name__)

    async def _cancel_wakes(self, owner_id: str, opportunity_id: str) -> None:
        try:
            from ambient.service import AmbientService

            await AmbientService(self.db).cancel_for_opportunity(owner_id, opportunity_id)
        except Exception as e:
            logger.info("wake cancel soft-fail: %s", type(e).__name__)

    # --- the bounds code is allowed to hold -------------------------------

    async def _may_push(
        self, user_id: str, moment: Dict[str, Any]
    ) -> tuple[bool, str]:
        """
        Whether a push is technically permissible. Never whether it is a good idea.

        Each of these is a fact about capability or a ceiling on volume. None
        of them looks at what the opportunity is about, and none can be
        reached by anything that does.
        """
        if not (moment.get("can_be_notified") or {}).get("push"):
            return False, "no_notification_permission"

        if moment.get("they_muted_this_concern"):
            # "Non notificarmi per questa cosa." Enforced here rather than
            # weighed, because somebody saying stop should not depend on a
            # model agreeing — and it is not a dismissal: the concern goes on
            # living wherever it was living.
            return False, "muted_by_user"

        recent = moment.get("recent_interruptions") or []
        within_hour = [
            r for r in recent
            if r.get("minutes_ago") is not None and r["minutes_ago"] <= 60
        ]
        if len(within_hour) >= MAX_PUSHES_PER_HOUR:
            return False, "rate_limited"
        if any(
            r.get("minutes_ago") is not None
            and r["minutes_ago"] < MIN_MINUTES_BETWEEN_PUSHES
            for r in recent
        ):
            return False, "too_soon_after_last"
        return True, ""

    async def _muted(self, user_id: str, opportunity_id: str) -> bool:
        """Whether they have asked not to be reached about this one thing."""
        try:
            from ambient.preferences import PreferenceService

            return await PreferenceService(self.db).is_suppressed(user_id, opportunity_id)
        except Exception as e:
            logger.info("suppression read soft-fail: %s", type(e).__name__)
            return False

    def _due(self, plan: DeliveryPlan) -> bool:
        return not plan.not_before or plan.not_before <= _now().isoformat()

    def _expired(self, plan: DeliveryPlan) -> bool:
        now = _now()
        if plan.not_after and plan.not_after < now.isoformat():
            return True
        try:
            created = datetime.fromisoformat(plan.created_at)
        except ValueError:
            return False
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return (now - created) > timedelta(hours=MAX_PLAN_HORIZON_HOURS)

    # --- proof of work ----------------------------------------------------

    async def note_activity(
        self,
        user_id: str,
        *,
        kind: str,
        summary: str = "",
        source_refs: Optional[List[str]] = None,
        provenance: Optional[Dict[str, Any]] = None,
        visible: bool = False,
    ) -> AmbientActivity:
        """
        Write down something ORA actually did.

        Called by the work, never by the surface. A screen that could create
        one of these to have something to say would be manufacturing its own
        evidence, which is exactly the failure this record exists to make
        impossible.
        """
        activity = AmbientActivity(
            owner_id=user_id,
            kind=kind,
            summary=summary[:200],
            source_refs=[str(r)[:120] for r in (source_refs or [])][:8],
            cognitive_provenance=provenance or {},
            visibility="ambient" if visible else "internal",
        )
        return await self.repo.record_activity(activity)

    async def summarise_recent(self, user_id: str, *, language: str = "it") -> Optional[Any]:
        """
        Turn work that really happened into one line a person could read.

        Called by the work, after the work. The model is shown the record and
        nothing else — it cannot reach a life, so it cannot claim anything the
        record does not contain, and a review that could not see half of
        somebody's sources produces a smaller sentence rather than a
        reassuring one.

        Rate-limited by the clock rather than by judgement: a line that
        rewrites itself every few minutes is not presence, it is fidgeting.
        """
        from delivery.reasoning import describe_ambient

        latest = await self.repo.latest_ambient(user_id)
        if latest is not None and not _older_than(
            latest.occurred_at, AMBIENT_REFRESH_HOURS
        ):
            return latest

        recent = await self.repo.recent_activity(user_id, visibility="internal", limit=6)
        if not recent:
            # Nothing was done, so there is nothing to say. This is the branch
            # that makes the whole feature honest.
            return None

        blind = sorted(
            {
                str(source)
                for activity in recent
                for source in (activity.cognitive_provenance.get("sources_unavailable") or [])
            }
        )
        answer = await describe_ambient(
            {
                "what_ora_did": [
                    {
                        "kind": a.kind,
                        "when": a.occurred_at,
                        "details": a.cognitive_provenance,
                    }
                    for a in recent
                ],
                "sources_it_could_not_check": blind,
                "language": language,
            },
            language=language,
        )
        if answer is None or not answer.get("worth_saying"):
            # Either the model was unreachable or it judged that nothing here
            # is worth a person reading. Neither produces a line.
            return None

        return await self.note_activity(
            user_id,
            kind=recent[0].kind,
            summary=answer["line"],
            source_refs=[r for a in recent for r in a.source_refs][:8],
            provenance={
                "written_from": [a.id for a in recent][:6],
                "sources_unavailable": blind,
            },
            visible=True,
        )

    async def permission_moment(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Whether there is now a reason to ask about notifications.

            NON CHIEDERE AL PRIMO AVVIO.

        Asked at launch, the question is about a feature and the honest answer
        is no. Asked here it is about something concrete: ORA judged that a
        particular thing was worth reaching them for, and could not. That is
        the only moment the question is worth a person's time, and it arrives
        by itself — nothing schedules it and nothing nags.

        Returns nothing at all when no such judgement is waiting, which is
        almost always.
        """
        held = [
            p for p in await self.repo.open_plans(user_id)
            if p.status == "held" and p.rationale == "no_notification_permission"
        ]
        if not held:
            return None
        return {
            "reason": "ORA può avvisarti quando cambia qualcosa che vale davvero la pena vedere.",
            # What it would have said, so the question is about something real
            # rather than about a permission dialog.
            "example": held[0].reason_to_open or None,
            "waiting": len(held),
        }

    async def ambient_line(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        The one line Home may show, or nothing.

        Reads what was already recorded — it never runs a review and never
        asks a model. If no real work is on file, there is nothing to say, and
        saying something anyway is the lie this whole layer is built to avoid.
        """
        latest = await self.repo.latest_ambient(user_id)
        if latest is None or not latest.summary:
            return None
        return latest.for_home()


def _older_than(when: str, hours: int) -> bool:
    try:
        moment = datetime.fromisoformat(str(when))
    except (TypeError, ValueError):
        return True
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (_now() - moment) > timedelta(hours=hours)


# The only places a notification may open. A model may reason about where a
# tap should land; it may never hand over a URL, because a URL from a model is
# a string somebody else's text could have influenced.
ALLOWED_TARGETS = {
    "opportunity": "/ora?opportunityId={id}&entry=notification",
    "conversation": "/ora?sessionId={id}&entry=notification",
    "home": "/",
}

# Opaque ids only. Anything else is not an id we produced.
_OPAQUE_ID = re.compile(r"^[A-Za-z0-9_-]{4,80}$")


def _deep_link(opportunity_id: str, *, target: str = "opportunity") -> str:
    """
    Where a tap lands, built here from a validated target and a validated id.

    The same handoff "Vediamo" uses, with the origin preserved so the
    conversation knows it began with an interruption. A notification that
    opens Home when we know exactly what it was about has thrown away the only
    thing it knew — and one that opens whatever a model wrote has thrown away
    rather more than that.
    """
    template = ALLOWED_TARGETS.get(target) or ALLOWED_TARGETS["home"]
    if "{id}" not in template:
        return template
    if not _OPAQUE_ID.match(str(opportunity_id or "")):
        return ALLOWED_TARGETS["home"]
    return template.format(id=opportunity_id)


def _default_not_after(opportunity) -> Optional[str]:
    """When the model did not say, the opportunity's own horizon does."""
    return getattr(opportunity, "valid_until", None)


def _bounded(raw: Any) -> Optional[str]:
    """A moment the model named, kept only if it is a moment and it is near."""
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    horizon = _now() + timedelta(hours=MAX_PLAN_HORIZON_HOURS)
    if moment > horizon:
        moment = horizon
    return moment.isoformat()
